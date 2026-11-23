"""Spreading upload and export: upload a report, read it, open a spread, export to Excel and CSV.
Run:  python tests/test_spreading_upload.py"""
import csv
import io
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
UPLOADS = os.path.join(tempfile.mkdtemp(), "uploads")
os.environ["COMPASS_UPLOADS"] = UPLOADS

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


DOCS = os.path.join(ROOT, "data", "sample_docs")
VANTAGE = open(os.path.join(DOCS, "vantage_infra_ar_fy2025-26_extract.pdf"), "rb").read()
MERIDIAN_SCAN = open(os.path.join(DOCS, "meridian_fabrics_ar_fy2025-26_extract.pdf"), "rb").read()
D = dict(client="g_vantage", doc_type="Annual report", fiscal_year="FY2025-26", basis="Consolidated", unit="INR crore")


def up(c, content, name="report.pdf", **over):
    return c.post("/spreading/upload", {**D, **over}, files={"file": (name, content, "application/pdf")})


def pdf_pages(src, pages):
    from pypdf import PdfReader, PdfWriter
    import io as _io
    r, w = PdfReader(_io.BytesIO(src)), PdfWriter()
    for p in pages:
        w.add_page(r.pages[p])
    b = _io.BytesIO()
    w.write(b)
    return b.getvalue()


rohan = login("rohan.rm")
pg = rohan.get("/spreading")
check("upload form is on the Spreading page with the client list", pg.status == 200 and "Upload a report" in pg.text and 'value="g_vantage"' in pg.text and "FY2025-26" in pg.text)
check("the page does not say the upload is limited to a file type", "PDF only" not in pg.text and "only PDF" not in pg.text and "PDFs only" not in pg.text)

# ---- a normal upload
r = up(rohan, VANTAGE, "Vantage annual report 2026.pdf")
check("upload redirects to the new spread", r.status == 303 and "/spreading/D-UP-0001" in r.headers["location"], r.headers.get("location", r.text[:200]))
page = rohan.get("/spreading/D-UP-0001?new=1")
check("new spread shows 18 lines read and the notice", page.status == 200 and "Report uploaded and read" in page.text and "Revenue from operations" in page.text)
check("file saved, document and 18 lines created", os.path.exists(os.path.join(UPLOADS, "D-UP-0001.pdf")) and q("SELECT COUNT(*) FROM spread_line WHERE document_id='D-UP-0001'")[0][0] == 18
      and q("SELECT status,fiscal_year,basis,unit,version FROM document WHERE id='D-UP-0001'")[0][0] == "Spread in progress")
check("details typed on the form are kept", tuple(q("SELECT fiscal_year,basis,unit,period_end FROM document WHERE id='D-UP-0001'")[0]) == ("FY2025-26", "Consolidated", "INR crore", "2026-03-31"))
check("read values are right (revenue 2,410.00; total assets 3,395.00)", q("SELECT fy_current FROM spread_line WHERE document_id='D-UP-0001' AND line_code='L01'")[0][0] == 2410.0
      and q("SELECT fy_current FROM spread_line WHERE document_id='D-UP-0001' AND line_code='L12'")[0][0] == 3395.0)
check("the uploaded report is shown beside the numbers", rohan.get("/spreading/D-UP-0001/pdf").body[:4] == b"%PDF" and "/spreading/D-UP-0001/pdf" in page.text)
check("the year the report does not hold shows a dash and does not break the checks", "–" in page.text and "Sum checks" in page.text and "Two years back: " not in page.text)
check("list shows the upload", "Vantage annual report 2026.pdf" in rohan.get("/spreading").text)
check("upload is in the audit log", q("SELECT COUNT(*) FROM audit_log WHERE action='upload_spread'")[0][0] == 1)
r2 = up(rohan, VANTAGE, "again.pdf")
check("uploading the same year again counts it as another version (sample + 2 uploads = 3)", q("SELECT version FROM document WHERE id='D-UP-0002'")[0][0] == 3)

# ---- it can be checked and signed off like any other spread
rohan.post("/spreading/D-UP-0001/accept-clean")
s = rohan.post("/spreading/D-UP-0001/sign-off")
check("uploaded spread can be signed off", q("SELECT status FROM document WHERE id='D-UP-0001'")[0][0] == "Spread complete")

# ---- things that must be refused, with nothing left behind
before = len(os.listdir(UPLOADS))
r = up(rohan, MERIDIAN_SCAN, "scan.pdf", client="g_meridian", basis="Standalone")
check("a file with no readable text is refused with a plain reason", r.status == 422 and "No readable text" in r.text)
r = up(rohan, b"hello, this is not a report")
check("a file that is not a report is refused", r.status == 422 and "could not open" in r.text)
r = up(rohan, b"")
check("no file chosen is refused", r.status == 422 and "Choose the report file" in r.text)
r = up(rohan, VANTAGE, client="")
check("no client is refused", r.status == 422 and "Pick the client" in r.text)
r = up(rohan, VANTAGE, fiscal_year="FY1999-00")
check("a made-up year is refused", r.status == 422)
r = up(rohan, VANTAGE, basis="Whatever")
check("a made-up basis is refused", r.status == 422)
check("the form keeps what was typed after an error", 'value="g_vantage"' in up(rohan, b"x").text and "selected" in up(rohan, b"x").text)
from reportlab.pdfgen import canvas  # noqa: E402
buf = io.BytesIO()
c = canvas.Canvas(buf)
c.drawString(100, 700, "Minutes of the board meeting. Nothing financial here.")
c.save()
r = up(rohan, buf.getvalue())
check("a readable file with no statements is refused", r.status == 422 and "usual statement figures" in r.text)
check("refused uploads leave no file and no document behind", len(os.listdir(UPLOADS)) == before and q("SELECT COUNT(*) FROM document WHERE id LIKE 'D-UP-%'")[0][0] == 2)
karan = login("karan.rm")
check("another team's client cannot be uploaded to", up(karan, VANTAGE).status == 403)
check("anonymous upload goes to sign-in", up(Client(app), VANTAGE).status == 303)

# ---- a file with only some statements: the rest are listed for the person to enter
part = pdf_pages(VANTAGE, [0])
r = up(rohan, part, "only_pnl.pdf", fiscal_year="FY2024-25")
did = r.headers["location"].split("/")[2].split("?")[0]
rows = {x[0]: x[1] for x in q("SELECT line_code,confidence FROM spread_line WHERE document_id=?", did)}
check("partial file: 3 lines read, 15 listed as 'not read'", len(rows) == 18 and sum(1 for v in rows.values() if v == 0) == 15, str(rows))
pp = rohan.get(f"/spreading/{did}")
check("not-read lines say so and block sign-off", "Could not be read from the report" in pp.text and "Not ready" in rohan.post(f"/spreading/{did}/sign-off").text)


# ---- two more reports with different layouts (data/test_reports): one clean, one with flaws printed inside the report itself
TR = os.path.join(ROOT, "data", "test_reports")
clean = open(os.path.join(TR, "test_report_Delta_Agro_Foods_FY2025-26_clean.pdf"), "rb").read()
bad = open(os.path.join(TR, "test_report_Corvina_Pharma_FY2025-26_with_errors.pdf"), "rb").read()
r = up(rohan, clean, "delta.pdf", client="g_delta", basis="Standalone")
dc = r.headers["location"].split("/")[2].split("?")[0]
rows = {x[0]: x for x in q("SELECT line_code,fy_current,confidence,note_ref_label,note_ref_value FROM spread_line WHERE document_id=?", dc)}
check("clean report with fewer rows (no 'other long-term liabilities') reads all 18 lines", len(rows) == 18 and all(v[2] >= 97 for v in rows.values()), str({k: v[2] for k, v in rows.items() if v[2] < 97}))
check("note cross-check works whatever the note is numbered (Note 13)", rows["L05"][3] == "Note 13 Borrowings" and rows["L05"][4] == 142.0)
check("clean report: nothing to fix, ready to sign off", "Everything checks out" in rohan.get(f"/spreading/{dc}").text)
rohan.post(f"/spreading/{dc}/sign-off")
check("clean report signs off at once", q("SELECT status FROM document WHERE id=?", dc)[0][0] == "Spread complete")
r = up(rohan, bad, "corvina.pdf", client="g_corvina", basis="Consolidated")
db_ = r.headers["location"].split("/")[2].split("?")[0]
pg = rohan.get(f"/spreading/{db_}")
check("flaws inside the report are caught (note total differs; totals do not add up)", "Note 13 Borrowings" in pg.text and "Liabilities add up" in pg.text and "Not ready" in rohan.post(f"/spreading/{db_}/sign-off").text)
tcl = q("SELECT fy_current FROM spread_line WHERE document_id=? AND line_code='L10'", db_)[0][0]
rohan.post(f"/spreading/{db_}/correct", {"code": "L10", "value": str(round(tcl - 12.0, 2)), "note": "Printed total is 12.00 too high; rows add up to this"})
rohan.post(f"/spreading/{db_}/accept", {"code": "L05", "note": "Balance sheet figure is right; Note 13 has a typing error"})
rohan.post(f"/spreading/{db_}/accept-clean")
rohan.post(f"/spreading/{db_}/sign-off")
check("after fixing, the flawed report can be signed off", q("SELECT status FROM document WHERE id=?", db_)[0][0] == "Spread complete")

# ---- export
r = rohan.get("/spreading/D-UP-0001/export/xlsx")
check("Excel download", r.status == 200 and "spreadsheetml" in r.headers["content-type"] and "attachment" in r.headers["content-disposition"] and ".xlsx" in r.headers["content-disposition"])
from openpyxl import load_workbook  # noqa: E402
wb = load_workbook(io.BytesIO(r.body))
ws = wb["Spread"]
vals = [[c.value for c in row] for row in ws.iter_rows()]
check("workbook has Spread and Checks sheets", wb.sheetnames == ["Spread", "Checks"])
check("workbook says the spread is signed off", any(v and "Signed off" in str(v) for row in vals for v in row))
header = next(i for i, row in enumerate(vals) if row and row[0] == "Code")
body = [row for row in vals[header + 1:] if row[0]]
check("workbook holds all 18 lines with numbers as numbers", len(body) == 18 and isinstance(body[0][3], (int, float)) and body[0][3] == 2410)
check("Checks sheet lists every sum check", sum(1 for row in wb["Checks"].iter_rows(values_only=True) if row[0] and str(row[0])[:1] == "S") >= 4)
r = rohan.get("/spreading/D-UP-0002/export/xlsx")
check("a draft spread is marked as a draft in the file", any("Draft" in str(v) for row in load_workbook(io.BytesIO(r.body))["Spread"].iter_rows(values_only=True) for v in row if v))
r = rohan.get("/spreading/D-UP-0001/export/csv")
rows = list(csv.reader(io.StringIO(r.body.decode("utf-8-sig"))))
check("CSV download: header plus 18 lines, signed-off status on each row", r.status == 200 and "text/csv" in r.headers["content-type"] and len(rows) == 19 and rows[1][4] == "Signed off", str(rows[:2]))
check("exports are in the audit log", q("SELECT COUNT(*) FROM audit_log WHERE action='export_spread'")[0][0] == 3)
check("another team cannot export", karan.get("/spreading/D-UP-0001/export/xlsx").status == 403 and karan.get("/spreading/D-UP-0001/export/csv").status == 403)
check("unknown format is 404, unknown spread is 404", rohan.get("/spreading/D-UP-0001/export/pdf").status == 404 and rohan.get("/spreading/D-NOPE/export/csv").status == 404)
check("export buttons are on the spread page", "export/xlsx" in rohan.get("/spreading/D-UP-0001").text and "export/csv" in rohan.get("/spreading/D-UP-0001").text)
check("the original sample spreads can be exported too", rohan.get("/spreading/D-VIP-FY26/export/xlsx").status == 200 and rohan.get("/spreading/D-MER-FY26/export/csv").status == 200)

# ---- Reset demo clears the uploaded files
db.rebuild()
check("Reset demo removes uploaded reports", not os.path.exists(UPLOADS))
print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED'}")
sys.exit(1 if FAILS else 0)
