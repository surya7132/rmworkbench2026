"""Step 1 checks: login, work queue, state rules, client list, reset.
Run:  python tests/test_shell_work_clients.py      (uses real FastAPI if installed, else tests/shim)"""
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
    r = c.post("/login", {"username": user, "password": "Demo@2026"})
    return c, r


def q(sql, *a):
    with db.connection() as conn:
        return conn.execute(sql, a).fetchall()


# --- login
c = Client(app)
check("work page redirects to login when signed out", c.get("/work").status == 303 and "/login" in c.get("/work").headers["location"])
check("login page shows demo accounts", "rohan.rm" in c.get("/login").text)
check("wrong password rejected", c.post("/login", {"username": "rohan.rm", "password": "bad"}).status == 401)
rohan, r = login("rohan.rm")
check("login succeeds and redirects", r.status == 303)

# --- work queue
page = rohan.get("/work")
check("work page loads", page.status == 200 and "My work" in page.text, page.text[:200])
mine = q("SELECT id FROM work_item WHERE owner_id='u_rohan' AND state IN ('Open','Accepted','In progress','Needs information')")
shown = set(re.findall(r'id="w-([A-Za-z0-9_-]+)"', page.text))
check("Rohan sees exactly his open items", shown == {m[0] for m in mine}, f"{len(shown)} vs {len(mine)}")
part = rohan.get("/work?kind=events", headers={"HX-Target": "work-list"})
check("HTMX filter returns a partial", "<html" not in part.text and part.status == 200)
check("events filter only shows event items", all(i in {r[0] for r in q("SELECT id FROM work_item WHERE source_event_id IS NOT NULL")} for i in re.findall(r'id="w-([^"]+)"', part.text)))

# --- state changes
open_item = q("SELECT id, version FROM work_item WHERE owner_id='u_rohan' AND state='Open' AND (completion_condition IS NOT NULL) LIMIT 1")[0]
wid, ver = open_item
r = rohan.post(f"/work/{wid}/state", {"to": "Accepted", "version": ver}, headers={"HX-Request": "true"})
check("Open -> Accepted works", r.status == 200 and q("SELECT state FROM work_item WHERE id=?", wid)[0][0] == "Accepted", r.text[:300])
check("version bumped", q("SELECT version FROM work_item WHERE id=?", wid)[0][0] == ver + 1)
check("thread line written", len(q("SELECT 1 FROM work_thread WHERE work_item_id=? AND text LIKE '%Accepted%'", wid)) >= 1)
n_audit = q("SELECT COUNT(*) FROM audit_log")[0][0]
r = rohan.post(f"/work/{wid}/state", {"to": "In progress", "version": ver})
check("stale version is refused", "X-Compass-Error".lower() in r.headers and q("SELECT state FROM work_item WHERE id=?", wid)[0][0] == "Accepted", str(r.headers))
check("refused change writes no audit row", q("SELECT COUNT(*) FROM audit_log")[0][0] == n_audit)
r = rohan.post(f"/work/{wid}/state", {"to": "Done", "version": ver + 1})
check("Done without confirm is refused", q("SELECT state FROM work_item WHERE id=?", wid)[0][0] == "Accepted")
r = rohan.post(f"/work/{wid}/state", {"to": "Needs information", "version": ver + 1, "note": ""})
check("Needs information without note is refused", q("SELECT state FROM work_item WHERE id=?", wid)[0][0] == "Accepted")
r = rohan.post(f"/work/{wid}/state", {"to": "Needs information", "version": ver + 1, "note": "Need the GST returns from the client"})
check("Needs information with note works", q("SELECT state FROM work_item WHERE id=?", wid)[0][0] == "Needs information", r.text[:300])
check("every change has an audit entry", q("SELECT COUNT(*) FROM audit_log")[0][0] >= n_audit + 1)
r = rohan.post(f"/work/{wid}/note", {"text": "Called the CFO"})
check("note added to thread", r.status == 200 and "Called the CFO" in r.text)

# --- ownership
other = q("SELECT id, version FROM work_item WHERE owner_id='u_karan' AND state='Open' LIMIT 1")[0]
check("cannot change someone else's item (403)", rohan.post(f"/work/{other[0]}/state", {"to": "Accepted", "version": other[1]}).status == 403)
check("cannot read someone else's thread (403)", rohan.get(f"/work/{other[0]}/thread").status == 403)
check("missing item is 404", rohan.post("/work/NOPE/state", {"to": "Accepted", "version": 1}).status == 404)

# --- hero routing visible
hero = rohan.get("/work?status=all&q=Steelco")
check("hero Steelco item reaches Rohan", "Steelco" in hero.text)
check("'Why am I seeing this' shown for routed items", "Why am I seeing this" in rohan.get("/work?kind=events").text)

# --- team lead
meera, _ = login("meera.lead")
team = meera.get("/work?scope=team")
check("lead sees team scope", team.status == 200 and "My team" in team.text)
n_team = len(set(re.findall(r'id="w-([^"]+)"', team.text)))
check("team scope shows more than mine", n_team > len(set(re.findall(r'id="w-([^"]+)"', meera.get("/work").text))), str(n_team))

# --- clients
cl = rohan.get("/clients?rm=mine")
check("clients page loads", cl.status == 200)
check("Rohan owns 38 groups", q("SELECT COUNT(*) FROM client_group WHERE rm_id='u_rohan'")[0][0] == 38 and "38 clients" in cl.text, re.findall(r"\d+ clients?", cl.text)[:1].__str__())
check("lead defaults to all 132", "132 clients" in meera.get("/clients").text)
check("client search works", "Vantage" in rohan.get("/clients?q=Vantage", headers={"HX-Target": "clients-table"}).text)
check("client sort works", rohan.get("/clients?sort=util").status == 200)
pg = rohan.get("/clients/g_vantage")
check("client page loads", pg.status == 200 and "Vantage Infra" in pg.text and "clientPage()" in pg.text, pg.text[:200])
check("client page shows facilities, evidence and map data", "Term Loan" in pg.text or "Cash Credit" in pg.text or "Facility" in pg.text)
check("work-queue link only shows when an open item is yours", "Open in my work queue" in pg.text and "Open in my work queue" not in rohan.get("/clients/g_bhinpu").text)
check("map script is served", rohan.get("/static/js/relmap.js").status == 200 and "RelMap" in rohan.get("/static/js/relmap.js").text and "relmap.js" in pg.text)
check("last contact matches the latest held meeting for every client", not q("""SELECT g.id FROM client_group g WHERE g.last_contact <>
        (SELECT MAX(substr(starts_at,1,10)) FROM meeting m WHERE m.client_group_id=g.id AND m.status='held')"""))
check("client page carries relationship map data", '"nodes"' in pg.text and '"edges"' in pg.text)
check("client page lists news with a publisher link and no real/demo label", "https://" in pg.text and "Real news" not in pg.text and "Demo event" not in pg.text)
check("evidence tab shows source links for real news facts", "target=\"_blank\"" in pg.text)
for g in [r[0] for r in q("SELECT id FROM client_group ORDER BY id")]:
    if rohan.get(f"/clients/{g}").status != 200:
        check(f"client page {g} loads", False)
        break
else:
    check("all 132 client pages load", True)
check("unknown client is 404", rohan.get("/clients/zzz").status == 404)
for p in ("/events", "/meetings", "/alerts", "/spreading"):
    check(f"placeholder {p} loads", rohan.get(p).status == 200)

# --- reset
rohan.post("/reset")
check("reset restores the item", q("SELECT state FROM work_item WHERE id=?", wid)[0][0] == "Open")
check("still signed in after reset", rohan.get("/work").status == 200)
r = rohan.post("/logout")
check("logout works", rohan.get("/work").status == 303)

# --- done with confirm, thread view
rohan, _ = login("rohan.rm")
d = q("SELECT id, version, due_at FROM work_item WHERE owner_id='u_rohan' AND state='Open' ORDER BY due_at LIMIT 1")[0]
r = rohan.post(f"/work/{d[0]}/state", {"to": "Done", "version": d[1], "confirm": "1", "note": "Sent"})
check("Done with confirm works", q("SELECT state FROM work_item WHERE id=?", d[0])[0][0] == "Done", r.text[:300])
check("thread view renders", "Sent" in rohan.get(f"/work/{d[0]}/thread").text)

# --- frozen clock, long text, filter highlight
from app import clock  # noqa: E402
import time as _t  # noqa: E402
a = clock.now(); _t.sleep(0.05)
check("demo clock is frozen", clock.now() == a and a.strftime("%Y-%m-%d %H:%M") == "2026-11-17 09:10")
rohan, _ = login("rohan.rm")
r = rohan.post("/clock/advance", {"hours": "24"}, headers={"Referer": "http://x/work?kind=events"})
check("advance moves the day and returns to the same page", r.status == 303 and r.headers["location"] == "/work?kind=events" and clock.now().strftime("%d") == "18")
rohan.post("/reset")
check("reset puts the clock back", clock.now().strftime("%Y-%m-%d %H:%M") == "2026-11-17 09:10")
cons = q("SELECT consequence FROM work_item WHERE source_event_id IS NOT NULL")
check("consequences hold no graph path in brackets and stay readable", all(len(c[0]) <= 400 and "(" not in c[0] and " supplies " not in c[0] for c in cons))
check("no consequence is exactly 300 characters (old cut-off)", all(len(c[0]) != 300 for c in cons))
check("event items keep the full path under 'why'", any("supplies" in w[0] for w in q("SELECT why_path FROM work_item WHERE source_event_id IS NOT NULL AND why_path IS NOT NULL")))
page = rohan.get("/work?kind=events").text
check("filter pills are driven by Alpine state", "x-model=\"kind\"" in page and "data-v=\"events\"" in page and ":class=\"kind === $el.dataset.v" in page)

print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
