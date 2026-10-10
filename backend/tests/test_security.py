"""Security headers, the same-origin check, log redaction, and payment matching."""
import json
import logging
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import checkout, customers, portal, security
from app.main import app

FIX = Path(__file__).parent / "fixtures"
SHIP = {"name": "Dana Lee", "line1": "1 Main St", "city": "Ballston Spa", "state": "NY", "zip": "12020"}


@pytest.fixture
def client():
    for lim in (portal.QUOTE_LIMIT, portal.REPRICE_LIMIT, portal.SUBMIT_LIMIT):
        lim.clear()
    customers._fails.clear()
    with TestClient(app) as c:
        c.put("/api/portal/settings", json={"enabled": True})
        yield c
        c.put("/api/portal/settings", json={"enabled": False})


def test_headers_on_pages_and_api(client):
    for path in ("/quote", "/api/public/info", "/api/public/account"):
        h = client.get(path).headers
        assert "script-src 'self'" in h["content-security-policy"] and "frame-ancestors 'self'" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "same-origin" and h["x-frame-options"] == "SAMEORIGIN"
    assert client.get("/api/public/account").headers["cache-control"] == "no-store"
    assert "strict-transport-security" in client.get("/quote", headers={"x-forwarded-proto": "https"}).headers


def test_cross_site_requests_refused(client):
    body = {"email": "x@example.com", "password": "nope"}
    assert client.post("/api/public/account/login", json=body, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/public/account/login", json=body, headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.post("/api/public/account/login", json=body, headers={"origin": "null"}).status_code == 403
    assert client.post("/api/public/account/login", json=body, headers={"origin": "http://testserver"}).status_code == 400  # same site: normal answer
    assert client.put("/api/portal/settings", json={"enabled": True}, headers={"origin": "https://evil.example"}).status_code == 403
    # Stripe's webhook has no Origin of ours; it is checked by signature instead
    assert client.post("/api/public/stripe/webhook", content=b"{}", headers={"origin": "https://stripe.com"}).status_code in (400, 404)


def test_private_links_are_redacted_from_logs():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4", "GET", "/api/public/quote/RQ-1?token=SECRET123&x=1", "1.1", 200), None)
    security.RedactFilter().filter(rec)
    assert "SECRET123" not in rec.getMessage() and "token=***" in rec.getMessage()
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", ("/quote/account?reset=abc&e=a@b.c",), None)
    security.RedactFilter().filter(rec)
    assert "abc" not in rec.getMessage()


def test_weak_and_common_passwords_refused(client):
    for pw in ("password123", "aaaaaaaaaaaa", "dana@example.com"):
        r = client.post("/api/public/account/register", json={"email": "dana@example.com", "password": pw, "name": "D"})
        assert r.status_code == 400 and "easy to guess" in r.json()["detail"]


def test_old_password_hashes_are_upgraded(client):
    from app.db import SessionLocal
    from app.models_customers import Customer

    em = f"old{time.time_ns()}@example.com"
    client.post("/api/public/account/register", json={"email": em, "password": "a-long-password", "name": "Pat"})
    with SessionLocal() as db:
        c = db.query(Customer).filter_by(email=em).one()
        import hashlib, secrets
        salt = secrets.token_bytes(16)
        c.password_hash = f"scrypt$16384$8$1${salt.hex()}${hashlib.scrypt(b'a-long-password', salt=salt, n=16384, r=8, p=1, dklen=32).hex()}"
        db.commit()
    assert client.post("/api/public/account/login", json={"email": em, "password": "a-long-password"}).status_code == 200
    with SessionLocal() as db:
        assert db.query(Customer).filter_by(email=em).one().password_hash.startswith(f"scrypt${customers.SCRYPT_N}$")


def test_sign_out_everywhere(client):
    client.post("/api/public/account/register", json={"email": f"e{time.time_ns()}@example.com", "password": "a-long-password", "name": "Pat"})
    cookie = client.cookies.get(customers.COOKIE)
    client.post("/api/public/account/logout?everywhere=1")
    with TestClient(app) as other:
        other.cookies.set(customers.COOKIE, cookie)
        assert other.get("/api/public/account").json()["customer"] is None


def test_card_payment_must_match_and_old_pages_are_closed(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(portal, "notify", lambda req, s: None)
    monkeypatch.setattr(portal, "confirm_to_customer", lambda req, s, url: None)
    alerts, expired, n = [], [], {"i": 0}
    monkeypatch.setattr(checkout, "_alert", lambda req, text: alerts.append(text))

    def handler(req: httpx.Request):
        if req.url.path == "/v1/checkout/sessions":
            n["i"] += 1
            return httpx.Response(200, json={"id": f"cs_{n['i']}", "url": f"https://checkout.stripe.com/c/pay/cs_{n['i']}"})
        if req.url.path.endswith("/expire"):
            expired.append(req.url.path.split("/")[-2])
            return httpx.Response(200, json={})
        return httpx.Response(404, json={})

    monkeypatch.setattr(checkout, "_transport", httpx.MockTransport(handler))
    q = client.post("/api/public/quote", data={"quantity": "2"}, files=[("files", ("b.step", (FIX / "cad" / "machined_block.step").read_bytes()))]).json()
    order = {"token": q["token"], "method": "card", "ship_to": SHIP, "accept_terms": True, "contact": {"name": "Dana", "email": "dana@example.com"}}
    client.post(f"/api/public/quote/{q['ref']}/checkout", json=order)
    client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "quantity": 3})  # changed the quote: page 1 is closed
    assert expired == ["cs_1"]
    v = client.post(f"/api/public/quote/{q['ref']}/checkout", json=order).json()["view"]
    cents = round(v["order"]["amount"] * 100)
    from app.db import SessionLocal
    from app.models_portal import PortalRequest

    with SessionLocal() as db:
        req = db.query(PortalRequest).filter_by(ref=q["ref"]).one()
        # paid on the old page anyway: kept for review, not marked paid
        assert not checkout.mark_paid(db, req, {"id": "cs_1", "payment_status": "paid", "amount_total": 1, "amount_subtotal": 1, "currency": "usd"})
        assert req.order["unmatched_payments"][0]["id"] == "cs_1" and alerts
        # wrong amount: held for review
        assert not checkout.mark_paid(db, req, {"id": "cs_2", "payment_status": "paid", "amount_subtotal": cents - 100, "amount_total": cents - 100, "currency": "usd"})
        assert req.order["status"] == "payment_review" and req.status != "ordered"
        req.order = {**req.order, "status": "awaiting_payment"}
        db.commit()
        # right amount (tax added on top is fine: the subtotal is compared)
        assert checkout.mark_paid(db, req, {"id": "cs_2", "payment_status": "paid", "amount_subtotal": cents, "amount_total": cents + 800, "currency": "usd"})
        assert req.order["status"] == "paid" and req.status == "ordered"
