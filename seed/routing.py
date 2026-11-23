"""Event routing: one market event -> the right people, each with a 'why you are seeing this'.

    resolve_entities(con, names)  -> [(node_id, confidence)]
    route_event(con, event_ids)   -> {recipient_user_id: task dict}   (nothing is written)

Steps: 1) match event names to graph nodes  2) walk the graph to the affected clients
3) apply every routing rule per recipient  4) merge events that share a cluster key.
"""
import json
import re
from .graph import Graph

SEV = {"Low": 1, "Medium": 2, "High": 3}
SUFFIX = [(r"\bpvt\.?\s*ltd\.?", "private limited"), (r"\bltd\.?", "limited"), (r"\bpvt\.?", "private"), (r"[.,]", "")]


def norm(name):
    s = name.lower().strip()
    for pat, rep in SUFFIX:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()


def resolve_entities(con, names):
    """Exact match on normalised name or legal name = 1.0. Otherwise no match (a real build would add fuzzy)."""
    index = {}
    for nid, name, attrs in con.execute("SELECT id,name,attrs FROM node WHERE node_type IN ('company','bank')"):
        index[norm(name)] = nid
        legal = json.loads(attrs).get("legal_name")
        if legal:
            index[norm(legal)] = nid
    return [(index[norm(n)], 1.0) for n in names if norm(n) in index]


def load_graph(con):
    nodes = {r[0]: dict(type=r[1], name=r[2], group=r[3]) for r in con.execute("SELECT id,node_type,name,client_group_id FROM node")}
    edges = list(con.execute("SELECT from_node,to_node,edge_type,confidence FROM edge"))
    return Graph(nodes, edges)


def route_event(con, event_ids):
    G = load_graph(con)
    rules = {r[0]: dict(zip(("id", "recipient", "task_type", "due", "title", "why", "cond"), r))
             for r in con.execute("SELECT id,recipient,task_type,due_in_hours,title_template,why_template,condition_json FROM routing_rule WHERE active=1 ORDER BY sort_order")}
    for r in rules.values():
        r["cond"] = json.loads(r["cond"])
    needs = [dict(zip(("id", "g", "name", "fam", "spec", "rev", "stage"), r))
             for r in con.execute("SELECT id,client_group_id,name,product_family,specialist_id,reviewer_id,stage FROM need WHERE status='active'")]
    rm = dict(con.execute("SELECT id,rm_id FROM client_group"))
    gname = dict(con.execute("SELECT id,short_name FROM client_group"))
    lead = con.execute("SELECT id FROM app_user WHERE role LIKE '%Team%' OR function='Team' LIMIT 1").fetchone()[0]
    tasks = {}

    def give(user, rule, ev, clients, why, title, extra=None):
        t = tasks.setdefault(user, dict(recipient=user, rules=set(), events=set(), clients=set(), why=[], titles=[], due_h=rule["due"], type=rule["task_type"], needs=[]))
        t["rules"].add(rule["id"]); t["events"].add(ev["id"]); t["clients"].update(clients)
        if why not in t["why"]:
            t["why"].append(why)
        t["titles"].append(title)
        t["due_h"] = min(t["due_h"], rule["due"])
        if extra:
            t["needs"].append(extra)

    for eid in event_ids:
        row = con.execute("SELECT id,event_type,headline,severity,entity_names FROM market_event WHERE id=?", (eid,)).fetchone()
        ev = dict(zip(("id", "type", "headline", "sev", "names"), row))
        starts = resolve_entities(con, json.loads(ev["names"]))
        recs = [r for nid, _ in starts for r in G.impact_walk([nid], max_hops=3)]
        best = {}
        for r in recs:                                   # keep the shortest path per client
            if r["group"] not in best or r["hops"] < best[r["group"]]["hops"]:
                best[r["group"]] = r
        recs = list(best.values())
        for r in recs:
            r["why"] = G.describe(r["path"])
            r["entity_name"] = G.nodes[r["entity"]]["name"]
        sev = SEV[ev["sev"]]

        def ok(rule, r=None):
            c = rule["cond"]
            return (sev >= SEV[c.get("min_severity", "Low")] and ev["type"] in c.get("event_types", [ev["type"]])
                    and (r is None or r["hops"] <= c.get("max_hops", 9)))

        for r in recs:
            g, ent = r["group"], r["entity_name"]
            ctx = dict(entity=ent, clients=gname[g], client=gname[g], path=r["why"], headline=ev["headline"])
            R = rules["RR-01"]
            if ok(R, r) and r["hops"] <= 2:
                give(rm[g], R, ev, [g], R["why"].format(**ctx), R["title"].format(**ctx))
            R = rules["RR-06"]
            if ok(R, r) and r["hops"] == 0:
                give(rm[g], R, ev, [g], R["why"].format(**ctx), R["title"].format(**ctx))
            for n in needs:
                if n["g"] != g:
                    continue
                R = rules["RR-02"]
                c = R["cond"]
                if ok(R, r) and n["fam"] in c["families"] and r["kind"] in ("direct", c["direction"]) :
                    give(n["spec"], R, ev, [g], R["why"].format(need=n["name"], **ctx), R["title"].format(need=n["name"], **ctx), n["id"])
                R = rules["RR-03"]
                if ok(R, r) and n["rev"]:
                    give(n["rev"], R, ev, [g], R["why"].format(**ctx), R["title"].format(**ctx), n["id"])
        R = rules["RR-05"]
        if ok(R) and recs:
            ent = recs[0]["entity_name"]
            ctx = dict(entity=ent, clients=", ".join(gname[r["group"]] for r in recs))
            give("u_miu", R, ev, [r["group"] for r in recs], R["why"].format(**ctx), R["title"].format(**ctx))
        clients = {r["group"] for r in recs}
        rms = {rm[g] for g in clients}
        R = rules["RR-04"]
        if len(clients) >= R["cond"]["min_clients"] and sev >= SEV[R["cond"]["min_severity"]]:
            exp = sum(con.execute("SELECT outstanding_cr FROM client_group WHERE id=?", (g,)).fetchone()[0] for g in clients)
            ctx = dict(entity=recs[0]["entity_name"], clients=", ".join(sorted(gname[g] for g in clients)), n_clients=len(clients), n_rms=len(rms), exposure=f"{exp:,.0f}")
            give(lead, R, ev, clients, R["why"].format(**ctx), R["title"].format(**ctx))

    for t in tasks.values():                              # merge: one task per person
        t["rules"], t["events"], t["clients"] = sorted(t["rules"]), sorted(t["events"]), sorted(t["clients"])
        t["title"] = t["titles"][0] if len(t["titles"]) == 1 else f"{t['titles'][0]} (+{len(t['titles']) - 1} related)"
    return tasks
