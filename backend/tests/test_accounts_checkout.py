"""Customer accounts and checkout (card through a mocked Stripe, and purchase orders)."""
import hashlib
import hmac
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import checkout, customers, portal
from app.main import app

FIX = Path(__file__).parent / "fixtures"
SHIP = {"name": "Dana Lee", "company": "Navy school", "line1": "1 Main St", "city": "Ballston Spa", "state": "NY", "zip": "12020"}


@pytest.fixture
def client():
    for lim in (portal.QUOTE_LIMIT, portal.REPRICE_LIMIT, portal.SUBMIT_LIMIT):
        lim.clear()
    customers._fails.clear()
    with TestClient(app) as c:
        c.put("/api/portal/settings", json={"enabled": True})
        yield c
        c.put("/api/portal/settings", json={"enabled": False})


def _quote(c, path, **form):
    return c.post("/api/public/quote", data={"quantity": "1", **{k: str(v) for k, v in form.items()}},
                  files=[("files", (path.name, path.read_bytes(), "application/octet-stream"))]).json()


def _email():
    return f"buyer{time.time_ns()}@example.com"


def test_register_login_profile_and_password_change(client):
    em = _email()
    r = client.post("/api/public/account/register", json={"email": em, "password": "short", "name": "Pat"})
    assert r.status_code == 400 and "10 characters" in r.json()["detail"]
    r = client.post("/api/public/account/register", json={"email": em.upper(), "password": "a-long-password", "name": "Pat", "company": "Acme"})
    assert r.status_code == 200 and r.json()["customer"]["email"] == em
    assert client.get("/api/public/account").json()["customer"]["name"] == "Pat"
    assert client.post("/api/public/account/register", json={"email": em, "password": "a-long-password", "name": "Pat"}).status_code == 400
    r = client.put("/api/public/account", json={"addresses": [SHIP], "phone": "555-0100"}).json()
    assert r["customer"]["addresses"][0]["city"] == "Ballston Spa"
    assert client.put("/api/public/account", json={"addresses": [{"name": "x"}]}).status_code == 400
    old_cookie = client.cookies.get(customers.COOKIE)
    assert client.put("/api/public/account", json={"password": "wrong", "new_password": "another-long-one"}).status_code == 400
    assert client.put("/api/public/account", json={"password": "a-long-password", "new_password": "another-long-one"}).status_code == 200
    with TestClient(app) as other:  # the old session (another device) is signed out by the password change
        other.cookies.set(customers.COOKIE, old_cookie)
        assert other.get("/api/public/account").json()["customer"] is None
    client.post("/api/public/account/logout")
    assert client.get("/api/public/account").json()["customer"] is None
    assert client.post("/api/public/account/login", json={"email": em, "password": "a-long-password"}).status_code == 400
    assert client.post("/api/public/account/login", json={"email": em, "password": "another-long-one"}).status_code == 200
    assert client.get("/api/portal/requests").status_code == 200  # (staff routes are a different login; open in tests)


def test_password_reset(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.cli.send_email", lambda subject, body, html_body=None, to=None, allow_customer=False: sent.append((to, body)) or to)
    em = _email()
    client.post("/api/public/account/register", json={"email": em, "password": "a-long-password", "name": "Pat"})
    client.post("/api/public/account/logout")
    assert client.post("/api/public/account/forgot", json={"email": "nobody@example.com"}).status_code == 200 and not sent
    assert client.post("/api/public/account/forgot", json={"email": em}).status_code == 200
    to, body = sent[0]
    assert to == em and "reset=" in body
    tok = body.split("reset=")[1].split("&")[0]
    assert client.post("/api/public/account/reset", json={"email": em, "token": "bad", "password": "new-long-password"}).status_code == 400
    r = client.post("/api/public/account/reset", json={"email": em, "token": tok, "password": "new-long-password"})
    assert r.status_code == 200 and client.get("/api/public/account").json()["customer"]["email"] == em
    assert client.post("/api/public/account/reset", json={"email": em, "token": tok, "password": "again-long-password"}).status_code == 400  # used once


def test_quotes_belong_to_the_account_and_can_be_claimed(client):
    q0 = _quote(client, FIX / "cad" / "machined_block.step")  # before signing in
    client.post("/api/public/account/register", json={"email": _email(), "password": "a-long-password", "name": "Pat"})
    q1 = _quote(client, FIX / "cad" / "turned_shaft.step")
    refs = [r["ref"] for r in client.get("/api/public/account/requests").json()]
    assert q1["ref"] in refs and q0["ref"] not in refs
    assert client.post("/api/public/account/claim", json={"items": [{"ref": q0["ref"], "token": "wrong"}]}).json()["added"] == 0
    assert client.post("/api/public/account/claim", json={"items": [{"ref": q0["ref"], "token": q0["token"]}]}).json()["added"] == 1
    assert q0["ref"] in [r["ref"] for r in client.get("/api/public/account/requests").json()]
    client.post("/api/public/account/logout")
    assert client.get("/api/public/account/requests").status_code == 401


def test_checkout_by_invoice(client, monkeypatch):
    notices = []
    monkeypatch.setattr(portal, "notify", lambda req, s: notices.append(req.ref))
    monkeypatch.setattr(portal, "confirm_to_customer", lambda req, s, url: notices.append("customer"))
    q = _quote(client, FIX / "cad" / "machined_block.step", quantity=5)
    assert q["checkout"]["eligible"] and q["checkout"]["methods"] == ["invoice"]  # no Stripe key here
    total = q["result"]["total"]
    base = {"token": q["token"], "method": "po", "contact": {"name": "Dana", "email": "dana@example.com"}, "ship_to": SHIP, "accept_terms": True}
    assert client.post(f"/api/public/quote/{q['ref']}/checkout", json={**base, "po_number": "PO-1", "ship_to": {"name": "x"}}).status_code == 400
    bad = client.post(f"/api/public/quote/{q['ref']}/checkout", json={**base, "po_number": "PO-1", "expected_total": total + 50})
    assert bad.status_code == 409 and bad.json()["detail"]["total"] == pytest.approx(total)
    r = client.post(f"/api/public/quote/{q['ref']}/checkout", json={**base, "po_number": "PO-1", "expected_total": total})
    assert r.status_code == 200, r.text
    v = r.json()["view"]
    assert v["status"] == "ordered" and v["order"]["status"] == "invoice_due" and v["order"]["amount"] == pytest.approx(total)
    assert v["order"]["invoice_number"] and v["order"]["po_number"] == "PO-1"
    assert v["order"]["lines"][0]["qty"] == 5 and not v["checkout"]["eligible"]
    assert q["ref"] in notices and "customer" in notices
    assert client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "quantity": 9}).status_code == 400  # locked
    rid = next(x["id"] for x in client.get("/api/portal/requests").json() if x["ref"] == q["ref"])
    assert client.put(f"/api/portal/requests/{rid}/order", json={"status": "paid"}).json()["order"]["status"] == "paid"


def test_estimates_cannot_check_out(client):
    q = _quote(client, FIX / "cad" / "weldment.step")
    assert not q["checkout"]["eligible"] and "review" in q["checkout"]["why"]
    r = client.post(f"/api/public/quote/{q['ref']}/checkout", json={"token": q["token"], "method": "po", "po_number": "1", "ship_to": SHIP,
                                                                 "contact": {"name": "D", "email": "d@example.com"}, "accept_terms": True})
    assert r.status_code == 400


def test_card_checkout_with_stripe(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(portal, "notify", lambda req, s: None)
    monkeypatch.setattr(portal, "confirm_to_customer", lambda req, s, url: None)
    seen = {}

    def handler(req: httpx.Request):
        if req.method == "POST" and req.url.path == "/v1/checkout/sessions":
            form = dict(httpx.QueryParams(req.content.decode()))
            seen["form"] = form
            return httpx.Response(200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"})
        if req.url.path == "/v1/checkout/sessions/cs_test_1":
            return httpx.Response(200, json={"id": "cs_test_1", "payment_status": seen.get("paid", "unpaid"), "amount_total": seen.get("cents", 0)})
        return httpx.Response(404, json={"error": {"message": "nope"}})

    monkeypatch.setattr(checkout, "_transport", httpx.MockTransport(handler))
    q = _quote(client, FIX / "cad" / "machined_block.step", quantity=2)
    assert q["checkout"]["methods"] == ["card", "invoice"]
    r = client.post(f"/api/public/quote/{q['ref']}/checkout", json={"token": q["token"], "method": "card", "ship_to": SHIP, "accept_terms": True,
                                                                 "contact": {"name": "Dana", "email": "dana@example.com"}}).json()
    assert r["redirect"].startswith("https://checkout.stripe.com") and r["view"]["order"]["status"] == "awaiting_payment"
    f = seen["form"]
    assert f["line_items[0][quantity]"] == "2" and int(f["line_items[0][price_data][unit_amount]"]) == round(q["result"]["items"][0]["unit_price"] * 100)
    assert f["metadata[ref]"] == q["ref"] and "{CHECKOUT_SESSION_ID}" in f["success_url"]
    # back from Stripe before paying: still waiting; after paying: ordered
    assert client.get(f"/api/public/quote/{q['ref']}?token={q['token']}").json()["order"]["status"] == "awaiting_payment"
    seen.update(paid="paid", cents=int(round(q["result"]["total"] * 100)))
    v = client.get(f"/api/public/quote/{q['ref']}?token={q['token']}").json()
    assert v["order"]["status"] == "paid" and v["status"] == "ordered"
    # the webhook: signed events only
    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_test_1", "payment_status": "paid", "metadata": {"ref": q["ref"]}}}}).encode()
    assert client.post("/api/public/stripe/webhook", content=payload, headers={"stripe-signature": "t=1,v1=bad"}).status_code == 400
    ts = str(int(time.time()))
    sig = hmac.new(b"whsec_test", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    assert client.post("/api/public/stripe/webhook", content=payload, headers={"stripe-signature": f"t={ts},v1={sig}"}).json() == {"received": True}
