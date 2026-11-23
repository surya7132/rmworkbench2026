"""Step 4 checks: meetings list, brief, prep, debrief (follow-ups), dictation markup, optional AI.
Run:  python tests/test_meetings.py"""
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
os.environ.pop("ANTHROPIC_API_KEY", None)

from tests.asgi_client import Client  # noqa: E402
from app.main import app  # noqa: E402
from app import db  # noqa: E402
from app.features.meetings import ai  # noqa: E402

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


check("meetings need login", Client(app).get("/meetings").status == 303)
rohan = login("rohan.rm")
pg = rohan.get("/meetings")
check("list loads", pg.status == 200 and "Coming up" in pg.text)
check("two meetings wait for notes", "Add your notes" in pg.text and pg.text.count(">Add notes<") == 2)
check("seven upcoming meetings", pg.text.count(">Open brief<") == 7)
check("source is shown (calendar and Outlook)", "Outlook (detected)" in pg.text and "Calendar" in pg.text)
check("sidebar: Meetings is no longer 'Soon'", pg.text.count(">Soon<") == 0)

b = rohan.get("/meetings/mt_v_1118")
check("brief loads with plan, avoid list and questions", b.status == 200 and "Must cover" in b.text and "Avoid" in b.text and "Questions to ask" in b.text and "Refinancing intent" in b.text)
check("brief shows the linked opportunity", "Opportunity behind this meeting" in b.text and "Refinance" in b.text)
check("brief shows 'what changed' with sources", "What changed since last time" in b.text and "We promised" in b.text and "Work queue W-2001" in b.text)
check("brief has a short summary and copy button", "In short" in b.text and ">Copy<" in b.text)
check("AI buttons hidden when AI is not set up", "Rewrite with AI" not in b.text and "Tidy with AI" not in b.text)
check("dictation control and speech code are present", "Speak your notes" in b.text and "SpeechRecognition" in b.text and 'lang = \'en-IN\'' in b.text)
check("dictation writes into the box live (no separate interim text)", "x-text=\"interim\"" not in b.text and "e.results.length" in b.text and "base + spoken" in b.text)
check("brief text is cut at word boundaries and summary is short", "compan..." not in rohan.get("/meetings/mt_shijonpro_1113").text and len(re.search(r'data-text="([^"]*)"', rohan.get("/meetings/mt_shijonpro_1113").text).group(1)) < 520)
check("market lines say why they reach the client", "Why it matters here:" in rohan.get("/meetings/mt_shijonpro_1113").text and "Vibel Fabrics" in rohan.get("/meetings/mt_shijonpro_1113").text)
check("meeting 404 and cross-team 403", rohan.get("/meetings/NOPE").status == 404 and login("kavita.trade").get("/meetings/mt_v_1118").status == 403)
check("client page links to the meeting", 'href="/meetings/mt_v_1118"' in rohan.get("/clients/g_vantage").text)

# market event now reaches Vantage -> shows up in the brief
rohan.post("/events/ME-1101/process")
check("a processed market event appears in the brief", "Steelco" in rohan.get("/meetings/mt_v_1118").text)

# prep
r = rohan.post("/meetings/mt_v_1118/prep", {"objective": "", "success": "", "must": "", "if_time": "", "avoid": "", "ready": "1"})
check("cannot mark prep ready without objective and must-cover", r.status == 422 and "objective" in r.text)
r = rohan.post("/meetings/mt_v_1118/prep", {"objective": "Secure the refinancing talk", "success": "Date fixed", "must": "NCD plan\nGuarantee timing", "if_time": "", "avoid": "Quoting a rate", "ready": "1"})
check("prep saved and marked ready", r.status == 303 and q("SELECT prep_status FROM meeting WHERE id='mt_v_1118'")[0][0] == "ready")
check("saved prep keeps the questions", "Refinancing intent" not in rohan.get("/meetings/mt_v_1118").text and "Questions to ask" in rohan.get("/meetings/mt_v_1118").text)

# debrief
check("empty notes refused", rohan.post("/meetings/mt_shijonpro_1113/debrief", {"notes": ""}).status == 422)
check("follow-up without date refused", rohan.post("/meetings/mt_shijonpro_1113/debrief", {"notes": "Talked.", "f_title": "Send note", "f_owner": "u_rohan", "f_due": "", "f_kind": "task"}).status == 422)
w0 = q("SELECT COUNT(*) FROM work_item")[0][0]
a0 = q("SELECT COUNT(*) FROM audit_log")[0][0]
r = rohan.post("/meetings/mt_shijonpro_1113/debrief", {"notes": "Reviewed working capital. Client wants a higher cash credit limit.", "decisions": "Revisit in December",
               "f_title": ["Send revised limit proposal", "Check drawing power with Credit"], "f_owner": ["u_rohan", "u_ananya"], "f_due": ["2026-11-24", "2026-11-26"], "f_kind": ["promise", "specialist"]})
check("debrief saves and redirects with ids", r.status == 303 and "done=W-" in r.headers["location"], r.headers.get("location", ""))
check("two work items created", q("SELECT COUNT(*) FROM work_item")[0][0] == w0 + 2)
m = q("SELECT status,logged,outcome FROM meeting WHERE id='mt_shijonpro_1113'")[0]
check("meeting marked held and logged with the notes and decisions", m[0] == "held" and m[1] == 1 and "higher cash credit" in m[2] and "Decisions: Revisit in December" in m[2])
items = q("SELECT id,owner_id,work_type,state,visibility,why_path FROM work_item WHERE why_path LIKE '%mt_shijonpro_1113%' ORDER BY id")
check("follow-ups have the right owner, type and a reason", [(i[1], i[2], i[3]) for i in items] == [("u_rohan", "commitment", "Open"), ("u_ananya", "specialist_request", "Open")] and "Raised in the meeting" in items[0][5])
check("each follow-up has a thread line and one audit entry covers the meeting", all(q("SELECT COUNT(*) FROM work_thread WHERE work_item_id=?", i[0])[0][0] >= 1 for i in items) and q("SELECT COUNT(*) FROM audit_log")[0][0] == a0 + 1)
after = rohan.get(r.headers["location"])
check("page shows banner, recorded notes and follow-ups", "Notes saved." in after.text and "What was recorded" in after.text and "Send revised limit proposal" in after.text)
check("the notes-pending list shrinks", rohan.get("/meetings").text.count(">Add notes<") == 1)
check("saving notes twice is refused", rohan.post("/meetings/mt_shijonpro_1113/debrief", {"notes": "again"}).status == 409)
check("Ananya sees the new request in her queue", "Check drawing power" in login("ananya.credit").get("/work").text)

# optional AI
check("AI endpoint is off without a key", rohan.post("/meetings/mt_m_1123/ai", {"mode": "tidy", "text": "hello"}).status == 503)
os.environ["ANTHROPIC_API_KEY"] = "test"
ai._call = lambda system, user: "TIDY:" + user
bb = rohan.get("/meetings/en_m_1116")
check("AI buttons appear when a key is set", "Tidy with AI" in bb.text and "Rewrite with AI" in bb.text)
r = rohan.post("/meetings/en_m_1116/ai", {"mode": "tidy", "text": "rough notes"})
check("AI tidy returns text", r.status == 200 and "TIDY:rough notes" in r.text)
check("AI with empty text is refused", rohan.post("/meetings/en_m_1116/ai", {"mode": "tidy", "text": " "}).status == 422)
ai._call = lambda s, u: (_ for _ in ()).throw(RuntimeError("down"))
check("AI failure is reported and nothing breaks", rohan.post("/meetings/en_m_1116/ai", {"mode": "tidy", "text": "x"}).status == 502)

print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
