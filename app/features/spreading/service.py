"""Spreading: the numbers from an annual report, checked against the report itself.

The PDF sits beside the extracted lines. Rule checks flag what to fix:
  R1  extracted figure differs from the figure printed in the report
  R2  balance-sheet figure differs from its supporting note
  R3  the reader was not sure of the figure (confidence below 80)
  S1  total assets equal total equity and liabilities
  S2  equity + long-term borrowings + other non-current + current liabilities equal the total
  S3  trade payables + short-term borrowings + other current liabilities equal total current liabilities
  S4  opening cash + operating + investing + financing equals closing cash

Reports can be uploaded here (upload) and the finished spread exported (export.py).

A line that trips R1 to R3 stays "to fix" until a person accepts it (with a reason) or corrects it.
The spread can be signed off only when no line is to fix and every sum check passes.
Every accept, correct and sign-off writes an audit entry.
"""
from ... import auth, clock, config
from . import extract as X
from ..work import service as W

TOL = 0.5
LOW_CONF = 80
YEARS = [("fy_current", "Current year"), ("fy_prior1", "Prior year"), ("fy_prior2", "Two years back")]
SUMS = [("S1", "Balance sheet balances", "Total assets equal total equity and liabilities", ["L12"], ["L11"]),
        ("S2", "Liabilities add up", "Equity, long-term borrowings, other non-current and current liabilities equal the total", ["L04", "L05", "L06", "L10"], ["L11"]),
        ("S3", "Current liabilities add up", "Trade payables, short-term borrowings and other current liabilities equal the total", ["L07", "L08", "L09"], ["L10"]),
        ("S4", "Cash flow ties to cash", "Opening cash plus the three cash flows equals closing cash", ["L17", "L14", "L15", "L16"], ["L18"])]
STATEMENTS = ["P&L", "Balance sheet", "Current liabilities", "Cash flow", "Notes"]


class SpreadError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _num(x):
    return f"{x:,.2f}"


def _doc(db, user, did):
    row = db.execute("""SELECT d.*, g.short_name AS client_name, g.rm_id FROM document d JOIN client_group g ON g.id=d.client_group_id WHERE d.id=?""", (did,)).fetchone()
    if not row or not db.execute("SELECT 1 FROM spread_line WHERE document_id=?", (did,)).fetchone():
        raise SpreadError(404, "Spread not found")
    if row["rm_id"] not in auth.team_ids(db, user):
        raise SpreadError(403, "This client belongs to another team")
    return row


def _check_lines(rows):
    """Returns (lines, sums). Each line gets .flags (R1-R3) and .reviewed."""
    lines = []
    by = {}
    for r in rows:
        l = dict(r)
        flags = []
        if abs((l["fy_current"] or 0) - (l["printed_current"] or 0)) > TOL:
            flags.append(("R1", f"Report prints {_num(l['printed_current'])}; extracted {_num(l['fy_current'])}"))
        if l["note_ref_value"] is not None and abs(l["fy_current"] - l["note_ref_value"]) > TOL:
            flags.append(("R2", f"{l['note_ref_label']} ({l['note_ref_page']}) shows {_num(l['note_ref_value'])}"))
        if l["confidence"] < LOW_CONF:
            flags.append(("R3", "Could not be read from the report. Enter the figure from the report" if l["confidence"] == 0 else f"Low confidence ({l['confidence']}%). Check against the report"))
        l["flags"] = flags
        l["reviewed"] = l["status"] in ("confirmed", "corrected")
        l["to_fix"] = bool(flags) and not l["reviewed"]
        l["changed"] = l["status"] == "corrected"
        lines.append(l)
        by[l["line_code"]] = l
    sums = []
    for code, title, text, left, right in SUMS:
        if not all(c in by for c in left + right):
            continue
        per = []
        ok = True
        for col, label in YEARS:
            if any(by[c][col] is None for c in left + right):    # a year the report does not hold (two years back on an upload)
                continue
            a = sum(by[c][col] for c in left)
            b = sum(by[c][col] for c in right)
            good = abs(a - b) <= TOL
            ok = ok and good
            per.append(dict(label=label, a=a, b=b, diff=round(a - b, 2), ok=good))
        sums.append(dict(code=code, title=title, text=text, ok=ok, per=per, lines=left + right))
    return lines, sums


def _progress(lines, sums):
    to_fix = [l for l in lines if l["to_fix"]]
    failing = [s for s in sums if not s["ok"]]
    return dict(total=len(lines), reviewed=sum(1 for l in lines if l["reviewed"]), to_fix=len(to_fix), failing=len(failing),
                ready=not to_fix and not failing)


def list_spreads(db, user):
    ids = auth.team_ids(db, user)
    ph = ",".join("?" * len(ids))
    out = []
    for d in db.execute(f"""SELECT d.*, g.short_name AS client_name, u.name AS rm_name FROM document d JOIN client_group g ON g.id=d.client_group_id
                           JOIN app_user u ON u.id=g.rm_id WHERE g.rm_id IN ({ph}) AND d.id IN (SELECT document_id FROM spread_line) ORDER BY d.uploaded_at DESC""", ids):
        lines, sums = _check_lines(db.execute("SELECT * FROM spread_line WHERE document_id=? ORDER BY id", (d["id"],)).fetchall())
        x = dict(d)
        x["progress"] = _progress(lines, sums)
        x["complete"] = d["status"] == "Spread complete"
        x["uploaded"] = clock.parse(d["uploaded_at"]).strftime("%d %b")
        out.append(x)
    return out


def get(db, user, did):
    d = _doc(db, user, did)
    lines, sums = _check_lines(db.execute("SELECT * FROM spread_line WHERE document_id=? ORDER BY id", (did,)).fetchall())
    groups = [(s, [l for l in lines if l["statement"] == s]) for s in STATEMENTS if any(l["statement"] == s for l in lines)]
    history = []
    for h in db.execute("""SELECT l.at, l.summary, u.name AS who FROM audit_log l LEFT JOIN app_user u ON u.id=l.user_id
                           WHERE l.affected LIKE ? ORDER BY l.at DESC, l.txn_id DESC LIMIT 8""", (f'%"{did}"%',)):
        h = dict(h)
        h["when"] = clock.parse(h["at"]).strftime("%d %b, %H:%M") if "T" in h["at"] else h["at"]
        history.append(h)
    doc = dict(d)
    doc["complete"] = d["status"] == "Spread complete"
    return dict(doc=doc, groups=groups, sums=sums, progress=_progress(lines, sums), history=history, first_page=next((l["pdf_page"] for l in lines if l["to_fix"]), 1))


def pdf_path(db, user, did):
    d = _doc(db, user, did)
    if not d["storage_path"]:
        raise SpreadError(404, "No file attached")
    if d["storage_path"].startswith("data/uploads/"):     # reports uploaded on the Spreading screen
        p = (config.UPLOAD_DIR / d["storage_path"].split("/")[-1]).resolve()
    else:
        p = (config.ROOT / d["storage_path"]).resolve()
    allowed = [(config.ROOT / "data" / "sample_docs").resolve(), config.UPLOAD_DIR.resolve()]
    if not any(str(p).startswith(str(a)) for a in allowed) or not p.is_file():
        raise SpreadError(404, "File not found")
    return p


def _line(db, did, code):
    r = db.execute("SELECT * FROM spread_line WHERE document_id=? AND line_code=?", (did, code)).fetchone()
    if not r:
        raise SpreadError(404, "Line not found")
    return r


def _open_doc(d):
    if d["status"] == "Spread complete":
        raise SpreadError(409, "This spread is signed off. No more changes.")


def accept(db, user, did, code, note=""):
    d = _doc(db, user, did)
    _open_doc(d)
    r = _line(db, did, code)
    lines, _ = _check_lines([r])
    note = (note or "").strip()
    if lines[0]["flags"] and not note:
        raise SpreadError(422, "This line is flagged. Say why the figure is right as extracted")
    cur = db.execute("UPDATE spread_line SET status='confirmed' WHERE id=? AND status=?", (r["id"], r["status"]))
    if cur.rowcount == 0:
        raise SpreadError(409, "Someone else changed this line. The latest version is shown.")
    W._audit(db, user, "accept_spread_line", f"{d['client_name']} {d['fiscal_year']}: accepted {code} {r['label']} at {_num(r['fy_current'])}" + (f". {note}" if note else ""), [did])


def correct(db, user, did, code, value, note=""):
    d = _doc(db, user, did)
    _open_doc(d)
    r = _line(db, did, code)
    note = (note or "").strip()
    try:
        v = round(float(str(value).replace(",", "").strip()), 2)
    except ValueError:
        raise SpreadError(422, "Enter the figure as a number")
    if not note:
        raise SpreadError(422, "Say where the right figure comes from (for example, page 97)")
    cur = db.execute("UPDATE spread_line SET fy_current=?, status='corrected' WHERE id=? AND fy_current=?", (v, r["id"], r["fy_current"]))
    if cur.rowcount == 0:
        raise SpreadError(409, "Someone else changed this line. The latest version is shown.")
    W._audit(db, user, "correct_spread_line", f"{d['client_name']} {d['fiscal_year']}: corrected {code} {r['label']} from {_num(r['fy_current'])} to {_num(v)}. {note}", [did])


def accept_clean(db, user, did):
    """Mark every line with no flag as reviewed in one go. Returns how many."""
    d = _doc(db, user, did)
    _open_doc(d)
    lines, _ = _check_lines(db.execute("SELECT * FROM spread_line WHERE document_id=? ORDER BY id", (did,)).fetchall())
    todo = [l for l in lines if not l["flags"] and not l["reviewed"]]
    for l in todo:
        db.execute("UPDATE spread_line SET status='confirmed' WHERE id=? AND status='extracted'", (l["id"],))
    if todo:
        W._audit(db, user, "accept_spread_clean", f"{d['client_name']} {d['fiscal_year']}: accepted {len(todo)} unflagged lines", [did])
    return len(todo)


def sign_off(db, user, did):
    d = _doc(db, user, did)
    _open_doc(d)
    lines, sums = _check_lines(db.execute("SELECT * FROM spread_line WHERE document_id=? ORDER BY id", (did,)).fetchall())
    p = _progress(lines, sums)
    if p["to_fix"] or p["failing"]:
        raise SpreadError(422, f"Not ready: {p['to_fix']} line(s) to fix and {p['failing']} failing sum check(s)")
    unreviewed = [l for l in lines if not l["reviewed"]]
    for l in unreviewed:
        db.execute("UPDATE spread_line SET status='confirmed' WHERE id=?", (l["id"],))
    cur = db.execute("UPDATE document SET status='Spread complete' WHERE id=? AND status=?", (did, d["status"]))
    if cur.rowcount == 0:
        raise SpreadError(409, "Someone else changed this spread. The latest version is shown.")
    W._audit(db, user, "sign_off_spread", f"{d['client_name']} {d['fiscal_year']}: spread signed off ({p['total']} lines, {sum(1 for l in lines if l['changed'])} corrected)", [did])


def read_again(db, user, did):
    """Read the report file again. Lines nobody has confirmed or corrected are refreshed; reviewed lines are left alone.
    Works for text PDFs. A scan has no text, so it needs OCR, which is not switched on."""
    d = _doc(db, user, did)
    _open_doc(d)
    p = pdf_path(db, user, did)
    if not X.has_text(p):
        raise SpreadError(422, "This file is a scan (pictures only), so it cannot be read like a text PDF. It needs OCR")
    lines, missing = X.extract(p)
    changed = 0
    for l in lines:
        cur = db.execute("""UPDATE spread_line SET fy_current=?, fy_prior1=?, printed_current=?, page_ref=?, pdf_page=?, confidence=?,
                            note_ref_label=?, note_ref_value=?, note_ref_page=? WHERE document_id=? AND line_code=? AND status='extracted'
                            AND (fy_current IS NOT ? OR fy_prior1 IS NOT ? OR printed_current IS NOT ?)""",
                         (l["fy_current"], l["fy_prior1"], l["printed_current"], l["page_ref"], l["pdf_page"], l["confidence"], l["note_ref_label"],
                          l["note_ref_value"], l["note_ref_page"], did, l["line_code"], l["fy_current"], l["fy_prior1"], l["printed_current"]))
        changed += cur.rowcount
    W._audit(db, user, "reread_spread", f"{d['client_name']} {d['fiscal_year']}: report read again from the file. {changed} line(s) updated, "
             f"{len(missing)} not found" + (f" ({', '.join(missing)})" if missing else ""), [did])
    return changed, missing


# ----------------------------------------------------------------------------------------------------- upload
DOC_TYPES = ["Annual report", "Audited financial statements", "Provisional financials"]
BASES = ["Consolidated", "Standalone"]
UNITS = ["INR crore", "INR lakh", "INR million"]


def fiscal_years():
    """The financial years offered on the upload form: next, current and three before. -> ['FY2026-27', ...]"""
    y = clock.now().year + (1 if clock.now().month >= 4 else 0)     # end year of the running financial year
    return [f"FY{e - 1}-{str(e)[2:]}" for e in range(y, y - 5, -1)]


def upload_options(db, user):
    ids = auth.team_ids(db, user)
    ph = ",".join("?" * len(ids))
    clients = [dict(r) for r in db.execute(f"SELECT id, short_name FROM client_group WHERE rm_id IN ({ph}) ORDER BY short_name", ids)]
    return dict(clients=clients, doc_types=DOC_TYPES, bases=BASES, units=UNITS, years=fiscal_years())


def upload(db, user, client, doc_type, fiscal_year, basis, unit, filename, data):
    """Save an uploaded report, read it, and open a spread for it. Returns the new document id.
    Lines the reader cannot find are still created (confidence 0) so the person enters them from the report."""
    client = (client or "").strip()
    g = db.execute("SELECT id, short_name, rm_id FROM client_group WHERE id=?", (client,)).fetchone()
    if not g:
        raise SpreadError(422, "Pick the client this report belongs to")
    if g["rm_id"] not in auth.team_ids(db, user):
        raise SpreadError(403, "This client belongs to another team")
    if doc_type not in DOC_TYPES or basis not in BASES or unit not in UNITS or fiscal_year not in fiscal_years():
        raise SpreadError(422, "Fill in every detail: document type, year, basis and unit")
    if not data:
        raise SpreadError(422, "Choose the report file to upload")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise SpreadError(422, f"This file is larger than {config.MAX_UPLOAD_MB} MB")
    if not data.startswith(b"%PDF"):
        raise SpreadError(422, "We could not open this file as a report")
    n = db.execute("SELECT COUNT(*) FROM document WHERE id LIKE 'D-UP-%'").fetchone()[0] + 1
    while db.execute("SELECT 1 FROM document WHERE id=?", (f"D-UP-{n:04d}",)).fetchone():
        n += 1
    did = f"D-UP-{n:04d}"
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = config.UPLOAD_DIR / f"{did}.pdf"
    path.write_bytes(data)
    try:
        try:
            readable = X.has_text(path)
        except Exception:
            raise SpreadError(422, "We could not open this file as a report")
        if not readable:
            raise SpreadError(422, "No readable text was found in this file, so no figures could be read. Reading scanned pages is not switched on yet")
        lines, missing = X.extract(path)
        if not lines:
            raise SpreadError(422, "We could not find the usual statement figures in this file. Check that it holds the financial statements")
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = len(pdf.pages)
        end_year = 2000 + int(fiscal_year[-2:])
        version = db.execute("SELECT COUNT(*) FROM document WHERE client_group_id=? AND fiscal_year=? AND basis=? AND doc_type=? AND id IN (SELECT document_id FROM spread_line)",
                             (client, fiscal_year, basis, doc_type)).fetchone()[0] + 1
        label = (filename or "report.pdf").replace("\\", "/").split("/")[-1][:80]
        db.execute("INSERT INTO document (id,client_group_id,name,doc_type,fiscal_year,period_end,basis,unit,version,source,storage_path,page_count,status,uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (did, client, f"{doc_type} {fiscal_year}: {label}", doc_type, fiscal_year, f"{end_year}-03-31", basis, unit, version,
                    f"Uploaded by {user['name']}", f"data/uploads/{did}.pdf", pages, "Spread in progress", clock.iso(clock.now())))
        ins = "INSERT INTO spread_line (document_id,line_code,label,statement,fy_current,fy_prior1,fy_prior2,printed_current,page_ref,pdf_page,confidence,status,note_ref_label,note_ref_value,note_ref_page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        for l in lines:
            db.execute(ins, (did, l["line_code"], l["label"], l["statement"], l["fy_current"], l["fy_prior1"], None, l["printed_current"], l["page_ref"], l["pdf_page"],
                             l["confidence"], "extracted", l["note_ref_label"], l["note_ref_value"], l["note_ref_page"]))
        for code, label, stmt, *_ in X.FORM:
            if code in missing:
                db.execute(ins, (did, code, label, stmt, 0.0, 0.0, None, 0.0, "p. -", 1, 0, "extracted", None, None, None))
        W._audit(db, user, "upload_spread", f"{g['short_name']} {fiscal_year}: report uploaded and read ({len(lines)} of {len(lines) + len(missing)} lines found"
                 + (f"; not found: {', '.join(missing)}" if missing else "") + ")", [did])
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return did
