from fastapi import APIRouter, Request
from fastapi.responses import Response

from ... import auth, db
from . import detail, service as svc
from ...templating import templates

router = APIRouter()


@router.get("/clients")
def clients_page(request: Request):
    p = request.query_params
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        lead = auth.is_lead(conn, user)
        rm = p.get("rm", "all" if lead else "mine")
        try:
            page = int(p.get("page", "1"))
        except ValueError:
            page = 1
        rows, total, page, pages = svc.list_clients(conn, user, rm, p.get("q", "").strip(), p.get("sector", ""), p.get("segment", ""), p.get("sort", "name"), page)
        ctx = dict(user=user, lead=lead, rows=rows, total=total, page=page, pages=pages, rm=rm, q=p.get("q", ""), sector=p.get("sector", ""),
                   segment=p.get("segment", ""), sort=p.get("sort", "name"), sorts=svc.SORTS, f=svc.filters(conn, user), active="clients")
    name = "clients/_table.html" if request.headers.get("HX-Target") == "clients-table" else "clients/index.html"
    return templates.TemplateResponse(request, name, ctx)


@router.get("/clients/{gid}")
def client_page(request: Request, gid: str):
    with db.connection() as conn:
        user = auth.current_user(request, conn)
        d = detail.get(conn, gid)
        if not d:
            return Response("Client not found", status_code=404)
        return templates.TemplateResponse(request, "clients/detail.html", {"user": user, "active": "clients", "mine": d["g"]["rm_id"] == user["id"],
                                                           "mine_work": any(w["owner_id"] == user["id"] for w in d["work"]), **d})
