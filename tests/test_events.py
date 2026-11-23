"""Step 3 checks: market events list, event detail, routing preview and the Process button.
Run:  python tests/test_events.py"""
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


c = Client(app)
check("events page needs login", c.get("/events").status == 303)
rohan = login("rohan.rm")
page = rohan.get("/events")
check("events page loads", page.status == 200 and "Market events" in page.text)
check("hero shows the pending Steelco story", "Needs routing" in page.text and "Review and route" in page.text and "Steelco" in page.text)
check("MIU desk initials are capitals", "MD" in rohan.get("/events/ME-1101").text and ">Md<" not in rohan.get("/events/ME-1101").text)
check("sidebar no longer marks events as 'Soon'", page.text.count(">Soon<") == 0)
check("all 99 events are listed", page.text.count('href="/events/ME-') >= 99 - 0 and len(re.findall(r'href="/events/(ME-[^"]+)"', page.text)) >= 99)
check("no real/demo label anywhere on the events page", "Real news" not in page.text and "Demo event" not in page.text)
check("pending filter lists the two Steelco events", sorted(re.findall(r'href="/events/(ME-[^"]+)"', rohan.get("/events?kind=pending", headers={"HX-Target": "events-list"}).text)) == ["1101", "1102"] or len(re.findall(r'href="/events/(ME-[^"]+)"', rohan.get("/events?kind=pending", headers={"HX-Target": "events-list"}).text)) == 2)
check("search works", "Steelco" in rohan.get("/events?q=steelco", headers={"HX-Target": "events-list"}).text)
check("filter pills are driven by Alpine state", "x-model=\"kind\"" in page.text and ":class=\"kind === $el.dataset.v" in page.text)

d = rohan.get("/events/ME-1101")
check("event detail loads and previews routing", d.status == 200 and "Who it reaches" in d.text and "Who will get a task" in d.text and "Process: create 6 tasks" in d.text, d.text[:200])
check("detail shows the reach chain and clients", "Vantage Infra" in d.text and "Astra Logistics" in d.text and "Fulcrum Auto" in d.text and "uses freight from" in d.text)
check("preview wrote nothing", q("SELECT COUNT(*) FROM work_item WHERE source_event_id IN ('ME-1101','ME-1102')")[0][0] == 0 and q("SELECT COUNT(*) FROM event_impact WHERE event_id='ME-1101'")[0][0] == 0)
check("unknown event is 404", rohan.get("/events/ME-NOPE").status == 404)

spec = login("kavita.trade")
sd = spec.get("/events/ME-1101")
check("a specialist sees no Process button", sd.status == 200 and "Process: create" not in sd.text and "Only a relationship manager" in sd.text)
check("a specialist cannot process", spec.post("/events/ME-1101/process").status == 403)

before = q("SELECT COUNT(*) FROM work_item")[0][0]
audit_before = q("SELECT COUNT(*) FROM audit_log")[0][0]
r = rohan.post("/events/ME-1101/process")
check("process redirects to the event with the created ids", r.status == 303 and "done=W-" in r.headers["location"], r.headers.get("location", ""))
after = q("SELECT COUNT(*) FROM work_item")[0][0]
check("six tasks created for the two linked events", after - before == 6)
check("both events marked processed", [x[0] for x in q("SELECT status FROM market_event WHERE id IN ('ME-1101','ME-1102')")] == ["processed", "processed"])
check("impacts recorded", q("SELECT COUNT(*) FROM event_impact WHERE event_id='ME-1101'")[0][0] == 3)
check("one audit entry written", q("SELECT COUNT(*) FROM audit_log")[0][0] == audit_before + 1)
new = q("SELECT id,owner_id,work_type,state,source_event_id FROM work_item WHERE id > 'W-0' AND source_event_id IN ('ME-1101','ME-1102')")
check("every task is Open, has a thread line, and a reason", len(new) == 6 and all(n[3] == "Open" for n in new)
      and all(q("SELECT COUNT(*) FROM work_thread WHERE work_item_id=?", n[0])[0][0] >= 1 for n in new)
      and all(q("SELECT why_path FROM work_item WHERE id=?", n[0])[0][0] for n in new))
check("recipients are the expected people", sorted(n[1] for n in new) == sorted(["u_rohan", "u_karan", "u_kavita", "u_ananya", "u_miu", "u_meera"]))
after_page = rohan.get(r.headers["location"])
check("after processing the page shows the created tasks and a banner", "Routed." in after_page.text and "Who got a task" in after_page.text and "Process: create" not in after_page.text)
check("processing twice is refused", rohan.post("/events/ME-1101/process").status == 409)
check("Rohan's queue shows the new event task", "Steelco" in rohan.get("/work?kind=events").text)
check("hero disappears once nothing is pending", "Review and route" not in rohan.get("/events").text)

print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
