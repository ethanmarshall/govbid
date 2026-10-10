"""Single-user login for a hosted copy of GovBid Pro.

Login is required whenever APP_PASSWORD is set (always set it on a server). Without it, the app
runs open, which is only safe on your own computer.

  APP_USERNAME      login name (default "admin")
  APP_PASSWORD      the password
  SESSION_SECRET    random string used to sign the login cookie (set it so logins survive restarts)
  SESSION_DAYS      how long a login lasts (default 30)
  COOKIE_SECURE     1 on an HTTPS site so the cookie is only sent over HTTPS
  CALENDAR_TOKEN    secret for the calendar feed URL (calendar apps cannot log in)

The session is a signed, HttpOnly, SameSite=Lax cookie. Lax blocks the cookie on cross-site POSTs,
which covers CSRF for this JSON API. Repeated wrong passwords from one address are slowed down.
"""
from __future__ import annotations

import hmac
import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from pydantic import BaseModel

COOKIE = "govbid_session"
OPEN_PATHS = {"/api/auth/login", "/api/auth/status", "/api/auth/logout", "/api/health"}
MAX_FAILS, WINDOW_S = 5, 15 * 60


def settings() -> dict:
    return {
        "username": os.getenv("APP_USERNAME", "admin"),
        "password": os.getenv("APP_PASSWORD", ""),
        "secret": os.getenv("SESSION_SECRET", "") or _fallback_secret(),
        "days": float(os.getenv("SESSION_DAYS", "30") or 30),
        "secure": os.getenv("COOKIE_SECURE", "") in ("1", "true", "yes"),
        "calendar_token": os.getenv("CALENDAR_TOKEN", ""),
    }


_FALLBACK = secrets.token_urlsafe(32)


def _fallback_secret() -> str:
    return _FALLBACK  # without SESSION_SECRET, logins reset when the server restarts


def enabled() -> bool:
    return bool(os.getenv("APP_PASSWORD"))


def _signer() -> TimestampSigner:
    return TimestampSigner(settings()["secret"], salt="govbid-login")


def _session_value(s: dict) -> str:
    """The signed cookie value: the username plus a fingerprint of the password, so changing APP_PASSWORD signs
    every device out."""
    import hashlib

    fp = hashlib.sha256(f"{s['password']}|{s['secret']}".encode()).hexdigest()[:16]
    return f"{s['username']}|{fp}"


def session_token() -> str:
    return _signer().sign(_session_value(settings())).decode()


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    s = settings()
    try:
        value = _signer().unsign(token, max_age=int(s["days"] * 86400)).decode()
    except (BadSignature, SignatureExpired):
        return False
    return hmac.compare_digest(value, _session_value(s))


_fails: dict[str, deque] = defaultdict(deque)


# Across all addresses: caps guessing from many IPs at once (a short password must not be brute-forceable)
GLOBAL_MAX_FAILS, GLOBAL_WINDOW_S = 30, 60 * 60
_all_fails: deque = deque()


def _client(request: Request) -> str:
    """The address the hosting proxy saw. The proxy appends it as the LAST X-Forwarded-For entry; earlier
    entries come from the client and can be forged, so they must not be used for lockouts."""
    fwd = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
    return fwd[-1] if fwd else (request.client.host if request.client else "?")


def _prune(q: deque, window: float) -> None:
    now = time.time()
    while q and now - q[0] > window:
        q.popleft()


def _too_many(ip: str) -> bool:
    from .security import weak_staff_password

    q = _fails[ip]
    _prune(q, WINDOW_S)
    if weak_staff_password():  # a short password could be guessed from many addresses: allow far fewer misses a day
        _prune(_all_fails, 24 * 3600)
        return len(q) >= MAX_FAILS or len(_all_fails) >= 10
    _prune(_all_fails, GLOBAL_WINDOW_S)
    return len(q) >= MAX_FAILS or len(_all_fails) >= GLOBAL_MAX_FAILS


def is_open_path(path: str, query: dict) -> bool:
    if not path.startswith("/api/"):
        return True  # the page itself and its assets; the app asks for login before showing data
    if path in OPEN_PATHS or path.startswith("/api/public/"):  # the customer quote portal (app/portal_api.py)
        return True
    if path == "/api/calendar.ics":
        tok = settings()["calendar_token"]
        return bool(tok) and hmac.compare_digest(query.get("token", ""), tok)
    return False


async def middleware(request: Request, call_next):
    if enabled() and not is_open_path(request.url.path, dict(request.query_params)) and not valid_session(request.cookies.get(COOKIE)):
        return JSONResponse({"detail": "Please sign in."}, status_code=401)
    return await call_next(request)


router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    username: str
    password: str


@router.get("/status")
def status(request: Request):
    s = settings()
    signed_in = (not enabled()) or valid_session(request.cookies.get(COOKIE))
    return {"login_required": enabled(), "signed_in": signed_in, "username": s["username"] if enabled() else None,
            # calendar apps cannot sign in, so the feed URL carries its own secret (only shown once signed in)
            "calendar_token": s["calendar_token"] if (signed_in and enabled()) else "",
            "weak_password": bool(signed_in and enabled() and __import__("app.security", fromlist=["x"]).weak_staff_password())}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    if not enabled():
        return {"ok": True, "login_required": False}
    ip = _client(request)
    if _too_many(ip):
        raise HTTPException(429, "Too many wrong passwords. Wait a while (up to an hour) and try again.")
    s = settings()
    ok = hmac.compare_digest(body.username.strip().encode(), s["username"].encode()) & hmac.compare_digest(body.password.encode(), s["password"].encode())
    if not ok:
        _fails[ip].append(time.time())
        _all_fails.append(time.time())
        time.sleep(0.5)
        raise HTTPException(401, "Wrong username or password.")
    _fails.pop(ip, None)
    token = session_token()
    response.set_cookie(COOKIE, token, max_age=int(s["days"] * 86400), httponly=True, samesite="lax", secure=s["secure"], path="/")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
