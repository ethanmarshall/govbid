"""Checkout: customers order instant quotes (every line priced, nothing needing review) without waiting for us.

Two ways to pay:
  - card, through Stripe Checkout (a page hosted by Stripe; card numbers never touch this server). Needs
    STRIPE_SECRET_KEY, and STRIPE_WEBHOOK_SECRET for the webhook (optional: payment is also checked when the
    customer returns). Turned on when the key is set.
  - purchase order: the order is placed and you invoice against the PO (government and company buyers).

At checkout the quote is priced again, so the order is always at today's price; if that changes the total, the
customer is shown the new total before anything is placed. The order is a snapshot of the lines and prices.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime

from sqlalchemy.orm import Session

STRIPE_API = "https://api.stripe.com/v1"
ORDER_LABEL = {"awaiting_payment": "Waiting for card payment", "paid": "Paid by card", "po_received": "Purchase order received",
               "invoiced": "Invoiced", "cancelled": "Cancelled"}


class CheckoutError(ValueError):
    pass


def stripe_enabled() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def methods() -> list[str]:
    return (["card"] if stripe_enabled() else []) + ["po"]


def eligible(req) -> tuple[bool, str]:
    r = req.public_result or {}
    if req.kind == "concept":
        return False, "Project ideas are quoted by an engineer."
    if req.export_controlled:
        return False, "Export-controlled projects are handled directly with us."
    if req.status in ("declined", "closed", "ordered", "in_production", "shipped"):
        return False, "This request is closed or already ordered."
    if (req.order or {}).get("status") in ("paid", "po_received", "invoiced"):
        return False, "This quote has already been ordered."
    if r.get("kind") != "instant":
        return False, "Some parts need an engineer's review first. Send it for review and we will confirm the price; then you can order here."
    if not r.get("items"):
        return False, "There is nothing to order."
    return True, ""


def _snapshot(req) -> list[dict]:
    return [{"key": it.get("key"), "name": it["name"], "group": it.get("group") or "", "qty": int(it.get("qty") or 1),
             "unit_price": round(float(it["unit_price"]), 2), "total": round(round(float(it["unit_price"]), 2) * int(it.get("qty") or 1), 2),
             "desc": it.get("desc") or "", "material": it.get("material") or "", "finish": it.get("finish") or "",
             "process": it.get("process_label") or ""} for it in (req.public_result or {}).get("items") or []]


def place(db: Session, req, data: dict, customer=None, base_url: str = "") -> dict:
    """Validate, price again, and place the order. Returns {"order": ..., "redirect": url or None}."""
    from . import customers, portal

    ok, why = eligible(req)
    if not ok:
        raise CheckoutError(why)
    if req.status == "draft":  # still the customer's to change: price it again at today's rates
        req.order = {}
        portal.price_request(db, req)
        db.commit()
        ok, why = eligible(req)
        if not ok:
            raise CheckoutError(why)
    lines = _snapshot(req)
    total = round(sum(l["total"] for l in lines), 2)
    expected = data.get("expected_total")
    if expected is not None and abs(float(expected) - total) > 0.01:
        raise CheckoutError(f"PRICE_CHANGED:{total}")
    contact = data.get("contact") or {}
    name = str(contact.get("name") or (customer.name if customer else "")).strip()[:120]
    email = str(contact.get("email") or (customer.email if customer else "")).strip()[:160]
    if not name:
        raise CheckoutError("Enter your name.")
    if not portal.EMAIL_RX.match(email):
        raise CheckoutError("Enter a valid email address.")
    ship = customers.clean_address(data.get("ship_to") or {})
    if not customers.address_ok(ship):
        raise CheckoutError("Enter the shipping address: name, street, city, state and ZIP code.")
    if not data.get("accept_terms"):
        raise CheckoutError("Please accept the terms.")
    method = data.get("method") or "po"
    if method not in methods():
        raise CheckoutError("Choose how to pay.")
    po = str(data.get("po_number") or "").strip()[:60]
    if method == "po" and not po:
        raise CheckoutError("Enter your purchase order number.")
    req.contact_name, req.email = name, email
    req.company = str(contact.get("company") or (customer.company if customer else "")).strip()[:160]
    req.phone = customers._phone(contact.get("phone") or (customer.phone if customer else ""))
    nb = str(data.get("needed_by") or "")[:10]
    if nb:
        req.needed_by = nb
    if customer:
        req.customer_id = customer.id
        if data.get("save_address") and not any(a.get("line1") == ship["line1"] and a.get("zip") == ship["zip"] for a in customer.addresses or []):
            customer.addresses = (customer.addresses or []) + [ship]
    order = {"number": req.ref, "method": method, "placed_at": datetime.utcnow().isoformat(timespec="seconds"), "amount": total,
             "lines": lines, "ship_to": ship, "po_number": po, "billing_email": str(data.get("billing_email") or "").strip()[:160],
             "notes": str(data.get("notes") or "").strip()[:2000], "lead_days": (req.public_result or {}).get("lead_days")}
    redirect = None
    if method == "po":
        order["status"] = "po_received"
        req.status = "ordered"
        req.submitted_at = req.submitted_at or datetime.utcnow()
    else:
        sess = create_stripe_session(req, lines, email, base_url)
        order.update(status="awaiting_payment", stripe_session_id=sess["id"])
        redirect = sess["url"]
    req.order = order
    db.commit()
    return {"order": order, "redirect": redirect}


# ------------------------------------------------------------------ Stripe
def _stripe(method: str, path: str, data: dict | None = None, transport=None) -> dict:
    import httpx

    key = os.getenv("STRIPE_SECRET_KEY", "")
    kw = {"transport": transport} if transport else {}
    with httpx.Client(timeout=20, **kw) as http:
        r = http.request(method, STRIPE_API + path, data=data, auth=(key, ""))
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        raise CheckoutError(f"Card payment is not available right now ({msg}). Choose purchase order, or try again later.")
    return r.json()


_transport = None  # tests set an httpx.MockTransport here


def create_stripe_session(req, lines: list[dict], email: str, base_url: str) -> dict:
    from urllib.parse import quote

    back = f"{base_url}/quote/status/{req.ref}?t={quote(req.token)}"
    data = {"mode": "payment", "success_url": back + "&paid={CHECKOUT_SESSION_ID}", "cancel_url": back + "&cancelled=1",
            "customer_email": email, "client_reference_id": req.ref, "metadata[ref]": req.ref,
            "payment_intent_data[metadata][ref]": req.ref, "billing_address_collection": "required"}
    if os.getenv("STRIPE_AUTOMATIC_TAX") in ("1", "true"):
        data["automatic_tax[enabled]"] = "true"
    for i, l in enumerate(lines):
        data[f"line_items[{i}][quantity]"] = str(l["qty"])
        data[f"line_items[{i}][price_data][currency]"] = "usd"
        data[f"line_items[{i}][price_data][unit_amount]"] = str(int(round(l["unit_price"] * 100)))
        data[f"line_items[{i}][price_data][product_data][name]"] = (l["name"] + (f" ({l['group']})" if l["group"] else ""))[:250]
        if l["desc"]:
            data[f"line_items[{i}][price_data][product_data][description]"] = l["desc"][:500]
    return _stripe("POST", "/checkout/sessions", data, _transport)


def confirm_if_paid(db: Session, req) -> bool:
    """Ask Stripe whether a waiting card order was paid (when the customer comes back). True when it is now paid."""
    o = dict(req.order or {})
    if o.get("status") != "awaiting_payment" or not o.get("stripe_session_id") or not stripe_enabled():
        return False
    try:
        sess = _stripe("GET", f"/checkout/sessions/{o['stripe_session_id']}", None, _transport)
    except CheckoutError:
        return False
    return mark_paid(db, req, sess)


def mark_paid(db: Session, req, sess: dict) -> bool:
    o = dict(req.order or {})
    if sess.get("payment_status") != "paid" or sess.get("id") != o.get("stripe_session_id"):
        return False
    if o.get("status") == "paid":
        return False
    paid = (sess.get("amount_total") or 0) / 100
    o.update(status="paid", paid_at=datetime.utcnow().isoformat(timespec="seconds"), paid_amount=paid,
             payment_intent=sess.get("payment_intent") or "")
    req.order = o
    req.status = "ordered"
    req.submitted_at = req.submitted_at or datetime.utcnow()
    db.commit()
    return True


def verify_webhook(payload: bytes, sig_header: str, secret: str, tolerance: int = 300) -> dict:
    """Stripe's signature: t=timestamp,v1=HMAC-SHA256(secret, "t.payload")."""
    parts = dict(p.split("=", 1) for p in (sig_header or "").split(",") if "=" in p)
    ts = parts.get("t", "")
    sigs = [v for k, v in (p.split("=", 1) for p in (sig_header or "").split(",") if "=" in p) if k == "v1"]
    if not ts or not sigs:
        raise CheckoutError("Bad signature")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise CheckoutError("Bad signature")
    if abs(time.time() - int(ts)) > tolerance:
        raise CheckoutError("Old event")
    return json.loads(payload)


def public_order(req) -> dict | None:
    o = req.order or {}
    if not o:
        return None
    return {k: o.get(k) for k in ("number", "method", "status", "placed_at", "amount", "lines", "ship_to", "po_number", "paid_at", "lead_days")} | {
        "status_label": ORDER_LABEL.get(o.get("status"), o.get("status"))}
