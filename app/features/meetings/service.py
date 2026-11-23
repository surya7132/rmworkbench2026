"""Meetings: the list, the brief before a meeting, and the debrief after it.

Brief  = what is already known (objective, agenda, questions, need) + what changed since last time (market events,
         promises, alerts, exposure), every line with its source. Nothing is invented: the talking points are rules over data.
Debrief = notes (typed or dictated) + follow-ups. Each follow-up becomes a work item in the same queue, so nothing is typed twice.
"""
import datetime as dt
import json

from ... import auth, clock
from . import ai
from ..events import service as E
from ..work import service as W

SOURCE = {"calendar": "Calendar", "outlook-detected": "Outlook (detected)", "rm": "Logged by RM"}
FOLLOW_TYPES = [("task", "Task for me or a colleague", "task", "internal"),
                ("promise", "Promise made to the client", "commitment", "client"),
                ("client", "Something the client asked for", "client_request", "client"),
                ("specialist", "Ask a specialist", "specialist_request", "internal")]
FOLLOW_MAP = {k: (t, v) for k, _, t, v in FOLLOW_TYPES}
SEV = {"High": 0, "Medium": 1, "Low": 2}


class MeetingError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _j(s, default):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default


def _cut(text, n):
    """Cut at a word boundary, never mid-word."""
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",;:- ") + "..."


def _people(db):
    out = {}
    for r in db.execute("SELECT id,name,attrs FROM node WHERE node_type='person'"):
        out[r["id"]] = dict(id=r["id"], name=r["name"], role=_j(r["attrs"], {}).get("role", ""))
    return out


def _decorate(m, people):
    m = dict(m)
    m["when"] = clock.parse(m["starts_at"])
    m["source_label"] = SOURCE.get(m["source"], m["source"])
    m["attendees"] = [people[i] for i in _j(m["attendee_node_ids"], []) if i in people]
    return m


_BASE = """SELECT m.*, g.short_name AS client_name, g.rm_id AS rm_id, u.name AS rm_name
           FROM meeting m JOIN client_group g ON g.id=m.client_group_id JOIN app_user u ON u.id=g.rm_id"""


def list_meetings(db, user):
    ids = auth.team_ids(db, user)
    ph = ",".join("?" * len(ids))
    people = _people(db)
    now = clock.now()
    rows = [_decorate(r, people) for r in db.execute(_BASE + f" WHERE g.rm_id IN ({ph})", ids)]
    pending = sorted([m for m in rows if m["status"] == "notes_pending"], key=lambda m: m["when"])
    upcoming = sorted([m for m in rows if m["status"] == "scheduled"], key=lambda m: m["when"])
    recent = sorted([m for m in rows if m["status"] == "held"], key=lambda m: m["when"], reverse=True)[:8]
    for m in upcoming:
        m["days_to"] = (m["when"].date() - now.date()).days
    return dict(pending=pending, upcoming=upcoming, recent=recent)


# ---------------------------------------------------------------- the brief

def _points(db, m, g):
    """Rule-based talking points. Each: dict(tag, text, source, href)."""
    pts = []
    now = clock.now()
    last = db.execute("SELECT title, starts_at, outcome FROM meeting WHERE client_group_id=? AND status='held' AND starts_at < ? ORDER BY starts_at DESC LIMIT 1",
                      (g["id"], m["starts_at"])).fetchone()
    if last and last["outcome"]:
        d = clock.parse(last["starts_at"]).strftime("%d %b")
        pts.append(dict(tag="Last time", text=f"On {d} ({last['title']}): {_cut(last['outcome'], 220)}", short=f"last met on {d}", source="Meeting history", href=f"/clients/{g['id']}#meetings"))
    gap = (now.date() - clock.parse(g["last_contact"] + "T00:00:00+05:30").date()).days if g["last_contact"] else None
    if gap is not None and gap > g["cadence_days"]:
        pts.append(dict(tag="Contact", text=f"Last contact was {gap} days ago. The usual rhythm for this client is {g['cadence_days']} days.", short=f"no contact for {gap} days", source="Client record", href=f"/clients/{g['id']}"))
    for r in db.execute("""SELECT w.id,w.title,w.due_at,w.state,w.work_type FROM work_item w WHERE w.client_group_id=? AND w.state IN ('Open','Accepted','In progress','Needs information')
                           AND w.work_type IN ('commitment','client_request') ORDER BY w.due_at LIMIT 3""", (g["id"],)):
        late = (now - clock.parse(r["due_at"])).days
        kind = "We promised" if r["work_type"] == "commitment" else "The client asked"
        when = f"overdue by {late} day{'s' if late != 1 else ''}" if late > 0 else f"due {clock.parse(r['due_at']).strftime('%d %b')}"
        pts.append(dict(tag="Open items", text=f"{kind}: {r['title']} ({when})", short=f"{'promised' if r['work_type'] == 'commitment' else 'asked'}: {_cut(r['title'], 60)} ({when})", source=f"Work queue {r['id']}", href="/work?kind=client"))
    since = (now - dt.timedelta(days=14)).isoformat()
    seen = set()
    for r in db.execute("""SELECT e.id,e.headline,e.severity,e.published_at,i.hops,i.reason FROM event_impact i JOIN market_event e ON e.id=i.event_id
                           WHERE i.client_group_id=? AND e.published_at >= ? AND e.severity<>'Low' ORDER BY e.published_at DESC, i.hops""", (g["id"], since)):
        if r["id"] in seen or len(seen) >= 2:
            continue
        seen.add(r["id"])
        steps = [s for s in (r["reason"] or "").split("; ") if s]
        if steps and " is part of " in steps[-1]:          # the last step only names the client group
            steps = steps[:-1]
        pts.append(dict(tag="Market", text=f"{r['headline']} ({clock.parse(r['published_at']).strftime('%d %b')})", short=f"market news: {_cut(r['headline'], 70)}",
                        detail=("Why it matters here: " + "; ".join(steps) + ".") if r["hops"] and steps else "About the client directly.", source="Market events", href=f"/events/{r['id']}"))
    for r in db.execute("SELECT id,title,severity,required_action FROM alert WHERE client_group_id=? AND state<>'Resolved' AND severity IN ('High','Medium') ORDER BY CASE severity WHEN 'High' THEN 1 ELSE 2 END LIMIT 2", (g["id"],)):
        pts.append(dict(tag="Early warning", text=f"{r['title']}. Next step: {r['required_action']}", short=f"early warning: {_cut(r['title'], 70)}", source=f"Alert {r['id']}", href=f"/clients/{g['id']}#overview"))
    util = round(100 * g["outstanding_cr"] / g["sanctioned_cr"]) if g["sanctioned_cr"] else 0
    if util >= 85:
        pts.append(dict(tag="Exposure", text=f"Limit use is {util}% (₹{g['outstanding_cr']:,.0f} cr of ₹{g['sanctioned_cr']:,.0f} cr). Ask about headroom needs.", short=f"limit use is {util}%", source="Account data", href=f"/clients/{g['id']}#facilities"))
    return pts[:8]


def _summary(m, g, points):
    who = ", ".join(a["name"] for a in m["attendees"]) or "the client"
    s = f"Meeting with {who} ({g['short_name']}) on {m['when'].strftime('%d %b %Y')}."
    if m["objective"]:
        s += f" Objective: {m['objective'].rstrip('.')}."
    shorts = [p["short"] for p in points if p.get("short")][:4]
    if shorts:
        s += " Worth knowing: " + "; ".join(shorts) + "."
    return s


def get(db, user, mid):
    row = db.execute(_BASE + " WHERE m.id=?", (mid,)).fetchone()
    if not row:
        raise MeetingError(404, "Meeting not found")
    if row["rm_id"] not in auth.team_ids(db, user):
        raise MeetingError(403, "This meeting belongs to another team")
    people = _people(db)
    m = _decorate(row, people)
    g = dict(db.execute("SELECT * FROM client_group WHERE id=?", (m["client_group_id"],)).fetchone())
    ag = _j(m["agenda"], {})
    need = db.execute("SELECT id,name,stage,product,next_action,value_lo_cr,value_hi_cr FROM need WHERE id=?", (m["need_id"],)).fetchone() if m["need_id"] else None
    need = dict(need) if need else None
    if need:
        nba = _j(need["next_action"], {}).get("nba", {})
        need["action"], need["why"] = nba.get("action"), nba.get("why")
    points = _points(db, m, g)
    followups = [dict(r) for r in db.execute("""SELECT w.id,w.title,w.state,w.due_at,w.work_type,u.name AS owner_name FROM work_item w JOIN app_user u ON u.id=w.owner_id
                                                WHERE w.why_path LIKE ? ORDER BY w.id""", (f'%"meeting": "{mid}"%',))]
    for f in followups:
        f["type_label"] = W.TYPE_LABEL.get(f["work_type"], f["work_type"])
    owners = [dict(r) for r in db.execute("SELECT id,name,role FROM app_user WHERE can_login=1 OR role IN ('Specialist','Credit reviewer','Credit analyst','Legal counsel','Function queue') ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END, name", (user["id"],))]
    return dict(m=m, g=g, util=round(100 * g["outstanding_cr"] / g["sanctioned_cr"]) if g["sanctioned_cr"] else 0, agenda=ag.get("agenda", {}), questions={k: v for k, v in ag.get("questions", {}).items() if v},
                info=ag.get("info", []), need=need, points=points, summary=_summary(m, g, points), followups=followups, owners=owners,
                follow_types=[(k, l) for k, l, _, _ in FOLLOW_TYPES], default_due=(clock.now() + dt.timedelta(days=7)).strftime("%Y-%m-%d"),
                can_debrief=m["status"] in ("scheduled", "notes_pending"), ai_on=ai.available())


# ---------------------------------------------------------------- writes

def _own(db, user, mid):
    row = db.execute(_BASE + " WHERE m.id=?", (mid,)).fetchone()
    if not row:
        raise MeetingError(404, "Meeting not found")
    if row["rm_id"] not in auth.team_ids(db, user):
        raise MeetingError(403, "This meeting belongs to another team")
    return row


def _lines(text):
    return [x.strip(" -•\t") for x in (text or "").splitlines() if x.strip(" -•\t")]


def save_prep(db, user, mid, objective, success, must, if_time, avoid, ready):
    row = _own(db, user, mid)
    if row["status"] != "scheduled":
        raise MeetingError(409, "Only an upcoming meeting can be prepared")
    ag = _j(row["agenda"], {})
    ag["agenda"] = dict(must=_lines(must), ifTime=_lines(if_time), avoid=_lines(avoid))
    objective, success = (objective or "").strip(), (success or "").strip()
    if ready and not (objective and ag["agenda"]["must"]):
        raise MeetingError(422, "To mark the prep ready, write an objective and at least one must-cover point")
    status = "ready" if ready else (row["prep_status"] or "incomplete")
    db.execute("UPDATE meeting SET objective=?, success_criteria=?, agenda=?, prep_status=? WHERE id=?", (objective, success, json.dumps(ag), status, mid))
    W._audit(db, user, "prepare_meeting", f"Prepared {row['title']} with {row['client_name']}", [mid])


def debrief(db, user, mid, notes, decisions, followups):
    """followups: list of dict(title, owner, due, kind). Returns created work ids."""
    row = _own(db, user, mid)
    if row["status"] not in ("scheduled", "notes_pending"):
        raise MeetingError(409, "Notes were already saved for this meeting")
    notes, decisions = (notes or "").strip(), (decisions or "").strip()
    if not notes:
        raise MeetingError(422, "Write or dictate what was discussed first")
    clean = []
    users = {r["id"] for r in db.execute("SELECT id FROM app_user")}
    for f in followups:
        t = (f.get("title") or "").strip()
        if not t:
            continue
        if f.get("owner") not in users:
            raise MeetingError(422, f"Pick who owns: {t}")
        try:
            due = dt.date.fromisoformat(f.get("due") or "")
        except ValueError:
            raise MeetingError(422, f"Give a due date for: {t}")
        if f.get("kind") not in FOLLOW_MAP:
            raise MeetingError(422, f"Pick the kind of follow-up for: {t}")
        clean.append(dict(title=t, owner=f["owner"], due=due, kind=f["kind"]))
    now = clock.now()
    when = clock.iso(now)
    outcome = notes + (f"\n\nDecisions: {decisions}" if decisions else "")
    db.execute("UPDATE meeting SET status='held', logged=1, outcome=? WHERE id=?", (outcome, mid))
    n = E._next_work_no(db)
    created = []
    day = row["starts_at"][:10]
    for f in clean:
        wid = f"W-{n}"
        n += 1
        wtype, vis = FOLLOW_MAP[f["kind"]]
        why = f"Raised in the meeting '{row['title']}' with {row['client_name']} on {clock.parse(row['starts_at']).strftime('%d %b')}."
        db.execute("INSERT INTO work_item VALUES (" + ",".join("?" * 21) + ")",
                   (wid, f["title"], wtype, row["client_group_id"], None, f["owner"], user["id"], when, f["due"].isoformat() + "T18:00:00+05:30", None, why, "Open",
                    "Done and the client or requester informed", "[]", 0, vis, None, None, None, json.dumps({"why": [why], "rules": [], "meeting": mid}), 1))
        db.execute("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)",
                   (wid, when, user["id"], "system", f"Created from the meeting notes by {user['name']}"))
        created.append(wid)
    W._audit(db, user, "log_meeting", f"Logged {row['title']} with {row['client_name']}: {len(created)} follow-ups", [mid, *created])
    return created


def ai_text(db, user, mid, mode, text):
    _own(db, user, mid)
    if not ai.available():
        raise MeetingError(503, "AI help is not set up on this server")
    text = (text or "").strip()
    if not text:
        raise MeetingError(422, "Nothing to work on yet")
    try:
        return ai.tidy(text) if mode == "tidy" else ai.rewrite(text)
    except Exception:
        raise MeetingError(502, "The AI service did not answer. Your text is unchanged.")
