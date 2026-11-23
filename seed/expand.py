"""Expand the demo into a realistically sized book of business.

Called from build_db.build() after the hand-made seed is loaded.  Adds, on top
of the 12 hand-made clients and 12 staff:

    6 more RMs, ~120 client groups (large / mid / SME), their companies and
    people, ~65 shared counterparties (suppliers, customers, lenders, buyers),
    facilities that add up to each group's limit, facts with sources,
    needs, meetings, work items, alerts, documents, ~70 processed market
    events (with their graph impacts and the tasks they created) and an
    audit trail.

Rules that keep it honest
  * Own random generator, so the hand-made rows never change.
  * Nothing generated touches Steelco or Western Mercantile Bank, so the
    hero story still reaches exactly the same six people.
  * Every number that appears in two places (limit totals, rating text,
    meeting note vs fact vs need) comes from one variable.
  * Only the Python standard library is used.
"""
import datetime as dt
import zlib
import json
import random
import re

from . import ids
from . import world_ops as WO
from .routing import route_event, load_graph

NOW = dt.datetime.fromisoformat(WO.DEMO_NOW).replace(tzinfo=None)
REPO = 5.50                       # RBI policy repo rate after the 7 Oct 2026 MPC decision (real)
RLLR = REPO + 3.20                # illustrative repo-linked lending rate = 8.70 per cent (the 3.20 spread is our assumption)
USD_CR = 9.7                      # Rs crore per USD million at about Rs 96.8 per dollar (rupee near 97 in Oct 2026, real)

# ------------------------------------------------------------------ helpers
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30"
day = lambda t: t.strftime("%Y-%m-%d")
slug = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
j = lambda x: json.dumps(x, ensure_ascii=False)


def rs(x):
    return f"Rs {x:,.0f} cr" if x >= 100 else f"Rs {x:,.1f} cr"


def roundto(x, step):
    return round(x / step) * step


def biz(t):
    while t.weekday() >= 5:
        t += dt.timedelta(days=1)
    return t


def at_hour(t, rng):
    return biz(t).replace(hour=rng.randint(10, 17), minute=rng.choice([0, 15, 30, 45]), second=0, microsecond=0)


def month_end(t):
    nxt = (t.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return nxt - dt.timedelta(days=1)


# ------------------------------------------------------------------ reference data
NEW_RMS = [("u_divya", "Divya Nair", "DN"), ("u_imran", "Imran Sheikh", "IS"), ("u_neelam", "Neelam Chopra", "NC"),
           ("u_vikram", "Vikram Bhatia", "VB"), ("u_pooja", "Pooja Reddy", "PR"), ("u_sanjay", "Sanjay Patil", "SP")]
QUOTA = {"u_rohan": 28, "u_karan": 26, "u_divya": 11, "u_imran": 11, "u_neelam": 11, "u_vikram": 11, "u_pooja": 11, "u_sanjay": 11}

NEW_SECTORS = [("s_it", "IT and business services"), ("s_power", "Power and renewables"),
               ("s_health", "Healthcare"), ("s_agri", "Agri and commodities")]

# sector id -> name words (long, short), NIC codes, cities, exports?, supplier sectors, customer sectors, weight
SEC = {
    "s_infra":     dict(w=[("Infra Projects", "Infra"), ("Constructions", "Constructions"), ("Highways", "Highways"), ("Engineering and Construction", "Engineering")],
                        nic=["42101", "42204", "41001"], city="west", exp=False, sup=["s_steel", "s_cement", "s_logistics"], cust=["govt", "s_realty"], wt=9),
    "s_textile":   dict(w=[("Textiles", "Textiles"), ("Spinning Mills", "Spinning"), ("Apparels", "Apparels"), ("Fabrics", "Fabrics")],
                        nic=["13111", "13121", "14101"], city="tex", exp=True, sup=["s_agri", "s_chemicals", "s_logistics"], cust=["s_textile", "foreign"], wt=9),
    "s_auto":      dict(w=[("Auto Components", "Auto"), ("Forgings", "Forgings"), ("Castings", "Castings"), ("Precision Components", "Precision")],
                        nic=["29301", "29302", "25910"], city="auto", exp=True, sup=["s_steel", "s_chemicals", "s_packaging"], cust=["s_auto", "foreign"], wt=9),
    "s_shipping":  dict(w=[("Shipping", "Shipping"), ("Marine Services", "Marine"), ("Offshore", "Offshore")],
                        nic=["50111", "50120"], city="port", exp=False, sup=["s_steel", "s_power"], cust=["s_steel", "s_agri", "s_chemicals"], wt=3),
    "s_pharma":    dict(w=[("Pharma", "Pharma"), ("Lifesciences", "Lifesciences"), ("Laboratories", "Labs"), ("Formulations", "Formulations")],
                        nic=["21001", "21002"], city="pharma", exp=True, sup=["s_chemicals", "s_packaging"], cust=["s_health", "foreign"], wt=8),
    "s_food":      dict(w=[("Foods", "Foods"), ("Dairy", "Dairy"), ("Agro Products", "Agro"), ("Beverages", "Beverages")],
                        nic=["10501", "10611", "10750"], city="west", exp=False, sup=["s_agri", "s_packaging", "s_logistics"], cust=["s_logistics", "s_food"], wt=8),
    "s_realty":    dict(w=[("Realty", "Realty"), ("Developers", "Developers"), ("Housing", "Housing"), ("Properties", "Properties")],
                        nic=["68100", "41001"], city="metro", exp=False, sup=["s_cement", "s_steel", "s_infra"], cust=["s_health", "s_it"], wt=6),
    "s_cement":    dict(w=[("Cement", "Cement"), ("Building Materials", "Materials"), ("Concrete Products", "Concrete")],
                        nic=["23941", "23959"], city="inland", exp=False, sup=["s_power", "s_logistics", "s_chemicals"], cust=["s_infra", "s_realty"], wt=4),
    "s_packaging": dict(w=[("Packaging", "Packaging"), ("Containers", "Containers"), ("Polymers", "Polymers")],
                        nic=["17021", "17024", "22203"], city="west", exp=False, sup=["s_chemicals", "s_power"], cust=["s_food", "s_pharma", "s_chemicals"], wt=6),
    "s_chemicals": dict(w=[("Chemicals", "Chemicals"), ("Specialty Chemicals", "Specialty"), ("Dyes and Intermediates", "Dyes"), ("Agrochem", "Agrochem")],
                        nic=["20119", "20211", "20231"], city="chem", exp=True, sup=["s_chemicals", "s_power", "s_logistics"], cust=["s_textile", "s_pharma", "foreign"], wt=8),
    "s_logistics": dict(w=[("Logistics", "Logistics"), ("Transport", "Transport"), ("Cold Chain", "Cold Chain"), ("Warehousing", "Warehousing")],
                        nic=["49231", "52101", "52109"], city="metro", exp=False, sup=["s_auto", "s_power"], cust=["s_auto", "s_steel", "s_food"], wt=6),
    "s_steel":     dict(w=[("Steel", "Steel"), ("Metals", "Metals"), ("Alloys", "Alloys"), ("Wires and Tubes", "Tubes")],
                        nic=["24105", "24201", "25911"], city="inland", exp=True, sup=["s_power", "s_logistics"], cust=["s_infra", "s_auto", "s_realty"], wt=5),
    "s_it":        dict(w=[("Technologies", "Tech"), ("Software", "Software"), ("Business Services", "Services"), ("Digital", "Digital")],
                        nic=["62011", "62020", "63111"], city="tech", exp=True, sup=["s_it", "s_power"], cust=["foreign", "s_health"], wt=4),
    "s_power":     dict(w=[("Power", "Power"), ("Renewables", "Renewables"), ("Solar Energy", "Solar"), ("Wind Energy", "Wind")],
                        nic=["35105", "35106"], city="inland", exp=False, sup=["s_infra", "s_steel", "s_it"], cust=["govt", "s_steel", "s_cement"], wt=4),
    "s_health":    dict(w=[("Hospitals", "Hospitals"), ("Healthcare", "Healthcare"), ("Diagnostics", "Diagnostics")],
                        nic=["86100", "86909"], city="metro", exp=False, sup=["s_pharma", "s_it"], cust=["govt"], wt=3),
    "s_agri":      dict(w=[("Agri Commodities", "Agri"), ("Edible Oils", "Oils"), ("Rice Mills", "Rice"), ("Sugar", "Sugar")],
                        nic=["10401", "10611", "46201"], city="inland", exp=True, sup=["s_logistics", "s_packaging", "s_chemicals"], cust=["s_food", "foreign", "s_textile"], wt=5),
}
CITIES = {  # name, state, CIN code, region
    "Mumbai": ("Maharashtra", "MH", "west"), "Pune": ("Maharashtra", "MH", "west"), "Nashik": ("Maharashtra", "MH", "west"),
    "Nagpur": ("Maharashtra", "MH", "west"), "Thane": ("Maharashtra", "MH", "west"), "Ahmedabad": ("Gujarat", "GJ", "west"),
    "Surat": ("Gujarat", "GJ", "west"), "Vadodara": ("Gujarat", "GJ", "west"), "Rajkot": ("Gujarat", "GJ", "west"),
    "Bengaluru": ("Karnataka", "KA", "south"), "Hubballi": ("Karnataka", "KA", "south"), "Chennai": ("Tamil Nadu", "TN", "south"),
    "Coimbatore": ("Tamil Nadu", "TN", "south"), "Tiruppur": ("Tamil Nadu", "TN", "south"), "Hyderabad": ("Telangana", "TG", "south"),
    "Visakhapatnam": ("Andhra Pradesh", "AP", "south"), "Kochi": ("Kerala", "KL", "south"), "Kolkata": ("West Bengal", "WB", "east"),
    "Bhubaneswar": ("Odisha", "OD", "east"), "Gurugram": ("Haryana", "HR", "north"), "Faridabad": ("Haryana", "HR", "north"),
    "New Delhi": ("Delhi", "DL", "north"), "Noida": ("Uttar Pradesh", "UP", "north"), "Kanpur": ("Uttar Pradesh", "UP", "north"),
    "Ludhiana": ("Punjab", "PB", "north"), "Jaipur": ("Rajasthan", "RJ", "north"), "Indore": ("Madhya Pradesh", "MP", "west"),
    "Raipur": ("Chhattisgarh", "CT", "east"), "Vapi": ("Gujarat", "GJ", "west"), "Aurangabad": ("Maharashtra", "MH", "west"),
}
CITY_SETS = {
    "west": ["Mumbai", "Pune", "Nashik", "Nagpur", "Thane", "Ahmedabad", "Surat", "Vadodara", "Rajkot", "Indore"],
    "tex": ["Tiruppur", "Coimbatore", "Surat", "Ludhiana", "Ahmedabad", "Kolkata"],
    "auto": ["Pune", "Aurangabad", "Chennai", "Faridabad", "Gurugram", "Bengaluru"],
    "port": ["Mumbai", "Kochi", "Visakhapatnam", "Chennai", "Vadodara"],
    "pharma": ["Hyderabad", "Vadodara", "Vapi", "Ahmedabad", "Bengaluru", "Pune"],
    "metro": ["Mumbai", "Bengaluru", "New Delhi", "Chennai", "Pune", "Hyderabad", "Kolkata", "Gurugram"],
    "inland": ["Nagpur", "Raipur", "Jaipur", "Indore", "Bhubaneswar", "Kanpur", "Visakhapatnam"],
    "chem": ["Vapi", "Vadodara", "Ahmedabad", "Mumbai", "Hyderabad", "Visakhapatnam"],
    "tech": ["Bengaluru", "Hyderabad", "Pune", "Gurugram", "Noida", "Chennai"],
}
FOREIGN = [("GmbH", "Germany"), ("Ltd", "United Kingdom"), ("Inc", "United States"), ("B.V.", "Netherlands"), ("S.p.A.", "Italy"), ("Pte Ltd", "Singapore")]
BANKS = ["Konkan Commercial Bank", "Northern Union Bank", "Southern Trust Bank", "Eastern Capital Bank", "Central Peninsula Bank", "Anand Merchants Bank"]
GRADE = {"A+": "IG-3", "A": "IG-4", "A-": "IG-4", "BBB+": "IG-5", "BBB": "IG-6", "BBB-": "IG-7", "BB+": "IG-8", "BB": "IG-9", "BB-": "IG-9"}
LADDER = ["A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-"]
RATING_W = {"Large": {"A+": 20, "A": 30, "A-": 25, "BBB+": 20, "BBB": 5}, "Mid": {"A-": 15, "BBB+": 30, "BBB": 30, "BBB-": 15, "BB+": 10},
            "SME": {"BBB": 15, "BBB-": 25, "BB+": 30, "BB": 20, "BB-": 10}}
AGENCIES = {"Large": ["CRISIL", "ICRA", "CARE Ratings", "India Ratings"], "Mid": ["CRISIL", "ICRA", "CARE Ratings", "India Ratings", "Acuite Ratings"],
            "SME": ["CARE Ratings", "Acuite Ratings", "Infomerics Valuation and Rating", "Brickwork Ratings"]}
SPREAD = {"IG-3": (0.5, 0.9), "IG-4": (0.8, 1.2), "IG-5": (1.1, 1.6), "IG-6": (1.5, 2.1), "IG-7": (2.0, 2.6), "IG-8": (2.6, 3.4), "IG-9": (3.2, 4.0)}
OUTLOOK = {"up": "Positive", "flat": "Stable", "down": "Negative"}
SPECIALIST = {"Lending": "u_arvind", "Trade": "u_kavita", "Treasury": "u_priya", "Cash management": "u_neha", "Supply-chain finance": "u_farhan"}
FAMILY_NODE = {"Lending": "pf_lending", "Trade": "pf_trade", "Treasury": "pf_treasury", "Supply-chain finance": "pf_scf", "Cash management": "pf_cash"}

FIRST_M = ["Rajesh", "Sunil", "Anil", "Vikram", "Amit", "Manoj", "Suresh", "Ramesh", "Deepak", "Nitin", "Prakash", "Harish", "Ashok", "Pradeep", "Mukesh", "Rahul",
           "Karthik", "Venkat", "Srikanth", "Arun", "Gopal", "Mohan", "Sudhir", "Ajay", "Naveen", "Satish", "Tarun", "Yogesh", "Hemant", "Rohit", "Imtiaz", "Faisal", "Jayesh", "Kunal", "Piyush"]
FIRST_F = ["Anita", "Sunita", "Kavitha", "Meenal", "Radhika", "Shalini", "Neeta", "Rekha", "Lakshmi", "Swati", "Seema", "Usha", "Madhuri", "Preeti", "Jyoti", "Farah", "Deepa", "Smita", "Archana"]
SUR = {"west": ["Patil", "Joshi", "Desai", "Shah", "Mehta", "Kulkarni", "Deshpande", "Parekh", "Thakkar", "Gandhi", "Naik", "Pawar", "Chavan", "Bhosale", "Doshi"],
       "south": ["Reddy", "Iyer", "Nair", "Rao", "Hegde", "Pillai", "Menon", "Naidu", "Subramanian", "Krishnan", "Shetty", "Gowda", "Varma"],
       "north": ["Sharma", "Gupta", "Malhotra", "Chopra", "Bansal", "Singh", "Kapoor", "Arora", "Khanna", "Tandon", "Saxena", "Mittal", "Garg"],
       "east": ["Banerjee", "Mukherjee", "Das", "Ghosh", "Sen", "Chatterjee", "Bose", "Mishra", "Panda", "Sahoo"]}
ONS = ["k", "v", "r", "s", "t", "m", "d", "n", "p", "b", "j", "g", "l", "sh", "dh", "bh", "kr", "pr", "tr", "gh", "z", "h"]
VOW = ["a", "e", "i", "o", "u", "ar", "an", "en", "in", "on", "al", "el", "or", "ai"]


# ------------------------------------------------------------------ meeting / insight text
GENERIC = ["Reviewed the quarter: sales up about {p}% on last year and collections are on schedule. No change in repayment plans.",
           "Walked through the stock and receivables position. Drawing pattern is in line with the sanctioned limits.",
           "Promoter said order inflow is steady and no large one-off expenses are planned this quarter.",
           "Discussed the pending renewal documents; the finance team will send the balance sheet extracts shortly.",
           "Client raised a delay in payments from one large customer; expects clearance within the month.",
           "Courtesy call. Business as usual; asked for a quicker turnaround on guarantee issuance."]
SECTOR_LINE = {
    "s_infra": "Order book stands at about {m} months of revenue; fewer new road awards from the authorities have made bidding tighter.",
    "s_textile": "US orders are slower than before the tariffs; sales are shifting toward the UK and Europe and the mill is running at about {u}% utilisation.",
    "s_auto": "OEM schedules are stable for the next two quarters; steel price pass-through works with a one month lag.",
    "s_shipping": "Fleet utilisation is high; war-risk premiums and freight costs have stayed elevated since the Gulf disruption.",
    "s_pharma": "Two new product approvals expected soon; generic exports are outside the new US tariff on patented drugs.",
    "s_food": "Raw material costs have stabilised and the new distribution tie-ups are adding volume.",
    "s_realty": "Pre-sales ran at about {q}% of plan; with unsold stock rising in the market, launches are being paced; escrow collections as expected.",
    "s_cement": "Despatches are healthy; power and fuel costs are rising and are the main margin worry.",
    "s_packaging": "Resin price swings are being passed on with a short lag; two new customers added.",
    "s_chemicals": "Plant running at about {u}%; one product line affected by cheaper imports.",
    "s_logistics": "Fleet utilisation about {u}%; diesel cost pass-through agreed with two key customers.",
    "s_steel": "Order inflow is steady; coking coal price remains the main risk to margins.",
    "s_it": "Headcount up modestly; client concentration is improving as the top client falls below {p}% of revenue.",
    "s_power": "Plant availability is above the contracted level; receivable days from the distribution company remain long.",
    "s_health": "Bed occupancy about {u}%; the new wing is on schedule.",
    "s_agri": "Crushing season starting; stock levels are in line with the sanctioned drawing power.",
}

# need ideas: key, sectors (None = any), family, product, builder(ctx) -> dict
def _L(ctx, f):
    return roundto(ctx["s"] * f, 5) or 5


INSIGHTS = [
    dict(k="capex", sec=None, fam="Lending", prod="Term loan for capex", ssz="large mid",
         say="plans capex of {c} over the next 12 months, partly debt funded", fact="Planned capex of {c} in the next 12 months (as told by the {role})"),
    dict(k="export", sec="exp", fam="Trade", prod="Packing credit", ssz="large mid sme",
         say="export orders are up {p}% on last year and the company wants a higher packing credit limit", fact="Export orders up {p}% year on year; wants a higher packing credit limit (as told by the {role})"),
    dict(k="fx", sec="exp", fam="Treasury", prod="FX forwards", ssz="large mid",
         say="has about USD {u} million of annual receivables and hedges only about half", fact="Annual USD receivables of about USD {u} million; roughly half is hedged (as told by the {role})"),
    dict(k="guarantee", sec=["s_infra", "s_power", "s_auto", "s_steel", "s_realty"], fam="Trade", prod="Performance guarantee", ssz="large mid sme",
         say="has been asked by a customer for a performance guarantee of {g}", fact="Customer asked for a performance guarantee of {g} (as told by the {role})"),
    dict(k="refi", sec=None, fam="Lending", prod="Term loan refinancing", ssz="large mid",
         say="pays {r:.2f}% on a term loan from another lender and would refinance if we price below {r2:.2f}%", fact="Existing term loan elsewhere priced at {r:.2f}%; open to refinance below {r2:.2f}% (as told by the {role})"),
    dict(k="scf", sec=["s_textile", "s_auto", "s_food", "s_pharma", "s_chemicals", "s_packaging", "s_cement", "s_steel"], fam="Supply-chain finance", prod="Supply chain finance", ssz="large mid",
         say="key suppliers ask for payment in {d} days and the company stretches to {d2}", fact="Top suppliers ask for payment in {d} days; the company pays in about {d2} (as told by the {role})"),
    dict(k="coll", sec=["s_infra", "s_realty", "s_health", "s_it", "s_power", "s_logistics", "s_food"], fam="Cash management", prod="Collections and escrow account", ssz="large mid sme",
         say="collections are spread over {n} banks and the company wants one collection account", fact="Collections spread over {n} banks; wants a single collection account (as told by the {role})"),
    dict(k="surplus", sec=None, fam="Treasury", prod="Liquid investments and sweep", ssz="large",
         say="holds about {x} idle in current accounts and wants short-term deployment", fact="About {x} idle in current accounts; looking at short-term deployment (as told by the {role})"),
]
FAMILY_RATE = {"Lending": 0.022, "Trade": 0.01, "Treasury": 0.0015, "Supply-chain finance": 0.018, "Cash management": 0.022}


def plain_why(text):
    """The routed 'why' text without the graph path in brackets, e.g. 'X is linked to Y. Fire at ...'.
    The full path is kept in work_item.why_path and shown under 'Why am I seeing this?'."""
    t = re.sub(r"\s*\([^()]*\)", "", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= 400 else t[:397].rsplit(" ", 1)[0] + "..."


class Expander:
    def __init__(self, con, rng, n_groups):
        self.con, self.rng, self.n = con, rng, n_groups
        self.ex = con.execute
        self.names = {r[0].lower() for r in con.execute("SELECT name FROM node")} | {u[1].lower() for u in NEW_RMS}
        self.slugs = {slug(r[0]) for r in con.execute("SELECT id FROM client_group")}
        self.cins, self.leis, self.dins, self.pans = set(), set(), set(), set()
        self.nodes = {r[0]: dict(type=r[1], name=r[2], group=r[3]) for r in con.execute("SELECT id,node_type,name,client_group_id FROM node")}
        self.edges = {(r[0], r[1], r[2]) for r in con.execute("SELECT from_node,to_node,edge_type FROM edge")}
        self.fact_no, self.work_no, self.ev_no = 7000, 6000, 1200
        self.audit = []
        self.groups = {}            # gid -> dict
        self.pool = {}              # sector id/'govt'/'foreign' -> [node ids]
        self.banks = []
        self.count = {}

    # ------------------------------------------------------------ small generators
    def bump(self, key, n=1):
        self.count[key] = self.count.get(key, 0) + n

    def stem(self):
        r = self.rng
        while True:
            s = "".join(r.choice(ONS) + r.choice(VOW) for _ in range(r.choice([2, 2, 3]))).capitalize()
            if 5 <= len(s) <= 9 and slug(s) not in self.slugs and not any(slug(s) in slug(n) for n in self.names):
                self.slugs.add(slug(s))
                return s

    def person_name(self, region):
        r = self.rng
        while True:
            first = r.choice(FIRST_F if r.random() < 0.22 else FIRST_M)
            n = f"{first} {r.choice(SUR[region])}"
            if n.lower() not in self.names:
                self.names.add(n.lower())
                return n

    def uniq(self, pool, fn):
        while True:
            v = fn()
            if v not in pool:
                pool.add(v)
                return v

    def node(self, nid, ntype, name, gid, attrs):
        assert nid not in self.nodes, nid
        self.nodes[nid] = dict(type=ntype, name=name, group=gid)
        self.names.add(name.lower())
        self.ex("INSERT INTO node VALUES (?,?,?,?,?)", (nid, ntype, name, gid, j(attrs)))
        self.bump("node")

    def edge(self, a, b, ty, attrs=None, fact=None, conf=1.0):
        if a == b or (a, b, ty) in self.edges:
            return
        assert a in self.nodes and b in self.nodes, (a, b, ty)
        self.edges.add((a, b, ty))
        self.ex("INSERT INTO edge (from_node,to_node,edge_type,attrs,source_fact_id,confidence,valid_from) VALUES (?,?,?,?,?,?,?)",
                (a, b, ty, j(attrs or {}), fact, conf, None))
        self.bump("edge")

    def fact(self, gid, node, stmt, label, share, source, sdate, conn, conf=1.0, val=None, unit=None, ref=None, eff=None):
        self.fact_no += 1
        fid = f"F-{self.fact_no}"
        self.ex("INSERT INTO fact VALUES (" + ",".join("?" * 15) + ")",
                (fid, gid, node, stmt, val, unit, source, ref, day(sdate) if isinstance(sdate, dt.datetime) else sdate, eff, label, share, conf, None, conn))
        self.bump("fact")
        return fid

    def company_attrs(self, name, kind, sector, role, st_code, city, state, yr=None, member=True):
        r = self.rng
        nic = r.choice(SEC[sector]["nic"]) if sector in SEC else "74999"
        yr = yr or r.randint(1988, 2019)
        listed = kind == "listed"
        a = {"role": role, "entity_kind": "Listed company" if listed else "Private limited company",
             "legal_name": name.replace(" Pvt Ltd", " Private Limited").replace(" Ltd", " Limited"),
             "cin": self.uniq(self.cins, lambda: ids.make_cin(r, listed, nic, st_code, yr)),
             "pan": self.uniq(self.pans, lambda: ids.make_pan(r, name, "C")), "nic_code": nic, "incorporated": yr,
             "registered_office": f"{city}, {state}", "status": "Active"}
        if member and (listed or role in ("Primary borrower", "Promoter entity", "Project SPV")):
            a["lei"] = self.uniq(self.leis, lambda: ids.make_lei(r))
        if not member:
            a["relationship"] = "counterparty"
        return a

    # ------------------------------------------------------------ 1. staff and sectors
    def staff(self):
        n = self.con.execute("SELECT COUNT(*) FROM app_user").fetchone()[0]
        for k, (uid, name, ini) in enumerate(NEW_RMS):
            first, last = name.lower().split()
            emp = f"RBL{104300 + 17 * (n + k + 1)}"
            self.ex("INSERT INTO app_user VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (uid, emp, name, f"{first}.{last}@compass-demo.example", "Relationship manager", "RM", ini, None, None, 0, "u_meera"))
            self.node(uid, "rbl_user", name, None, {"user_id": uid, "role": "Relationship manager", "function": "RM"})
        for sid, sname in NEW_SECTORS:
            self.node(sid, "sector", sname, None, {})

    # ------------------------------------------------------------ 2. shared counterparties
    def counterparties(self):
        r = self.rng
        for sid, cfg in SEC.items():
            self.pool[sid] = []
            for _ in range(5 if cfg["wt"] < 5 else 7):
                stem = self.stem()
                long = r.choice(cfg["w"])[0]
                cname = f"{stem} {long} Pvt Ltd" if r.random() < 0.7 else f"{stem} {long} Ltd"
                city = r.choice(CITY_SETS[cfg["city"]])
                state, code, _ = CITIES[city]
                nid = f"e_cp_{slug(stem)}"
                self.node(nid, "company", cname, None,
                          self.company_attrs(cname, "private" if cname.endswith("Pvt Ltd") else "listed", sid, "Trade counterparty", code, city, state, member=False))
                self.pool[sid].append(nid)
        self.pool["govt"] = []
        for _ in range(6):
            stem = self.stem()
            city = r.choice(CITY_SETS["metro"])
            nid = f"e_cp_{slug(stem)}"
            self.node(nid, "company", f"{stem} Urban Development Authority", None,
                      {"role": "Trade counterparty", "entity_kind": "State government authority", "registered_office": f"{city}, {CITIES[city][0]}", "relationship": "counterparty"})
            self.pool["govt"].append(nid)
        self.pool["foreign"] = []
        for _ in range(8):
            stem = self.stem()
            suf, country = r.choice(FOREIGN)
            nid = f"e_cp_{slug(stem)}"
            self.node(nid, "company", f"{stem} Trading {suf}", None,
                      {"role": "Trade counterparty", "entity_kind": "Foreign or multinational entity", "country": country, "relationship": "counterparty"})
            self.pool["foreign"].append(nid)
        for b in BANKS:
            nid = "b_" + slug(b.split()[0])
            self.node(nid, "bank", b, None, {"role": "Other lender", "entity_kind": "Lender", "note": "Other lender seen in credit bureau and MCA charge data", "relationship": "counterparty"})
            self.banks.append(nid)

    # ------------------------------------------------------------ 3. client groups
    def clients(self):
        r = self.rng
        rms = [u for u, q in QUOTA.items() for _ in range(q)]
        r.shuffle(rms)
        rms = rms[:self.n]
        segs = r.choices(["Large", "Mid", "SME"], [15, 40, 45], k=self.n)
        sectors = r.choices(list(SEC), [SEC[s]["wt"] for s in SEC], k=self.n)
        for i in range(self.n):
            self.one_group(rms[i], segs[i], sectors[i])

    def one_group(self, rm, seg, sec):
        r, cfg = self.rng, SEC[sec]
        stem = self.stem()
        long, short = r.choice(cfg["w"])
        gid = f"g_{slug(stem)}"
        city = r.choice(CITY_SETS[cfg["city"]])
        state, code, region = CITIES[city]
        listed = seg == "Large" and r.random() < 0.6 or seg == "Mid" and r.random() < 0.2
        pname = f"{stem} {long} {'Ltd' if listed else 'Pvt Ltd'}"
        gname = f"{stem} {long} Group" if seg == "Large" else f"{stem} {long}"
        pid = f"e_{slug(stem)}"
        yr = r.randint(1985, 2008) if seg == "Large" else r.randint(1992, 2016)
        self.node(gid, "client_group", gname, gid, {"segment": seg, "sector": SEC_NAME(sec)})
        self.node(pid, "company", pname, gid, self.company_attrs(pname, "listed" if listed else "private", sec, "Primary borrower", code, city, state, yr))
        ents = [pid]
        if seg != "SME" or r.random() < 0.3:
            hn = f"{stem} Holdings Pvt Ltd"
            hid = f"e_{slug(stem)}h"
            self.node(hid, "company", hn, gid, self.company_attrs(hn, "private", None, "Promoter entity", code, city, state, yr - r.randint(0, 6)))
            self.edge(hid, pid, "owns", {"pct": r.randint(38, 74)})
            ents.append(hid)
        if seg == "Large" and sec in ("s_infra", "s_realty", "s_power"):
            for k in range(1, r.randint(1, 3) + 1):
                sn = f"{stem} {short} SPV {k} Pvt Ltd"
                sid_ = f"e_{slug(stem)}s{k}"
                self.node(sid_, "company", sn, gid, self.company_attrs(sn, "private", sec, "Project SPV", code, city, state, r.randint(2018, 2025)))
                self.edge(pid, sid_, "owns", {"pct": r.choice([74, 100])})
                ents.append(sid_)
        for e in ents:
            self.edge(e, gid, "member_of", {"role": self.nodes[e] and self.role_of(e)})
        self.edge(gid, pid, "has_primary")
        self.edge(gid, rm, "managed_by")
        for e in ents:
            if self.role_of(e) in ("Primary borrower", "Project SPV"):
                self.edge(e, sec, "operates_in")
        # people
        people = [("Chairman and promoter" if seg == "Large" else "Managing Director", "director", True),
                  (r.choice(["Chief Financial Officer"] if seg != "SME" else ["Finance Controller", "Head of Finance", "Accounts Manager"]), "employee", False)]
        if seg == "Large":
            people += [("Head of Treasury", "employee", False), ("Managing Director", "director", True)]
        elif seg == "Mid":
            people.append(("Director", "director", True))
        pers = []
        for k, (role, kind, din) in enumerate(people, 1):
            nm = self.person_name(region)
            nid = f"p_{slug(stem)}{k}"
            a = {"role": role, "stakeholder": dict(strength=r.choice(["Strong", "Moderate", "Moderate", "Weak"]), influence=r.choice(["High", "Medium"]),
                                                  channel=r.choice(["In person", "Phone", "Email"]), owner=rm)}
            if din:
                a["din"] = self.uniq(self.dins, lambda: ids.make_din(r))
            self.node(nid, "person", nm, gid, a)
            self.edge(nid, pid, "director_of" if kind == "director" else "employed_by", {"role": role})
            pers.append(nid)
        # rating, limits, book data
        rating = r.choices(list(RATING_W[seg]), list(RATING_W[seg].values()))[0]
        trend = r.choices(["up", "flat", "down"], [15, 65, 20])[0]
        watch = "None" if trend != "down" and r.random() < 0.8 else r.choices(["None", "P3", "P2", "P1"], [30, 30, 28, 12])[0]
        agency = r.choice(AGENCIES[seg])
        grade = GRADE[rating]
        total = {"Large": lambda: roundto(r.uniform(150, 600), 5), "Mid": lambda: roundto(r.uniform(40, 150), 5), "SME": lambda: roundto(r.uniform(8, 40), 1)}[seg]()
        tier = {"Large": 1, "Mid": 2, "SME": 3}[seg]
        cadence = {1: r.choice([30, 45]), 2: r.choice([45, 60]), 3: r.choice([60, 90])}[tier]
        g = dict(id=gid, name=gname, short=f"{stem} {short}", primary=pid, primary_name=pname, seg=seg, sector=sec, rm=rm, tier=tier, rating=rating,
                 agency=agency, trend=trend, watch=watch, grade=grade, total=total, cadence=cadence, ents=ents, persons=pers, city=city, state=state,
                 review_due=NOW + dt.timedelta(days=r.randint(12, 330)), stem=stem, sup=[], cust=[], facts=[], needs=[], facilities=[], meet=[], region=region)
        self.groups[gid] = g

    def role_of(self, nid):
        a = json.loads(self.ex("SELECT attrs FROM node WHERE id=?", (nid,)).fetchone()[0])
        return a.get("role")

    # ------------------------------------------------------------ 4. facilities and the group row
    FAC = {"CC": ("Cash Credit", "Hypothecation of stock and book debts", "Current ratio at least 1.1x", (0.62, 0.93)),
           "WCDL": ("Working Capital Demand Loan", "Hypothecation of stock and receivables", "Current ratio at least 1.15x", (0.6, 0.9)),
           "TL": ("Term Loan", "First charge on fixed assets financed", "DSCR at least 1.2x; TOL/TNW at most 3.0x", (0.55, 0.95)),
           "BG": ("Bank Guarantee", "Margin and counter-guarantee", "None specific", (0.3, 0.7)),
           "LC": ("Letter of Credit", "Lien on goods", "None specific", (0.35, 0.75)),
           "PCFC": ("Packing Credit in Foreign Currency (PCFC)", "Lien on export orders and receivables", "Export realisation within 180 days", (0.4, 0.8)),
           "BD": ("Bill Discounting", "Assignment of receivables from approved buyers", "None specific", (0.5, 0.9)),
           "FX": ("Forward Contract Limit", "Margin on forward contracts", "None specific", (0.2, 0.6))}

    def facilities(self, g):
        r = self.rng
        seg, sec = g["seg"], g["sector"]
        n = {"Large": r.randint(4, 6), "Mid": r.randint(3, 4), "SME": r.randint(2, 3)}[seg]
        codes = ["CC" if r.random() < 0.75 else "WCDL"]
        if sec != "s_it" or seg != "SME":
            codes.append("TL")
        extras = (["PCFC"] * 3 + ["LC"] * 2 + ["BG"] + ["FX"] * 2) if SEC[sec]["exp"] else (["BG"] * 4 + ["LC"]) if sec in ("s_infra", "s_power", "s_realty") else ["LC"] * 2 + ["BG"] * 2 + ["BD"]
        while len(codes) < n:
            c = r.choice(extras)
            if c not in codes:
                codes.append(c)
            elif len(set(extras) - set(codes)) == 0:
                break
        step = 0.5 if g["total"] < 40 else 5
        while True:
            w = [r.uniform(0.5, 1.5) for _ in codes]
            parts = sorted([max(step, roundto(g["total"] * x / sum(w), step)) for x in w], reverse=True)
            parts[0] += g["total"] - sum(parts)
            if parts[0] >= step:
                break
        lo, hi = SPREAD[g["grade"]]
        rows, tot_s, tot_o = [], 0.0, 0.0
        for i, (code, s_) in enumerate(zip(codes, parts), 1):
            typ, sec_txt, cvn, (ul, uh) = self.FAC[code]
            if code == "TL":
                typ = r.choice(["Term Loan", "Term Loan (capex)", "Term Loan (plant and machinery)"])
            o_ = min(s_, roundto(s_ * r.uniform(ul, uh), 0.5))
            spread = r.uniform(lo, hi)
            if code in ("BG", "LC"):
                pricing = f"{r.uniform(0.8, 1.6):.2f}% a year"
            elif code == "FX":
                pricing = f"Dealing spread {r.choice([0.10, 0.15, 0.20]):.2f} rupees per USD"
            elif code == "PCFC":
                pricing = f"SOFR + {r.uniform(1.4, 2.4):.2f}% p.a."
            else:
                pricing = f"{RLLR + spread:.2f}% p.a. (RLLR + {spread:.2f}%)"
            mat = day(month_end(NOW + dt.timedelta(days=int(r.uniform(2, 7) * 365)))) if code == "TL" else None
            auth = "Delegated" if s_ <= 25 else "Credit committee"
            rows.append((f"fa_{slug(g['stem'])}{i}", g["id"], typ, f"XXXXXX{r.randint(1000, 9999)}", s_, o_, mat, pricing, sec_txt, "n/a", cvn, auth,
                         day(g["review_due"]), "Standard"))
            tot_s += s_
            tot_o += o_
        g["facilities"] = rows
        g["sanctioned"], g["outstanding"] = tot_s, tot_o
        return rows

    def insert_group(self, g):
        r = self.rng
        ext = f"{g['agency']} {g['rating']}/{OUTLOOK[g['trend']]}"
        last = NOW - dt.timedelta(days=r.randint(2, int(g["cadence"] * 1.4)))
        flow = r.choices(["High", "Medium", "Low"], {"Large": [50, 40, 10], "Mid": [25, 50, 25], "SME": [5, 35, 60]}[g["seg"]])[0]
        seg_txt = {"Large": "Large corporate", "Mid": "Mid corporate", "SME": "SME"}[g["seg"]]
        for f in self.facilities(g):
            self.ex("INSERT INTO facility VALUES (" + ",".join("?" * 14) + ")", f)
            self.bump("facility")
        self.ex("INSERT INTO client_group VALUES (" + ",".join("?" * 21) + ")",
                (g["id"], g["name"], g["short"], g["primary"], seg_txt, SEC_NAME(g["sector"]), g["tier"], g["rm"], r.randint(2008, 2025),
                 g["sanctioned"], g["outstanding"], round(g["outstanding"] * r.uniform(0.05, 0.35), 1), g["grade"], ext, g["trend"], g["watch"],
                 g["cadence"], day(last), day(g["review_due"]), flow, 0))
        g["last_contact"], g["ext"] = last, ext
        self.bump("client_group")

    # ------------------------------------------------------------ 5. supply chain, lenders, facts
    def candidates(self, sector_ids, exclude_group):
        out = []
        for s in sector_ids:
            out += self.pool.get(s, [])
            if s in SEC:
                out += [g["primary"] for g in self.groups.values() if g["sector"] == s and g["id"] != exclude_group and self.rng.random() < 0.25]
        return out

    def links_and_facts(self, g):
        r = self.rng
        cfg, pid, short = SEC[g["sector"]], g["primary"], g["short"]
        gid, scale = g["id"], g["total"]
        src = self.groups
        # limits fact
        h = g["sanctioned"] - g["outstanding"]
        g["facts"].append(self.fact(gid, pid, f"Group limit {rs(g['sanctioned'])}; utilised {rs(g['outstanding'])}; headroom {rs(h)}", "int", "discuss",
                                    "Limits and exposure system", NOW - dt.timedelta(days=2), "limits-exposure", val=h, unit="INR crore"))
        abbr = "".join(w[0] for w in g["primary_name"].split()[:3]).upper()
        rdate = NOW - dt.timedelta(days=r.randint(20, 220))
        g["facts"].append(self.fact(gid, pid, f"{g['agency']} rates {g['primary_name']} {g['rating']}/{OUTLOOK[g['trend']]}", "ext", "discuss",
                                    f"{g['agency']}: rating rationale", rdate, "rating-agencies", ref=f"RR/{abbr}/2026-27/{r.randint(100, 999):04d}"))
        cs, cu = self.candidates(cfg["sup"], gid), self.candidates(cfg["cust"], gid)
        sups = r.sample(cs, k=min(r.randint(2, 4), len(cs)))
        custs = r.sample(cu, k=min(r.randint(1, 3), len(cu)))
        for s_ in dict.fromkeys(sups):
            amt = max(0.8, round(scale * r.uniform(0.04, 0.22), 1))
            f = self.fact(gid, s_, f"{short} paid {self.nodes[s_]['name']} {rs(amt)} in the last 12 months ({r.randint(9, 64)} payments)", "int", "internal",
                          "Outward payment flows", NOW - dt.timedelta(days=r.randint(1, 20)), "core-banking", conf=round(r.uniform(0.86, 0.97), 2), val=amt, unit="INR crore")
            self.edge(s_, pid, "supplies_to", {"share_of_purchases_pct": r.randint(6, 38)}, f, round(r.uniform(0.86, 0.97), 2))
            g["sup"].append(s_)
        for c_ in dict.fromkeys(custs):
            amt = max(0.8, round(scale * r.uniform(0.08, 0.35), 1))
            f = self.fact(gid, c_, f"{self.nodes[c_]['name']} remitted {rs(amt)} to {short} in the last 12 months ({r.randint(8, 70)} credits)", "int", "internal",
                          "Inward remittances", NOW - dt.timedelta(days=r.randint(1, 20)), "core-banking", conf=round(r.uniform(0.86, 0.97), 2), val=amt, unit="INR crore")
            self.edge(pid, c_, "supplies_to", {"share_of_sales_pct": r.randint(8, 45)}, f, round(r.uniform(0.86, 0.97), 2))
            g["cust"].append(c_)
        if g["seg"] != "SME" and r.random() < 0.5:
            b = r.choice(self.banks)
            amt = roundto(scale * r.uniform(0.2, 0.6), 5) or 5
            cid = f"{r.randint(100000000, 100999999)}"
            f = self.fact(gid, b, f"{self.nodes[b]['name']} also lends to {short}: about {rs(amt)} per credit bureau and charge records", "ext", "internal",
                          "MCA registry; credit bureau", NOW - dt.timedelta(days=r.randint(5, 90)), "mca-registry", ref=f"Charge ID {cid}", val=amt, unit="INR crore")
            self.edge(b, pid, "lends_to", {"note": "other lender", "approx_cr": amt}, f, 0.9)
        growth = r.randint(-9, 24)
        g["facts"].append(self.fact(gid, pid, f"GST returns show turnover of {rs(scale * r.uniform(2.2, 4.5))} for the last four quarters, "
                                              f"{'up' if growth >= 0 else 'down'} {abs(growth)}% year on year", "ext", "internal", "GST returns", NOW - dt.timedelta(days=r.randint(8, 40)), "external-filings"))
        if r.random() < 0.6:
            g["facts"].append(self.fact(gid, pid, f"Commercial credit report shows no overdue with other lenders; total reported borrowing {rs(scale * r.uniform(1.0, 1.8))}", "ext", "internal",
                                        "Credit bureau (commercial)", NOW - dt.timedelta(days=r.randint(10, 80)), "external-filings"))

    # ------------------------------------------------------------ 6. meetings, insights, needs
    def meetings(self, g):
        r = self.rng
        gid, rm = g["id"], g["rm"]
        contacts = g["persons"]
        t = g["last_contact"]
        hist = []
        while len(hist) < 4 and t > NOW - dt.timedelta(days=170):
            hist.append(t)
            t = t - dt.timedelta(days=int(g["cadence"] * r.uniform(0.7, 1.3)))
        g["_hist"] = hist[::-1]
        applicable = [i for i in INSIGHTS if (i["sec"] is None or (i["sec"] == "exp" and SEC[g["sector"]]["exp"]) or (isinstance(i["sec"], list) and g["sector"] in i["sec"]))
                      and {"Large": "large", "Mid": "mid", "SME": "sme"}[g["seg"]] in i["ssz"].split()]
        want = 0 if r.random() > {"Large": 0.7, "Mid": 0.45, "SME": 0.22}[g["seg"]] else r.choice([1, 1, 2])
        chosen = r.sample(applicable, k=min(want, len(applicable)))
        slots = [i for i, d in enumerate(g["_hist"]) if d < NOW - dt.timedelta(days=4)]
        r.shuffle(slots)
        for k, ins in enumerate(chosen):
            if not slots:
                break
            self.make_need(g, ins, g["_hist"][slots.pop()], k + 1)
        for idx, when in enumerate(g["_hist"]):
            when = at_hour(when, r)
            mtype = r.choices(["meeting", "call", "email"], [55, 30, 15])[0]
            status, logged = "held", 1
            if when > NOW - dt.timedelta(days=9) and r.random() < 0.3:
                status, logged = "notes_pending", 0
            lines = [r.choice(GENERIC).format(p=r.randint(6, 28), u=r.randint(62, 91))]
            if r.random() < 0.55:
                lines.append(SECTOR_LINE[g["sector"]].format(p=r.randint(8, 32), u=r.randint(62, 91), m=r.randint(14, 36), q=r.randint(82, 112)))
            for n_ in g["needs"]:
                if n_["when_idx"] == idx and status == "held":
                    lines.append(f"{self.role_name(g, n_['contact'])} {n_['say']}.")
            outcome = None if status == "notes_pending" else " ".join(lines)
            title = {"meeting": r.choice(["Quarterly review with the finance head", "Annual review discussion", "Site visit and management meeting", "Review of working capital position"]),
                     "call": r.choice(["Catch-up call", "Call on renewal documents", "Call on stock statement and drawing power"]),
                     "email": r.choice(["Email thread on pending documents", "Email: financials for review", "Email: queries on the quarter"])}[mtype]
            where = {"meeting": r.choice([f"Client office, {g['city']}", f"RBL branch, {g['city']}", "Video call"]), "call": "Call", "email": "Email thread"}[mtype]
            parts = r.sample(contacts, k=min(len(contacts), r.randint(1, 2)))
            mid = f"mt_{slug(g['stem'])}_{when.strftime('%m%d')}"
            self.ex("INSERT INTO meeting VALUES (" + ",".join("?" * 17) + ")",
                    (mid, gid, mtype, title, iso(when), r.choice([30, 45, 60]) if mtype != "email" else 15, where, j(parts), status, None,
                     None, None, None, outcome, {"meeting": "calendar", "call": "rm", "email": "outlook-detected"}[mtype], logged,
                     next((n_["id"] for n_ in g["needs"] if n_["when_idx"] == idx), None)))
            self.bump("meeting")
            g["meet"].append((mid, when, status))
            if status == "held" and mtype != "email" and r.random() < 0.5:
                self.audit.append((rm, iso(when + dt.timedelta(hours=2)), "log_meeting", f"Logged {title.lower()} with {g['short']}", [mid]))
        if r.random() < {"Large": 0.4, "Mid": 0.3, "SME": 0.15}[g["seg"]]:      # upcoming meeting
            when = at_hour(NOW + dt.timedelta(days=r.randint(1, 16)), r)
            mid = f"mt_{slug(g['stem'])}_{when.strftime('%m%d')}"
            obj = r.choice([f"Agree the renewal timetable and documents for the {when.year + 1 if when.month > 9 else when.year} review.",
                            "Understand the capex plan and how it will be funded.", "Review the latest stock statement and drawing power.",
                            "Discuss the reasons for the lower account turnover and the outlook for the next two quarters."])
            self.ex("INSERT INTO meeting VALUES (" + ",".join("?" * 17) + ")",
                    (mid, gid, "meeting", r.choice(["Quarterly review", "Annual review preparation", "Management meeting"]), iso(when), r.choice([45, 60]), f"Client office, {g['city']}",
                     j(contacts[:2]), "scheduled", r.choice(["ready", "incomplete"]), obj, "Management shares the plan and agrees next steps with dates.",
                     j({"agenda": {"must": ["Business update and outlook", "Open commitments on both sides"], "ifTime": ["Other banking needs"], "avoid": ["Quoting pricing before approvals"]}}),
                     None, "calendar", 0, g["needs"][0]["id"] if g["needs"] else None))
            self.bump("meeting")

    def role_name(self, g, nid):
        return {"Chief Financial Officer": "The CFO", "Head of Finance": "The head of finance", "Finance Controller": "The finance controller",
                "Accounts Manager": "The accounts manager", "Head of Treasury": "The treasury head"}.get(self.role_of(nid), "The promoter")

    def make_need(self, g, ins, when, k):
        r = self.rng
        s = g["sanctioned"]
        ctx = dict(c=rs(roundto(s * r.uniform(0.25, 0.7), 5) or 5), p=r.randint(8, 35), u=r.randint(2, 18), g=rs(roundto(s * r.uniform(0.1, 0.35), 5) or 5),
                   r=RLLR + r.uniform(1.6, 2.6), d=r.choice([30, 45]), d2=r.choice([75, 90, 105]), n=r.randint(4, 11), x=rs(roundto(s * r.uniform(0.1, 0.3), 5) or 5))
        ctx["r2"] = ctx["r"] - 0.8
        fin_contact = next((p for p in g["persons"] if self.role_of(p) in ("Chief Financial Officer", "Head of Finance", "Finance Controller", "Accounts Manager")), g["persons"][0])
        ctx["role"] = self.role_of(fin_contact)
        fid = self.fact(g["id"], g["primary"], ins["fact"].format(**ctx), "client", "discuss", "Meeting note", when, "crm", ref=None)
        g["facts"].append(fid)
        base = {"capex": float(re.sub(r"[^\d.]", "", ctx["c"])) * 0.6, "export": s * 0.2, "fx": ctx["u"] * USD_CR, "guarantee": float(re.sub(r"[^\d.]", "", ctx["g"])),
                "refi": s * 0.35, "scf": s * 0.25, "coll": s * 0.2, "surplus": float(re.sub(r"[^\d.]", "", ctx["x"]))}[ins["k"]]
        rate = FAMILY_RATE[ins["fam"]]
        lo, hi = round(base * 0.7 * rate, 2), round(base * rate, 2)
        stage = r.choices(["Signal", "Hypothesis", "Need to validate", "Specialist engaged"], [30, 25, 25, 20])[0]
        spec = SPECIALIST[ins["fam"]]
        nid = f"opp_{slug(g['stem'])}{k}"
        day_due = day(NOW + dt.timedelta(days=r.randint(4, 14)))
        nba = dict(action=f"Confirm the {ins['prod'].lower()} requirement and timeline with {self.nodes[fin_contact]['name']}", why="Raised in the last meeting; a clear timeline decides who wins it.",
                   evidence=[fid], owner=g["rm"], due=day_due)
        feas = [["Limit headroom", f"Group headroom {rs(g['sanctioned'] - g['outstanding'])}", "int"],
                ["Competitor position", "Existing lenders hold similar facilities", "ext"]]
        self.node(nid, "need", f"{ins['prod']} for {g['short']}", g["id"], {"product": ins["prod"], "family": ins["fam"], "stage": stage})
        self.ex("INSERT INTO need VALUES (" + ",".join("?" * 24) + ")",
                (nid, g["id"], nid, f"{ins['prod']} for {g['short']}", ins["prod"], ins["fam"], stage, "Hypothesis" if stage in ("Signal", "Hypothesis") else "Client-stated",
                 fin_contact, spec, None, f"Meeting: {ins['k']} ({fid})", "Meeting note",
                 f"{self.role_name(g, fin_contact)} {ins['say'].format(**ctx)}.", "Within the next two quarters", "Other banks already provide a similar facility",
                 lo, hi, f"Rs {base * 0.7:,.0f}-{base:,.0f} cr base x {rate * 100:.2g}% yield (net income a year)", j([fid]), j(dict(nba=nba, feasibility=feas)), None, None, "active"))
        self.bump("need")
        self.edge(g["id"], nid, "has_need")
        self.edge(nid, FAMILY_NODE[ins["fam"]], "in_family")
        self.edge(nid, spec, "handled_by", {"role": "Specialist"})
        self.edge(fin_contact, nid, "stakeholder_for")
        idx = g["_hist"].index(when)
        g["needs"].append(dict(id=nid, say=ins["say"].format(**ctx), when_idx=idx, contact=fin_contact, prod=ins["prod"], fid=fid))

    # ------------------------------------------------------------ 7. alerts
    def alerts(self, g):
        r = self.rng
        n = 0 if r.random() > {"Large": 0.5, "Mid": 0.35, "SME": 0.3}[g["seg"]] else (2 if r.random() < 0.2 else 1)
        if g["trend"] == "down" and n == 0 and r.random() < 0.6:
            n = 1
        picked = []
        pool = ["OD", "DC", "DP", "BK", "CN", "GV1", "GV2", "WC", "CV", "OP"] + (["RT", "RT"] if g["trend"] == "down" else [])
        while len(picked) < n:
            c = r.choice(pool)
            if c not in picked:
                picked.append(c)
        for c in picked:
            self.one_alert(g, c)

    def one_alert(self, g, c):
        r = self.rng
        short, gid, out = g["short"], g["id"], g["outstanding"]
        det = at_hour(NOW - dt.timedelta(days=r.randint(0, 25)), r).replace(hour=r.choice([7, 9]), minute=0)
        sma, cov, blk, sev, code = None, 0, 0, "Medium", None
        cap = next(f for f in g["facilities"])
        if c == "OD":
            d = r.choice([3, 8, 12, 19, 27, 34, 41, 58, 66, 79])
            amt = round(cap[4] * r.uniform(0.005, 0.02), 1) or 0.2
            title, cat, code = f"Interest on {cap[2].lower()} overdue {d} days", "Repayment", "EWS-OD-01"
            sma = "SMA-0" if d <= 30 else "SMA-1" if d <= 60 else "SMA-2"
            sev, blk = ("High" if d > 20 else "Medium"), 1
            ctx = f"Interest of {rs(amt)} was due {d} days ago and has not been credited. The client has been called twice."
            req, src = "Obtain the payment date and the reason; check for any dispute with a customer", "Core banking; EWS engine"
        elif c == "DC":
            title, cat, code = f"Stock statement for {(det - dt.timedelta(days=30)).strftime('%B %Y')} not received", "Documentation", "EWS-DC-01"
            sev, ctx = "Low", "The monthly stock statement is overdue by more than 10 days; drawing power cannot be refreshed."
            req, src = "Request the statement and confirm the delivery date", "EWS engine"
        elif c == "DP":
            x = round(cap[4] * r.uniform(0.02, 0.08), 1) or 0.3
            title, cat, code = f"Drawing power exceeded by {rs(x)}", "Documentation", "EWS-DP-02"
            ctx, req, src = "Utilisation on the cash credit is above the drawing power computed from the latest stock statement.", "Ask the client to bring the account within drawing power", "Core banking; EWS engine"
            blk = 1
        elif c == "BK":
            k = r.randint(2, 6)
            title, cat, code = f"{k} cheque returns in the last 30 days", "Banking conduct", "EWS-BK-04"
            ctx, req, src = f"{k} outward cheques were returned for insufficient funds across two accounts.", "Ask the finance head about the cash position and the reason", "Core banking; EWS engine"
        elif c == "CN":
            p = r.randint(55, 78)
            title, cat, code = f"{p}% of inward remittances from one customer", "Concentration", "EWS-CN-02"
            ctx, req, src = "One customer accounts for most inward remittances in the last 90 days.", "Understand the contract and the customer's payment behaviour", "Inward remittances; Compass concentration rule"
        elif c == "GV1":
            title, cat, code = "Director resignation filed (DIR-11)", "Governance", "EWS-GV-01"
            sev, ctx, req, src = "Medium", "A director resigned from the primary borrower; filing seen on the MCA portal.", "Ask the client for the reason and the new board composition", "MCA director filings"
        elif c == "GV2":
            title, cat, code = "Statutory auditor resigned before term end (ADT-3)", "Governance", "EWS-GV-02"
            sev, ctx, req, src = "High", "The statutory auditor resigned before the end of the term. No reason was given in the filing.", "Obtain the auditor's resignation letter and the reason; inform Credit", "MCA filings"
            blk = 1
        elif c == "WC":
            p = r.randint(18, 45)
            title, cat, code = f"Receivable days up {p}% year on year", "Working capital", "EWS-WC-03"
            sev, blk = "High" if p > 30 else "Medium", int(p > 30)
            ctx, req, src = "Receivable days are rising faster than sales. The client attributes it to one large customer.", "Obtain customer-wise ageing; complete the credit review", "Client stock statements; EWS engine"
        elif c == "CV":
            dscr = round(r.uniform(1.04, 1.18), 2)
            title, cat, code = f"DSCR covenant breached ({dscr}x against 1.20x)", "Covenant", "EWS-CV-01"
            sev, cov, blk = "High", 1, 1
            ctx, req, src = "The DSCR in the latest quarterly numbers is below the sanctioned covenant.", "Ask for the cure plan; consider a waiver note to Credit", "Client financials; EWS engine"
        elif c == "RT":
            new = LADDER[min(LADDER.index(g["rating"]) + 1, len(LADDER) - 1)]
            title, cat, code = f"{g['agency']} downgrades {g['primary_name']} to {new}", "Rating", "EWS-RT-01"
            sev, ctx, req, src = "High", f"Rating moved from {g['rating']} to {new}; the outlook is Negative.", "Review the rating rationale and speak to the CFO", "Rating agency"
        else:
            title, cat, code = "Production halted at one plant for several days", "Operations", "EWS-OP-02"
            sev, ctx, req, src = "Medium", "A news report says one of the plants has been closed for several days.", "Confirm the cause and the expected restart date", "News feed"
        aid = f"a_{slug(g['stem'])}{c.lower()}"
        days_left = max(1, (g["review_due"] - NOW).days) if blk else None
        state = r.choices(["New", "Under review", "Responded", "Resolved"], [72, 12, 8, 8])[0]
        reason, by, at = (None, None, None)
        if state == "Resolved":
            reason, by, at = r.choice(["Client paid the overdue amount", "Explained by a customer delay; no concern", "Statement received and drawing power refreshed"]), g["rm"], iso(det + dt.timedelta(days=r.randint(1, 5)))
            self.audit.append((g["rm"], at, "resolve_alert", f"Resolved alert on {short}: {title}", [aid]))
        self.ex("INSERT INTO alert VALUES (" + ",".join("?" * 22) + ")",
                (aid, gid, title, cat, code, sma, src, iso(det), sev, out, blk, cov, days_left, state, ctx, req, f"{gid}|{code}|{det.strftime('%Y-%m')}", None, j([]), reason, by, at))
        self.bump("alert")
        g.setdefault("alert_ids", []).append((aid, title, sev, state, det, req))

    # ------------------------------------------------------------ 8. work items
    def work(self, g):
        r = self.rng
        gid, rm, short = g["id"], g["rm"], g["short"]
        contact = g["persons"][1] if len(g["persons"]) > 1 else g["persons"][0]
        cname = self.nodes[contact]["name"]
        items = []

        def add(title, typ, case, owner, requester, due, created, cons, completion, label=None, vis="internal", sla=None, depends=None, state=None, thread=None):
            items.append(dict(title=title, type=typ, case=case, owner=owner, requester=requester, due=due, created=created, cons=cons, completion=completion,
                              label=label, vis=vis, sla=sla, depends=depends or [], state=state, thread=thread or []))

        for n_ in g["needs"]:
            when = g["_hist"][n_["when_idx"]]
            add(f"Send indicative {n_['prod'].lower()} terms to {cname}", "commitment", n_["id"], rm, rm, when + dt.timedelta(days=r.randint(5, 12)), when,
                "The client expects a response before the next meeting.", "Terms sent to the client and logged", vis="client")
            if r.random() < 0.5:
                add(f"Specialist view on {n_['prod'].lower()} for {short}", "specialist_request", n_["id"], SPECIALIST_FOR(n_["prod"]), rm, when + dt.timedelta(days=r.randint(7, 14)),
                    when + dt.timedelta(days=1), "RM needs the specialist view before sharing terms.", "Specialist note attached to the need",
                    sla=r.choice(["Standard: 3 working days", "Standard: 5 working days"]))
        for aid, title, sev, state, det, req in g.get("alert_ids", []):
            if state in ("New", "Under review"):
                add(req[0].upper() + req[1:] + f": {short}", "client_request" if "client" in req.lower() or "ask" in req.lower() or "obtain" in req.lower() or "request" in req.lower() else "task",
                    aid, rm, rm, det + dt.timedelta(days=r.randint(1, 4 if sev == "High" else 9)), det + dt.timedelta(hours=3),
                    f"Open alert: {title}.", "Information received and alert updated", label=f"{cname} (client)", vis="client")
        if (g["review_due"] - NOW).days < 140:
            add(f"Prepare annual review note for {short}", "task", gid, rm, rm, g["review_due"] - dt.timedelta(days=r.randint(14, 28)), NOW - dt.timedelta(days=r.randint(5, 40)),
                f"Annual review is due on {g['review_due'].strftime('%d %B %Y')}.", "Review note submitted to Credit")
        if g["seg"] != "SME" and r.random() < 0.35:
            add(f"Collect audited FY26 financials from {short}", "client_request", gid, rm, rm, NOW + dt.timedelta(days=r.randint(-3, 30)), NOW - dt.timedelta(days=r.randint(5, 25)),
                "The annual review needs the FY26 spread.", "Statements received and filed", label=f"{cname} (client)", vis="client")
        if r.random() < 0.3:
            m_ = (NOW - dt.timedelta(days=30)).strftime("%B %Y")
            add(f"Request {m_} stock statement from {short}", "client_request", gid, rm, rm, NOW + dt.timedelta(days=r.randint(-2, 10)), NOW - dt.timedelta(days=r.randint(2, 12)),
                "Drawing power is refreshed from the monthly statement.", "Statement received", label=f"{cname} (client)", vis="client")
        if r.random() < 0.12:
            add(f"Periodic KYC refresh for {g['primary_name']}", "task", gid, rm, rm, NOW + dt.timedelta(days=r.randint(3, 40)), NOW - dt.timedelta(days=r.randint(1, 20)),
                "KYC must be refreshed on the periodic schedule.", "KYC documents updated and verified")
        if r.random() < 0.1:
            add(f"Insurance cover copy for hypothecated stock: {short}", "client_request", gid, rm, rm, NOW + dt.timedelta(days=r.randint(2, 35)), NOW - dt.timedelta(days=r.randint(1, 14)),
                "Cover must be current for the security to be valid.", "Policy copy received and filed", label=f"{cname} (client)", vis="client")
        if g["seg"] != "SME" and r.random() < 0.08:
            add(f"Legal vetting of renewal security documents for {short}", "legal", gid, "u_aditi", rm, NOW + dt.timedelta(days=r.randint(5, 30)), NOW - dt.timedelta(days=r.randint(1, 8)),
                "Renewal cannot be disbursed before vetting.", "Vetting note attached", sla="Standard: 5 working days")
        for w in items:
            self.insert_work(g, w)

    def insert_work(self, g, w):
        r = self.rng
        due, created = w["due"], w["created"]
        if isinstance(created, dt.datetime) and created > NOW:
            created = NOW - dt.timedelta(days=1)
        past = due < NOW
        state = w["state"] or (r.choices(["Done", "Open", "In progress", "Needs information", "Accepted", "Cancelled"], [60, 12, 15, 5, 4, 4])[0] if past and r.random() < 0.55
                               else r.choices(["Open", "In progress", "Accepted", "Needs information", "Done"], [42, 28, 10, 8, 12])[0])
        if state == "Done" and due > NOW + dt.timedelta(days=2):
            state = "In progress"
        # A live item is rarely months late. Pull stale open items to 1-14 days overdue; about 1 in 12 may stay up to 35 days late.
        # Uses a hash of the item number (not the RNG) so no other generated value changes.
        if state in ("Open", "In progress", "Needs information", "Accepted") and isinstance(due, dt.datetime) and due < NOW - dt.timedelta(days=14):
            h = zlib.crc32(f"W-{self.work_no + 1}".encode())
            late = 15 + h % 21 if h % 12 == 0 else 1 + h % 14
            due = NOW - dt.timedelta(days=late)
            if isinstance(created, dt.datetime) and created > due - dt.timedelta(days=1):
                created = due - dt.timedelta(days=3)
        due_s = iso(at_hour(due, r)) if isinstance(due, dt.datetime) else due
        self.work_no += 1
        wid = f"W-{self.work_no}"
        esc = 1 if state in ("Open", "In progress", "Needs information") and due < NOW - dt.timedelta(days=2) else 0
        cdl = iso(at_hour(due + dt.timedelta(days=r.randint(2, 9)), r)) if w["vis"] == "client" and r.random() < 0.35 else None
        self.ex("INSERT INTO work_item VALUES (" + ",".join("?" * 21) + ")",
                (wid, w["title"], w["type"], g["id"], w["case"], w["owner"], w["requester"], iso(created) if isinstance(created, dt.datetime) else created, due_s, cdl,
                 w["cons"], state, w["completion"], j(w["depends"]), esc, w["vis"], w["sla"], w["label"], None, None, 1))
        self.bump("work_item")
        cr_at = iso(created) if isinstance(created, dt.datetime) else created
        self.ex("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)", (wid, cr_at, w["requester"], "system", "Created in Compass"))
        if r.random() < 0.35:
            t1 = created + dt.timedelta(days=1) if isinstance(created, dt.datetime) else NOW - dt.timedelta(days=2)
            if t1 < NOW:
                self.ex("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)",
                        (wid, iso(t1), w["owner"], "message", r.choice(["Reminder sent to the client.", "Shared the checklist; waiting for the documents.", "Asked the team for the latest numbers.", "Picked up; will finish this week."])))
        if esc:
            self.ex("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)",
                    (wid, iso(min(NOW, due + dt.timedelta(days=2))), w["owner"], "ladder", "Reminder sent to the owner (ladder level 1)"))
        if state == "Done":
            self.audit.append((w["owner"], iso(min(NOW - dt.timedelta(hours=3), due + dt.timedelta(days=r.randint(-3, 1)) if isinstance(due, dt.datetime) else NOW - dt.timedelta(days=1))),
                               "complete_work_item", f"Completed: {w['title']}", [wid]))

    # ------------------------------------------------------------ 9. documents
    def documents(self, g):
        r = self.rng
        if g["seg"] == "SME" and r.random() < 0.6:
            return
        short = slug(g["stem"]).upper()
        rows = [(f"D-{short}-FY25", g["id"], "Annual report FY2024-25", "Annual report", "FY2024-25", "2025-03-31", "Consolidated" if g["seg"] == "Large" else "Standalone",
                 "INR crore", "Client upload", None, None, "Received", iso(NOW - dt.timedelta(days=r.randint(150, 330))))]
        if r.random() < 0.7:
            rows.append((f"D-{short}-SS", g["id"], f"Stock statement, {(NOW - dt.timedelta(days=45)).strftime('%B %Y')}", "Stock statement", "FY2026-27", day(month_end(NOW - dt.timedelta(days=45))),
                         None, "INR crore", "Client upload", None, None, "Received", iso(NOW - dt.timedelta(days=r.randint(8, 40)))))
        if g["trend"] != "flat":
            rows.append((f"D-{short}-RR", g["id"], f"{g['agency']} rating rationale", "Rating rationale", "FY2026-27", None, None, None, "Rating agency", None, None, "Received", iso(NOW - dt.timedelta(days=r.randint(20, 160)))))
        for d in rows:
            self.ex("INSERT INTO document (id,client_group_id,name,doc_type,fiscal_year,period_end,basis,unit,source,storage_path,page_count,status,uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", d)
            self.bump("document")

    # ------------------------------------------------------------ 10. market events, impacts, tasks
    def events(self):
        r = self.rng
        evs = []
        G = list(self.groups.values())

        def pub(days):
            return at_hour(NOW - dt.timedelta(days=days), r).replace(hour=r.choice([8, 11, 14, 17]))

        for g in G:                                         # rating actions that match the group's trend
            if g["trend"] != "flat" and r.random() < 0.8:
                up = g["trend"] == "up"
                verb = "upgrades" if up else "downgrades"
                sev = "Low" if up else r.choice(["Medium", "High"])
                days = r.randint(3, 120)
                abbr = "".join(w[0] for w in g["primary_name"].split()[:3]).upper()
                evs.append(("Rating action", f"{g['agency']} {verb} {g['primary_name']}'s long-term rating to {g['rating']} with {OUTLOOK[g['trend']]} outlook",
                            f"{g['agency']} {verb[:-1]}d the long-term bank facilities of {g['primary_name']} to '{g['rating']}/{OUTLOOK[g['trend']]}', citing "
                            f"{'a stronger order book and improved liquidity' if up else 'weaker liquidity and stretched working capital'}.",
                            f"{g['agency']}: rating rationale", f"RR/{abbr}/2026-27/{r.randint(100, 999):04d}", pub(days), sev, SEC_NAME(g["sector"]), [g["primary_name"]], [g["primary"]], None))
        for g in r.sample(G, k=min(8, len(G))):             # contract awards
            c = (g["cust"] or [None])[0]
            if c:
                amt = roundto(g["total"] * r.uniform(0.8, 2.5), 5) or 10
                evs.append(("Contract award", f"{g['primary_name']} bags {rs(amt)} order from {self.nodes[c]['name']}",
                            f"{g['primary_name']} informed the exchanges of an order worth about {rs(amt)} under Reg 30 disclosures. Execution is over 18 to 24 months.",
                            "BSE corporate announcements", f"BSE-ANN-{pub(0).strftime('%Y%m%d')}-{r.randint(100, 999):04d}", pub(r.randint(5, 100)), "Low", SEC_NAME(g["sector"]), [g["primary_name"]], [g["primary"]], None))
        for g in r.sample([x for x in G if x["seg"] != "SME"], k=min(6, len(G))):   # governance
            evs.append(("Governance", f"{g['primary_name']} appoints new Chief Financial Officer",
                        f"The company has appointed a new CFO with effect from {day(NOW - dt.timedelta(days=r.randint(3, 60)))}; the previous CFO has moved to an advisory role.",
                        "BSE corporate announcements", f"BSE-ANN-{pub(0).strftime('%Y%m%d')}-{r.randint(100, 999):04d}", pub(r.randint(3, 70)), "Medium", SEC_NAME(g["sector"]), [g["primary_name"]], [g["primary"]], None))
        shared = [n for pool in self.pool.values() for n in pool if n.startswith("e_cp_") and self.nodes[n]["type"] == "company"]
        linked = [n for n in shared if any(e[0] == n and e[2] == "supplies_to" for e in self.edges)]
        for n in r.sample(linked, k=min(10, len(linked))):  # charges on shared suppliers
            bank = r.choice(self.banks)
            amt = roundto(r.uniform(20, 140), 5)
            evs.append(("Charge registered", f"New charge of {rs(amt)} registered on {self.nodes[n]['name']}'s assets in favour of {self.nodes[bank]['name']}",
                        f"Form CHG-1 filed with the Registrar of Companies on {day(NOW - dt.timedelta(days=r.randint(4, 90)))}. Charge on current assets and plant. The filing does not say whether existing lenders consented.",
                        "MCA21 (Registrar of Companies)", f"Charge ID {r.randint(100200000, 100590000)}", pub(r.randint(4, 90)), "Medium", None,
                        [self.nodes[n]["name"].replace(" Pvt Ltd", " PRIVATE LIMITED").upper() if r.random() < 0.5 else self.nodes[n]["name"], self.nodes[bank]["name"]], [n, bank], f"CHG-{self.nodes[n]['name'][:6].upper()}"))
        for n in r.sample(linked, k=min(8, len(linked))):   # plant incidents and operations
            kind = r.choice([("Plant incident", "Fire at {n}'s unit; production halted for about {w} days", "High"),
                             ("Operations", "{n} reports a dispatch delay of about {w} days after a labour dispute", "Medium"),
                             ("Operations", "{n} shuts one line for maintenance for about {w} days", "Low")])
            w = r.randint(3, 21)
            nm = self.nodes[n]["name"]
            evs.append((kind[0], kind[1].format(n=nm, w=w), f"{nm} has told customers that dispatches will be affected for about {w} days.", "Regional business newswire (licensed feed)",
                        f"NW-{pub(0).strftime('%Y%m%d')}-{r.randint(100, 999):04d}", pub(r.randint(2, 75)), kind[2], None, [nm], [n], None))
        for sid in r.sample(list(SEC), k=8):                # sector moves
            ch = r.choice([-9, -6, -4, 5, 7, 11])
            evs.append(("Sector move", f"{SEC_NAME(sid)}: input prices {'fall' if ch < 0 else 'rise'} {abs(ch)}% in a month",
                        f"Industry data shows input prices in {SEC_NAME(sid).lower()} moved {ch}% over the last month; margins of mid-sized players are most exposed.",
                        "Industry data service", f"IDS-{pub(0).strftime('%Y%m')}-{r.randint(100, 999)}", pub(r.randint(3, 60)), "Low" if abs(ch) < 7 else "Medium", SEC_NAME(sid), [SEC_NAME(sid)], [sid], None))
        evs.sort(key=lambda e: e[5])
        down = {"High": "Medium", "Medium": "Low", "Low": "Low"}
        created = []
        for typ, head, summ, src, ref, pb, sev, sector, raw, resolved, cluster in evs:
            self.ev_no += 1
            eid = f"ME-{self.ev_no}"
            self.ex("INSERT INTO market_event VALUES (" + ",".join("?" * 14) + ")", (eid, typ, head, summ, src, ref, iso(pb), sev, sector, j(raw), cluster, "processed", iso(pb + dt.timedelta(minutes=r.randint(5, 40))), 0))
            self.bump("market_event")
            created.append((eid, typ, sev, pb, resolved))
        G_ = load_graph(self.con)
        for eid, typ, sev, pb, resolved in created:
            for nid in resolved:
                for rec in G_.impact_walk([nid], max_hops=2):
                    self.ex("INSERT INTO event_impact (event_id,node_id,client_group_id,hops,path,reason,impact_level,match_confidence) VALUES (?,?,?,?,?,?,?,?)",
                            (eid, nid, rec["group"], rec["hops"], j([dict(node=p[0], edge=p[1], dir=p[2]) for p in rec["path"]]), G_.describe(rec["path"]),
                             sev if rec["hops"] == 0 else down[sev], round(rec["conf"], 3)))
                    self.bump("event_impact")
        for eid, typ, sev, pb, resolved in created:         # tasks created by routing, only for recent, material events
            if sev == "Low" or pb < NOW - dt.timedelta(days=25):
                continue
            for user, t in route_event(self.con, [eid]).items():
                self.work_no += 1
                wid = f"W-{self.work_no}"
                created_at = pb + dt.timedelta(hours=1)
                due = created_at + dt.timedelta(hours=t["due_h"])
                state = r.choices(["Done", "Open", "In progress", "Accepted"], [45 if due < NOW else 5, 30, 15, 10])[0]
                if due > NOW and state == "Done":
                    state = "Open"
                self.ex("INSERT INTO work_item VALUES (" + ",".join("?" * 21) + ")",
                        (wid, t["title"], t["type"], t["clients"][0], None, user, user, iso(created_at), iso(due), None, plain_why(t["why"][0]), state,
                         "Reviewed and, if needed, followed up", "[]", 0, "internal", None, None, eid, j({"why": t["why"], "rules": t["rules"]}), 1))
                self.ex("INSERT INTO work_thread (work_item_id,at,by_user,kind,text) VALUES (?,?,?,?,?)", (wid, iso(created_at), user, "system", "Created by event routing"))
                self.bump("work_item_from_events")
                if state == "Done":
                    self.audit.append((user, iso(min(NOW, due - dt.timedelta(hours=r.randint(1, 20)))), "complete_work_item", f"Completed: {t['title']}", [wid]))

    # ------------------------------------------------------------ 11. history for thin hand-made groups
    def thin_groups(self):
        r = self.rng
        for gid, rm, cad, short in self.con.execute("SELECT id,rm_id,cadence_days,short_name FROM client_group WHERE has_detail=0 AND id NOT IN (%s)" %
                                                    ",".join("'%s'" % x for x in self.groups)).fetchall():
            have = self.con.execute("SELECT COUNT(*) FROM meeting WHERE client_group_id=?", (gid,)).fetchone()[0]
            persons = [x[0] for x in self.con.execute("SELECT id FROM node WHERE node_type='person' AND client_group_id=?", (gid,))]
            sector = {"g_corvina": "s_pharma", "g_delta": "s_food", "g_evergreen": "s_realty", "g_fulcrum": "s_auto", "g_granite": "s_cement",
                      "g_helix": "s_packaging", "g_kestrel": "s_chemicals", "g_astra": "s_logistics", "g_bluewater": "s_shipping", "g_nordholm": "s_auto"}.get(gid)
            if have >= 3 or not persons or sector is None:
                continue
            t = NOW - dt.timedelta(days=r.randint(40, 70))
            for i in range(3 - have):
                when = at_hour(t - dt.timedelta(days=int(cad * (i + 1) * r.uniform(0.8, 1.2))), r)
                text = " ".join([r.choice(GENERIC).format(p=r.randint(6, 25), u=r.randint(62, 90)), SECTOR_LINE[sector].format(p=r.randint(8, 30), u=r.randint(62, 90), m=r.randint(14, 30), q=r.randint(82, 112))])
                mid = f"mt_{slug(gid)[2:8]}_{when.strftime('%m%d')}"
                self.ex("INSERT INTO meeting VALUES (" + ",".join("?" * 17) + ")",
                        (mid, gid, "meeting", "Quarterly review", iso(when), 60, "Client office", j(persons[:1]), "held", None, None, None, None, text, "calendar", 1, None))
                self.bump("meeting")

    # ------------------------------------------------------------ 11b. last contact must match the meeting history
    def reconcile_last_contact(self):
        """A client's 'last contact' date is the date of its latest held meeting or call.
        Weekend dates are moved to a working day when meetings are created, so the two can drift by a day; hand-made
        clients also had contact dates with no meeting behind them. Fix both, without touching the random stream."""
        for gid, last in self.con.execute("SELECT id, last_contact FROM client_group").fetchall():
            row = self.con.execute("SELECT MAX(substr(starts_at,1,10)) FROM meeting WHERE client_group_id=? AND status='held'", (gid,)).fetchone()
            latest = row[0]
            if latest and latest > last:                      # a later meeting exists: contact is at least that recent
                self.ex("UPDATE client_group SET last_contact=? WHERE id=?", (latest, gid))
            elif latest != last:                              # contact recorded but no meeting behind it: add the call
                d = dt.datetime.fromisoformat(last)
                while d.weekday() >= 5:                       # calls happen on working days
                    d -= dt.timedelta(days=1)
                persons = [x[0] for x in self.con.execute("SELECT id FROM node WHERE node_type='person' AND client_group_id=? ORDER BY id", (gid,))]
                when = d.replace(hour=11, minute=30)
                self.ex("INSERT INTO meeting VALUES (" + ",".join("?" * 17) + ")",
                        (f"mtc_{gid[2:8]}_{d.strftime('%m%d')}", gid, "call", "Catch-up call", iso(when), 20, "Phone", j(persons[:1]), "held", None, None, None, None,
                         "Courtesy call. No new developments; business as usual.", "calendar", 1, None))
                self.ex("UPDATE client_group SET last_contact=? WHERE id=?", (day(d), gid))
                self.bump("meeting")

    # ------------------------------------------------------------ 12. audit trail
    def finish_audit(self):
        rows = [(r[1], r[2], r[3], r[4], r[7]) for r in self.con.execute("SELECT * FROM audit_log")]
        rows += [(at, uid, act, summ, j(aff)) for uid, at, act, summ, aff in self.audit]
        rows.sort(key=lambda x: x[0])
        self.ex("DELETE FROM audit_log")
        for i, (at, uid, act, summ, aff) in enumerate(rows, 1):
            self.ex("INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?)", (f"TXN-{i:06d}", at, uid, act, summ, None, None, aff))
        self.ex("UPDATE app_meta SET value=? WHERE key='audit_next'", (str(len(rows) + 1),))
        self.count["audit_log"] = len(rows)


def SEC_NAME(sid):
    names = dict(WO_SECTORS)
    return names[sid]


def SPECIALIST_FOR(prod):
    for ins in INSIGHTS:
        if ins["prod"] == prod:
            return SPECIALIST[ins["fam"]]
    return "u_arvind"


WO_SECTORS = []


def run(con, scale="full", seed=20261118):
    """Add the large book. scale: 'full' (about 120 new groups), 'lite' (about 30), 'base' (nothing)."""
    n = {"full": 120, "lite": 30}.get(scale, 0)
    if n == 0:
        return {}
    global WO_SECTORS
    WO_SECTORS = [(r[0], r[1]) for r in con.execute("SELECT id,name FROM node WHERE node_type='sector'")] + NEW_SECTORS
    X = Expander(con, random.Random(seed), n)
    X.staff()
    X.counterparties()
    X.clients()
    for g in X.groups.values():
        X.insert_group(g)
    for g in X.groups.values():
        X.links_and_facts(g)
    for g in X.groups.values():
        X.meetings(g)
    for g in X.groups.values():
        X.alerts(g)
    for g in X.groups.values():
        X.work(g)
        X.documents(g)
    X.events()
    X.thin_groups()
    X.reconcile_last_contact()
    X.finish_audit()
    con.execute("INSERT OR REPLACE INTO app_meta VALUES ('scale', ?)", (scale,))
    return X.count
