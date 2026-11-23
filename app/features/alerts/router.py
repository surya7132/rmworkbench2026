from fastapi import APIRouter, Request

from ... import auth, db
from . import service as svc
from ...templating import templates

router = APIRouter()


def _filters(p):
    return dict(state=p.get("state", "open"), prio=p.get("prio", "all"), category=p.get("category", ""), q=p.get("q", "").strip())


@router.get("/alerts")
def alerts_page(request: Request):
    f = _filters(request.query_params)
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        groups, n = svc.list_alerts(conn, user, **f)
        ctx = dict(user=user, active="alerts", groups=groups, n=n, summary=svc.summary(conn, user), categories=svc.categories(conn, user), states=svc.STATES,
                   prio_text=svc.PRIO_TEXT, dismiss_reasons=svc.DISMISS_REASONS, resolve_reasons=svc.RESOLVE_REASONS, **f)
    name = "alerts/_list.html" if request.headers.get("HX-Target") == "alerts-list" else "alerts/index.html"
    return templates.TemplateResponse(request, name, ctx)


@router.get("/alerts/tiles")
def alerts_tiles(request: Request):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        return templates.TemplateResponse(request, "alerts/_tiles.html", dict(summary=svc.summary(conn, user), prio_text=svc.PRIO_TEXT, prio=request.query_params.get("prio", "all")))


@router.post("/alerts/{aid}/{action}")
async def alert_action(request: Request, aid: str, action: str):
    f = await request.form()
    error = None
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        try:
            svc.transition(conn, user, aid, action, f.get("note"), f.get("reason"))
        except svc.AlertError as ex:
            error = ex.message
            if ex.status in (403, 404):
                return templates.TemplateResponse(request, "alerts/_card.html", dict(a=None, error=ex.message), status_code=ex.status)
        try:
            a = svc.get_one(conn, user, aid)
        except svc.AlertError as ex:
            return templates.TemplateResponse(request, "alerts/_card.html", dict(a=None, error=ex.message), status_code=ex.status)
    r = templates.TemplateResponse(request, "alerts/_card.html", dict(a=a, error=error, dismiss_reasons=svc.DISMISS_REASONS, resolve_reasons=svc.RESOLVE_REASONS))
    r.headers["HX-Trigger"] = "alerts-changed"
    return r
