"""Invoice orders wait for a signed order agreement before the invoice is made and work starts."""
import io
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import agreement, customers, portal
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
        c.put("/api/portal/settings", json={"enabled": True, "agreement_template": ""})
        yield c
        c.put("/api/portal/settings", json={"enabled": False, "agreement_template": ""})


def _placed(c, qty=4):
    q = c.post("/api/public/quote", data={"quantity": str(qty)}, files=[("files", ("b.step", (FIX / "cad" / "machined_block.step").read_bytes()))]).json()
    v = c.post(f"/api/public/quote/{q['ref']}/checkout", json={"token": q["token"], "method": "invoice", "po_number": "PO-77", "ship_to": SHIP,
                                                              "accept_terms": True, "contact": {"name": "Dana Lee", "email": "dana@example.com", "company": "Acme"}}).json()["view"]
    return q, v


def _sign(c, q, sha, **kw):
    body = {"token": q["token"], "sha256": sha, "name": "Dana Lee", "title": "Purchasing manager", "authority": True, "consent": True, "agree": True, **kw}
    return c.post(f"/api/public/quote/{q['ref']}/agreement/sign", json=body)


def _text(pdf: bytes) -> str:
    from pypdf import PdfReader

    return " ".join(" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(pdf)).pages)


def test_nothing_starts_until_signed(client):
    q, v = _placed(client)
    o = v["order"]
    assert o["status"] == "awaiting_signature" and v["status"] == "submitted" and not o.get("invoice_number") and not o["pay_online"]
    ag = o["agreement"]
    assert ag["status"] == "pending" and "Acme" in ag["text"] and "PO-77" in ag["text"] and "material bought or committed" in ag["text"]
    assert f"Quantity 4 at" in ag["text"] and "Due on receipt" in ag["text"]
    assert client.get(f"/api/public/quote/{q['ref']}/invoice.pdf", params={"token": q["token"]}).status_code == 404
    assert client.post(f"/api/public/quote/{q['ref']}/options", json={"token": q["token"], "quantity": 9}).status_code == 400  # locked
    # what a signature needs
    assert "full name" in _sign(client, q, ag["sha256"], name="Dana").json()["detail"]
    assert "three boxes" in _sign(client, q, ag["sha256"], consent=False).json()["detail"]
    assert "changed" in _sign(client, q, "0" * 64).json()["detail"]
    r = _sign(client, q, ag["sha256"])
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["status"] == "invoice_due" and o["invoice_number"] and o["agreement"]["status"] == "signed"
    assert o["agreement"]["signed"]["name"] == "Dana Lee" and o["agreement"]["text"] is None
    assert _sign(client, q, ag["sha256"]).status_code == 400  # once
    t = _text(client.get(f"/api/public/quote/{q['ref']}/agreement.pdf", params={"token": q["token"]}).content)
    assert "Signed electronically by Dana Lee (Purchasing manager)" in t and ag["sha256"] in t and "IP address" in t
    rid = next(x["id"] for x in client.get("/api/portal/requests").json() if x["ref"] == q["ref"])
    internal = client.get(f"/api/portal/requests/{rid}").json()
    assert internal["order"]["agreement"]["signed"]["ip"] and internal["order"]["agreement"]["signed"]["email_verified"] is False


def test_staff_can_release_without_online_signature(client):
    q, v = _placed(client)
    rid = next(x["id"] for x in client.get("/api/portal/requests").json() if x["ref"] == q["ref"])
    assert client.post(f"/api/portal/requests/{rid}/agreement/waive", json={"note": ""}).status_code == 400
    r = client.post(f"/api/portal/requests/{rid}/agreement/waive", json={"note": "Government order, signed contract on file"}).json()
    assert r["order"]["status"] == "invoice_due" and r["order"]["agreement"]["status"] == "waived" and r["status"] == "ordered"
    assert "Government order" in _text(client.get(f"/api/portal/requests/{rid}/agreement.pdf").content)


def test_email_code_when_email_is_set_up(client, monkeypatch):
    sent = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr("app.cli.send_email", lambda subject, body, html_body=None, to=None, allow_customer=False: sent.append((to, body)))
    q, v = _placed(client)
    sha = v["order"]["agreement"]["sha256"]
    assert "code" in _sign(client, q, sha).json()["detail"]
    r = client.post(f"/api/public/quote/{q['ref']}/agreement/code", json={"token": q["token"]}).json()
    assert r["sent_to"].startswith("d***@") and sent[-1][0] == "dana@example.com"
    code = sent[-1][1].split(" is ")[1][:6]
    assert _sign(client, q, sha, code="000000" if code != "000000" else "111111").status_code == 400
    r = _sign(client, q, sha, code=code)
    assert r.status_code == 200 and r.json()["order"]["status"] == "invoice_due"
    rid = next(x["id"] for x in client.get("/api/portal/requests").json() if x["ref"] == q["ref"])
    assert client.get(f"/api/portal/requests/{rid}").json()["order"]["agreement"]["signed"]["email_verified"] is True


def test_expired_agreement_and_custom_template(client):
    assert client.put("/api/portal/settings", json={"agreement_template": "Pay {total} or else {"}).status_code == 400
    client.put("/api/portal/settings", json={"agreement_template": "Custom terms for {buyer}: {payment_terms}, total {total}. {unknown}"})
    q, v = _placed(client)
    text = v["order"]["agreement"]["text"]
    assert "Custom terms for Acme: Due on receipt" in text and "{unknown}" in text and "Schedule A" in text
    from app.db import SessionLocal
    from app.models_portal import PortalRequest

    with SessionLocal() as db:
        req = db.query(PortalRequest).filter_by(ref=q["ref"]).one()
        o = dict(req.order)
        o["agreement"] = {**o["agreement"], "sent_at": (datetime.utcnow() - timedelta(days=31)).isoformat(timespec="seconds")}
        req.order = o
        db.commit()
    assert client.get(f"/api/public/quote/{q['ref']}", params={"token": q["token"]}).json()["order"]["agreement"]["expired"]
    assert "expired" in _sign(client, q, v["order"]["agreement"]["sha256"]).json()["detail"]
