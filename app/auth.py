"""Login and the current user. Passwords are PBKDF2-hashed in the database."""
import hashlib
import hmac

from fastapi import Request
from fastapi.responses import RedirectResponse, Response


class LoginRequired(Exception):
    pass


def verify(password, stored):
    try:
        algo, iters, salt, digest = stored.split("$")
    except (ValueError, AttributeError):
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
    return hmac.compare_digest(got, digest)


def login(db, username, password):
    row = db.execute("SELECT * FROM app_user WHERE username=? AND can_login=1", (username.strip().lower(),)).fetchone()
    if row and verify(password, row["password_hash"]):
        return row
    return None


def current_user(request: Request, db):
    uid = request.session.get("uid")
    if not uid:
        raise LoginRequired()
    row = db.execute("SELECT * FROM app_user WHERE id=? AND can_login=1", (uid,)).fetchone()
    if not row:
        request.session.clear()
        raise LoginRequired()
    return row


def team_ids(db, user):
    """People whose work this user may see: themselves, plus direct reports if they lead a team."""
    ids = [user["id"]]
    ids += [r["id"] for r in db.execute("SELECT id FROM app_user WHERE reports_to=?", (user["id"],))]
    return ids


def is_lead(db, user):
    return db.execute("SELECT 1 FROM app_user WHERE reports_to=? LIMIT 1", (user["id"],)).fetchone() is not None


async def login_required_handler(request: Request, exc: LoginRequired):
    if request.headers.get("HX-Request"):
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)
