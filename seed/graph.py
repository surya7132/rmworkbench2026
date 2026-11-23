"""Small graph helpers used by the seed (and reusable by the app engine later).

An event names one or more entities (nodes). `impact_walk` follows supply-chain
and ownership lines outward from those entities, up to a few company hops,
then steps from a company to its client group. Each result carries the full
path so the UI can show "why you are seeing this".
"""
from collections import deque

# company-to-company lines that carry business impact, and how to describe them
IMPACT_EDGES = {"supplies_to", "transports_for", "owns", "lends_to"}
PHRASE = {
    ("supplies_to", "fwd"): "supplies",
    ("supplies_to", "rev"): "buys from",
    ("transports_for", "fwd"): "carries freight for",
    ("transports_for", "rev"): "uses freight from",
    ("owns", "fwd"): "owns",
    ("owns", "rev"): "is owned by",
    ("lends_to", "fwd"): "lends to",
    ("lends_to", "rev"): "borrows from",
    ("member_of", "fwd"): "is part of",
    ("has_need", "fwd"): "has need",
    ("handled_by", "fwd"): "is handled by",
    ("reviewed_by", "fwd"): "is reviewed by",
    ("operates_in", "fwd"): "operates in",
    ("operates_in", "rev"): "includes",
    ("managed_by", "fwd"): "is managed by",
}


class Graph:
    def __init__(self, nodes, edges):
        """nodes: {id: dict(type, name, group)}; edges: [(from, to, type, confidence)]"""
        self.nodes = nodes
        self.out, self.inc = {}, {}
        for f, t, ty, conf in edges:
            self.out.setdefault(f, []).append((t, ty, conf))
            self.inc.setdefault(t, []).append((f, ty, conf))

    def neighbours(self, nid, types):
        for t, ty, conf in self.out.get(nid, []):
            if ty in types:
                yield t, ty, "fwd", conf
        for f, ty, conf in self.inc.get(nid, []):
            if ty in types:
                yield f, ty, "rev", conf

    def step(self, nid, ty):
        return [(t, c) for t, y, c in self.out.get(nid, []) if y == ty]

    def impact_walk(self, start_ids, max_hops=2):
        """Return one record per reached client group (shortest path wins).

        Two separate runs, never mixed (a supplier's trouble does not reach the
        customer's *other* suppliers):
          downstream: follow lines forward  (supplier -> customer: supply disruption)
          upstream:   follow lines backward (customer -> supplier: payment risk)
        A hop is one company-to-company line. A company reaches its client group
        through a member_of line (own entities only, not counterparties).
        """
        found = {}
        for sid in start_ids:
            seeds = [(sid, [(sid, None, None)])]
            if self.nodes[sid]["type"] == "sector":      # a sector event touches the companies in it
                seeds = [(f, [(sid, None, None), (f, "operates_in", "rev")])
                         for f, ty, _ in self.inc.get(sid, []) if ty == "operates_in"]
            for seed, base in seeds:
                for kind in ("downstream", "upstream"):
                    q = deque([(seed, base, 0, 1.0)])
                    seen = {seed}
                    while q:
                        nid, path, hops, conf = q.popleft()
                        if self.nodes[nid]["type"] == "company":
                            for gid, c in self.step(nid, "member_of"):
                                rec = dict(group=gid, entity=seed, hops=hops, kind=kind if hops else "direct",
                                           conf=round(conf * c, 3), path=path + [(gid, "member_of", "fwd")])
                                if gid not in found or hops < found[gid]["hops"]:
                                    found[gid] = rec
                        if hops >= max_hops:
                            continue
                        nxt = self.out.get(nid, []) if kind == "downstream" else self.inc.get(nid, [])
                        for other, ty, c in nxt:
                            if ty not in IMPACT_EDGES or other in seen or self.nodes[other]["type"] != "company":
                                continue
                            seen.add(other)
                            d = "fwd" if kind == "downstream" else "rev"
                            q.append((other, path + [(other, ty, d)], hops + 1, conf * c))
        return list(found.values())

    def describe(self, path):
        """Human text for a path: 'Steelco Suppliers supplies Vantage Infra Projects, is part of Vantage Infra Group'."""
        bits = []
        for i in range(1, len(path)):
            a = self.nodes[path[i - 1][0]]["name"]
            b = self.nodes[path[i][0]]["name"]
            ty, d = path[i][1], path[i][2]
            bits.append(f"{a} {PHRASE.get((ty, d), ty)} {b}")
        return "; ".join(bits)
