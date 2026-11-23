"""Market events: list them, show who each one reaches, and route a new one to the right people.

The pipeline for one event (this is what the Process button runs):
  1. match   - names in the news item are matched to companies in the graph
  2. reach   - the graph is walked (suppliers, customers, owners, lenders) to find the client groups affected
  3. route   - the routing rules decide who must look at it and why; one task per person
  4. record  - tasks land in the same work queue as everything else; the event is marked processed; the audit log is written

Steps 1-3 are the same code the seed uses (seed/routing.py), so what you preview is exactly what gets created.
"""
import datetime as dt
import json
import re

from seed import routing
from seed.graph import Graph  # noqa: F401  (kept so the dependency is explicit)

from ... import auth, clock
from ..work import service as W

SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}
DOWN = {"High": "Medium", "Medium": "Low", "Low": "Low"}
KINDS = [("all", "All"), ("pending", "Needs routing"), ("mine", "Reaches my clients"), ("high", "High and medium")]
CAN_PROCESS = ("Relationship manager", "Team lead")

RULE_PLAIN = {
    "RR-01": "The client's relationship manager reviews it",
    "RR-02": "A product specialist re-checks an active need",
    "RR-03": "The credit reviewer notes it on an open credit case",
    "RR-04": "The team lead sees the combined exposure",
    "RR-05": "The MIU desk checks the entity behind a new charge",
    "RR-06": "The relationship manager reviews a rating change on the client",
}


class EventError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _is_url(s):
    return bool(s) and str(s).startswith("http")


def _chain(reason):
    return [s for s in (reason or "").split("; ") if s]


def _decorate(r):
    e = dict(r)
    e["real"] = _is_url(e["source_ref"])
    e["url"] = e["source_ref"] if e["real"] else None
    e["names"] = json.loads(e["entity_names"] or "[]")
    return e


def counts(db, user):
    mine = auth.team_ids(db, user)
    q = ",".join("?" * len(mine))
    return dict(
        pending=db.execute("SELECT COUNT(*) FROM market_event WHERE status='pending'").fetchone()[0],
        total=db.execute("SELECT COUNT(*) FROM market_event").fetchone()[0],
        high=db.execute("SELECT COUNT(*) FROM market_event WHERE severity<>'Low'").fetchone()[0],
        mine=db.execute(f"SELECT COUNT(DISTINCT i.event_id) FROM event_impact i JOIN client_group g ON g.id=i.client_group_id WHERE g.rm_id IN ({q})", mine).fetchone()[0],
    )


def list_events(db, user, kind="all", q=""):
    mine = auth.team_ids(db, user)
    ph = ",".join("?" * len(mine))
    rows = db.execute(f"""
        SELECT e.*,
          (SELECT COUNT(DISTINCT client_group_id) FROM event_impact WHERE event_id=e.id) AS n_clients,
          (SELECT COUNT(DISTINCT i.client_group_id) FROM event_impact i JOIN client_group g ON g.id=i.client_group_id
             WHERE i.event_id=e.id AND g.rm_id IN ({ph})) AS n_mine,
          (SELECT COUNT(*) FROM work_item WHERE source_event_id=e.id) AS n_tasks
        FROM market_event e ORDER BY e.published_at DESC, e.id DESC""", mine).fetchall()
    out = []
    ql = q.strip().lower()
    for r in rows:
        e = _decorate(r)
        if kind == "pending" and e["status"] != "pending":
            continue
        if kind == "mine" and not e["n_mine"]:
            continue
        if kind == "high" and e["severity"] == "Low":
            continue
        if ql and ql not in " ".join([e["headline"], e["sector"] or "", e["event_type"], e["source_name"], " ".join(e["names"])]).lower():
            continue
        out.append(e)
    return out


def pending_clusters(db):
    """Pending events, grouped by cluster key so the same story is routed once (one task per person, not per article)."""
    rows = db.execute("SELECT * FROM market_event WHERE status='pending' ORDER BY published_at").fetchall()
    groups = {}
    for r in rows:
        e = _decorate(r)
        groups.setdefault(e["cluster_key"] or e["id"], []).append(e)
    return list(groups.values())


# ---------------------------------------------------------------- reach and routing (nothing is written here)

def _reach(db, e):
    """Clients the event reaches, by walking the graph from the entities named in it. Returns a list of dicts."""
    G = routing.load_graph(db)
    starts = routing.resolve_entities(db, e["names"])
    best = {}
    for nid, _conf in starts:
        for r in G.impact_walk([nid], max_hops=3):
            if r["group"] not in best or r["hops"] < best[r["group"]]["hops"]:
                best[r["group"]] = r
    out = []
    for gid, r in best.items():
        g = db.execute("SELECT g.id,g.short_name,g.rm_id,g.outstanding_cr,u.name AS rm_name FROM client_group g JOIN app_user u ON u.id=g.rm_id WHERE g.id=?", (gid,)).fetchone()
        sev = e["severity"]
        out.append(dict(group=gid, client=g["short_name"], rm_id=g["rm_id"], rm_name=g["rm_name"], exposure=g["outstanding_cr"], hops=r["hops"],
                        impact=sev if r["hops"] == 0 else DOWN[sev], node=r["entity"], conf=r["conf"],
                        chain=_chain(G.describe(r["path"])), path=[dict(node=p[0], edge=p[1], dir=p[2]) for p in r["path"]]))
    out.sort(key=lambda x: (x["hops"], -x["exposure"]))
    return out, [G.nodes[n]["name"] for n, _ in starts]


def _recorded_reach(db, eid):
    rows = db.execute("""SELECT i.*, g.short_name, g.rm_id, g.outstanding_cr, u.name AS rm_name FROM event_impact i
                         JOIN client_group g ON g.id=i.client_group_id JOIN app_user u ON u.id=g.rm_id
                         WHERE i.event_id=? ORDER BY i.hops, g.outstanding_cr DESC""", (eid,)).fetchall()
    best = {}
    for r in rows:
        best.setdefault(r["client_group_id"], r)
    return [dict(group=r["client_group_id"], client=r["short_name"], rm_id=r["rm_id"], rm_name=r["rm_name"], exposure=r["outstanding_cr"], hops=r["hops"],
                 impact=r["impact_level"], conf=r["match_confidence"], chain=_chain(r["reason"])) for r in best.values()]


def _plan(db, ids):
    """What routing would create for these events: one dict per recipient."""
    names = {r["id"]: (r["name"], r["role"]) for r in db.execute("SELECT id,name,role FROM app_user")}
    plan = []
    for uid, t in routing.route_event(db, ids).items():
        plan.append(dict(user_id=uid, user_name=names[uid][0], user_role=names[uid][1], type=t["type"], type_label=W.TYPE_LABEL.get(t["type"], t["type"]),
                         rules=t["rules"], rule_names=[RULE_PLAIN.get(r, r) for r in t["rules"]], title=t["title"], why=t["why"], due_h=t["due_h"],
                         clients=t["clients"], events=t["events"], needs=t["needs"]))
    order = {"Relationship manager": 0, "Specialist": 1, "Credit reviewer": 2, "Function queue": 3, "Team lead": 4}
    plan.sort(key=lambda p: (order.get(p["user_role"], 9), p["user_name"]))
    return plan


def _sibling_ids(db, e):
    if e["status"] != "pending" or not e["cluster_key"]:
        return [e["id"]]
    return [r["id"] for r in db.execute("SELECT id FROM market_event WHERE status='pending' AND cluster_key=? ORDER BY published_at", (e["cluster_key"],))]


def get(db, user, eid):
    r = db.execute("SELECT * FROM market_event WHERE id=?", (eid,)).fetchone()
    if not r:
        raise EventError(404, "Market event not found")
    e = _decorate(r)
    mine = set(auth.team_ids(db, user))
    if e["status"] == "pending":
        reach, matched = _reach(db, e)
        ids = _sibling_ids(db, e)
        plan = _plan(db, ids)
        tasks = []
    else:
        reach = _recorded_reach(db, eid)
        matched = [x["name"] for x in db.execute("SELECT DISTINCT n.name FROM event_impact i JOIN node n ON n.id=i.node_id WHERE i.event_id=?", (eid,))]
        ids = [r[0] for r in db.execute("SELECT id FROM market_event WHERE cluster_key=? ORDER BY published_at", (e["cluster_key"],))] if e["cluster_key"] else [eid]
        plan = []
        q = ",".join("?" * len(ids))
        tasks = [dict(w) for w in db.execute(f"""SELECT w.id,w.title,w.state,w.due_at,w.work_type,w.owner_id,u.name AS owner_name,u.role AS owner_role,w.why_path
                                               FROM work_item w JOIN app_user u ON u.id=w.owner_id WHERE w.source_event_id IN ({q}) ORDER BY u.role, u.name""", ids)]
        for t in tasks:
            t["type_label"] = W.TYPE_LABEL.get(t["work_type"], t["work_type"])
            wp = json.loads(t["why_path"] or "{}")
            t["rules"], t["why"] = wp.get("rules", []), (wp.get("why") or [""])[0]
            t["rule_names"] = [RULE_PLAIN.get(x, x) for x in t["rules"]]
            t["mine"] = t["owner_id"] in mine
    for x in reach:
        x["mine"] = x["rm_id"] in mine
    siblings = [dict(id=i, headline=db.execute("SELECT headline FROM market_event WHERE id=?", (i,)).fetchone()[0]) for i in ids if i != eid]
    return dict(e=e, reach=reach, matched=matched, plan=plan, tasks=tasks, siblings=siblings, exposure=sum(x["exposure"] for x in reach),
                n_rms=len({x["rm_id"] for x in reach}), can_process=user["role"] in CAN_PROCESS and e["status"] == "pending",
                rules=[dict(r) for r in db.execute("SELECT * FROM routing_rule WHERE active=1 ORDER BY sort_order")])


# ---------------------------------------------------------------- the Process button (writes)

def _next_work_no(db):
    return max(int(r[0][2:]) for r in db.execute("SELECT id FROM work_item WHERE id GLOB 'W-[0-9]*'")) + 1


def _plain_why(text):
    t = re.sub(r"\s*\([^()]*\)", "", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= 400 else t[:397].rsplit(" ", 1)[0] + "..."


def process(db, user, eid):
    """Route a pending event (and the pending events in its cluster) and create the tasks. Returns the list of created work ids."""
    r = db.execute("SELECT * FROM market_event WHERE id=?", (eid,)).fetchone()
    if not r:
        raise EventError(404, "Market event not found")
    e = _decorate(r)
    if user["role"] not in CAN_PROCESS:
        raise EventError(403, "Only a relationship manager or team lead can route an event")
    if e["status"] != "pending":
        raise EventError(409, "This event has already been processed")
    ids = _sibling_ids(db, e)
    now = clock.now()
    when = clock.iso(now)
    # 2. reach: record who each event touches
    for i in ids:
        ev = _decorate(db.execute("SELECT * FROM market_event WHERE id=?", (i,)).fetchone())
        reach, _ = _reach(db, ev)
        for x in reach:
            db.execute("INSERT INTO event_impact (event_id,node_id,client_group_id,hops,path,reason,impact_level,match_confidence) VALUES (?,?,?,?,?,?,?,?)",
                       (i, x["node"], x["group"], x["hops"], json.dumps(x["path"]), "; ".join(x["chain"]), x["impact"], round(x["conf"], 3)))
    # 3. route and 4. record
    plan = _plan(db, ids)
    n = _next_work_no(db)
    created = []
    for p in plan:
        wid = f"W-{n}"
        n += 1
        due = clock.iso(now + dt.timedelta(hours=p["due_h"]))
        db.execute("INSERT INTO work_item VALUES (" + ",".join("?" * 21) + ")",
                   (wid, p["title"], p["type"], p["clients"][0], None, p["user_id"], user["id"], when, due, None, _plain_why(p["why"][0]), "Open",
                    "Reviewed and, if needed, followed up", "[]", 0, "internal", None, None, p["events"][0], json.dumps({"why": p["why"], "rules": p["rules"]}), 1))
        db.execute("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)",
                   (wid, when, user["id"], "system", f"Created by event routing (rules {', '.join(p['rules'])}), processed by {user['name']}"))
        created.append(wid)
    q = ",".join("?" * len(ids))
    db.execute(f"UPDATE market_event SET status='processed', processed_at=? WHERE id IN ({q})", [when, *ids])
    W._audit(db, user, "process_event", f"Routed {', '.join(ids)}: {len(created)} tasks created", [*ids, *created])
    return ids, created
