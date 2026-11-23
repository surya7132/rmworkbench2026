"""Build data/compass.db from the schema and the seed data.

    python -m seed.build_db                 # fresh database, standard demo password
    python -m seed.build_db --password X    # choose the demo password

Deterministic: the same command always yields the same database.
Only the Python standard library is needed.
"""
import argparse
import hashlib
import json
import os
import random
import re
import secrets
import sqlite3
import sys

from . import ids, financials as fin
from . import world_nodes as WN, world_ops as WO
from .graph import Graph

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "compass.db")
SCHEMA = os.path.join(ROOT, "db", "schema.sql")
MOCKUP = os.path.join(ROOT, "seed", "data", "mockup_seed.json")

LOGIN = {"u_rohan": "rohan.rm", "u_karan": "karan.rm", "u_meera": "meera.lead",
         "u_kavita": "kavita.trade", "u_ananya": "ananya.credit"}
CONNECTOR_LABEL = {"external-filings": "Filings and exchange disclosures", "core-banking": "Account data",
                   "crm": "Meeting note", "compass-model": "Compass model", "news-feed": "News",
                   "mca-registry": "MCA registry", "rating-agencies": "Rating agency", "limits-exposure": "Limits and exposure",
                   "los-credit": "Credit workflow", "documents": "Client documents", "ews-engine": "Early warning engine"}
FACT_REF = {"F-1001": "DT/NCD/VIPL/2026/118", "F-1002": "Charge ID 100593741", "F-1003": "RR/VIPL/2026-27/0412",
            "F-1005": "BSE-ANN-20261102-0457", "F-3002": "EWS-WC-03"}
MEMBER_ROLES = {"Primary borrower", "Promoter entity", "Project SPV", "Parent"}
PROMOTER_TITLES = {"p_dilip": "Chairman and promoter", "p_anil": "Promoter and MD"}


def hash_pw(pw, rng):
    salt = secrets.token_hex(8) if rng is None else "".join(rng.choice("0123456789abcdef") for _ in range(16))
    iters = 120_000
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), iters).hex()
    return f"pbkdf2_sha256${iters}${salt}${h}"


def verify_pw(pw, stored):
    algo, iters, salt, h = stored.split("$")
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(iters)).hex() == h


def j(x):
    return json.dumps(x, ensure_ascii=False)


def legal_name(name, spec):
    if spec.get("display"):
        return spec["display"]
    n = name
    n = re.sub(r"\bPvt Ltd\b", "Private Limited", n)
    n = re.sub(r"\bLtd\b", "Limited", n)
    return n


def rupee_text(s):
    """Seed text uses the rupee sign; keep it. (Only PDFs avoid it, for font reasons.)"""
    return s


def build(db_path=DB_PATH, password="Demo@2026", scale="full"):
    rng = random.Random(20261117)
    S = json.load(open(MOCKUP, encoding="utf-8"))
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(open(SCHEMA, encoding="utf-8").read())
    con.execute("PRAGMA foreign_keys = OFF")      # bulk load; foreign_key_check runs at the end
    ex = con.execute

    # ------------------------------------------------------------ app_user
    n = 104300
    for u in S["users"]:
        n += 17
        first, *rest = u["name"].lower().replace(".", "").split()
        email = f"{first}.{rest[-1] if rest else 'desk'}@compass-demo.example"
        un = LOGIN.get(u["id"])
        ex("INSERT INTO app_user VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           (u["id"], f"RBL{n}", u["name"], email, u["role"], u["fn"], u["ini"], un,
            hash_pw(password, rng) if un else None, 1 if un else 0,
            "u_meera" if u["fn"] == "RM" and u["id"] != "u_meera" else None))

    # ------------------------------------------------------------ groups (+ facilities first, for totals)
    facilities = []
    for f in S["facilities"]:
        ftype = {"Term loans": "Term Loan", "Bank guarantees": "Bank Guarantee",
                 "Packing credit": "Packing Credit in Foreign Currency (PCFC)",
                 "Trade finance": "Trade Finance Line (LC, BG, bill discounting)"}.get(f["type"], f["type"])
        facilities.append(dict(id=f["id"], g=f["group"], type=ftype, s=f["sanctioned"], o=f["outstanding"], mat=f["maturity"],
                               pricing=f["pricing"], sec=f["security"], cov=f["coverage"], cvn=f["covenants"], auth=f["authority"],
                               rev=f["review"], status=f["status"]))
    gmap = {g["id"]: g for g in S["groups"]}
    for gid, rows in WN.EXTRA_FACILITIES.items():
        for i, (t, s_, o_, pr, sec, cvn, auth, yr) in enumerate(rows, 1):
            facilities.append(dict(id=f"fa_{gid[2:5]}{i}", g=gid, type=t, s=s_, o=o_, mat=f"{yr}-03-31" if yr else None,
                                   pricing=pr, sec=sec, cov="n/a", cvn=cvn, auth=auth, rev=gmap[gid]["reviewDue"], status="Standard"))
    tot = {}
    for f in facilities:
        a = tot.setdefault(f["g"], [0, 0]); a[0] += f["s"]; a[1] += f["o"]
    primary = {p["group"]: p["id"] for p in S["parties"] if p["role"] == "Primary borrower"}
    primary.update({n_[3]: n_[0] for n_ in WN.NEW_NODES if n_[2] == "Primary borrower"})
    for g in S["groups"]:
        assert tot[g["id"]] == [g["sanctioned"], g["utilised"]], (g["id"], tot[g["id"]])
        ex("INSERT INTO client_group VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (g["id"], g["name"], g["short"], primary[g["id"]], g["segment"], g["sector"], g["tier"], g["rm"], g["since"],
            g["sanctioned"], g["utilised"], g["deposits"], WN.INTERNAL_GRADE[g["rating"]],
            f"{WN.AGENCY[g['id']]} {g['rating']}/{WN.OUTLOOK[g['trend']]}", g["trend"], g["watch"], g["cadence"],
            g["lastContact"], g["reviewDue"], g["flows"], 1 if g.get("seeded") else 0))
    for f in facilities:
        ex("INSERT INTO facility VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (f["id"], f["g"], f["type"], f"XXXXXX{rng.randint(1000, 9999)}", f["s"], f["o"], f["mat"], f["pricing"],
            f["sec"], f["cov"], f["cvn"], f["auth"], f["rev"], f["status"]))

    # ------------------------------------------------------------ nodes
    nodes = {}

    def add_node(nid, ntype, name, gid, attrs):
        assert nid not in nodes, nid
        nodes[nid] = dict(type=ntype, name=name, group=gid)
        ex("INSERT INTO node VALUES (?,?,?,?,?)", (nid, ntype, name, gid, j(attrs)))

    for u in S["users"]:
        add_node(u["id"], "rbl_user", u["name"], None, {"user_id": u["id"], "role": u["role"], "function": u["fn"]})
    for g in S["groups"]:
        add_node(g["id"], "client_group", g["name"], g["id"], {"segment": g["segment"], "tier": g["tier"], "sector": g["sector"]})
    for sid, sname in WN.SECTORS:
        add_node(sid, "sector", sname, None, {})
    for pid, pname in WN.PRODUCT_FAMILIES:
        add_node(pid, "product_family", pname, None, {})
    stake = {s["id"]: s for s in S["stakeholders"]}

    def company_attrs(nid, name, role):
        spec = WN.COMPANIES.get(nid, {})
        kind = spec.get("kind")
        a = {"role": role}
        if kind in ("listed", "private"):
            a.update(entity_kind="Listed company" if kind == "listed" else "Private limited company", legal_name=legal_name(name, spec),
                     cin=ids.make_cin(rng, kind == "listed", spec["nic"], spec["st"], spec["yr"]), pan=ids.make_pan(rng, name, "C"),
                     nic_code=spec["nic"], incorporated=spec["yr"], registered_office=f"{spec['city']}, {spec['state']}", status="Active")
            if role in ("Primary borrower", "Promoter entity", "Project SPV") or kind == "listed":
                a["lei"] = ids.make_lei(rng)
        elif kind == "firm":
            a.update(entity_kind="Partnership or proprietorship", pan=ids.make_pan(rng, name, "F"), registered_office=f"{spec['city']}, {spec['state']}")
        elif kind == "govt":
            a.update(entity_kind="State government authority", registered_office=f"{spec['city']}, {spec['state']}")
        elif kind == "foreign":
            a.update(entity_kind="Foreign or multinational entity", country=spec["country"], note=spec.get("note"))
        elif kind == "lender":
            a.update(entity_kind="Lender", note=spec.get("note", "Other lenders to the client"))
        if role not in MEMBER_ROLES:
            a["relationship"] = "counterparty"
        return a

    def person_attrs(nid, role):
        a = {"role": role}
        if nid in WN.DIN_PERSONS:
            a["din"] = ids.make_din(rng)
        st = stake.get(nid)
        if st:
            a["stakeholder"] = {k: st[k] for k in ("strength", "rights", "influence", "channel", "priorities", "objection", "last", "knows", "owner") if k in st}
        return a

    for p in S["parties"]:
        if p["type"] == "person":
            add_node(p["id"], "person", p["name"], p["group"], person_attrs(p["id"], p["role"]))
        else:
            add_node(p["id"], "bank" if p["type"] == "bank" else "company", p["name"], p["group"], company_attrs(p["id"], p["name"], p["role"]))
    for nid, name, role, gid, kind, _sec in WN.NEW_NODES:
        if kind == "person":
            add_node(nid, "person", name, gid, person_attrs(nid, role))
        else:
            add_node(nid, kind, name, gid, company_attrs(nid, name, role))
    for nid, name, role, gid in WO.EXTRA_PEOPLE:
        add_node(nid, "person", name, gid, person_attrs(nid, role))

    # ------------------------------------------------------------ needs (also nodes)
    users = {u["id"]: u for u in S["users"]}
    opps = list(S["opps"])
    opps.append(dict(id="opp_v3", group="g_vantage", name="Escrow and collections account for highway receipts",
                     product="Escrow and collections", family="Cash management", stage="Signal", stakeholder="p_rajiv", specialist="u_neha",
                     origin="Signal: payment flows (F-1015)", need="The State Highway Authority paid Rs 96 cr through RBL in 12 months and the new Rs 520 cr contract will route receipts through an escrow account. RBL has no transaction-banking mandate yet.",
                     needStatus="Hypothesis", timeline="Before the first payment under the new contract (estimated first quarter of 2027)",
                     provider="Consortium lenders hold escrow on existing projects", facts=["F-1015", "F-1005", "F-1007"], deal=None, status="active",
                     range=dict(lo=0.88, hi=1.76, text="Rs 40-80 cr average balances x 2.2% spread over cost of funds", metric="Net interest income a year"),
                     feas=[["Limit headroom", "Not applicable: deposit and fee product", "int"],
                           ["Competitor position", "Consortium lenders already hold escrow on earlier projects", "ext"]],
                     nba=dict(action="Ask the CFO who will hold the escrow account for the new contract", why="Payments under the contract will start within a quarter and the account is not yet chosen.",
                              evidence=["F-1015", "F-1005"], owner="u_rohan", due="2026-11-26")))
    facts_by = {f["id"]: f for f in S["facts"]}
    deals = {d["id"]: d for d in S["deals"]}
    for o in opps:
        reviewer = deals[o["deal"]]["reviewer"] if o.get("deal") else None
        canvas = j(deals[o["deal"]]) if o.get("deal") else None
        tdec = deals[o["deal"]]["targetDecision"] if o.get("deal") else None
        labels = []
        for fid in o["facts"]:
            if fid in facts_by:
                lab = CONNECTOR_LABEL.get(facts_by[fid]["connector"], facts_by[fid]["connector"])
                if lab not in labels and lab != "Compass model":
                    labels.append(lab)
        r = o.get("range") or {}
        add_node(o["id"], "need", o["name"], o["group"], {"product": o["product"], "family": o["family"], "stage": o["stage"]})
        ex("INSERT INTO need VALUES (" + ",".join("?" * 24) + ")",
           (o["id"], o["group"], o["id"], o["name"], o["product"], o["family"], o["stage"], o["needStatus"], o["stakeholder"],
            o["specialist"], reviewer, o["origin"], "; ".join(labels) or "Meeting note", o["need"], o.get("timeline"), o.get("provider"),
            r.get("lo"), r.get("hi"), (r.get("text", "") + (" (" + r["metric"] + ")" if r.get("metric") else "")) or None,
            j(o["facts"]), j(dict(nba=o.get("nba"), feasibility=o.get("feas"))), canvas, tdec, o.get("status", "active")))
    # ------------------------------------------------------------ facts
    def fact_row(fid, g, node, stmt, label, share, src, sdate, conn, match, val=None, unit=None, eff=None, sup=None, ref=None):
        ex("INSERT INTO fact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (fid, g, node, stmt, val, unit, src, ref or FACT_REF.get(fid), sdate, eff, label, share, match, sup, conn))

    for f in S["facts"]:
        fact_row(f["id"], f["group"], f["entity"], f["statement"], f["label"], f["share"], f["source"], f["date"], f["connector"],
                 f["match"], eff=f["eff"], sup=f["sup"])
    for m in S["miu"]:
        fact_row("F-10" + str(15 + int(m["id"][1:])), "g_vantage", "e_vip" if m["id"] == "M1" else "p_dilip",
                 f"MIU finding {m['id']}: {m['finding']}", "miu", "internal", "MIU report", m["date"], "miu-reports", m["match"],
                 ref=f"MIU/{m['id']}/VIPL/2026")
    for t in WN.EXTRA_FACTS:
        fact_row(t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9], val=t[10], unit=t[11])
    for k, (gid, rows) in enumerate(WN.EXTRA_FACILITIES.items(), 1):
        s_, o_ = tot[gid]
        fact_row(f"F-60{k:02d}", gid, primary[gid], f"Group limit Rs {s_} cr; utilised Rs {o_} cr; headroom Rs {s_ - o_} cr",
                 "int", "discuss", "Limits and exposure system", "2026-11-15", "limits-exposure", 1.0, val=s_ - o_, unit="INR crore")

    # ------------------------------------------------------------ edges
    edge_seen = set()

    def add_edge(a, b, ty, attrs=None, fact=None, conf=1.0):
        assert a in nodes and b in nodes, (a, b, ty)
        if (a, b, ty) in edge_seen:
            return
        edge_seen.add((a, b, ty))
        ex("INSERT INTO edge (from_node,to_node,edge_type,attrs,source_fact_id,confidence,valid_from) VALUES (?,?,?,?,?,?,?)",
           (a, b, ty, j(attrs or {}), fact, conf, None))

    LINKFACT = {("e_steel", "e_vip"): ("F-1013", 0.93), ("e_ridge", "e_vip"): ("F-1014", 0.88), ("e_vip", "e_sha"): ("F-1015", 1.0),
                ("e_coastal", "e_mer"): ("F-2006", 0.90), ("e_dyeing", "e_mer"): ("F-2006", 0.90),
                ("e_weave", "e_mer"): ("F-2006", 0.90), ("e_sunrise", "e_mer"): ("F-2006", 0.90), ("e_nord", "e_oem"): ("F-3003", 1.0)}
    for l in S["links"]:
        a, b, t = l["from"], l["to"], l["type"]
        if t.startswith("owns"):
            m = re.search(r"(\d+)%", t)
            add_edge(a, b, "owns", {"pct": int(m.group(1))} if m else {}, conf=1.0)
        elif t == "directs":
            add_edge(a, b, "director_of", {"role": "Chairman"})
        elif t == "MD of":
            add_edge(a, b, "director_of", {"role": "Managing Director"})
        elif t in ("CFO of", "Head of Projects at", "Finance Manager of", "Finance Controller of"):
            add_edge(a, b, "employed_by", {"role": t.rsplit(" ", 1)[0] if t.endswith(" of") else t[:-3]})
        elif t == "buys from":
            fid, c = LINKFACT.get((b, a), (None, 0.95))
            add_edge(b, a, "supplies_to", {}, fid, c)
        elif t == "lends to":
            add_edge(a, b, "lends_to", {"note": "consortium lenders"})
        elif t == "treasury of":
            add_edge(a, b, "treasury_of", {})
        else:
            raise ValueError(t)
    for a, b, ty, at, fid, c in WN.EXTRA_EDGES:
        add_edge(a, b, ty, at, fid, c)
    role_of = {p["id"]: p["role"] for p in S["parties"]}
    role_of.update({n_[0]: n_[2] for n_ in WN.NEW_NODES})
    for nid, nd in nodes.items():
        if nd["type"] == "company" and role_of.get(nid) in MEMBER_ROLES:
            add_edge(nid, nd["group"], "member_of", {"role": role_of[nid]})
    for gid, pn in primary.items():
        add_edge(gid, pn, "has_primary")
        add_edge(gid, gmap[gid]["rm"], "managed_by")
    for nid, sec in WN.SECTOR_OF_NODE.items():
        add_edge(nid, sec, "operates_in")
    for gid, pn in primary.items():
        add_edge(pn, WN.SECTOR_OF_GROUP[gid], "operates_in")
    for pid, cid in WN.PROMOTER_OF.items():
        add_edge(pid, cid, "director_of", {"role": role_of[pid]})
    for nid, _n, role, gid in WO.EXTRA_PEOPLE:
        add_edge(nid, primary[gid], "employed_by", {"role": role})
    for o in opps:
        add_edge(o["group"], o["id"], "has_need")
        add_edge(o["id"], WN.FAMILY_NODE[o["family"]], "in_family")
        add_edge(o["id"], o["specialist"], "handled_by", {"role": "Specialist"})
        add_edge(o["stakeholder"], o["id"], "stakeholder_for")
        if o.get("deal"):
            add_edge(o["id"], deals[o["deal"]]["reviewer"], "reviewed_by", {"role": "Credit reviewer"})

    # ------------------------------------------------------------ meetings
    EXTRA_KEYS = ("agenda", "questions", "brief", "prep_items", "nba", "pending")
    for e in S["eng"] + WO.EXTRA_MEETINGS:
        m = re.search(r"(\d+)\s*minutes", e.get("where", ""))
        dur = e.get("dur") or (int(m.group(1)) if m else 60)
        extra = {k: e[k] for k in e if k not in ("id", "group", "type", "title", "date", "where", "parts", "status", "prep", "objective",
                                                  "success", "outcome", "logged", "source", "opp", "dur", "detected")}
        ex("INSERT INTO meeting VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (e["id"], e["group"], e["type"], e["title"], e["date"], dur, e.get("where"), j(e.get("parts", [])), e["status"],
            e.get("prep"), e.get("objective"), e.get("success"), j(extra) if extra else None, e.get("outcome"), e["source"],
            1 if e.get("logged", True) else 0, e.get("opp")))

    # ------------------------------------------------------------ work items and threads
    for w in S["work"] + WO.EXTRA_WORK:
        ex("INSERT INTO work_item VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (w["id"], w["title"], w["type"], w["group"], w.get("caseId"), w["owner"], w["requester"], w["created"], w["due"],
            w.get("clientDeadline"), w.get("consequence"), w["state"], w.get("completion"), j(w.get("dependsOn", [])), w.get("esc", 0),
            w["vis"], w.get("sla"), w.get("from"), None, None, w.get("v", 1)))
        for t in w.get("thread", []):
            ex("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)", (w["id"], t["t"], t["by"], "message", t["text"]))
        for t in w.get("hist", []):
            kind = "ladder" if "ladder" in t["text"].lower() else "system"
            ex("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)",
               (w["id"], t["t"], "u_rohan" if t["by"] == "system" and w["owner"] == "u_rohan" else (w["requester"] if t["by"] == "system" else t["by"]), kind, t["text"]))

    # ------------------------------------------------------------ documents and spreads
    docs = [("D-VIP-FY26", "g_vantage", "Annual report FY2025-26 (extract, pages 82-86, 97, 112)", "Annual report", "FY2025-26", "2026-03-31", "Consolidated",
             "INR crore", "Client upload", "data/sample_docs/vantage_infra_ar_fy2025-26_extract.pdf", 7, "Spread in progress", "2026-11-12T16:20:00+05:30"),
            ("D-VIP-FY25", "g_vantage", "Annual report FY2024-25", "Annual report", "FY2024-25", "2025-03-31", "Consolidated",
             "INR crore", "Client upload", None, None, "Received (prior year, not uploaded)", "2025-09-02T11:00:00+05:30"),
            ("D-VIP-RR", "g_vantage", "CRISIL rating rationale, October 2026", "Rating rationale", "FY2026-27", None, None, None, "Rating agency", None, None, "Received", "2026-10-27T12:00:00+05:30"),
            ("D-VIP-CHG", "g_vantage", "MCA charge filing CHG-1, ID 100593741", "Regulatory filing", "FY2026-27", None, None, None, "MCA registry", None, None, "Received", "2026-10-28T14:30:00+05:30"),
            ("D-MER-FY26", "g_meridian", "Annual report FY2025-26 (extract, pages 58-62, 71, 84)", "Annual report", "FY2025-26", "2026-03-31", "Standalone",
             "INR crore", "Client upload", "data/sample_docs/meridian_fabrics_ar_fy2025-26_extract.pdf", 7, "Spread in progress", "2026-11-10T10:45:00+05:30"),
            ("D-NOR-SS", "g_nordholm", "Stock statement, September 2026", "Stock statement", "FY2026-27", "2026-09-30", None, "INR crore", "Client upload", None, None, "Received", "2026-10-19T09:30:00+05:30"),
            ("D-HEL-SS", "g_helix", "Stock statement, September 2026", "Stock statement", "FY2026-27", "2026-09-30", None, "INR crore", "Client upload", None, None, "Received", "2026-10-14T15:10:00+05:30"),
            ("D-GRA-SS", "g_granite", "Stock statement, September 2026", "Stock statement", "FY2026-27", "2026-09-30", None, "INR crore", "Client upload", None, None, "Received", "2026-10-09T12:05:00+05:30")]
    for d in docs:
        ex("INSERT INTO document (id,client_group_id,name,doc_type,fiscal_year,period_end,basis,unit,source,storage_path,page_count,status,uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", d)

    def add_spread(doc_id, lines, errors=None, refs=None, conf_map=None, default_conf=97):
        errors, refs, conf_map = errors or {}, refs or {}, conf_map or {}
        for code, label, stmt, c26, c25, c24, page, pdf in lines:
            ext, conf, _ = errors.get(code, (c26, conf_map.get(code, default_conf), ""))
            ref = refs.get(code, (None, None, None))
            ex("INSERT INTO spread_line (document_id,line_code,label,statement,fy_current,fy_prior1,fy_prior2,printed_current,page_ref,pdf_page,confidence,status,note_ref_label,note_ref_value,note_ref_page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (doc_id, code, label, stmt, ext, c25, c24, c26, page, pdf, conf, "extracted", *ref))
    v = fin.vantage()
    # Vantage is read from its PDF for real (text file). The third year is not in the report, so it comes from the fixtures.
    from app.features.spreading import extract as X
    vlines, vmissing = X.extract(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_docs", "vantage_infra_ar_fy2025-26_extract.pdf"))
    assert not vmissing, f"Vantage PDF: lines not found {vmissing}"
    prior2 = {x[0]: x[5] for x in v["lines"]}
    for l in vlines:
        ex("INSERT INTO spread_line (document_id,line_code,label,statement,fy_current,fy_prior1,fy_prior2,printed_current,page_ref,pdf_page,confidence,status,note_ref_label,note_ref_value,note_ref_page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           ("D-VIP-FY26", l["line_code"], l["label"], l["statement"], l["fy_current"], l["fy_prior1"], prior2[l["line_code"]], l["printed_current"], l["page_ref"], l["pdf_page"],
            l["confidence"], "extracted", l["note_ref_label"], l["note_ref_value"], l["note_ref_page"]))
    m = fin.meridian()
    add_spread("D-MER-FY26", m["lines"], None, {"L05": ("Note 13 borrowings", 70.00, "p. 71")}, {"L13": 93, "L06": 95, "L09": 96}, 98)

    # ------------------------------------------------------------ alerts
    alerts = list(S["alerts"]) + WO.EXTRA_ALERTS
    for a in alerts:
        code, sma = WO.ALERT_CODES.get(a["id"], (a.get("ews"), a.get("sma")))
        ex("INSERT INTO alert VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (a["id"], a["group"], a["title"], a["category"], code, sma, a["source"], a["detected"], a["severity"], a["exposure"],
            1 if a.get("blocksCredit") else 0, 1 if a.get("covenant") else 0, a.get("reviewDays"), "New", a.get("context"),
            a.get("required"), WO.ALERT_DEDUPE.get(a["id"]), WO.ALERT_EVENT.get(a["id"]), j(a.get("facts", [])), None, None, None))

    # ------------------------------------------------------------ market events and impacts of processed ones
    edges = [(r[0], r[1], r[2], r[3]) for r in con.execute("SELECT from_node,to_node,edge_type,confidence FROM edge")]
    G = Graph(nodes, edges)
    sev_down = {"High": "Medium", "Medium": "Low", "Low": "Low"}
    for e in WO.EVENTS:
        eid, typ, head, summ, src, ref, pub, sev, sector, raw, resolved, cluster, status, hero = e
        ex("INSERT INTO market_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (eid, typ, head, summ, src, ref, pub, sev, sector, j(raw), cluster, status, pub if status == "processed" else None, hero))
        if status == "processed":
            for nid, conf in resolved:
                for rec in G.impact_walk([nid], max_hops=2):
                    ex("INSERT INTO event_impact (event_id,node_id,client_group_id,hops,path,reason,impact_level,match_confidence) VALUES (?,?,?,?,?,?,?,?)",
                       (eid, nid, rec["group"], rec["hops"], j([dict(node=p[0], edge=p[1], dir=p[2]) for p in rec["path"]]),
                        G.describe(rec["path"]), sev if rec["hops"] == 0 else sev_down[sev], round(rec["conf"] * conf, 3)))

    # ------------------------------------------------------------ routing rules
    for r in WO.ROUTING_RULES:
        rid, so, name, applies, cond, recip, ttype, due_h, tt, wt = r
        ex("INSERT INTO routing_rule VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (rid, so, name, applies, j(cond), recip, ttype, due_h, tt, wt, "recipient", 1))

    # ------------------------------------------------------------ audit history and meta
    for i, (uid, at, act, summ, aff) in enumerate(WO.AUDIT_SEED, 1):
        ex("INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?)", (f"TXN-{i:06d}", at, uid, act, summ, None, None, j(aff)))
    meta = {"demo_now": WO.DEMO_NOW, "currency": "INR crore", "schema_version": "1.0", "data_notice": "All data is synthetic. No real client, person or company.",
            "build_seed": "20261117", "audit_next": str(len(WO.AUDIT_SEED) + 1)}
    for k, val in meta.items():
        ex("INSERT INTO app_meta VALUES (?,?)", (k, val))

    if scale != "base":                                   # realistic-size book (seed/expand.py)
        from . import expand
        expand.run(con, scale)
    from . import realworld                              # real, dated, linkable news (seed/realworld.py)
    realworld.run(con)
    con.commit()
    bad = con.execute("PRAGMA foreign_key_check").fetchall()
    if bad:
        raise SystemExit(f"Foreign key violations: {bad[:10]}")
    con.execute("PRAGMA foreign_keys = ON")
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1")}
    con.close()
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--password", default="Demo@2026")
    ap.add_argument("--scale", choices=["base", "lite", "full"], default="full",
                    help="base = hand-made data only; lite = about 30 more groups; full = about 120 more groups")
    a = ap.parse_args(argv)
    counts = build(a.db, a.password, a.scale)
    print(f"Built {a.db}")
    for t, c in counts.items():
        print(f"  {t:<14}{c:>6}")


if __name__ == "__main__":
    main()
