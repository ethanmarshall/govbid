"""Web security for the whole app: response headers, a same-origin check on requests that change data, and
private links kept out of the server logs.

Headers
  Content-Security-Policy  pages may only run scripts from this site (blocks injected scripts), load fonts from
                           Google Fonts, and may not be framed by other sites (clickjacking).
  Strict-Transport-Security  browsers always use HTTPS for this site (when served over HTTPS).
  Referrer-Policy same-origin  private quote links (?t=...) are never sent to other sites, including Stripe.
  X-Content-Type-Options, Permissions-Policy, and no caching of account and quote data.

Same-origin check
  Sign-in cookies are SameSite=Lax, so browsers already leave them off cross-site form posts. As a second lock,
  any POST/PUT/PATCH/DELETE to /api/ that comes from a page on another site (its Origin header, or the browser's
  Sec-Fetch-Site) is refused. Stripe's webhook is exempt: it is checked by its signature instead.
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self' blob:; "
       "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
EXEMPT = {"/api/public/stripe/webhook"}
DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}
NO_STORE = ("/api/public/account", "/api/public/quote/", "/api/portal/", "/api/auth/")


def _allowed_origins(request: Request) -> set[str]:
    out = set(DEV_ORIGINS)
    host = request.headers.get("host", "")
    if host:
        out |= {f"https://{host}", f"http://{host}"}
    for env in ("PUBLIC_URL", "APP_URL"):
        u = (os.getenv(env) or "").strip()
        if u:
            p = urlsplit(u)
            out.add(f"{p.scheme}://{p.netloc}")
    return out


def cross_site(request: Request) -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS") or not request.url.path.startswith("/api/") or request.url.path in EXEMPT:
        return False
    origin = request.headers.get("origin")
    if origin and origin != "null":
        return origin.rstrip("/") not in _allowed_origins(request)
    if origin == "null":
        return True
    return request.headers.get("sec-fetch-site") == "cross-site"


async def middleware(request: Request, call_next):
    if cross_site(request):
        return JSONResponse({"detail": "Requests from other websites are not allowed."}, status_code=403)
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("X-Frame-Options", "SAMEORIGIN")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    path = request.url.path
    if path.startswith(NO_STORE) and not path.endswith(".svg"):
        h["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------ logs
_SECRET_PARAM = re.compile(r"([?&](?:t|token|reset|paid|session_id|code)=)[^&\s\"]+", re.I)


class RedactFilter(logging.Filter):
    """Access logs record each URL. Private quote links and reset tokens are replaced with *** before they are written."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, tuple):
            record.args = tuple(_SECRET_PARAM.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = _SECRET_PARAM.sub(r"\1***", record.msg)
        return True


def install_log_filter() -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactFilter) for f in lg.filters):
            lg.addFilter(RedactFilter())


# ------------------------------------------------------------------ staff password
def weak_staff_password() -> bool:
    pw = os.getenv("APP_PASSWORD", "")
    return bool(pw) and (len(pw) < 12 or len(set(pw)) < 5)
