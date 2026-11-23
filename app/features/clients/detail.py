"""Everything the client page shows, gathered in one place.

Read-only. Any signed-in user can open any client (the list already lets an RM browse other books);
changes are made in the work queue, where ownership is enforced.
"""
import json

from ... import clock
from ..work import service as W

LABELS = {"int": "Bank system", "ext": "External source", "client": "Client said", "rm": "RM note", "model": "Model estimate",
          "ind": "Industry", "need": "Need", "blk": "Blocker", "sup": "Supporting", "miu": "MIU finding"}
SHARE = {"internal": ("Internal only", "For the bank. Do not raise with the client."),
         "discuss": ("Can discuss", "Fine to raise with the client as a topic."),
         "confirmed": ("Client confirmed", "The client has confirmed this.")}
EDGE_LABEL = {"supplies_to": "supplies", "member_of": "part of", "director_of": "director of", "employed_by": "works at", "operates_in": "operates in",
              "owns": "owns", "stakeholder_for": "contact for", "has_need": "has need", "lends_to": "lends to", "transports_for": "freight for",
              "has_primary": "primary borrower"}
MAP_HIDE_TYPES = ("rbl_user", "bank", "product_family")
MAP_HIDE_EDGES = ("managed_by", "in_family", "handled_by", "reviewed_by", "treasury_of")


def _j(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _is_url(s):
    return bool(s) and str(s).startswith("https://")


def _facilities(db, gid):
    out = []
    for r in db.execute("SELECT * FROM facility WHERE client_group_id=? ORDER BY sanctioned_cr DESC", (gid,)):
        f = dict(r)
        f["util"] = round(100 * f["outstanding_cr"] / f["sanctioned_cr"]) if f["sanctioned_cr"] else 0
        out.append(f)
    return out


def _facts(db, gid):
    rows = db.execute("SELECT * FROM fact WHERE client_group_id=? ORDER BY superseded_by IS NOT NULL, source_date DESC, id", (gid,)).fetchall()
    out = []
    for r in rows:
        f = dict(r)
        f["label_name"] = LABELS.get(f["evidence_label"], f["evidence_label"])
        f["share_name"], f["share_hint"] = SHARE.get(f["shareability"], (f["shareability"], ""))
        f["link"] = f["source_ref"] if _is_url(f["source_ref"]) else None
        f["superseded"] = bool(f["superseded_by"])
        out.append(f)
    return out


def _needs(db, gid, facts_by_id):
    out = []
    names = {n["id"]: n["name"] for n in db.execute("SELECT id, name FROM node WHERE client_group_id=? AND node_type='person'", (gid,))}
    users = {u["id"]: u["name"] for u in db.execute("SELECT id, name FROM app_user")}
    for r in db.execute("SELECT * FROM need WHERE client_group_id=? ORDER BY value_hi_cr DESC", (gid,)):
        n = dict(r)
        n["specialist_name"] = users.get(n["specialist_id"])
        n["reviewer_name"] = users.get(n["reviewer_id"])
        n["stakeholder_name"] = names.get(n["stakeholder_node_id"])
        n["facts"] = [facts_by_id[i] for i in _j(n["fact_ids"], []) if i in facts_by_id]
        out.append(n)
    return out


def _people(db, gid):
    people, entities = [], []
    for r in db.execute("SELECT * FROM node WHERE client_group_id=? AND node_type IN ('person','company') ORDER BY node_type DESC, name", (gid,)):
        a = _j(r["attrs"], {})
        item = dict(id=r["id"], name=r["name"], attrs=a)
        (people if r["node_type"] == "person" else entities).append(item)
    return people, entities


def _meetings(db, gid):
    people = {n["id"]: n["name"] for n in db.execute("SELECT id, name FROM node WHERE node_type='person'")}
    now = clock.now()
    rows = []
    for r in db.execute("SELECT * FROM meeting WHERE client_group_id=?", (gid,)):
        m = dict(r)
        m["attendees"] = [people.get(i, i) for i in _j(m["attendee_node_ids"], [])]
        m["when"] = clock.parse(m["starts_at"])
        m["upcoming"] = m["status"] == "scheduled" and m["when"] >= now
        rows.append(m)
    rows.sort(key=lambda m: (0 if m["upcoming"] else 1, m["when"] if m["upcoming"] else -m["when"].timestamp()))
    return rows


def _work(db, gid):
    active = ",".join(f"'{s}'" for s in W.ACTIVE)
    rows = W._decorate(db, db.execute(W._SELECT + f" WHERE w.client_group_id=? AND w.state IN ({active})", (gid,)).fetchall())
    order = {b: i for i, (b, _) in enumerate(W.BUCKETS)}
    rows.sort(key=lambda w: (order[w["due"]["bucket"]], w["due_at"]))
    return rows


def _alerts(db, gid):
    return [dict(r) for r in db.execute(
        "SELECT * FROM alert WHERE client_group_id=? ORDER BY state='Resolved', CASE severity WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, detected_at DESC", (gid,))]


def _news(db, gid):
    """Events that reach this client, each once, with the shortest route (fewest hops) as a readable chain."""
    out = {}
    for r in db.execute("""SELECT e.*, i.hops, i.reason, i.impact_level FROM event_impact i JOIN market_event e ON e.id=i.event_id
                           WHERE i.client_group_id=? ORDER BY e.published_at DESC, i.hops""", (gid,)):
        if r["id"] in out:
            continue
        e = dict(r)
        e["real"] = _is_url(e["source_ref"])
        e["chain"] = [s for s in (e["reason"] or "").split("; ") if s]
        out[e["id"]] = e
    return list(out.values())[:40]


def _graph(db, gid):
    """Nodes and links around this client: its own entities plus the companies one step away."""
    own = {r["id"] for r in db.execute("SELECT id FROM node WHERE client_group_id=?", (gid,))}
    ids = ",".join("?" * len(own))
    edges = db.execute(f"SELECT * FROM edge WHERE from_node IN ({ids}) OR to_node IN ({ids})", [*own, *own]).fetchall()
    keep = set(own)
    for e in edges:
        keep.update((e["from_node"], e["to_node"]))
    q = ",".join("?" * len(keep))
    nodes = {n["id"]: n for n in db.execute(f"SELECT * FROM node WHERE id IN ({q})", list(keep))}
    nodes = {i: n for i, n in nodes.items() if n["node_type"] not in MAP_HIDE_TYPES}
    news = {}
    nq = ",".join("?" * len(nodes))
    for r in db.execute(f"""SELECT DISTINCT i.node_id, e.id, e.headline, e.published_at, e.source_ref FROM event_impact i JOIN market_event e ON e.id=i.event_id
                            WHERE i.client_group_id=? AND i.node_id IN ({nq}) ORDER BY e.published_at DESC""", [gid, *nodes]):
        lst = news.setdefault(r["node_id"], [])
        if len(lst) < 3:
            lst.append(dict(headline=r["headline"], date=r["published_at"][:10], real=_is_url(r["source_ref"]), url=r["source_ref"] if _is_url(r["source_ref"]) else None))
    members = {e["from_node"] for e in edges if e["edge_type"] == "member_of" and e["to_node"] == gid}   # real group companies
    out_nodes, out_edges = [], []
    for i, n in nodes.items():
        a = _j(n["attrs"], {})
        out_nodes.append(dict(id=i, label=n["name"], type=n["node_type"], mine=(i in members) if n["node_type"] == "company" else (i in own), role=a.get("role") or a.get("entity_kind") or "",
                              detail=" · ".join(str(a[k]) for k in ("legal_name", "cin", "registered_office", "status") if a.get(k)), news=news.get(i, [])))
    for e in edges:
        if e["edge_type"] in MAP_HIDE_EDGES or e["from_node"] not in nodes or e["to_node"] not in nodes:
            continue
        out_edges.append(dict(id=f"e{e['id']}", source=e["from_node"], target=e["to_node"], label=EDGE_LABEL.get(e["edge_type"], e["edge_type"].replace("_", " ")),
                              weak=e["confidence"] < 0.8))
    return dict(nodes=out_nodes, edges=out_edges, center=f"{gid}")


def get(db, gid):
    g = db.execute("SELECT g.*, u.name AS rm_name FROM client_group g JOIN app_user u ON u.id=g.rm_id WHERE g.id=?", (gid,)).fetchone()
    if not g:
        return None
    g = dict(g)
    g["util"] = round(100 * g["outstanding_cr"] / g["sanctioned_cr"]) if g["sanctioned_cr"] else 0
    last = clock.parse(g["last_contact"])
    g["days_since"] = (clock.now().date() - last.date()).days if last else None
    g["contact_late"] = g["days_since"] is not None and g["days_since"] > g["cadence_days"]
    facts = _facts(db, gid)
    people, entities = _people(db, gid)
    d = dict(g=g, facilities=_facilities(db, gid), facts=facts, needs=_needs(db, gid, {f["id"]: f for f in facts}), people=people, entities=entities,
             meetings=_meetings(db, gid), work=_work(db, gid), alerts=_alerts(db, gid), news=_news(db, gid), graph=_graph(db, gid),
             documents=[dict(r) for r in db.execute("SELECT * FROM document WHERE client_group_id=? ORDER BY uploaded_at DESC", (gid,))],
             labels=LABELS)
    d["labels_present"] = [k for k in LABELS if any(f["evidence_label"] == k for f in facts)]
    d["open_alerts"] = [a for a in d["alerts"] if a["state"] != "Resolved"]
    d["real_news"] = sum(1 for n in d["news"] if n["real"])
    return d
