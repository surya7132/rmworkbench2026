"""Step 5 checks: early-warning triage (accept, respond, resolve, dismiss), priorities, access, audit.
Run:  python tests/test_alerts.py"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import fastapi  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.join(ROOT, "tests", "shim"))
os.environ["COMPASS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

from tests.asgi_client import Client  # noqa: E402
from app.main import app  # noqa: E402
from app import db  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        FAILS.append(name)


def login(user):
    c = Client(app)
    c.post("/login", {"username": user, "password": "Demo@2026"})
    return c


def q(sql, *a):
    with db.connection() as conn:
        return conn.execute(sql, a).fetchall()


H = {"HX-Target": "alerts-list"}
cards = lambda t: re.findall(r'id="a-([^"]+)"', t)

check("alerts need login", Client(app).get("/alerts").status == 303)
rohan = login("rohan.rm")
pg = rohan.get("/alerts")
check("page loads with tiles and filters", pg.status == 200 and "Early warnings" in pg.text and "Everything open" in pg.text and 'data-v="P1"' in pg.text)
check("sidebar: no menu item says Soon", pg.text.count(">Soon<") == 0)
check("24 open alerts for Rohan (20 new, 2 under review, 2 responded)", len(cards(pg.text)) == 24)
check("P1 comes before P2 before P3", pg.text.index(">P1<") < pg.text.index(">P2<") < pg.text.index(">P3<"))
check("filter pills are driven by Alpine state", "x-model=\"state\"" in pg.text and ":class=\"state === $el.dataset.v" in pg.text and "x-model=\"prio\"" in pg.text)
check("to-triage filter", len(cards(rohan.get("/alerts?state=New", headers=H).text)) == 20)
check("resolved filter", len(cards(rohan.get("/alerts?state=Resolved", headers=H).text)) == q("SELECT COUNT(*) FROM alert a JOIN client_group g ON g.id=a.client_group_id WHERE g.rm_id='u_rohan' AND a.state='Resolved'")[0][0])
p1 = cards(rohan.get("/alerts?prio=P1", headers=H).text)
check("P1 filter shows only High alerts", p1 and all(q("SELECT severity FROM alert WHERE id=?", i)[0][0] == "High" for i in p1))
check("search finds a client's warning", "a_e1" in cards(rohan.get("/alerts?q=evergreen", headers=H).text))
check("category filter", all(q("SELECT category FROM alert WHERE id=?", i)[0][0] == "Covenant" for i in cards(rohan.get("/alerts?category=Covenant", headers=H).text)))
tiles = rohan.get("/alerts/tiles").text
check("tiles endpoint returns counts", "still to triage" in tiles and "Act today" in tiles)

# accept: creates a task when none is open, but never a duplicate
w0 = q("SELECT COUNT(*) FROM work_item")[0][0]
au0 = q("SELECT COUNT(*) FROM audit_log")[0][0]
r = rohan.post("/alerts/a_probhenrt/accept")
check("accept returns the card in 'Under review' and asks tiles to refresh", r.status == 200 and "Under review" in r.text and r.headers.get("hx-trigger") == "alerts-changed")
check("alert state is Under review", q("SELECT state FROM alert WHERE id='a_probhenrt'")[0][0] == "Under review")
pt = q("SELECT id,owner_id,work_type,due_at,why_path FROM work_item WHERE case_ref='a_probhenrt' AND created_at LIKE '2026-11-17T09:10%'")
check("a task was created for the client's RM, linked to the alert", q("SELECT COUNT(*) FROM work_item")[0][0] == w0 + 1 and len(pt) == 1 and pt[0][1] == "u_rohan" and pt[0][2] == "task" and "alert" in pt[0][4])
check("P1 task is due in one day (18 Nov)", pt[0][3].startswith("2026-11-18"), pt[0][3])
check("one audit entry for accept", q("SELECT COUNT(*) FROM audit_log")[0][0] == au0 + 1)
check("task shows in the work queue under 'From alerts'", pt[0][0] in rohan.get("/work?kind=alerts").text)
check("accepting twice is refused with a clear message", "is now" in rohan.post("/alerts/a_probhenrt/accept").text)

# accept on an alert that already has open tasks: no duplicate
w1 = q("SELECT COUNT(*) FROM work_item")[0][0]
rohan.post("/alerts/a_n1/accept")
check("accept on an alert with open tasks moves the state but creates no duplicate", q("SELECT state FROM alert WHERE id='a_n1'")[0][0] == "Under review" and q("SELECT COUNT(*) FROM work_item")[0][0] == w1)
check("the audit entry says it linked to the existing tasks", "Linked to existing tasks W-3001, W-3002" in q("SELECT summary FROM audit_log WHERE affected LIKE '%\"a_n1\"%' ORDER BY txn_id DESC LIMIT 1")[0][0])
nw = q("SELECT id FROM work_item WHERE case_ref='a_n1' AND state IN ('Open','Accepted','In progress','Needs information') ORDER BY id DESC LIMIT 1")[0]

# respond
check("respond needs a note", "Write what you did" in rohan.post("/alerts/a_n1/respond", {"note": " "}).text and q("SELECT state FROM alert WHERE id='a_n1'")[0][0] == "Under review")
rohan.post("/alerts/a_n1/respond", {"note": "Controller sent the ageing by customer."})
check("respond moves to Responded", q("SELECT state FROM alert WHERE id='a_n1'")[0][0] == "Responded")
check("response is written on the open linked task", any("Controller sent the ageing" in t[0] for t in q("SELECT text FROM work_thread WHERE work_item_id=?", nw[0])))

# resolve
check("resolve needs a reason", "Pick a reason" in rohan.post("/alerts/a_n1/resolve", {"reason": ""}).text)
check("'Other' needs a note", "Say what the reason is" in rohan.post("/alerts/a_n1/resolve", {"reason": "Other"}).text)
rr = rohan.post("/alerts/a_n1/resolve", {"reason": "Documents or payment received", "note": "Ageing reviewed by Credit"})
a = q("SELECT state,resolution_reason,resolved_by,resolved_at FROM alert WHERE id='a_n1'")[0]
check("resolved with reason, person and time", a[0] == "Resolved" and "Documents or payment received: Ageing reviewed by Credit" == a[1] and a[2] == "u_rohan" and a[3])
check("card shows the closing reason", "Closed." in rr.text)
check("resolved alert has no more buttons", ">Accept<" not in rr.text and ">Resolve<" not in rr.text)
hist = rohan.get("/alerts?state=Resolved", headers=H).text
check("history lists the moves with who and when", "Under review to Responded" in hist and "Rohan Deshmukh" in hist and q("SELECT COUNT(*) FROM audit_log WHERE affected LIKE '%\"a_n1\"%'")[0][0] == 3)

# dismiss
check("dismiss needs a reason", "Pick a reason" in rohan.post("/alerts/a_m1/dismiss", {"reason": ""}).text and q("SELECT state FROM alert WHERE id='a_m1'")[0][0] == "New")
rohan.post("/alerts/a_m1/dismiss", {"reason": "Not material", "note": ""})
check("dismiss closes the alert with the reason", tuple(q("SELECT state,resolution_reason FROM alert WHERE id='a_m1'")[0]) == ("Resolved", "Not material"))
check("cannot reopen a resolved alert", "Someone else" in rohan.post("/alerts/a_m1/reopen").text or "is now" in rohan.post("/alerts/a_m1/reopen").text)

# reopen from Responded
rohan.post("/alerts/a_f1/accept"); rohan.post("/alerts/a_f1/respond", {"note": "Asked the finance head"})
rohan.post("/alerts/a_f1/reopen")
check("back to review works from Responded", q("SELECT state FROM alert WHERE id='a_f1'")[0][0] == "Under review")

# access
karan = login("karan.rm")
check("another RM cannot act on Rohan's alert", karan.post("/alerts/a_e1/accept").status == 403 and q("SELECT state FROM alert WHERE id='a_e1'")[0][0] == "New")
check("unknown alert is 404", rohan.post("/alerts/NOPE/accept").status == 404)
meera = login("meera.lead")
check("team lead sees the whole team's alerts", len(cards(meera.get("/alerts").text)) > len(cards(rohan.get("/alerts").text)))
check("team lead can act on a report's alert", meera.post("/alerts/a_e1/accept").status == 200 and q("SELECT state FROM alert WHERE id='a_e1'")[0][0] == "Under review"
      and q("SELECT owner_id FROM work_item WHERE case_ref='a_e1' ORDER BY id DESC LIMIT 1")[0][0] == "u_rohan")
check("tiles reflect the changes (fewer to triage)", "still to triage" in rohan.get("/alerts/tiles").text)

print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
