from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from ... import auth, db
from . import service as svc
from ...templating import templates

router = APIRouter()


@router.get("/meetings")
def meetings_page(request: Request):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        ctx = dict(user=user, active="meetings", **svc.list_meetings(conn, user))
    return templates.TemplateResponse(request, "meetings/index.html", ctx)


def _detail(request, conn, user, mid, error=None, status_code=200, form=None):
    try:
        d = svc.get(conn, user, mid)
    except svc.MeetingError as ex:
        return Response(ex.message, status_code=ex.status)
    p = request.query_params
    done = [x for x in p.get("done", "").split(",") if x]
    return templates.TemplateResponse(request, "meetings/detail.html", dict(user=user, active="meetings", error=error, done=done, saved=p.get("saved"), form=form or {}, **d), status_code=status_code)


@router.get("/meetings/{mid}")
def meeting_page(request: Request, mid: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        return _detail(request, conn, user, mid)


@router.post("/meetings/{mid}/prep")
async def meeting_prep(request: Request, mid: str):
    f = await request.form()
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            svc.save_prep(conn, user, mid, f.get("objective"), f.get("success"), f.get("must"), f.get("if_time"), f.get("avoid"), f.get("ready") == "1")
        except svc.MeetingError as ex:
            return _detail(request, conn, user, mid, error=ex.message, status_code=ex.status)
    return RedirectResponse(f"/meetings/{mid}?saved=1", status_code=303)


@router.post("/meetings/{mid}/debrief")
async def meeting_debrief(request: Request, mid: str):
    f = await request.form()
    titles, owners, dues, kinds = (f.getlist(k) for k in ("f_title", "f_owner", "f_due", "f_kind"))
    items = [dict(title=t, owner=o, due=d, kind=k) for t, o, d, k in zip(titles, owners, dues, kinds)]
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            created = svc.debrief(conn, user, mid, f.get("notes"), f.get("decisions"), items)
        except svc.MeetingError as ex:
            return _detail(request, conn, user, mid, error=ex.message, status_code=ex.status, form=dict(notes=f.get("notes"), decisions=f.get("decisions")))
    return RedirectResponse(f"/meetings/{mid}?done={','.join(created) or 'none'}", status_code=303)


@router.post("/meetings/{mid}/ai")
async def meeting_ai(request: Request, mid: str):
    f = await request.form()
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            return JSONResponse({"text": svc.ai_text(conn, user, mid, f.get("mode"), f.get("text"))})
        except svc.MeetingError as ex:
            return JSONResponse({"error": ex.message}, status_code=ex.status)
