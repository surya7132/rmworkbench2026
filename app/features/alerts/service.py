"""Early warnings: triage, in four moves.

    New            --Accept-->   Under review   (a task is created in the work queue, with a due date by priority)
    Under review   --Respond-->  Responded      (what was done or what the client said is recorded)
    Responded      --Resolve-->  Resolved       (with a reason)
    New / Under review --Dismiss--> Resolved    (with a reason: false alarm, not material ...)

Priority: P1 = High, P2 = Medium, P3 = Low. Every move writes an audit entry. Two people moving the same alert:
the second one is told it changed (the update only applies if the alert is still in the state they saw).
"""
import datetime as dt
import json

from ... import auth, clock
from ..clients import detail as CD
from ..events import service as E
from ..work import service as W

PRIO = {"High": "P1", "Medium": "P2", "Low": "P3"}
DUE_DAYS = {"P1": 1, "P2": 3, "P3": 7}
PRIO_TEXT = {"P1": ("Act today", "High severity. A task is due in 1 day once accepted."),
             "P2": ("This week", "Medium severity. A task is due in 3 days once accepted."),
             "P3": ("Keep watching", "Low severity. A task is due in 7 days once accepted.")}
OPEN = ("New", "Under review", "Responded")
STATES = [("open", "Open"), ("New", "To triage"), ("Under review", "Under review"), ("Responded", "Responded"), ("Resolved", "Resolved")]
DISMISS_REASONS = ["False alarm", "Already handled", "Not material", "Duplicate of another alert", "Other"]
RESOLVE_REASONS = ["Client rectified the issue", "Documents or payment received", "Credit review completed", "Risk accepted with approval", "Other"]
BUTTONS = {"New": [("accept", "Accept", "primary"), ("dismiss", "Dismiss", "plain")],
           "Under review": [("respond", "Respond", "primary"), ("dismiss", "Dismiss", "plain")],
           "Responded": [("resolve", "Resolve", "primary"), ("reopen", "Back to review", "plain")],
           "Resolved": []}


class AlertError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _j(s, d):
    try:
        return json.loads(s) if s else d
    except ValueError:
        return d


_SELECT = """SELECT a.*, g.short_name AS client_name, g.rm_id AS rm_id, u.name AS rm_name, g.outstanding_cr AS client_outstanding
             FROM alert a JOIN client_group g ON g.id=a.client_group_id JOIN app_user u ON u.id=g.rm_id"""


def _decorate(db, rows):
    now = clock.now()
    out = []
    for r in rows:
        a = dict(r)
        a["prio"] = PRIO[a["severity"]]
        d = clock.parse(a["detected_at"])
        a["detected"] = d.strftime("%d %b")
        a["days_open"] = max((now.date() - d.date()).days, 0)
        ids = _j(a["fact_ids"], [])
        a["facts"] = []
        if ids:
            q = ",".join("?" * len(ids))
            a["facts"] = [dict(f, label=CD.LABELS.get(f["evidence_label"], f["evidence_label"])) for f in db.execute(
                f"SELECT id,statement,source_name,source_date,evidence_label,shareability FROM fact WHERE id IN ({q})", ids)]
        a["work"] = [dict(w) for w in db.execute("SELECT w.id,w.title,w.state,w.due_at,u.name AS owner FROM work_item w JOIN app_user u ON u.id=w.owner_id WHERE w.case_ref=? ORDER BY w.id", (a["id"],))]
        a["event"] = db.execute("SELECT id,headline FROM market_event WHERE id=?", (a["source_event_id"],)).fetchone() if a["source_event_id"] else None
        a["history"] = [dict(h) for h in db.execute("""SELECT l.at,l.summary,u.name AS who FROM audit_log l LEFT JOIN app_user u ON u.id=l.user_id
                                                       WHERE l.affected LIKE ? ORDER BY l.at DESC, l.txn_id DESC LIMIT 5""", (f'%"{a["id"]}"%',))]
        for h in a["history"]:
            h["when"] = clock.parse(h["at"]).strftime("%d %b, %H:%M") if "T" in h["at"] else h["at"]
        a["buttons"] = BUTTONS[a["state"]]
        out.append(a)
    return out


def _team_clause(db, user):
    ids = auth.team_ids(db, user)
    return ",".join("?" * len(ids)), ids


def summary(db, user):
    ph, ids = _team_clause(db, user)
    rows = db.execute(f"SELECT a.severity, a.state, COUNT(*) n FROM alert a JOIN client_group g ON g.id=a.client_group_id WHERE g.rm_id IN ({ph}) GROUP BY 1,2", ids).fetchall()
    s = {p: dict(open=0, new=0) for p in ("P1", "P2", "P3")}
    for r in rows:
        if r["state"] in OPEN:
            s[PRIO[r["severity"]]]["open"] += r["n"]
            if r["state"] == "New":
                s[PRIO[r["severity"]]]["new"] += r["n"]
    return dict(prio=s, total=sum(v["open"] for v in s.values()), new=sum(v["new"] for v in s.values()))


def categories(db, user):
    ph, ids = _team_clause(db, user)
    return [r[0] for r in db.execute(f"SELECT DISTINCT a.category FROM alert a JOIN client_group g ON g.id=a.client_group_id WHERE g.rm_id IN ({ph}) ORDER BY 1", ids)]


def list_alerts(db, user, state="open", prio="all", category="", q=""):
    ph, ids = _team_clause(db, user)
    rows = db.execute(_SELECT + f" WHERE g.rm_id IN ({ph}) ORDER BY CASE a.severity WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, a.detected_at DESC", ids).fetchall()
    ql = q.strip().lower()
    keep = []
    for r in rows:
        if state == "open" and r["state"] not in OPEN:
            continue
        if state in ("New", "Under review", "Responded", "Resolved") and r["state"] != state:
            continue
        if prio in ("P1", "P2", "P3") and PRIO[r["severity"]] != prio:
            continue
        if category and r["category"] != category:
            continue
        if ql and ql not in f"{r['title']} {r['client_name']} {r['id']} {r['ews_code']}".lower():
            continue
        keep.append(r)
    alerts = _decorate(db, keep)
    groups = []
    for p in ("P1", "P2", "P3"):
        items = [a for a in alerts if a["prio"] == p]
        if items:
            groups.append((p, PRIO_TEXT[p][0], items))
    return groups, len(alerts)


def get_one(db, user, aid):
    row = db.execute(_SELECT + " WHERE a.id=?", (aid,)).fetchone()
    if not row:
        raise AlertError(404, "Alert not found")
    if row["rm_id"] not in auth.team_ids(db, user):
        raise AlertError(403, "This alert belongs to another team")
    return _decorate(db, [row])[0]


def transition(db, user, aid, action, note="", reason=""):
    row = db.execute(_SELECT + " WHERE a.id=?", (aid,)).fetchone()
    if not row:
        raise AlertError(404, "Alert not found")
    if row["rm_id"] not in auth.team_ids(db, user):
        raise AlertError(403, "This alert belongs to another team")
    note, reason = (note or "").strip(), (reason or "").strip()
    rules = {"accept": (("New",), "Under review"), "respond": (("Under review",), "Responded"), "resolve": (("Responded",), "Resolved"),
             "dismiss": (("New", "Under review"), "Resolved"), "reopen": (("Responded",), "Under review")}
    if action not in rules:
        raise AlertError(422, "Unknown action")
    frm, to = rules[action]
    if row["state"] not in frm:
        raise AlertError(409, f"This alert is now '{row['state']}'. Someone else may have moved it. The latest version is shown.")
    if action == "respond" and not note:
        raise AlertError(422, "Write what you did or what the client said")
    if action in ("dismiss", "resolve"):
        allowed = DISMISS_REASONS if action == "dismiss" else RESOLVE_REASONS
        if reason not in allowed:
            raise AlertError(422, "Pick a reason")
        if reason == "Other" and not note:
            raise AlertError(422, "Say what the reason is")
    now = clock.now()
    when = clock.iso(now)
    created = []
    if to == "Resolved":
        why = reason + (f": {note}" if note else "")
        cur = db.execute("UPDATE alert SET state=?, resolution_reason=?, resolved_by=?, resolved_at=? WHERE id=? AND state=?", (to, why, user["id"], when, aid, row["state"]))
    else:
        cur = db.execute("UPDATE alert SET state=? WHERE id=? AND state=?", (to, aid, row["state"]))
    if cur.rowcount == 0:
        raise AlertError(409, "Someone else changed this alert. The latest version is shown.")
    text = f"{aid} ({row['client_name']}): {row['state']} to {to}"
    existing = [w["id"] for w in db.execute("SELECT id FROM work_item WHERE case_ref=? AND state IN ('Open','Accepted','In progress','Needs information')", (aid,))] if action == "accept" else []
    if action == "accept" and existing:
        text += f". Linked to existing task{'s' if len(existing) > 1 else ''} {', '.join(existing)}; no new task created"
    elif action == "accept":
        p = PRIO[row["severity"]]
        wid = f"W-{E._next_work_no(db)}"
        due = (now + dt.timedelta(days=DUE_DAYS[p])).date().isoformat() + "T18:00:00+05:30"
        why_line = f"Early warning {aid} ({p}) on {row['client_name']}: {row['title']}."
        db.execute("INSERT INTO work_item VALUES (" + ",".join("?" * 21) + ")",
                   (wid, row["required_action"] or row["title"], "task", row["client_group_id"], aid, row["rm_id"], user["id"], when, due, None,
                    (row["context"] or why_line)[:400], "Open", "Action taken and the alert updated", "[]", 0, "internal", None, None, row["source_event_id"],
                    json.dumps({"why": [why_line], "rules": [], "alert": aid}), 1))
        db.execute("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)", (wid, when, user["id"], "system", f"Created when {user['name']} accepted early warning {aid}"))
        created.append(wid)
        text += f". Task {wid} created"
    elif action == "respond":
        text += f". {note}"
        for w in db.execute("SELECT id FROM work_item WHERE case_ref=? AND state IN ('Open','Accepted','In progress','Needs information')", (aid,)):
            db.execute("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)", (w["id"], when, user["id"], "message", f"Response recorded on {aid}: {note}"))
    elif to == "Resolved":
        text += f". {reason}" + (f": {note}" if note else "")
    audit_name = {"accept": "accept_alert", "respond": "respond_alert", "resolve": "resolve_alert", "dismiss": "dismiss_alert", "reopen": "reopen_alert"}[action]
    W._audit(db, user, audit_name, text, [aid, *created])
    return created
