"""Step 6 checks: spreading (rule checks, accept, correct, sign-off, access, PDF, audit).
Run:  python tests/test_spreading.py"""
import os
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
from app.features.spreading import service as S  # noqa: E402

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


def state(did):
    with db.connection() as conn:
        u = conn.execute("SELECT * FROM app_user WHERE id='u_rohan'").fetchone()
        return S.get(conn, u, did)


V, M = "D-VIP-FY26", "D-MER-FY26"
check("spreading needs login", Client(app).get("/spreading").status == 303)
rohan = login("rohan.rm")
pg = rohan.get("/spreading")
check("list loads", pg.status == 200 and "Vantage" in pg.text and "Ready to review" in pg.text, pg.text[:200])
check("sidebar: no 'Soon' left", pg.text.count(">Soon<") == 0)

# Vantage is read for real from its PDF, so it comes out clean. To test the checks, we damage three lines the way a bad read would.
s = state(V)
check("Vantage read from the PDF: 18 lines, nothing flagged, every sum passes",
      s["progress"]["total"] == 18 and s["progress"]["to_fix"] == 0 and s["progress"]["failing"] == 0, str(s["progress"]))
check("real notes are cross-checked (L05, L08, L09)", {l["line_code"] for _, ls in s["groups"] for l in ls if l["note_ref_value"] is not None} == {"L05", "L08", "L09"})
check("Meridian (clean) has no flags and every sum passes", not any(l["flags"] for _, ls in state(M)["groups"] for l in ls) and all(x["ok"] for x in state(M)["sums"]))

with db.connection() as conn:
    conn.execute("UPDATE spread_line SET fy_current=124.0, confidence=91 WHERE document_id=? AND line_code='L05'", (V,))
    conn.execute("UPDATE spread_line SET fy_current=98.8, printed_current=105.0 WHERE document_id=? AND line_code='L09'", (V,))
    conn.execute("UPDATE spread_line SET confidence=62 WHERE document_id=? AND line_code='L13'", (V,))
s = state(V)
flags = {l["line_code"]: [f[0] for f in l["flags"]] for _, ls in s["groups"] for l in ls if l["flags"]}
check("damaged lines are flagged: L05 (R1+R2), L09 (R1+R2), L13 (R3)", flags == {"L05": ["R1", "R2"], "L09": ["R1", "R2"], "L13": ["R3"]}, str(flags))
check("S2 and S3 fail, S1 and S4 pass", {x["code"]: x["ok"] for x in s["sums"]} == {"S1": True, "S2": False, "S3": False, "S4": True}, str({x["code"]: x["ok"] for x in s["sums"]}))

page = rohan.get(f"/spreading/{V}")
check("detail page shows pdf, flags and checks", page.status == 200 and f"/spreading/{V}/pdf" in page.text and "Report prints" in page.text and "Read the report again" in page.text and "Sum checks" in page.text)
pdf = rohan.get(f"/spreading/{V}/pdf")
check("PDF is served", pdf.status == 200 and pdf.body[:4] == b"%PDF")

# Vantage is a text PDF; Meridian is a scan (pictures only, nothing to select or copy)
from app.features.spreading import extract as X
def has_text(did):
    return X.has_text(os.path.join(ROOT, q("SELECT storage_path FROM document WHERE id=?", did)[0][0]))
check("Vantage PDF has selectable text", has_text(V))
check("Meridian PDF is a scan with no text layer", not has_text(M))

# cannot sign off while things are open
r = rohan.post(f"/spreading/{V}/sign-off")
check("sign-off blocked while lines are flagged", "Not ready" in r.text and q("SELECT status FROM document WHERE id=?", V)[0][0] != "Spread complete")

# reading the report again repairs lines nobody has reviewed, keeps reviewed ones
rohan.post(f"/spreading/{V}/accept", {"code": "L13", "note": "Checked by eye on page 112"})
with db.connection() as conn:
    conn.execute("UPDATE spread_line SET confidence=50 WHERE document_id=? AND line_code='L13'", (V,))
r = rohan.post(f"/spreading/{V}/read-again")
rows = {x[0]: x for x in q("SELECT line_code,fy_current,confidence,status FROM spread_line WHERE document_id=?", V)}
check("read again repairs unreviewed lines (L05 back to 1,240, L09 to 105)", rows["L05"][1] == 1240.0 and rows["L09"][1] == 105.0, str(rows["L05"]))
check("read again leaves a reviewed line alone", rows["L13"][2] == 50 and rows["L13"][3] == "confirmed")
check("read again is in the history", "read again from the file" in rohan.get(f"/spreading/{V}").text)
check("a scan cannot be read like a text PDF", "scan" in rohan.post(f"/spreading/{M}/read-again").text and "OCR" in rohan.post(f"/spreading/{M}/read-again").text)
with db.connection() as conn:
    conn.execute("UPDATE spread_line SET confidence=62 WHERE document_id=? AND line_code='L13'", (V,))
    conn.execute("UPDATE spread_line SET status='extracted' WHERE document_id=? AND line_code='L13'", (V,))
    conn.execute("UPDATE spread_line SET fy_current=124.0 WHERE document_id=? AND line_code='L05'", (V,))
    conn.execute("UPDATE spread_line SET fy_current=98.8 WHERE document_id=? AND line_code='L09'", (V,))

# validation
check("flagged accept needs a reason", "flagged" in rohan.post(f"/spreading/{V}/accept", {"code": "L13", "note": ""}).text and q("SELECT status FROM spread_line WHERE document_id=? AND line_code='L13'", V)[0][0] == "extracted")
check("correction needs a number", "number" in rohan.post(f"/spreading/{V}/correct", {"code": "L05", "value": "abc", "note": "p. 97"}).text)
check("correction needs a source note", "where the right figure" in rohan.post(f"/spreading/{V}/correct", {"code": "L05", "value": "1240", "note": ""}).text)

# fix them
n_audit = q("SELECT COUNT(*) FROM audit_log")[0][0]
rohan.post(f"/spreading/{V}/correct", {"code": "L05", "value": "1,240.00", "note": "Printed on page 84 and in Note 14, page 97"})
rohan.post(f"/spreading/{V}/correct", {"code": "L09", "value": "105", "note": "Page 85"})
rohan.post(f"/spreading/{V}/accept", {"code": "L13", "note": "Checked the scanned table by eye on page 112: 412"})
s = state(V)
check("after the fixes nothing is to fix and all sums pass", s["progress"]["to_fix"] == 0 and s["progress"]["failing"] == 0 and s["progress"]["ready"], str(s["progress"]))
check("each change wrote an audit entry", q("SELECT COUNT(*) FROM audit_log")[0][0] == n_audit + 3)
check("history shows the corrections", "corrected L05" in rohan.get(f"/spreading/{V}").text)
check("accept-all marks the unflagged lines", "Corrected" in rohan.post(f"/spreading/{V}/accept-clean").text and q("SELECT COUNT(*) FROM spread_line WHERE document_id=? AND status='extracted'", V)[0][0] == 0)

# access
ananya = login("ananya.credit")
check("someone outside the team cannot open it", ananya.get(f"/spreading/{V}").status in (403, 404) and ananya.get(f"/spreading/{V}/pdf").status in (403, 404))
check("or change it", ananya.post(f"/spreading/{V}/accept-clean").status in (403, 404))
check("unknown spread is 404", rohan.get("/spreading/D-NOPE").status == 404)

# sign-off locks it
rohan.post(f"/spreading/{V}/sign-off")
check("signed off", q("SELECT status FROM document WHERE id=?", V)[0][0] == "Spread complete")
r = rohan.post(f"/spreading/{V}/correct", {"code": "L01", "value": "1", "note": "x"})
check("no changes after sign-off", "signed off" in r.text and q("SELECT fy_current FROM spread_line WHERE document_id=? AND line_code='L01'", V)[0][0] == 2410.0)
check("list shows Signed off", "Signed off" in rohan.get("/spreading").text)

# Meridian can be signed off straight away
rohan.post(f"/spreading/{M}/sign-off")
check("clean spread signs off in one click", q("SELECT status FROM document WHERE id=?", M)[0][0] == "Spread complete")
print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
