from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from ... import auth, db
from . import service as svc
from ...templating import templates

router = APIRouter()


def _page_ctx(conn, user, scope, status, kind, client, q):
    groups, n = svc.list_work(conn, user, scope, status, kind, client, q)
    return dict(user=user, lead=auth.is_lead(conn, user), scope=scope, status=status, kind=kind, client=client, q=q, groups=groups, n=n,
                kinds=svc.KINDS, summary=svc.summary(conn, user, scope), clients=svc.client_options(conn, user, scope), active="work")


@router.get("/work")
def work_page(request: Request):
    p = request.query_params
    scope = p.get("scope", "mine")
    status, kind, client, q = p.get("status", "active"), p.get("kind", "all"), p.get("client", ""), p.get("q", "").strip()
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        ctx = _page_ctx(conn, user, scope, status, kind, client, q)
    name = "work/_list.html" if request.headers.get("HX-Target") == "work-list" else "work/index.html"
    return templates.TemplateResponse(request, name, ctx)


def _row_response(request, conn, user, wid, error=None, status_code=200):
    w = svc.get_one(conn, wid)
    headers = {"X-Compass-Error": str(status_code)} if error else {}
    return templates.TemplateResponse(request, "work/_row.html", {"w": w, "user": user, "error": error},
                                      status_code=200, headers=headers)


@router.post("/work/{wid}/state")
async def work_state(request: Request, wid: str):
    form = await request.form()
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            svc.change_state(conn, user, wid, str(form.get("to", "")), int(form.get("version", 0) or 0), str(form.get("note", "")), form.get("confirm") == "1")
        except svc.ServiceError as e:
            if e.status in (403, 404):
                return Response(e.message, status_code=e.status)
            conn.rollback()
            return _row_response(request, conn, user, wid, error=e.message, status_code=e.status)
        return _row_response(request, conn, user, wid)


@router.post("/work/{wid}/note")
async def work_note(request: Request, wid: str):
    form = await request.form()
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            svc.add_note(conn, user, wid, str(form.get("text", "")))
        except svc.ServiceError as e:
            if e.status in (403, 404):
                return Response(e.message, status_code=e.status)
            return templates.TemplateResponse(request, "work/_thread.html",
                                              {"w": svc.get_one(conn, wid), "thread": svc.thread(conn, wid), "error": e.message})
        return templates.TemplateResponse(request, "work/_thread.html", {"w": svc.get_one(conn, wid), "thread": svc.thread(conn, wid), "error": None})


@router.get("/work/{wid}/thread")
def work_thread(request: Request, wid: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        w = svc.get_one(conn, wid)
        if w["owner_id"] not in auth.team_ids(conn, user):
            return Response("This item belongs to someone else", status_code=403)
        return templates.TemplateResponse(request, "work/_thread.html", {"w": w, "thread": svc.thread(conn, wid), "error": None})
