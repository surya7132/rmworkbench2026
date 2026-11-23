from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from ... import auth, db
from . import export, service as svc
from ...templating import templates

router = APIRouter()


def _page(request, conn, user, did, error=None, status=200, notice=None):
    ctx = dict(user=user, active="spreading", error=error, notice=notice, **svc.get(conn, user, did))
    name = "spreading/_body.html" if request.headers.get("HX-Request") else "spreading/detail.html"
    return templates.TemplateResponse(request, name, ctx, status_code=status)


def _index(request, conn, user, error=None, form=None, status=200):
    ctx = dict(user=user, active="spreading", spreads=svc.list_spreads(conn, user), error=error, form=form or {}, **svc.upload_options(conn, user))
    return templates.TemplateResponse(request, "spreading/index.html", ctx, status_code=status)


@router.get("/spreading")
def spreading_list(request: Request):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        return _index(request, conn, user)


@router.post("/spreading/upload")
async def spread_upload(request: Request):
    f = await request.form()
    up = f.get("file")
    data = await up.read() if up is not None and hasattr(up, "read") else b""
    form = {k: f.get(k, "") for k in ("client", "doc_type", "fiscal_year", "basis", "unit")}
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            did = svc.upload(conn, user, filename=getattr(up, "filename", ""), data=data, **form)
        except svc.SpreadError as ex:
            return _index(request, conn, user, error=ex.message, form=form, status=ex.status)
    return RedirectResponse(f"/spreading/{did}?new=1", status_code=303)


@router.get("/spreading/{did}")
def spread_page(request: Request, did: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            notice = None
            if request.query_params.get("new"):
                d = svc.get(conn, user, did)
                notice = (f"Report uploaded and read. {d['progress']['total']} lines are listed below. "
                          "Lines marked in red need a look: check them against the report, then accept or correct.")
            return _page(request, conn, user, did, notice=notice)
        except svc.SpreadError as ex:
            return HTMLResponse(ex.message, status_code=ex.status)


@router.get("/spreading/{did}/export/{fmt}")
def spread_export(request: Request, did: str, fmt: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            if fmt not in ("xlsx", "csv"):
                return HTMLResponse("Unknown format", status_code=404)
            body, name, kind = (export.to_xlsx if fmt == "xlsx" else export.to_csv)(conn, user, did)
        except svc.SpreadError as ex:
            return HTMLResponse(ex.message, status_code=ex.status)
    return Response(body, media_type=kind, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/spreading/{did}/pdf")
def spread_pdf(request: Request, did: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            p = svc.pdf_path(conn, user, did)
        except svc.SpreadError as ex:
            return HTMLResponse(ex.message, status_code=ex.status)
    return FileResponse(p, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@router.post("/spreading/{did}/{action}")
async def spread_action(request: Request, did: str, action: str):
    f = await request.form()
    error = None
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            if action == "accept":
                svc.accept(conn, user, did, f.get("code", ""), f.get("note"))
            elif action == "correct":
                svc.correct(conn, user, did, f.get("code", ""), f.get("value", ""), f.get("note"))
            elif action == "accept-clean":
                svc.accept_clean(conn, user, did)
            elif action == "read-again":
                n, miss = svc.read_again(conn, user, did)
            elif action == "sign-off":
                svc.sign_off(conn, user, did)
            else:
                return HTMLResponse("Unknown action", status_code=404)
        except svc.SpreadError as ex:
            error = ex.message
            if ex.status in (403, 404):
                return HTMLResponse(ex.message, status_code=ex.status)
        try:
            return _page(request, conn, user, did, error)
        except svc.SpreadError as ex:
            return HTMLResponse(ex.message, status_code=ex.status)
