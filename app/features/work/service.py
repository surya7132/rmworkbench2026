"""Work queue: reading it, filtering it and changing it.

Rules the screen relies on
  * An RM sees the items they own. A team lead also sees the team's.
  * State changes follow TRANSITIONS only, and each one writes a thread line and an audit entry.
  * Two people changing the same item: the second one gets a conflict (version check), not a silent overwrite.
"""
import json

from ... import auth, clock

ACTIVE = ("Open", "Accepted", "In progress", "Needs information")
TRANSITIONS = {
    "Open": ["Accepted", "In progress", "Needs information", "Done", "Cancelled"],
    "Accepted": ["In progress", "Needs information", "Done", "Cancelled"],
    "In progress": ["Needs information", "Done", "Cancelled"],
    "Needs information": ["In progress", "Cancelled"],
    "Done": ["In progress"],
    "Cancelled": [],
}
BUTTON = {"Accepted": "Accept", "In progress": "Start", "Needs information": "Need info", "Done": "Mark done", "Cancelled": "Cancel"}
TYPE_LABEL = {"client_request": "Client request", "commitment": "Commitment", "task": "Task", "specialist_request": "Specialist request",
              "clarification": "Clarification", "legal": "Legal", "miu_response": "MIU response", "market_event_review": "Market event",
              "follow_up": "Follow-up"}
BUCKETS = [("overdue", "Overdue"), ("today", "Due today"), ("week", "Next 7 days"), ("later", "Later"), ("done", "Closed")]
KINDS = [("all", "All"), ("client", "With the client"), ("events", "From market events"), ("alerts", "From alerts"), ("specialist", "Specialist requests")]


class ServiceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


_SELECT = """
SELECT w.*, g.short_name AS client_name, g.watch_flag AS watch_flag, o.name AS owner_name, r.name AS requester_name,
       e.headline AS ev_headline, e.source_ref AS ev_ref, e.source_name AS ev_source,
       (SELECT COUNT(*) FROM work_thread t WHERE t.work_item_id = w.id) AS n_thread
FROM work_item w
LEFT JOIN client_group g ON g.id = w.client_group_id
LEFT JOIN app_user o ON o.id = w.owner_id
LEFT JOIN app_user r ON r.id = w.requester_id
LEFT JOIN market_event e ON e.id = w.source_event_id
"""


def _decorate(db, rows):
    dep_ids = set()
    for r in rows:
        dep_ids.update(json.loads(r["depends_on"] or "[]"))
    dep_state = {}
    if dep_ids:
        q = ",".join("?" * len(dep_ids))
        dep_state = {d["id"]: (d["state"], d["title"]) for d in db.execute(f"SELECT id,state,title FROM work_item WHERE id IN ({q})", list(dep_ids))}
    out = []
    for r in rows:
        w = dict(r)
        active = w["state"] in ACTIVE
        w["active"] = active
        w["due"] = clock.due_info(w["due_at"], active)
        w["type_label"] = TYPE_LABEL.get(w["work_type"], w["work_type"])
        w["next_states"] = [(s, BUTTON[s] if not (s == "In progress" and w["state"] == "Done") else "Reopen") for s in TRANSITIONS[w["state"]]]
        w["blocked_by"] = [(d, dep_state[d][1]) for d in json.loads(w["depends_on"] or "[]") if d in dep_state and dep_state[d][0] != "Done"]
        why = json.loads(w["why_path"]) if w["why_path"] else None
        w["why_lines"] = why.get("why", []) if why else []
        w["why_rules"] = why.get("rules", []) if why else []
        w["ev_real"] = bool(w["ev_ref"] and str(w["ev_ref"]).startswith("https://"))
        cr = w["case_ref"] or ""
        w["case_kind"] = ("alert" if cr.startswith("a_") else "need" if cr.startswith("opp_") else "meeting" if cr.startswith(("mt_", "en_")) else "client" if cr.startswith("g_") else "")
        w["client_deadline_info"] = clock.parse(w["client_deadline"]).strftime("%d %b") if w["client_deadline"] else None
        w["client_deadline_late"] = bool(w["client_deadline"] and active and clock.parse(w["client_deadline"]) < clock.now())
        out.append(w)
    return out


def _visible_ids(db, user, scope):
    return auth.team_ids(db, user) if scope == "team" and auth.is_lead(db, user) else [user["id"]]


def summary(db, user, scope):
    ids = _visible_ids(db, user, scope)
    rows = _decorate(db, db.execute(_SELECT + f" WHERE w.owner_id IN ({','.join('?' * len(ids))}) AND w.state IN ('Open','Accepted','In progress','Needs information')", ids).fetchall())
    s = dict(overdue=0, today=0, week=0, later=0, client=0, events=0, total=len(rows))
    for w in rows:
        s[w["due"]["bucket"]] += 1
        s["client"] += w["visibility"] == "client"
        s["events"] += bool(w["source_event_id"])
    return s


def list_work(db, user, scope="mine", status="active", kind="all", client="", q=""):
    ids = _visible_ids(db, user, scope)
    sql = _SELECT + f" WHERE w.owner_id IN ({','.join('?' * len(ids))})"
    args = list(ids)
    if status == "active":
        sql += " AND w.state IN ('Open','Accepted','In progress','Needs information')"
    elif status == "closed":
        sql += " AND w.state IN ('Done','Cancelled')"
    if client:
        sql += " AND w.client_group_id = ?"
        args.append(client)
    if q:
        sql += " AND (w.title LIKE ? OR g.short_name LIKE ? OR w.id LIKE ?)"
        args += [f"%{q}%"] * 3
    rows = _decorate(db, db.execute(sql, args).fetchall())
    if kind == "client":
        rows = [w for w in rows if w["visibility"] == "client"]
    elif kind == "events":
        rows = [w for w in rows if w["source_event_id"]]
    elif kind == "alerts":
        rows = [w for w in rows if w["case_kind"] == "alert"]
    elif kind == "specialist":
        rows = [w for w in rows if w["work_type"] == "specialist_request"]
    order = {b: i for i, (b, _) in enumerate(BUCKETS)}
    rows.sort(key=lambda w: (order[w["due"]["bucket"]], clock.parse(w["due_at"]) or clock.now()))
    grouped = []
    for key, label in BUCKETS:
        items = [w for w in rows if w["due"]["bucket"] == key]
        if items:
            grouped.append((key, label, items))
    return grouped, len(rows)


def client_options(db, user, scope):
    ids = _visible_ids(db, user, scope)
    return db.execute(f"SELECT DISTINCT g.id, g.short_name FROM work_item w JOIN client_group g ON g.id=w.client_group_id "
                      f"WHERE w.owner_id IN ({','.join('?' * len(ids))}) ORDER BY g.short_name", ids).fetchall()


def get_one(db, wid):
    row = db.execute(_SELECT + " WHERE w.id = ?", (wid,)).fetchone()
    if not row:
        raise ServiceError(404, "Work item not found")
    return _decorate(db, [row])[0]


def thread(db, wid):
    return db.execute("SELECT t.*, u.name AS by_name FROM work_thread t LEFT JOIN app_user u ON u.id=t.by_user "
                      "WHERE t.work_item_id=? ORDER BY t.at, t.id", (wid,)).fetchall()


def _audit(db, user, action, summary_text, affected):
    n = int(db.execute("SELECT value FROM app_meta WHERE key='audit_next'").fetchone()[0])
    db.execute("INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?)",
               (f"TXN-{n:06d}", clock.iso(clock.now()), user["id"], action, summary_text, None, None, json.dumps(affected)))
    db.execute("UPDATE app_meta SET value=? WHERE key='audit_next'", (str(n + 1),))


def _check_access(db, user, row):
    if row["owner_id"] not in auth.team_ids(db, user):
        raise ServiceError(403, "This item belongs to someone else")


def change_state(db, user, wid, to, version, note="", confirm=False):
    row = db.execute("SELECT * FROM work_item WHERE id=?", (wid,)).fetchone()
    if not row:
        raise ServiceError(404, "Work item not found")
    _check_access(db, user, row)
    if to not in TRANSITIONS.get(row["state"], []):
        raise ServiceError(422, f"Cannot move from {row['state']} to {to}")
    if to == "Done" and not confirm:
        raise ServiceError(422, "Confirm the completion condition first")
    if to == "Needs information" and not note.strip():
        raise ServiceError(422, "Say what information is needed")
    cur = db.execute("UPDATE work_item SET state=?, version=version+1 WHERE id=? AND version=?", (to, wid, version))
    if cur.rowcount == 0:
        raise ServiceError(409, "Someone else changed this item. The latest version is shown.")
    when = clock.iso(clock.now())
    text = f"{row['state']} to {to} by {user['name']}" + (f". {note.strip()}" if note.strip() else "")
    db.execute("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)", (wid, when, user["id"], "system", text))
    _audit(db, user, "work_state_change", f"{wid}: {row['state']} to {to}", [wid])
    return get_one(db, wid)


def add_note(db, user, wid, text):
    row = db.execute("SELECT * FROM work_item WHERE id=?", (wid,)).fetchone()
    if not row:
        raise ServiceError(404, "Work item not found")
    _check_access(db, user, row)
    if not text.strip():
        raise ServiceError(422, "Write a note first")
    db.execute("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)",
               (wid, clock.iso(clock.now()), user["id"], "message", text.strip()))
    _audit(db, user, "work_note", f"Note on {wid}", [wid])
