"""Export a spread: Excel (two sheets: the spread, and the checks) or CSV (one flat table).

The export always says whether the spread is signed off, so a draft is never mistaken for a final one.
Every export is recorded in the audit log.
"""
import csv
import io
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ... import clock
from . import service as S
from ..work import service as W

REVIEW = {"extracted": "Not yet checked", "confirmed": "Accepted", "corrected": "Corrected"}
HEAD = ["Code", "Line", "Statement", "Current year", "Prior year", "Two years back", "Confidence %", "Review", "Flags", "Report page", "Note cross-check"]


def _data(db, user, did):
    d = S.get(db, user, did)
    doc = d["doc"]
    rows = []
    for stmt, lines in d["groups"]:
        for l in lines:
            note = f"{l['note_ref_label']}: {l['note_ref_value']:,.2f} ({l['note_ref_page']})" if l["note_ref_value"] is not None else ""
            rows.append([l["line_code"], l["label"], stmt, l["fy_current"], l["fy_prior1"], l["fy_prior2"], l["confidence"],
                         REVIEW.get(l["status"], l["status"]), "; ".join(f"{c} {t}" for c, t in l["flags"]), l["page_ref"], note])
    status = "Signed off" if doc["complete"] else "Draft, not signed off"
    meta = [("Client", doc["client_name"]), ("Report", doc["name"]), ("Fiscal year", doc["fiscal_year"]), ("Basis", doc["basis"]),
            ("Unit", doc["unit"]), ("Spread status", status), ("Exported", clock.now().strftime("%d %b %Y, %H:%M"))]
    return doc, meta, rows, d["sums"], d["progress"]


def filename(doc, ext):
    base = re.sub(r"[^A-Za-z0-9]+", "_", f"spread {doc['client_name']} {doc['fiscal_year']} {doc['basis']}").strip("_")
    return f"{base}.{ext}"


def to_csv(db, user, did):
    doc, meta, rows, _, _ = _data(db, user, did)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Client", "Fiscal year", "Basis", "Unit", "Spread status"] + HEAD)
    for r in rows:
        w.writerow([meta[0][1], meta[2][1], meta[3][1], meta[4][1], meta[5][1]] + ["" if v is None else v for v in r])
    _log(db, user, doc, "CSV")
    return out.getvalue().encode("utf-8-sig"), filename(doc, "csv"), "text/csv"


def to_xlsx(db, user, did):
    doc, meta, rows, sums, progress = _data(db, user, did)
    wb = Workbook()
    ws = wb.active
    ws.title = "Spread"
    ws["A1"] = "Spread"
    ws["A1"].font = Font(bold=True, size=14)
    for i, (k, v) in enumerate(meta, start=3):
        ws.cell(i, 1, k).font = Font(bold=True)
        ws.cell(i, 2, v)
    top = len(meta) + 4
    for c, h in enumerate(HEAD, start=1):
        cell = ws.cell(top, c, h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="12294D")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    flagged = PatternFill("solid", fgColor="FDECEC")
    for r, row in enumerate(rows, start=top + 1):
        for c, v in enumerate(row, start=1):
            cell = ws.cell(r, c, v)
            if c in (4, 5, 6) and v is not None:
                cell.number_format = "#,##0.00;[Red]-#,##0.00"
            if row[8]:
                cell.fill = flagged
    for c, w in enumerate([7, 46, 20, 14, 14, 15, 12, 16, 60, 12, 40], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(top + 1, 3)

    cs = wb.create_sheet("Checks")
    cs["A1"] = "Sum checks"
    cs["A1"].font = Font(bold=True, size=14)
    for c, h in enumerate(["Check", "What it tests", "Year", "Left side", "Right side", "Difference", "Result"], start=1):
        cs.cell(3, c, h).font = Font(bold=True)
    r = 4
    for s in sums:
        for y in s["per"]:
            for c, v in enumerate([f"{s['code']} {s['title']}", s["text"], y["label"], y["a"], y["b"], y["diff"], "Pass" if y["ok"] else "Fails"], start=1):
                cs.cell(r, c, v)
            for c in (4, 5, 6):
                cs.cell(r, c).number_format = "#,##0.00"
            r += 1
    cs.cell(r + 1, 1, f"Lines to fix: {progress['to_fix']}. Sum checks failing: {progress['failing']}.")
    for c, w in enumerate([34, 80, 16, 14, 14, 12, 10], start=1):
        cs.column_dimensions[get_column_letter(c)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    _log(db, user, doc, "Excel")
    return buf.getvalue(), filename(doc, "xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _log(db, user, doc, kind):
    W._audit(db, user, "export_spread", f"{doc['client_name']} {doc['fiscal_year']}: spread exported to {kind} ({'signed off' if doc['complete'] else 'draft'})", [doc["id"]])
