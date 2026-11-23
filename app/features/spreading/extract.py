"""Read the numbers straight out of a text PDF annual report. No database, no web app: just a file in, lines out.

How it works
  1. pdfplumber gives every line of text on each page (the PDF stores real text, so there is nothing to guess).
  2. A line is split into  label | note number | this year | last year.  Brackets mean negative; a dash means zero.
  3. The standard spread form (FORM below) says which row of which page feeds which line.
     "row"  = one row, found by its label.   "sum" = add whichever of several rows the report has (for example the small
     non-current liabilities: a report may list two of them, another three).
  4. A few lines also read the supporting note's total (borrowings, other current liabilities), whatever number the report gives
     the note, so the tool can cross-check them.

Confidence is 99 when one row matched, 97 when the figure is a sum of rows, and the line is left out when
nothing matched (the caller reports it). Scanned files have no text, so they need OCR instead (not in this file).
The report holds two years, so the third year (two years back) is not read here. It comes from the earlier spread.
"""
import re

import pdfplumber

NUM = r"\(?-?[\d,]+\.\d{2}\)?|-"
ROW = re.compile(rf"^(?P<label>.+?)\s+(?:(?P<note>\d{{1,2}}[A-Z]?)\s+)?(?P<cur>{NUM})\s+(?P<prior>{NUM})$")
FOLIO = re.compile(r"(\d{1,3})\s*$")

# code, label, statement, page heading, how, row pattern(s), supporting note (label, page heading, row pattern)
FORM = [
    ("L01", "Revenue from operations", "P&L", r"Statement of Profit and Loss", "row", [r"^I\. Revenue from operations"], None),
    ("L02", "EBITDA", "P&L", r"Statement of Profit and Loss", "row", [r"^EBITDA"], None),
    ("L03", "Profit after tax", "P&L", r"Statement of Profit and Loss", "row", [r"^VII\. Profit for the year"], None),
    ("L04", "Net worth (total equity)", "Balance sheet", r"Equity and Liabilities", "row", [r"^Total equity$"], None),
    ("L05", "Long-term borrowings (balance sheet)", "Balance sheet", r"Equity and Liabilities", "row", [r"^Long-term borrowings"],
     ("borrowings", r"Note \d+: Borrowings", r"^Total long-term borrowings")),
    ("L06", "Other non-current liabilities", "Balance sheet", r"Equity and Liabilities", "sum",
     [r"^Deferred tax liabilities", r"^Other long-term liabilities", r"^Long-term provisions"], None),
    ("L07", "Trade payables", "Current liabilities", r"Current liabilities", "row", [r"^Trade payables"], None),
    ("L08", "Short-term borrowings (incl. current maturities)", "Current liabilities", r"Current liabilities", "row", [r"^Short-term borrowings"],
     ("borrowings", r"Note \d+: Borrowings", r"^Total short-term borrowings")),
    ("L09", "Other current liabilities", "Current liabilities", r"Current liabilities", "row", [r"^Other current liabilities$"],
     ("other current liabilities", r"Note \d+: Other current liabilities", r"^Total$")),
    ("L10", "Total current liabilities (reported)", "Current liabilities", r"Current liabilities", "row", [r"^Total current liabilities"], None),
    ("L11", "Total equity and liabilities", "Balance sheet", r"Current liabilities", "row", [r"^TOTAL EQUITY AND LIABILITIES"], None),
    ("L12", "Total assets", "Balance sheet", r"Balance Sheet as at .*Assets", "row", [r"^TOTAL ASSETS"], None),
    ("L13", "Contingent liabilities", "Notes", r"Contingent liabilities", "row", [r"^Total contingent liabilities"], None),
    ("L14", "Net cash from operating activities", "Cash flow", r"Statement of Cash Flows", "row", [r"^Net cash from operating activities"], None),
    ("L15", "Net cash from investing activities", "Cash flow", r"Statement of Cash Flows", "row", [r"^Net cash from investing activities"], None),
    ("L16", "Net cash from financing activities", "Cash flow", r"Statement of Cash Flows", "row", [r"^Net cash from financing activities"], None),
    ("L17", "Opening cash and cash equivalents", "Cash flow", r"Statement of Cash Flows", "row", [r"^Cash and cash equivalents at the beginning"], None),
    ("L18", "Closing cash and cash equivalents", "Cash flow", r"Statement of Cash Flows", "row", [r"^Cash and cash equivalents at the end"], None),
]


def _num(tok):
    if tok == "-":
        return 0.0
    neg = tok.startswith("(") or tok.startswith("-")
    v = float(tok.strip("()-").replace(",", ""))
    return -v if neg else v


def has_text(path):
    """True when the PDF carries real text (so this reader works). A scan returns False."""
    with pdfplumber.open(path) as pdf:
        return any((p.extract_text() or "").strip() for p in pdf.pages)


def read_pages(path):
    """-> list of pages: {'n': physical page, 'folio': printed page number, 'text': whole text, 'rows': [(label, note, cur, prior)]}"""
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            lines = [l["text"].strip() for l in p.extract_text_lines()]
            rows = []
            for t in lines:
                m = ROW.match(t)
                if m:
                    rows.append((m["label"].strip(), m["note"], _num(m["cur"]), _num(m["prior"])))
            foot = next((t for t in reversed(lines) if t.startswith("Extract of selected pages")), "")
            f = FOLIO.search(foot)
            pages.append({"n": i, "folio": f"p. {f.group(1)}" if f else f"p. {i}", "text": "\n".join(lines), "rows": rows})
    return pages


def _find(pages, heading, patterns, optional=False):
    """Rows matching the patterns, on the first page whose text matches the heading. -> (page, [row,...], heading match) or (None, [], None).
    optional=True: each pattern may match nothing (a sum of whichever rows the report has), but at least one must."""
    for pg in pages:
        hm = re.search(heading, pg["text"])
        if not hm:
            continue
        found = []
        for pat in patterns:
            hit = [r for r in pg["rows"] if re.search(pat, r[0])]
            if len(hit) == 1:
                found.append(hit[0])
            elif len(hit) > 1 or not optional:
                found = []
                break
        if found and (optional or len(found) == len(patterns)):
            return pg, found, hm
    return None, [], None


def extract(path):
    """-> (lines, missing). Each line: dict with the spread_line columns (no id, no document, no third year)."""
    pages = read_pages(path)
    out, missing = [], []
    for code, label, stmt, heading, how, pats, note in FORM:
        pg, rows, _ = _find(pages, heading, pats, optional=(how == "sum"))
        if not rows:
            missing.append(code)
            continue
        cur, prior = round(sum(r[2] for r in rows), 2), round(sum(r[3] for r in rows), 2)
        line = dict(line_code=code, label=label, statement=stmt, fy_current=cur, fy_prior1=prior, printed_current=cur,
                    page_ref=pg["folio"], pdf_page=pg["n"], confidence=99 if how == "row" else 97,
                    note_ref_label=None, note_ref_value=None, note_ref_page=None)
        if note:
            npg, nrows, hm = _find(pages, note[1], [note[2]])
            if nrows:
                line.update(note_ref_label=hm.group(0).replace(":", ""), note_ref_value=nrows[0][2], note_ref_page=npg["folio"])
        out.append(line)
    return out, missing
