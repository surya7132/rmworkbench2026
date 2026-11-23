"""Real-world news layer.

Adds public, dated, linkable news items to the synthetic book and ties them to
clients through sectors and facility data.

What is real here
  * the news items: publisher, date, link and the facts quoted from them
What stays synthetic
  * every client, company, person, facility and meeting

Rules we follow
  * Every item below was opened and read on 19 Nov 2026; figures are copied from
    the page, nothing is rounded up or guessed.
  * A real event is never attached to a made-up company. It is attached to a
    SECTOR (or to the whole economy) and reaches clients through the graph.
  * Each item keeps its publisher, date and link (source_ref) so an RM can click through.
  * The two hero events (fire and charge at Steelco) stay fictional on purpose.

Run order: build_db -> expand -> realworld.   Standard library only.
"""
import csv
import json
import os

from .routing import load_graph

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "real_world_sources.csv")
j = lambda x: json.dumps(x, ensure_ascii=False)

ALL = "ALL"
EXPORTERS = {"Textiles and apparel", "Pharmaceuticals", "Auto components", "Chemicals", "IT and business services", "Agri and commodities", "Steel and metals"}

# id, replaces, type, severity, sectors, headline, summary, publisher, url, published (IST)
ITEMS = [
    dict(id="ME-R01", type="Policy rate", sev="Medium", sectors=ALL, pub="2026-10-07T10:00:00+05:30",
         head="RBI raises the repo rate by 25 bps to 5.50% and moves to a calibrated tightening stance",
         summ="The Monetary Policy Committee voted unanimously to raise the policy repo rate to 5.50%. The standing deposit facility rate is 5.25% and the MSF and Bank Rate are 5.75%. "
              "Two members preferred a neutral stance. The RBI projects FY2026-27 real GDP growth of 7.1% and CPI inflation of 5.2%.",
         pub_name="Reserve Bank of India: Monetary Policy Committee resolution, 5 to 7 October 2026", url="https://rbi.org.in/scriptS/BS_PressReleaseDisplay.aspx?prid=63742"),
    dict(id="ME-R02", type="Currency", sev="Medium", sectors=ALL, pub="2026-10-08T13:36:00+05:30",
         head="Rupee trades near its record low of about 97 per dollar as RBI defences weaken",
         summ="The rupee was at about 96.68 to 97 per US dollar on 8 October, 0.2% from its record low of 96.97 set in May 2026, and down more than 7% in 2026. "
              "Forex reserves were $734 billion in the week to 2 October, down from a record $785 billion in the week to 4 September.",
         pub_name="Business Today", url="https://www.businesstoday.in/latest/economy/story/rupee-near-record-low-why-rbis-multiple-defences-are-losing-effectiveness-560381-2026-10-08"),
    dict(id="ME-R03", type="Macro", sev="Low", sectors=["Steel and metals", "Cement", "EPC and infrastructure", "Auto components", "Real estate"], pub="2026-08-31T17:30:00+05:30",
         head="India's economy grew 7.8% in April to June 2026, helped by manufacturing and investment",
         summ="Real GDP grew 7.8% in Q1 FY27 and GVA grew 8.2%. Manufacturing grew 9.2% and gross fixed capital formation grew 11.9%. "
              "Financial services, real estate, IT and professional services grew 12.1%. Capex of the Centre, states and public-sector companies grew 16.9%.",
         pub_name="Business Today", url="https://www.businesstoday.in/amp/latest/economy/story/capital-formation-and-exports-boost-q1fy27-gdp-growth-to-7-8-552372-2026-08-31"),
    dict(id="ME-R04", type="Bank results", sev="Low", sectors=[], pub="2026-10-12T17:06:00+05:30",
         head="RBL Bank reports Q2 FY27 net profit of Rs 482 crore, up 170%",
         summ="For the quarter ended 30 September 2026: net interest income Rs 2,131 crore (up 37%), net interest margin 4.61%, net advances Rs 142,314 crore (up 42%) with a retail to wholesale mix of 56:44, "
              "deposits Rs 156,272 crore (up 34%), gross NPA 1.02% and net NPA 0.29%.",
         pub_name="Free Press Journal", url="https://www.freepressjournal.in/business/rbl-banks-net-profit-surges-170-to-482-crore-in-q2-fy27"),
    dict(id="ME-R05", type="Regulation", sev="Low", sectors=[], pub="2026-03-10T10:00:00+05:30",
         head="RBI credit facilities amendment directions for commercial banks, effective 1 April 2026",
         summ="Banks may finance acquisitions subject to safeguards; bridge finance is formally defined; credit to capital market intermediaries must be fully secured; "
              "directors with a stake in a proposed facility must step back from decisions and related-party exposures face closer monitoring. Existing facilities run to maturity but renewals and enhancements must comply.",
         pub_name="Mondaq (law firm summary of the RBI directions)", url="https://www.mondaq.com/india/financial-services/1756084/rbi-commercial-banks-credit-facilities-amendment-directions-2026-re-shaping-the-prudential-framework-for-bank-lending"),
    dict(id="ME-R06", type="Trade policy", sev="Medium", sectors=["Textiles and apparel"], pub="2026-11-11T09:00:00+05:30",
         head="Indian garment makers cut reliance on the US after the tariff shock",
         summ="Textile, apparel and home-furnishing exports to the US fell 9.8% to $4.0 billion in April to August while shipments to other markets rose 3.7% to $15.2 billion. "
              "The US share of India's exports fell to 25.4% by end-August. Exporters are moving sales to the UK, the EU and the UAE; Indian clothing has duty-free access to Britain under a trade deal effective July.",
         pub_name="Reuters, via The Star", url="https://www.thestar.com.my/news/world/2026/11/11/india-garment-makers-rethink-reliance-on-us-after-tariff-shock"),
    dict(id="ME-R07", type="Sector move", sev="Medium", sectors=["Shipping", "Logistics"], pub="2026-11-09T15:31:00+05:30",
         head="West Asia crisis lifts tanker freight to India almost five times",
         summ="Freight for Gulf crude from Fujairah to India's west coast rose from $1.57 a barrel in late February to $7.51 in October. Voyages around the Cape add 3,500 to 4,000 nautical miles and 10 to 14 sailing days, "
              "war-risk premiums are higher and India's crude imports hit a record 5.6 million barrels a day in October.",
         pub_name="ThePrint", url="https://theprint.in/economy/west-asia-crisis-hits-indias-gulf-oil-shipping-edge-tanker-freight-costs-up-5x-all-eyes-on-hormuz/3092205/"),
    dict(id="ME-R08", type="Sector move", sev="Low", sectors=["Cement", "EPC and infrastructure", "Real estate"], pub="2026-10-16T10:00:00+05:30",
         head="Cement prices likely to rise Rs 10 to 15 a bag from mid-October",
         summ="Emkay Research expects a price increase of Rs 10 to 15 a bag from 12 October as power and fuel costs have raised input costs by Rs 300 to 400 a tonne over six to seven months. "
              "Industry volumes are expected to grow 7 to 8% in the first half of FY27.",
         pub_name="Construction World (citing Emkay Research)", url="https://www.constructionworld.in/cement-news/cement-prices-likely-to-rise-rs.-10-15-per-bag-from-mid-october/98923"),
    dict(id="ME-1006", type="Sector move", sev="Low", sectors=["Steel and metals", "EPC and infrastructure"], pub="2026-10-21T13:59:00+05:30",
         head="Indian steel prices firm after the festive break",
         summ="On 21 October Raipur rebar was Rs 51,500 a tonne (up Rs 200), Mumbai rebar Rs 53,000 (unchanged), Raipur sponge iron Rs 28,200 (up Rs 500) and Mandi billet Rs 47,000 (up Rs 200). "
              "The market was described as mostly firm as trading resumed after Dussehra and Navratri.",
         pub_name="SMM Steel", url="https://news.metal.com/newscontent/104171317-smm-steel-indian-domestic-steel-prices-firm-after-festive-break"),
    dict(id="ME-R09", type="Trade policy", sev="Medium", sectors=["Pharmaceuticals"], pub="2026-09-29T10:00:00+05:30",
         head="US 100% tariff on patented drugs phases in; generics are not covered",
         summ="The US Section 232 tariff of 100% on specified patented pharmaceuticals and their ingredients took effect for the next group of companies on 29 September. "
              "Generic drugs and their ingredients are outside the tariff, and India is one of 20 jurisdictions eligible for zero duty on listed speciality categories such as orphan drugs and plasma-derived therapies.",
         pub_name="Business Standard", url="https://www.business-standard.com/world-news/trump-100-percent-pharma-tariff-india-select-drugs-exemption-126092900121_1.html"),
    dict(id="ME-R10", type="Sector move", sev="Low", sectors=["Real estate"], pub="2026-09-29T10:00:00+05:30",
         head="Housing sales in top seven cities rise 3% in July to September; unsold stock up 12%",
         summ="Anarock Research data: about 100,220 units sold (up 3%), about 114,320 new launches (up 18%) and about 630,590 unsold units at the end of the quarter (up 12%). "
              "Mumbai region led with about 31,750 units sold.",
         pub_name="Business Today (citing Anarock Research)", url="https://www.businesstoday.in/real-estate/story/housing-sales-in-top-seven-cities-rise-3-percent-on-year-in-q3-mumbai-records-highest-sales-558274-2026-09-29"),
    dict(id="ME-R11", type="Sector move", sev="Medium", sectors=["EPC and infrastructure"], pub="2026-03-31T10:00:00+05:30",
         head="ICRA: road construction likely to moderate to 9,000 to 9,500 km in FY2027 as awarding stays subdued",
         summ="ICRA expects road construction of 9,000 to 9,500 km in FY2027. It points to a declining order book, weaker revenue visibility and the need for a meaningful pick-up in awards from the road ministry, "
              "while asset monetisation stayed strong with Rs 28,078 crore in FY2026.",
         pub_name="ICRA Ratings", url="https://www.icra.in/Research/ViewResearchReport/road-construction-likely-to-moderate-to-9-000-9-500-km-in-fy2027-as-subdued-project-awarding-activity-dampens-construction-visibility/6874"),
]
DOWN = {"High": "Medium", "Medium": "Low", "Low": "Low"}


def rs(x):
    return f"Rs {x:,.0f} cr" if x >= 100 else f"Rs {x:,.1f} cr"


def run(con):
    ex = con.execute
    q = lambda s, *a: ex(s, a).fetchall()
    sec_id = {n: i for i, n in q("SELECT id,name FROM node WHERE node_type='sector'")}
    groups = {r[0]: dict(id=r[0], short=r[1], sector=r[2], node=r[3]) for r in q("SELECT id,short_name,sector,primary_node_id FROM client_group")}

    # 1. remove the invented sector-price events (made-up percentages); real items replace them
    old = [r[0] for r in q("SELECT id FROM market_event WHERE event_type='Sector move' AND id LIKE 'ME-12%' AND is_hero=0")]
    for t in ("event_impact",):
        ex(f"DELETE FROM {t} WHERE event_id IN ({','.join('?' * len(old))})", old) if old else None
    if old:
        ex(f"DELETE FROM market_event WHERE id IN ({','.join('?' * len(old))})", old)
    ex("DELETE FROM event_impact WHERE event_id='ME-1006'")
    ex("DELETE FROM market_event WHERE id='ME-1006'")

    # 2. insert the real events and compute who they reach
    G = load_graph(con)
    rows = []
    for it in ITEMS:
        names = list(sec_id) if it["sectors"] == ALL else it["sectors"]
        sector_label = None if it["sectors"] in (ALL, []) else (it["sectors"][0] if len(it["sectors"]) == 1 else ", ".join(it["sectors"]))
        ex("INSERT INTO market_event VALUES (" + ",".join("?" * 14) + ")",
           (it["id"], it["type"], it["head"], it["summ"], it["pub_name"], it["url"], it["pub"], it["sev"], sector_label,
            j(names if it["sectors"] != [] else []), None, "processed", it["pub"], 0))
        reached = {}
        for n in (names if it["sectors"] != [] else []):
            for rec in G.impact_walk([sec_id[n]], max_hops=0 if it["sectors"] == ALL else 2):
                if rec["group"] not in reached or rec["hops"] < reached[rec["group"]][0]["hops"]:
                    reached[rec["group"]] = (rec, sec_id[n])
        for gid, (rec, nid) in reached.items():
            ex("INSERT INTO event_impact (event_id,node_id,client_group_id,hops,path,reason,impact_level,match_confidence) VALUES (?,?,?,?,?,?,?,?)",
               (it["id"], nid, gid, rec["hops"], j([dict(node=p[0], edge=p[1], dir=p[2]) for p in rec["path"]]), G.describe(rec["path"]),
                it["sev"] if rec["hops"] == 0 else DOWN[it["sev"]], round(rec["conf"], 3)))
        rows.append((it, len(reached)))

    # 3. client-level facts that tie each news item to the client's own facility data
    next_no = max(int(r[0][2:]) for r in q("SELECT id FROM fact WHERE id GLOB 'F-[0-9]*'")) + 1
    fact_of = {}                                        # (item id, group) -> fact id
    exposure = {r[0]: r for r in q("SELECT client_group_id, "
                                   "SUM(CASE WHEN pricing LIKE '%RLLR%' OR pricing LIKE '%floating%' OR pricing LIKE '%grid%' THEN outstanding_cr ELSE 0 END), "
                                   "SUM(CASE WHEN facility_type LIKE '%PCFC%' OR facility_type LIKE '%Forward%' OR facility_type LIKE '%Letter of Credit%' THEN sanctioned_cr ELSE 0 END), "
                                   "SUM(sanctioned_cr) FROM facility GROUP BY client_group_id")}
    by_item = {it["id"]: it for it in ITEMS}

    def add(item_id, gid, stmt):
        nonlocal next_no
        it = by_item[item_id]
        fid = f"F-{next_no}"
        next_no += 1
        ex("INSERT INTO fact VALUES (" + ",".join("?" * 15) + ")",
           (fid, gid, groups[gid]["node"], stmt, None, None, it["pub_name"], it["url"], it["pub"][:10], None, "ext", "discuss", 1.0, None, "news-feed"))
        fact_of[(item_id, gid)] = fid

    for gid, g in groups.items():
        _, floating, fx_lines, total = exposure[gid]
        sec, s = g["sector"], g["short"]
        if floating > 0:
            add("ME-R01", gid, f"RBI raised the repo rate by 25 bps to 5.50% on 7 Oct 2026 and moved to calibrated tightening. About {rs(floating)} of {s}'s outstanding is floating-rate and reprices at the next reset (exposure from the limits system).")
        if fx_lines > 0 or sec in EXPORTERS:
            tail = (f"{s} has {rs(fx_lines)} of forex-linked lines (packing credit, forward contracts, letters of credit) with RBL." if fx_lines > 0
                    else f"{s} is in an export-linked sector and has no forex lines with RBL yet.")
            add("ME-R02", gid, f"The rupee is about 96.7 to 97 per US dollar, near its record low (Business Today, 8 Oct 2026). {tail}")
        if sec == "Textiles and apparel":
            add("ME-R06", gid, f"US share of India's textile, apparel and home-furnishing exports fell to 25.4% by end-August; exporters are shifting sales to the UK, EU and UAE (Reuters, 11 Nov 2026). {s} has {rs(total)} of limits with RBL; ask about its US share of sales and new-market orders.")
        if sec in ("Shipping", "Logistics"):
            add("ME-R07", gid, f"Tanker freight on the Gulf to India west coast route rose from $1.57 to $7.51 a barrel between February and October 2026, and Cape diversions add 10 to 14 sailing days (ThePrint, 9 Nov 2026). {s} has {rs(total)} of limits with RBL.")
        if sec in ("Cement", "EPC and infrastructure", "Real estate"):
            add("ME-R08", gid, f"Emkay Research expects cement prices to rise Rs 10 to 15 a bag from mid-October on higher power and fuel costs (Construction World, 16 Oct 2026). "
                               f"{'Margin and pricing context for ' if sec == 'Cement' else 'Input cost context for '}{s}.")
        if sec in ("Steel and metals", "EPC and infrastructure"):
            add("ME-1006", gid, f"Indian steel prices were mostly firm on 21 Oct 2026: Raipur rebar Rs 51,500 a tonne, Mumbai rebar Rs 53,000 (SMM Steel). {'Input cost context' if sec == 'EPC and infrastructure' else 'Realisation context'} for {s}.")
        if sec == "Pharmaceuticals":
            add("ME-R09", gid, f"The US 100% tariff on patented drugs phased in on 29 Sep 2026; generics and their ingredients are not covered (Business Standard). Check whether {s} sells any patented or speciality products into the US.")
        if sec == "Real estate":
            add("ME-R10", gid, f"Top seven cities sold about 100,220 homes in July to September 2026 (up 3%) while unsold stock rose 12% to about 630,590 units (Anarock via Business Today, 29 Sep 2026). Market context for {s}.")
        if sec == "EPC and infrastructure":
            add("ME-R11", gid, f"ICRA expects road construction to moderate to 9,000 to 9,500 km in FY2027 as awarding stays subdued (ICRA, 31 Mar 2026). Order-book context for {s}.")

    # 4. link the news facts to needs that grew out of the same topic
    linked = 0
    for nid, gid, origin, fids, sector in q("SELECT n.id,n.client_group_id,n.origin,n.fact_ids,g.sector FROM need n JOIN client_group g ON g.id=n.client_group_id"):
        extra = []
        if origin.startswith("Meeting: fx"):
            extra.append(("ME-R02", "rupee near record low"))
        elif origin.startswith("Meeting: refi"):
            extra.append(("ME-R01", "repo rate raised"))
        elif origin.startswith("Meeting: export") and sector == "Textiles and apparel":
            extra.append(("ME-R06", "US tariff shift"))
        for item_id, label in extra:
            fid = fact_of.get((item_id, gid))
            if fid:
                ex("UPDATE need SET fact_ids=?, origin=? WHERE id=?", (j(json.loads(fids) + [fid]), origin + f"; backed by news: {label} ({fid})", nid))
                linked += 1

    # 5. provenance file and notice
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["event_id", "published_ist", "publisher", "event_type", "headline", "sectors_reached", "clients_reached", "client_facts_added", "link"])
        for it, n in rows:
            w.writerow([it["id"], it["pub"], it["pub_name"], it["type"], it["head"], "all sectors" if it["sectors"] == ALL else "; ".join(it["sectors"]) or "bank-level (no client link)", n,
                        sum(1 for k in fact_of if k[0] == it["id"]), it["url"]])
    ex("UPDATE app_meta SET value=? WHERE key='data_notice'",
       ("Clients, companies, people, facilities and meetings are synthetic. News items with a publisher, date and link (events ME-R01 onward and ME-1006) are real public reports; "
        "the Steelco fire and charge are fictional.",))
    ex("INSERT OR REPLACE INTO app_meta VALUES ('real_news_items', ?)", (str(len(ITEMS)),))
    return dict(real_events=len(ITEMS), removed_synthetic_events=len(old) + 1, real_client_facts=len(fact_of), needs_linked=linked)
