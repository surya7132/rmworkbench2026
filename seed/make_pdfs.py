"""Create the two sample annual-report extracts (needs: pip install reportlab).

The PDFs print the CORRECT figures. The planted errors live in the extracted
spread lines (see financials.VANTAGE_EXTRACTION_ERRORS), exactly like a real
extraction engine that misreads a page.

Run:  python -m seed.make_pdfs
"""
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from . import financials as fin

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "data", "sample_docs")
ST = getSampleStyleSheet()
H = ParagraphStyle("h", parent=ST["Heading2"], fontName="Helvetica-Bold", fontSize=12, spaceAfter=2, leading=15)
SUB = ParagraphStyle("s", parent=ST["Normal"], fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#444444"), spaceAfter=8)


def num(v, dash=False):
    if v is None:
        return ""
    if dash and abs(v) < 0.005:
        return "-"
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


class Rows:
    def __init__(self):
        self.rows, self.style = [], []

    def head(self, t):
        self.rows.append([t, "", "", ""]); self.style.append(("bold", len(self.rows) - 1))

    def item(self, label, a, b, note="", indent=1):
        self.rows.append([("   " * indent) + label, note, num(a, True), num(b, True)])

    def total(self, label, a, b, note=""):
        self.rows.append([label, note, num(a), num(b)]); self.style.append(("total", len(self.rows) - 1))

    def table(self, year_hdr):
        data = [["Particulars", "Note", year_hdr[0], year_hdr[1]]] + self.rows
        t = Table(data, colWidths=[102 * mm, 14 * mm, 30 * mm, 30 * mm], repeatRows=1)
        cs = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.6), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.6),
              ("ALIGN", (2, 0), (3, -1), "RIGHT"), ("ALIGN", (1, 0), (1, -1), "CENTER"),
              ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black), ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
              ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]
        for kind, i in self.style:
            r = i + 1
            if kind == "bold":
                cs.append(("FONT", (0, r), (-1, r), "Helvetica-Bold", 8.6))
            else:
                cs += [("FONT", (0, r), (-1, r), "Helvetica-Bold", 8.6), ("LINEABOVE", (2, r), (3, r), 0.4, colors.black),
                       ("LINEBELOW", (2, r), (3, r), 0.4, colors.black)]
        t.setStyle(TableStyle(cs))
        return t


def page_cb(company, folio_list, basis):
    state = {"i": 0}

    def cb(canvas, doc):
        canvas.saveState()
        folio = folio_list[state["i"]]; state["i"] += 1
        canvas.setFont("Helvetica", 7.5); canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(18 * mm, 287 * mm, f"{company}   |   Annual Report 2025-26   |   {basis} Financial Statements")
        canvas.line(18 * mm, 285 * mm, 192 * mm, 285 * mm)
        canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.drawString(18 * mm, 10 * mm, "Extract of selected pages. Synthetic sample document; not a real annual report.")
        canvas.setFont("Helvetica-Bold", 9); canvas.setFillColor(colors.black)
        canvas.drawRightString(192 * mm, 10 * mm, str(folio))
        canvas.restoreState()
    return cb


def build(data, company, basis, path, folios, shares_cr, notes_no, unit="Rs in crore, unless otherwise stated"):
    d, doc_story = data, []
    yh = ("Year ended\n31 March 2026", "Year ended\n31 March 2025")
    bh = ("As at\n31 March 2026", "As at\n31 March 2025")
    pl, c, bs, el, asset, cf = d["pl"]["items"], d["pl"]["calc"], d["bs"], d["el"], d["asset"], d["cf"]
    N = notes_no

    def title(t, hdr):
        doc_story.extend([Paragraph(f"{company.upper()}", H), Paragraph(t, H), Paragraph(f"({unit})", SUB)])

    # ---- page 1: statement of profit and loss
    title(f"{basis} Statement of Profit and Loss for the year ended 31 March 2026", yh)
    R = Rows()
    R.item("I.  Revenue from operations", pl["revenue"][0], pl["revenue"][1], N["rev"], 0)
    R.item("II.  Other income", pl["other_income"][0], pl["other_income"][1], N["oi"], 0)
    R.total("III.  Total income (I + II)", c["fy26"]["total_income"], c["fy25"]["total_income"])
    R.head("IV.  Expenses")
    for k, lab in d.get("pl_lines", []):
        R.item(lab, pl[k][0], pl[k][1], N.get(k, ""))
    R.item("Depreciation and amortisation expense", pl["dep"][0], pl["dep"][1], N["dep"])
    R.item("Finance costs", pl["finance"][0], pl["finance"][1], N["fin"])
    R.total("Total expenses", c["fy26"]["total_exp"], c["fy25"]["total_exp"])
    R.total("V.  Profit before tax (III - IV)", c["fy26"]["pbt"], c["fy25"]["pbt"])
    R.head("VI.  Tax expense")
    R.item("Current tax", pl["tax_current"][0], pl["tax_current"][1], "")
    R.item("Deferred tax", pl["tax_deferred"][0], pl["tax_deferred"][1], "")
    R.total("Total tax expense", c["fy26"]["tax"], c["fy25"]["tax"])
    R.total("VII.  Profit for the year (V - VI)", c["fy26"]["pat"], c["fy25"]["pat"])
    R.item("Earnings per equity share (face value Rs 10): basic and diluted (in Rs)", c["fy26"]["eps"], c["fy25"]["eps"], "", 0)
    doc_story.append(R.table(yh)); doc_story.append(Spacer(1, 10))
    doc_story.append(Paragraph("Additional information: key performance indicators", H))
    K = Rows()
    K.item("Operating expenses (excluding depreciation and finance costs)", c["fy26"]["opex"], c["fy25"]["opex"], "", 0)
    K.total("EBITDA (revenue from operations less operating expenses)", c["fy26"]["ebitda"], c["fy25"]["ebitda"])
    doc_story.append(K.table(yh)); doc_story.append(PageBreak())

    # ---- page 2: assets
    title(f"{basis} Balance Sheet as at 31 March 2026: Assets", bh)
    R = Rows(); A = lambda k: asset[k]
    R.head("ASSETS"); R.head("Non-current assets")
    for k, lab, n in [("ppe", "Property, plant and equipment", N.get("ppe", "3")), ("cwip", "Capital work-in-progress", "3"),
                      ("intang", "Intangible assets (incl. concession rights)", "4"), ("nc_inv", "Non-current investments", "5"),
                      ("lt_loans", "Long-term loans and advances", "6"), ("other_nca", "Other non-current assets", "7")]:
        R.item(lab, A(k)[0], A(k)[1], n)
    R.total("Total non-current assets", bs["fy26"]["nca"], bs["fy25"]["nca"])
    R.head("Current assets")
    cur = [("inventories", "Inventories", "8")]
    cur += [("receivables", "Trade receivables", "9")]
    if "contract_assets" in asset:
        cur += [("contract_assets", "Contract assets (unbilled revenue)", "10")]
    cur += [("cash", "Cash and cash equivalents", "11"), ("other_bank", "Other bank balances", "11"),
            ("st_loans", "Short-term loans and advances", "12"), ("other_ca", "Other current assets", "13")]
    for k, lab, n in cur:
        R.item(lab, A(k)[0], A(k)[1], n)
    R.total("Total current assets", bs["fy26"]["ca"], bs["fy25"]["ca"])
    R.total("TOTAL ASSETS", bs["fy26"]["tot_a"], bs["fy25"]["tot_a"])
    doc_story.append(R.table(bh)); doc_story.append(PageBreak())

    # ---- page 3: equity and non-current liabilities
    title(f"{basis} Balance Sheet as at 31 March 2026: Equity and Liabilities", bh)
    R = Rows(); E = lambda k: el[k]
    R.head("EQUITY AND LIABILITIES"); R.head("Equity")
    R.item("Equity share capital", E("share_capital")[0], E("share_capital")[1], "14A")
    R.item("Other equity", E("other_equity")[0], E("other_equity")[1], "15")
    R.total("Total equity", bs["fy26"]["equity"], bs["fy25"]["equity"])
    R.head("Non-current liabilities")
    R.item("Long-term borrowings", E("ltb")[0], E("ltb")[1], N["borrow"])
    R.item("Deferred tax liabilities (net)", E("dtl")[0], E("dtl")[1], "16")
    if "other_ltl" in el:
        R.item("Other long-term liabilities", E("other_ltl")[0], E("other_ltl")[1], "16")
    R.item("Long-term provisions", E("lt_prov")[0], E("lt_prov")[1], "16")
    ncl = (E("ltb")[0] + E("dtl")[0] + (E("other_ltl")[0] if "other_ltl" in el else 0) + E("lt_prov")[0],
           E("ltb")[1] + E("dtl")[1] + (E("other_ltl")[1] if "other_ltl" in el else 0) + E("lt_prov")[1])
    R.total("Total non-current liabilities", round(ncl[0], 2), round(ncl[1], 2))
    R.head("Current liabilities (see next page)")
    doc_story.append(R.table(bh)); doc_story.append(PageBreak())

    # ---- page 4: current liabilities
    title(f"{basis} Balance Sheet as at 31 March 2026 (continued): Current liabilities", bh)
    R = Rows()
    R.head("Current liabilities")
    R.item("Short-term borrowings (including current maturities of long-term debt)", E("stb")[0], E("stb")[1], N["borrow"])
    R.item("Trade payables", E("payables")[0], E("payables")[1], "17")
    R.item("Other current liabilities", bs["fy26"]["ocl"], bs["fy25"]["ocl"], "18")
    R.total("Total current liabilities", bs["fy26"]["cl"], bs["fy25"]["cl"])
    R.total("TOTAL EQUITY AND LIABILITIES", bs["fy26"]["tot_el"], bs["fy25"]["tot_el"])
    doc_story.append(R.table(bh)); doc_story.append(Spacer(1, 10))
    doc_story.append(Paragraph("Note 18: Other current liabilities", H))
    R = Rows()
    R.item("Other financial liabilities", E("ocl_fin")[0], E("ocl_fin")[1], "", 0)
    R.item("Advances from customers", E("ocl_adv")[0], E("ocl_adv")[1], "", 0)
    R.item("Statutory dues and other liabilities", E("ocl_stat")[0], E("ocl_stat")[1], "", 0)
    R.total("Total", bs["fy26"]["ocl"], bs["fy25"]["ocl"])
    doc_story.append(R.table(bh)); doc_story.append(PageBreak())

    # ---- page 5: cash flow
    title(f"{basis} Statement of Cash Flows for the year ended 31 March 2026", yh)
    R = Rows(); a, b = cf["fy26"], cf["fy25"]
    R.head("A.  Cash flow from operating activities")
    R.item("Profit before tax", a["pbt"], b["pbt"]); R.head("Adjustments for:")
    R.item("Depreciation and amortisation", a["dep"], b["dep"]); R.item("Finance costs", a["finance"], b["finance"])
    R.item("Interest income", a["int_income"], b["int_income"])
    R.total("Operating profit before working capital changes", a["opwc"], b["opwc"])
    R.head("Changes in working capital:")
    R.item("(Increase) in inventories", a["inventories"], b["inventories"])
    R.item("(Increase) in trade receivables and contract assets", a["recv"], b["recv"])
    R.item("Increase in trade payables", a["payables"], b["payables"])
    R.item("(Increase) in loans, advances and other assets", a["other_assets"], b["other_assets"])
    R.item("Increase in other liabilities and provisions", a["other_liab"], b["other_liab"])
    R.total("Cash generated from operations", a["cash_ops"], b["cash_ops"])
    R.item("Income taxes paid (net)", a["tax_paid"], b["tax_paid"])
    R.total("Net cash from operating activities (A)", a["cfo"], b["cfo"])
    R.head("B.  Cash flow from investing activities")
    R.item("Purchase of property, plant and equipment, CWIP and intangibles", a["capex"], b["capex"])
    R.item("Proceeds from disposal of property, plant and equipment", a["disposal"], b["disposal"])
    R.item("Purchase of non-current investments", a["nc_inv"], b["nc_inv"])
    R.item("Increase in long-term loans, advances and other non-current assets", a["loans_other"], b["loans_other"])
    R.item("Net (increase) / decrease in other bank balances", a["other_bank"], b["other_bank"])
    R.item("Interest received", a["int_recv"], b["int_recv"])
    R.total("Net cash from investing activities (B)", a["cfi"], b["cfi"])
    R.head("C.  Cash flow from financing activities")
    R.item("Proceeds from long-term borrowings", a["lt_proceeds"], b["lt_proceeds"])
    R.item("Repayment of long-term borrowings", a["lt_repay"], b["lt_repay"])
    R.item("Net increase in short-term borrowings (working capital)", a["st_net"], b["st_net"])
    R.item("Dividend paid", a["dividend"], b["dividend"]); R.item("Finance costs paid", a["int_paid"], b["int_paid"])
    R.total("Net cash from financing activities (C)", a["cff"], b["cff"])
    R.total("Net increase in cash and cash equivalents (A + B + C)", a["net"], b["net"])
    R.item("Cash and cash equivalents at the beginning of the year", a["opening"], b["opening"], "", 0)
    R.total("Cash and cash equivalents at the end of the year", a["closing"], b["closing"])
    doc_story.append(R.table(yh)); doc_story.append(PageBreak())

    # ---- page 6: borrowings note
    title(f"Note {N['borrow']}: Borrowings", bh)
    R = Rows(); n14 = d["note14"]
    R.head("Non-current borrowings")
    for lab, x, y in n14["noncurrent"]:
        R.item(lab, x, y, "", 1)
    R.total("Total long-term borrowings", round(sum(r[1] for r in n14["noncurrent"]), 2), round(sum(r[2] for r in n14["noncurrent"]), 2))
    R.head("Current borrowings")
    for lab, x, y in n14["current"]:
        R.item(lab, x, y, "", 1)
    R.total("Total short-term borrowings", round(sum(r[1] for r in n14["current"]), 2), round(sum(r[2] for r in n14["current"]), 2))
    doc_story.append(R.table(bh))
    doc_story.append(Spacer(1, 8)); doc_story.append(Paragraph(d["note14_text"], SUB)); doc_story.append(PageBreak())

    # ---- page 7: contingent liabilities
    title(f"Note {N['cont']}: Contingent liabilities and commitments", bh)
    R = Rows()
    R.head("Contingent liabilities (to the extent not provided for)")
    for lab, x, y in d["note31"]:
        R.item(lab, x, y, "", 1)
    R.total("Total contingent liabilities", round(sum(r[1] for r in d["note31"]), 2), round(sum(r[2] for r in d["note31"]), 2))
    doc_story.append(R.table(bh))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    cb = page_cb(company, folios, basis)
    SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                      title=f"{company} Annual Report 2025-26 (extract)", author="Synthetic sample").build(
        doc_story, onFirstPage=cb, onLaterPages=cb)
    return path


def main():
    v = fin.vantage()
    v["pl_lines"] = [("materials", "Cost of materials consumed (incl. construction materials)"),
                     ("subcontract", "Subcontracting and labour charges"), ("employee", "Employee benefits expense"),
                     ("other_exp", "Other expenses")]
    v["note14_text"] = ("The Rs 180.00 crore 9.15% secured redeemable non-convertible debentures are redeemable on 9 February 2027 "
                        "and are therefore classified as current maturities of long-term debt at 31 March 2026.")
    build(v, "Vantage Infra Projects Limited", "Consolidated", os.path.join(OUT, "vantage_infra_ar_fy2025-26_extract.pdf"),
          [82, 83, 84, 85, 86, 97, 112], 5.2, {"rev": "19", "oi": "20", "materials": "21", "subcontract": "22", "employee": "23",
                                               "other_exp": "24", "dep": "4", "fin": "25", "borrow": "14", "cont": "31", "ppe": "3"})
    m = fin.meridian()
    m["pl_lines"] = [("materials", "Cost of raw materials consumed"), ("employee", "Employee benefits expense"),
                     ("power", "Power and fuel"), ("other_exp", "Other expenses")]
    m["note14_text"] = ("Packing credit in foreign currency is secured by hypothecation of stock and receivables. "
                        "Term loans are secured by first charge on plant and machinery at the Tiruppur and Surat units.")
    build(m, "Meridian Fabrics Limited", "Standalone", os.path.join(OUT, "meridian_fabrics_ar_fy2025-26_extract.pdf"),
          [58, 59, 60, 61, 62, 71, 84], 2.4, {"rev": "18", "oi": "19", "materials": "20", "employee": "21", "power": "22",
                                              "other_exp": "23", "dep": "4", "fin": "24", "borrow": "13", "cont": "29", "ppe": "3"})
    # Meridian is delivered as a scan (pictures only, no selectable text), to give us unstructured material of a harder kind.
    from .make_scan import make_scan
    f = os.path.join(OUT, "meridian_fabrics_ar_fy2025-26_extract.pdf")
    make_scan(f, f)
    print("PDFs written to", OUT)


if __name__ == "__main__":
    main()
