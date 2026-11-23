"""Check the built database like a data-quality gate.   python -m seed.validate"""
import json, os, re, sqlite3, sys
from . import ids, financials as fin
from .routing import route_event
from .build_db import DB_PATH, verify_pw

fails, passes = [], 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
    else:
        fails.append(f"{name} {detail}")


def main():
    c = sqlite3.connect(DB_PATH)
    q = lambda s, *a: c.execute(s, a).fetchall()
    check("foreign keys", q("PRAGMA foreign_key_check") == [])
    check("integrity", q("PRAGMA integrity_check") == [("ok",)])
    # identifiers
    for nid, a in q("SELECT id,attrs FROM node WHERE node_type IN ('company','person')"):
        a = json.loads(a)
        if "cin" in a: check(f"CIN {nid}", bool(ids.CIN_RE.match(a["cin"])), a["cin"])
        if "pan" in a: check(f"PAN {nid}", bool(ids.PAN_RE.match(a["pan"])), a["pan"])
        if "lei" in a: check(f"LEI {nid}", bool(ids.LEI_RE.match(a["lei"])) and ids.lei_ok(a["lei"]), a["lei"])
        if "din" in a: check(f"DIN {nid}", bool(ids.DIN_RE.match(a["din"])), a["din"])
    # limits tie to facilities
    for g, s, o, fs, fo in q("SELECT g.id,g.sanctioned_cr,g.outstanding_cr,SUM(f.sanctioned_cr),SUM(f.outstanding_cr) FROM client_group g JOIN facility f ON f.client_group_id=g.id GROUP BY g.id"):
        check(f"limits {g}", (s, o) == (fs, fo), f"{s}/{o} vs {fs}/{fo}")
        check(f"outstanding<=sanctioned {g}", o <= s)
    # logins
    users = q("SELECT username,password_hash FROM app_user WHERE can_login=1")
    check("5 login users", len(users) == 5, str(len(users)))
    check("demo password verifies", all(verify_pw("Demo@2026", h) for _, h in users))
    # edges
    check("no self edges", q("SELECT COUNT(*) FROM edge WHERE from_node=to_node")[0][0] == 0)
    check("member_of only own entities", q("SELECT COUNT(*) FROM edge e JOIN node n ON n.id=e.from_node WHERE e.edge_type='member_of' AND json_extract(n.attrs,'$.relationship')='counterparty'")[0][0] == 0)
    # statements tie out (printed figures = FY26 column, balance sheet balances)
    v = fin.vantage()
    for name, d in (("vantage", v), ("meridian", fin.meridian())):
        check(f"{name} fixtures", True)
    doc = "D-VIP-FY26"
    L = {r[0]: r for r in q("SELECT line_code,fy_current,printed_current,confidence FROM spread_line WHERE document_id=?", doc)}
    fx = {x[0]: x for x in v["lines"]}
    check("Vantage lines read from the PDF match the statements", all(abs(r[1] - fx[k][3]) < .005 for k, r in L.items()) and len(L) == len(fx), str(len(L)))
    check("Vantage PDF read has full confidence and no planted errors", all(r[1] == r[2] and r[3] >= 97 for r in L.values()))
    for d in ("D-VIP-FY26", "D-MER-FY26"):
        rows = q("SELECT printed_current,line_code,statement,label FROM spread_line WHERE document_id=?", d)
        check(f"{d} has lines", len(rows) > 15)
    # hero routing
    t = route_event(c, ["ME-1101", "ME-1102"])
    check("hero recipients", set(t) == {"u_rohan", "u_karan", "u_kavita", "u_ananya", "u_meera", "u_miu"}, str(sorted(t)))
    check("every task has a why", all(x["why"] for x in t.values()))
    check("hero events still pending", q("SELECT COUNT(*) FROM market_event WHERE status='pending'")[0][0] == 2)
    check("processed events have impacts", q("SELECT COUNT(*) FROM market_event m WHERE status='processed' AND NOT EXISTS (SELECT 1 FROM event_impact i WHERE i.event_id=m.id)")[0][0] <= 3)
    # alerts
    check("alert states", {r[0] for r in q("SELECT DISTINCT state FROM alert")} <= {"New", "Under review", "Responded", "Resolved"})
    check("resolved alerts carry a reason", q("SELECT COUNT(*) FROM alert WHERE state='Resolved' AND (resolution_reason IS NULL OR resolved_at IS NULL)")[0][0] == 0)
    # ---- size and shape of the expanded book
    n_groups = q("SELECT COUNT(*) FROM client_group")[0][0]
    if n_groups > 20:
        check("at least 100 client groups", n_groups >= 100, str(n_groups))
        books = [r[1] for r in q("SELECT rm_id,COUNT(*) FROM client_group GROUP BY rm_id")]
        check("RM books between 8 and 45 groups", min(books) >= 8 and max(books) <= 45, str(books))
        check("every group has a primary company node", q("SELECT COUNT(*) FROM client_group g LEFT JOIN node n ON n.id=g.primary_node_id WHERE n.id IS NULL")[0][0] == 0)
        check("every group has an RM who exists", q("SELECT COUNT(*) FROM client_group g LEFT JOIN app_user u ON u.id=g.rm_id WHERE u.id IS NULL")[0][0] == 0)
        check("every group has facilities", q("SELECT COUNT(*) FROM client_group g WHERE NOT EXISTS (SELECT 1 FROM facility f WHERE f.client_group_id=g.id)")[0][0] == 0)
        check("every group has meetings", q("SELECT COUNT(*) FROM client_group g WHERE NOT EXISTS (SELECT 1 FROM meeting m WHERE m.client_group_id=g.id)")[0][0] == 0)
        check("every group has facts", q("SELECT COUNT(*) FROM client_group g WHERE NOT EXISTS (SELECT 1 FROM fact f WHERE f.client_group_id=g.id)")[0][0] == 0)
        for col in ("cin", "pan", "lei", "din"):
            vals = [json.loads(a).get(col) for (a,) in q("SELECT attrs FROM node")]
            vals = [x for x in vals if x]
            check(f"{col.upper()} values are unique", len(vals) == len(set(vals)), f"{len(vals)} vs {len(set(vals))}")
        check("every need has a specialist and a family node", q("SELECT COUNT(*) FROM need n WHERE specialist_id IS NULL OR NOT EXISTS (SELECT 1 FROM edge e WHERE e.from_node=n.id AND e.edge_type='in_family')")[0][0] == 0)
        check("processed events all have impacts", q("SELECT COUNT(*) FROM market_event m WHERE status='processed' AND NOT EXISTS (SELECT 1 FROM event_impact i WHERE i.event_id=m.id)")[0][0] <= 12)
        check("work due dates present and ordered after creation", q("SELECT COUNT(*) FROM work_item WHERE due_at IS NULL OR substr(due_at,1,10) < substr(created_at,1,10)")[0][0] <= 3,
              str(q("SELECT id,created_at,due_at FROM work_item WHERE substr(due_at,1,10) < substr(created_at,1,10) LIMIT 5")))
        check("no meeting is scheduled in the past", q("SELECT COUNT(*) FROM meeting WHERE status='scheduled' AND starts_at < ?", "2026-11-17")[0][0] <= 1)
        check("tier matches segment", q("SELECT COUNT(*) FROM client_group WHERE (segment LIKE 'Large%' AND tier<>1) OR (segment='SME' AND tier<>3)")[0][0] == 0)
        check("outstanding never above sanctioned", q("SELECT COUNT(*) FROM facility WHERE outstanding_cr > sanctioned_cr")[0][0] == 0)
        check("audit trail is in time order", [r[0] for r in q("SELECT at FROM audit_log ORDER BY txn_id")] == sorted(r[0] for r in q("SELECT at FROM audit_log")))
    check("work states valid", all(r[0] in ("Open", "Accepted", "In progress", "Needs information", "Done", "Cancelled") for r in q("SELECT DISTINCT state FROM work_item")))
    # ---- real-world news layer
    real = q("SELECT id,source_ref,source_name,published_at FROM market_event WHERE id LIKE 'ME-R%' OR id='ME-1006'")
    check("12 real news events present", len(real) == 12, str(len(real)))
    check("every real event has a link, publisher and date", all(r[1].startswith("https://") and r[2] and r[3] for r in real))
    check("every linked fact has a publisher and a date", q("SELECT COUNT(*) FROM fact WHERE source_ref LIKE 'https://%' AND (source_name IS NULL OR source_date IS NULL OR connector<>'news-feed')")[0][0] == 0)
    check("real facts exist for clients", q("SELECT COUNT(*) FROM fact WHERE connector='news-feed' AND source_ref LIKE 'https://%'")[0][0] > 100)
    check("no invented sector-price events remain", q("SELECT COUNT(*) FROM market_event WHERE event_type='Sector move' AND source_ref NOT LIKE 'https://%'")[0][0] == 0)
    names = [r[0] for r in q("SELECT name FROM node WHERE node_type IN ('company','client_group')")]
    check("real events never name a made-up company", not any(n.lower() in (e[0] + " " + e[1]).lower() for n in names for e in q("SELECT headline,summary FROM market_event WHERE id LIKE 'ME-R%'")))
    check("real news dates are not in the future of the demo day", all(r[3] <= "2026-11-17" for r in real))
    check("hero events are still fictional and pending", q("SELECT COUNT(*) FROM market_event WHERE is_hero=1 AND status='pending' AND source_ref NOT LIKE 'https://%'")[0][0] == 2)
    print(f"{passes} checks passed, {len(fails)} failed")
    for f in fails: print("  FAIL", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
