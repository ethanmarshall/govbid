"""Invoice orders: due on receipt for everyone, net terms for accounts you approve, paid online or marked paid."""
import io
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import checkout, customers, portal
from app.main import app

FIX = Path(__file__).parent / "fixtures"
SHIP = {"name": "Dana Lee", "company": "Acme", "line1": "1 Main St", "city": "Ballston Spa", "state": "NY", "zip": "12020"}


@pytest.fixture
def client(monkeypatch):
    for lim in (portal.QUOTE_LIMIT, portal.REPRICE_LIMIT, portal.SUBMIT_LIMIT, portal.SIGN_LIMIT):
        lim.clear()
    customers._fails.clear()
    monkeypatch.setattr(portal, "notify", lambda req, s: None)
    monkeypatch.setattr(portal, "confirm_to_customer", lambda req, s, url: None)
    with TestClient(app) as c:
        c.put("/api/portal/settings", json={"enabled": True, "pay_instructions": "ACH to First Bank, routing 000000000. Checks to the address above.",
                                            "remit_to": "Valley Power Systems LLC\n1 Shop Rd\nTown, NY 12000"})
        yield c
        c.put("/api/portal/settings", json={"enabled": False})


def _quote(c, qty=1):
    return c.post("/api/public/quote", data={"quantity": str(qty)},
                  files=[("files", ("block.step", (FIX / "cad" / "machined_block.step").read_bytes()))]).json()


class _R:  # the checkout reply, after signing the agreement for invoice orders
    def __init__(self, view):
        self.status_code, self._v = 200, view

    def json(self):
        return {"view": self._v}


def _order(c, q, sign=True, **kw):
    body = {"token": q["token"], "method": "invoice", "contact": {"name": "Dana", "email": "dana@example.com", "company": "Acme"},
            "ship_to": SHIP, "accept_terms": True, **kw}
    r = c.post(f"/api/public/quote/{q['ref']}/checkout", json=body)
    assert r.status_code == 200, r.text
    v = r.json()["view"]
    if not sign or v["order"]["status"] != "awaiting_signature":
        return r
    s = c.post(f"/api/public/quote/{q['ref']}/agreement/sign", json={"token": q["token"], "sha256": v["order"]["agreement"]["sha256"],
                                                                   "name": "Dana Lee", "title": "Purchasing", "authority": True, "consent": True, "agree": True})
    assert s.status_code == 200, s.text
    return _R(s.json())


def _text(pdf: bytes) -> str:
    from pypdf import PdfReader

    return " ".join(" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(pdf)).pages)


def _finance(c, ref):
    return next(i for i in c.get("/api/finance/invoices").json() if i["delivery_order"] == ref)


def test_guest_invoice_is_due_on_receipt(client):
    q = _quote(client, 3)
    r = _order(client, q)  # no PO number: fine
    assert r.status_code == 200, r.text
    o = r.json()["view"]["order"]
    assert o["status"] == "invoice_due" and o["terms_days"] == 0 and o["due_date"] == date.today().isoformat() and o["invoice_number"]
    inv = _finance(client, q["ref"])
    assert inv["number"] == o["invoice_number"] and inv["status"] == "submitted" and inv["total"] == pytest.approx(o["amount"])
    pdf = client.get(f"/api/public/quote/{q['ref']}/invoice.pdf", params={"token": q["token"]})
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    t = _text(pdf.content)
    assert "INVOICE" in t and o["invoice_number"] in t and "due on receipt" in t and "ACH to First Bank" in t and "1 Shop Rd" in t
    assert client.get(f"/api/public/quote/{q['ref']}/invoice.pdf", params={"token": "wrong"}).status_code in (400, 404)
    # you mark it paid: the order and the invoice in Invoices and finance are both paid
    rid = next(x["id"] for x in client.get("/api/portal/requests").json() if x["ref"] == q["ref"])
    client.put(f"/api/portal/requests/{rid}/order", json={"status": "paid"})
    assert _finance(client, q["ref"])["status"] == "paid"
    assert "PAID" in _text(client.get(f"/api/public/quote/{q['ref']}/invoice.pdf", params={"token": q["token"]}).content)


def test_approved_account_gets_net_terms_and_requests_show_first(client):
    em = f"buyer{time.time_ns()}@example.com"
    client.post("/api/public/account/register", json={"email": em, "password": "a-long-password", "name": "Dana", "company": "Acme"})
    r = client.post("/api/public/account/terms-request", json={"note": "10 years in business, AP pays net 30"}).json()
    assert r["customer"]["terms_requested"] and r["customer"]["net_terms_days"] == 0
    listed = client.get("/api/portal/customers").json()
    assert listed[0]["email"] == em and listed[0]["terms_request_note"].startswith("10 years")
    assert client.put(f"/api/portal/customers/{listed[0]['id']}", json={"net_terms_days": 7}).status_code == 400
    client.put(f"/api/portal/customers/{listed[0]['id']}", json={"net_terms_days": 30})
    assert client.get("/api/public/account").json()["customer"]["net_terms_days"] == 30
    q = _quote(client)
    o = _order(client, q, po_number="4500012345").json()["view"]["order"]
    assert o["status"] == "invoiced" and o["terms_days"] == 30 and o["due_date"] == (date.today() + timedelta(days=30)).isoformat()
    t = _text(client.get(f"/api/public/quote/{q['ref']}/invoice.pdf", params={"token": q["token"]}).content)
    assert "Net 30" in t and "4500012345" in t
    row = next(x for x in client.get("/api/portal/customers").json() if x["email"] == em)
    assert row["orders"] == 1 and row["owed"] == pytest.approx(o["amount"])


def test_cancelling_an_unpaid_invoice_order_removes_the_invoice(client):
    q = _quote(client)
    num = _order(client, q).json()["view"]["order"]["invoice_number"]
    rid = next(x["id"] for x in client.get("/api/portal/requests").json() if x["ref"] == q["ref"])
    client.put(f"/api/portal/requests/{rid}/order", json={"status": "cancelled"})
    assert num not in [i["number"] for i in client.get("/api/finance/invoices").json()]


def test_pay_invoice_online_and_card_receipt(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    state = {"n": 0, "paid": set(), "cents": {}}

    def handler(req: httpx.Request):
        p = req.url.path
        if p == "/v1/checkout/sessions":
            state["n"] += 1
            sid = f"cs_{state['n']}"
            form = dict(httpx.QueryParams(req.content.decode()))
            state["cents"][sid] = sum(int(form[k]) * int(form[k.replace("[price_data][unit_amount]", "[quantity]")])
                                      for k in form if k.endswith("[price_data][unit_amount]"))
            return httpx.Response(200, json={"id": sid, "url": f"https://checkout.stripe.com/c/pay/{sid}"})
        if p.endswith("/expire"):
            return httpx.Response(200, json={})
        sid = p.rsplit("/", 1)[-1]
        paid = sid in state["paid"]
        return httpx.Response(200, json={"id": sid, "payment_status": "paid" if paid else "unpaid", "currency": "usd",
                                         "amount_total": state["cents"].get(sid, 0), "amount_subtotal": state["cents"].get(sid, 0)})

    monkeypatch.setattr(checkout, "_transport", httpx.MockTransport(handler))
    q = _quote(client, 2)
    v = _order(client, q).json()["view"]
    assert v["order"]["pay_online"]
    t = _text(client.get(f"/api/public/quote/{q['ref']}/invoice.pdf", params={"token": q["token"]}).content)
    assert f"/quote/status/{q['ref']}" in t
    r = client.post(f"/api/public/quote/{q['ref']}/pay", json={"token": q["token"]}).json()
    assert r["redirect"].endswith("cs_1")
    state["paid"].add("cs_1")
    v = client.get(f"/api/public/quote/{q['ref']}", params={"token": q["token"]}).json()
    assert v["order"]["status"] == "paid" and _finance(client, q["ref"])["status"] == "paid"
    # a card order gets a paid invoice (receipt) once Stripe confirms it
    q2 = _quote(client)
    _order(client, q2, method="card")
    state["paid"].add("cs_2")
    v2 = client.get(f"/api/public/quote/{q2['ref']}", params={"token": q2["token"]}).json()
    assert v2["order"]["status"] == "paid" and v2["order"]["invoice_number"]
    t = _text(client.get(f"/api/public/quote/{q2['ref']}/invoice.pdf", params={"token": q2["token"]}).content)
    assert "RECEIPT" in t and "PAID" in t and _finance(client, q2["ref"])["status"] == "paid"
