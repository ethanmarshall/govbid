"""Customer accounts: register, sign in, profile, addresses, password reset, and their quotes and orders.

Separate from the staff login (auth.py): its own cookie and signing salt, and a signed-in customer can only see
requests linked to their account. Passwords are hashed with scrypt (standard library).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models_customers import Customer

COOKIE = "vps_customer"
DAYS = 60
EMAIL_RX = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


class AccountError(ValueError):
    pass


# ------------------------------------------------------------------ passwords
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(dk)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), dk)


def _check_new_password(pw: str) -> None:
    if len(pw or "") < 10:
        raise AccountError("Use a password of at least 10 characters.")
    if len(pw) > 200:
        raise AccountError("That password is too long.")


# ------------------------------------------------------------------ sessions
def _signer() -> TimestampSigner:
    from .auth import settings

    return TimestampSigner(settings()["secret"], salt="vps-customer")


def session_token(c: Customer) -> str:
    return _signer().sign(f"{c.id}.{c.session_version}").decode()


def current(db: Session, token: str | None) -> Customer | None:
    if not token:
        return None
    try:
        raw = _signer().unsign(token, max_age=DAYS * 86400).decode()
        cid, ver = (int(x) for x in raw.split("."))
    except (BadSignature, SignatureExpired, ValueError):
        return None
    c = db.get(Customer, cid)
    if not c or not c.active or c.session_version != ver:
        return None
    return c


# ------------------------------------------------------------------ guessing limits
_fails: dict[str, deque] = defaultdict(deque)


def _limited(key: str, n: int = 8, window: int = 900) -> bool:
    q = _fails[key]
    now = time.time()
    while q and now - q[0] > window:
        q.popleft()
    return len(q) >= n


def _fail(key: str) -> None:
    _fails[key].append(time.time())


# ------------------------------------------------------------------ account
def public(c: Customer) -> dict:
    return {"id": c.id, "email": c.email, "name": c.name, "company": c.company, "phone": c.phone, "addresses": c.addresses or [],
            "since": c.created_at.date().isoformat() if c.created_at else ""}


def register(db: Session, data: dict) -> Customer:
    email = str(data.get("email") or "").strip().lower()[:160]
    if not EMAIL_RX.match(email):
        raise AccountError("Enter a valid email address.")
    _check_new_password(str(data.get("password") or ""))
    name = str(data.get("name") or "").strip()[:120]
    if not name:
        raise AccountError("Enter your name.")
    if db.scalar(select(Customer).where(Customer.email == email)):
        raise AccountError("There is already an account for that email. Sign in, or reset your password.")
    c = Customer(email=email, password_hash=hash_password(data["password"]), name=name,
                 company=str(data.get("company") or "").strip()[:160], phone=_phone(data.get("phone")))
    db.add(c)
    db.commit()
    return c


def login(db: Session, email: str, password: str, ip: str) -> Customer:
    email = (email or "").strip().lower()
    if _limited(f"ip:{ip}", 20) or _limited(f"email:{email}"):
        raise AccountError("Too many tries. Wait 15 minutes, or reset your password.")
    c = db.scalar(select(Customer).where(Customer.email == email))
    if not c or not c.active or not check_password(password or "", c.password_hash):
        _fail(f"ip:{ip}")
        _fail(f"email:{email}")
        time.sleep(0.3)
        raise AccountError("Wrong email or password.")
    c.last_login = datetime.utcnow()
    db.commit()
    return c


def _phone(v) -> str:
    return re.sub(r"[^0-9+()\-. x]", "", str(v or ""))[:40]


ADDRESS_KEYS = {"label": 40, "name": 120, "company": 160, "line1": 160, "line2": 160, "city": 80, "state": 40, "zip": 20, "country": 60, "phone": 40}


def clean_address(a: dict) -> dict:
    out = {k: str(a.get(k) or "").strip()[:n] for k, n in ADDRESS_KEYS.items()}
    out["country"] = out["country"] or "United States"
    return out


def address_ok(a: dict) -> bool:
    return all(a.get(k) for k in ("name", "line1", "city", "state", "zip"))


def update(db: Session, c: Customer, data: dict) -> Customer:
    if "name" in data:
        name = str(data.get("name") or "").strip()[:120]
        if not name:
            raise AccountError("Enter your name.")
        c.name = name
    if "company" in data:
        c.company = str(data.get("company") or "").strip()[:160]
    if "phone" in data:
        c.phone = _phone(data.get("phone"))
    if "addresses" in data:
        addrs = [clean_address(a) for a in (data.get("addresses") or [])[:10] if isinstance(a, dict)]
        bad = [a for a in addrs if not address_ok(a)]
        if bad:
            raise AccountError("Each address needs a name, street, city, state and ZIP code.")
        c.addresses = addrs
    if data.get("new_password"):
        if not check_password(str(data.get("password") or ""), c.password_hash):
            raise AccountError("Your current password is not right.")
        _check_new_password(str(data["new_password"]))
        c.password_hash = hash_password(data["new_password"])
        c.session_version += 1  # signs out every other device
    db.commit()
    return c


def start_reset(db: Session, email: str, base_url: str, ip: str) -> None:
    """Email a reset link (when email is set up). Says nothing about whether the account exists."""
    from .cli import send_email

    email = (email or "").strip().lower()
    if _limited(f"reset:{ip}", 5, 3600) or _limited(f"reset-to:{email}", 3, 86400):
        raise AccountError("Too many reset requests. Try again later.")
    _fail(f"reset:{ip}")
    _fail(f"reset-to:{email}")
    c = db.scalar(select(Customer).where(Customer.email == email))
    if not c or not c.active:
        return
    tok = secrets.token_urlsafe(32)
    c.reset_hash = hashlib.sha256(tok.encode()).hexdigest()
    c.reset_expires = datetime.utcnow() + timedelta(hours=2)
    db.commit()
    link = f"{base_url}/quote/account?reset={tok}&e={c.email}"
    try:
        send_email("Reset your password", f"Someone asked to reset the password for {c.email}.\n\nTo choose a new password, open this link "
                                          f"within 2 hours:\n{link}\n\nIf it was not you, ignore this email.", to=c.email, allow_customer=True)
    except Exception as exc:  # noqa: BLE001
        raise AccountError("We could not send the email right now. Contact us and we will help you sign in.") from exc


def finish_reset(db: Session, email: str, token: str, new_password: str) -> Customer:
    c = db.scalar(select(Customer).where(Customer.email == (email or "").strip().lower()))
    ok = (c and c.reset_hash and c.reset_expires and c.reset_expires > datetime.utcnow()
          and hmac.compare_digest(c.reset_hash, hashlib.sha256((token or "").encode()).hexdigest()))
    if not ok:
        raise AccountError("That reset link is not valid or has expired. Ask for a new one.")
    _check_new_password(new_password)
    c.password_hash = hash_password(new_password)
    c.reset_hash, c.reset_expires = "", None
    c.session_version += 1
    db.commit()
    return c


def email_enabled() -> bool:
    return bool(os.getenv("SMTP_HOST"))
