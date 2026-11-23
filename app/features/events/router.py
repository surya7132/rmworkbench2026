from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ... import auth, db
from . import service as svc
from ...templating import templates

router = APIRouter()


@router.get("/events")
def events_page(request: Request):
    p = request.query_params
    kind, q = p.get("kind", "all"), p.get("q", "").strip()
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        ctx = dict(user=user, active="events", kind=kind, q=q, kinds=svc.KINDS, events=svc.list_events(conn, user, kind, q),
                   counts=svc.counts(conn, user), clusters=svc.pending_clusters(conn) if kind == "all" and not q else [])
    name = "events/_list.html" if request.headers.get("HX-Target") == "events-list" else "events/index.html"
    return templates.TemplateResponse(request, name, ctx)


def _detail(request, conn, user, eid, error=None, status_code=200):
    try:
        d = svc.get(conn, user, eid)
    except svc.EventError as ex:
        return Response(ex.message, status_code=ex.status)
    p = request.query_params
    done = [x for x in p.get("done", "").split(",") if x]
    return templates.TemplateResponse(request, "events/detail.html", dict(user=user, active="events", error=error, done=done, **d), status_code=status_code)


@router.get("/events/{eid}")
def event_page(request: Request, eid: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        return _detail(request, conn, user, eid)


@router.post("/events/{eid}/process")
def event_process(request: Request, eid: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            ids, created = svc.process(conn, user, eid)
        except svc.EventError as ex:
            return _detail(request, conn, user, eid, error=ex.message, status_code=ex.status)
    return RedirectResponse(f"/events/{eid}?done={','.join(created)}", status_code=303)
