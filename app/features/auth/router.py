from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ... import auth, db
from ...templating import templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    if request.session.get("uid"):
        return RedirectResponse("/work", status_code=303)
    with db.connection() as conn:
        demo = conn.execute("SELECT name, role, function, username FROM app_user WHERE can_login=1 ORDER BY CASE username WHEN 'rohan.rm' THEN 1 WHEN 'karan.rm' THEN 2 WHEN 'meera.lead' THEN 3 WHEN 'ananya.credit' THEN 4 ELSE 5 END").fetchall()
    return templates.TemplateResponse(request, "auth/login.html", {"demo": demo, "error": None})


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    with db.connection() as conn:
        user = auth.login(conn, str(form.get("username", "")), str(form.get("password", "")))
        demo = conn.execute("SELECT name, role, function, username FROM app_user WHERE can_login=1 ORDER BY CASE username WHEN 'rohan.rm' THEN 1 WHEN 'karan.rm' THEN 2 WHEN 'meera.lead' THEN 3 WHEN 'ananya.credit' THEN 4 ELSE 5 END").fetchall()
    if not user:
        return templates.TemplateResponse(request, "auth/login.html", {"demo": demo, "error": "That username and password do not match."}, status_code=401)
    request.session["uid"] = user["id"]
    return RedirectResponse("/work", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.post("/clock/advance")
async def advance_clock(request: Request):
    """Move the demo day forward (default one day). Stays on the same page."""
    from urllib.parse import urlsplit
    from ... import clock
    with db.connection() as conn:
        auth.current_user(request, conn)
    form = await request.form()
    try:
        hours = max(1, min(int(form.get("hours", 24)), 24 * 30))
    except ValueError:
        hours = 24
    clock.advance(hours)
    ref = urlsplit(request.headers.get("referer", ""))
    back = (ref.path or "/work") + (f"?{ref.query}" if ref.query else "")
    return RedirectResponse(back if back.startswith("/") else "/work", status_code=303)


@router.post("/reset")
async def reset_demo(request: Request):
    """Rebuild the whole demo from the seed. Keeps you signed in."""
    with db.connection() as conn:
        auth.current_user(request, conn)
    db.rebuild()
    return RedirectResponse("/work", status_code=303)
