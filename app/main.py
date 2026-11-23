"""Compass: relationship manager workbench.

Run:   python -m app.main        (or: uvicorn app.main:app --reload)
Open:  http://127.0.0.1:8000   (demo logins are shown on the sign-in page)
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, db
from .features.alerts import router as alerts
from .features.auth import router as auth_router
from .features.clients import router as clients
from .features.events import router as events
from .features.home import router as home
from .features.meetings import router as meetings
from .features.spreading import router as spreading
from .features.work import router as work

db.ensure_db()

app = FastAPI(title="Compass", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, same_site="lax", max_age=60 * 60 * 8)
app.add_exception_handler(auth.LoginRequired, auth.login_required_handler)
app.mount("/static", StaticFiles(directory=str(config.ROOT / "app" / "static")), name="static")
for r in (auth_router.router, work.router, clients.router, events.router, meetings.router, alerts.router, spreading.router, home.router):
    app.include_router(r)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
