"""Client list for the book of business."""
from ... import auth, clock, config

SORTS = {
    "name": ("Name", "g.short_name"),
    "limit": ("Largest limit", "g.sanctioned_cr DESC"),
    "watch": ("Watch flag", "CASE g.watch_flag WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, g.short_name"),
    "review": ("Review due", "g.review_due"),
    "contact": ("Longest since contact", "g.last_contact"),
}


def filters(db, user):
    return dict(
        sectors=[r[0] for r in db.execute("SELECT DISTINCT sector FROM client_group ORDER BY 1")],
        segments=[r[0] for r in db.execute("SELECT DISTINCT segment FROM client_group ORDER BY 1")],
        rms=db.execute("SELECT DISTINCT u.id, u.name FROM client_group g JOIN app_user u ON u.id=g.rm_id ORDER BY u.name").fetchall())


def list_clients(db, user, rm="mine", q="", sector="", segment="", sort="name", page=1):
    where, args = ["1=1"], []
    if rm == "mine":
        where.append("g.rm_id = ?")
        args.append(user["id"])
    elif rm not in ("", "all"):
        where.append("g.rm_id = ?")
        args.append(rm)
    if q:
        where.append("(g.name LIKE ? OR g.short_name LIKE ? OR g.id LIKE ?)")
        args += [f"%{q}%"] * 3
    if sector:
        where.append("g.sector = ?")
        args.append(sector)
    if segment:
        where.append("g.segment = ?")
        args.append(segment)
    order = SORTS.get(sort, SORTS["name"])[1]
    base = " FROM client_group g JOIN app_user u ON u.id = g.rm_id WHERE " + " AND ".join(where)
    total = db.execute("SELECT COUNT(*)" + base, args).fetchone()[0]
    page = max(1, page)
    rows = db.execute(
        "SELECT g.*, u.name AS rm_name, "
        "(SELECT COUNT(*) FROM work_item w WHERE w.client_group_id=g.id AND w.state IN ('Open','Accepted','In progress','Needs information')) AS open_work, "
        "(SELECT COUNT(*) FROM alert a WHERE a.client_group_id=g.id AND a.state IN ('New','Under review','Responded')) AS open_alerts" + base +
        f" ORDER BY {order} LIMIT ? OFFSET ?", args + [config.PAGE_SIZE, (page - 1) * config.PAGE_SIZE]).fetchall()
    today = clock.now().date()
    out = []
    for r in rows:
        c = dict(r)
        c["util"] = round(100 * r["outstanding_cr"] / r["sanctioned_cr"]) if r["sanctioned_cr"] else 0
        last = clock.parse(r["last_contact"])
        c["days_since"] = (today - last.date()).days if last else None
        c["contact_late"] = c["days_since"] is not None and c["days_since"] > r["cadence_days"]
        out.append(c)
    return out, total, page, max(1, -(-total // config.PAGE_SIZE))


def get_group(db, gid):
    return db.execute("SELECT g.*, u.name AS rm_name FROM client_group g JOIN app_user u ON u.id=g.rm_id WHERE g.id=?", (gid,)).fetchone()
