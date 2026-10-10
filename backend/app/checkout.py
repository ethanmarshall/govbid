"""Checkout: customers order instant quotes (every line priced, nothing needing review) without waiting for us.

Two ways to pay:
  - card, through Stripe Checkout (a page hosted by Stripe; card numbers never touch this server). Needs
    STRIPE_SECRET_KEY, and STRIPE_WEBHOOK_SECRET for the webhook (optional: payment is also checked when the
    customer returns). Turned on when the key is set.
  - invoice (invoicing.py): an invoice is made at once, with the customer's PO number if they have one. Accounts you
    approved for terms get net terms and the work starts; everyone else pays the invoice before we start (bank
    transfer, check, or online through Stripe).

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
ORDER_LABEL = {"awaiting_payment": "Waiting for card payment", "paid": "Paid", "po_received": "Purchase order received",
               "invoiced": "Invoiced", "invoice_due": "Invoice sent, we start when it is paid", "cancelled": "Cancelled",
               "payment_review": "Payment received, we are checking it"}
PLACED = ("paid", "po_received", "invoiced", "invoice_due", "payment_review")


class CheckoutError(ValueError):
    pass


def stripe_enabled() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def methods() -> list[str]:
    return (["card"] if stripe_enabled() else []) + ["invoice"]


def eligible(req) -> tuple[bool, str]:
    r = req.public_result or {}
    if req.kind == "concept":
        return False, "Project ideas are quoted by an engineer."
    if req.export_controlled:
        return False, "Export-controlled projects are handled directly with us."
    if req.status in ("declined", "closed", "ordered", "in_production", "shipped"):
        return False, "This request is closed or already ordered."
    if (req.order or {}).get("status") in PLACED:
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
    from . import customers, invoicing, portal

    ok, why = eligible(req)
    if not ok:
        raise CheckoutError(why)
    if req.status == "draft":  # still the customer's to change: price it again at today's rates
        retire_session(req)
        retired = (req.order or {}).get("retired_sessions") or []
        req.order = {"retired_sessions": retired} if retired else {}
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
    method = data.get("method") or "invoice"
    if method == "po":  # the earlier name for invoice
        method = "invoice"
    if method not in methods():
        raise CheckoutError("Choose how to pay.")
    po = str(data.get("po_number") or "").strip()[:60]
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
    order = {"retired_sessions": (req.order or {}).get("retired_sessions", []), "number": req.ref, "method": method, "placed_at": datetime.utcnow().isoformat(timespec="seconds"), "amount": total,
             "lines": lines, "ship_to": ship, "po_number": po, "billing_email": str(data.get("billing_email") or "").strip()[:160],
             "notes": str(data.get("notes") or "").strip()[:2000], "lead_days": (req.public_result or {}).get("lead_days")}
    redirect = None
    if method == "invoice":
        terms = invoicing.terms_for(customer)
        order["status"] = "invoiced" if terms else "invoice_due"
        req.status = "ordered"
        req.submitted_at = req.submitted_at or datetime.utcnow()
        invoicing.create(db, req, order, terms)
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


def pay_invoice(db: Session, req, base_url: str) -> str:
    """Pay an open invoice online (bank transfer or card, whichever you turned on in Stripe). Returns Stripe's page."""
    o = dict(req.order or {})
    if o.get("status") not in ("invoiced", "invoice_due") or not stripe_enabled():
        raise CheckoutError("This invoice cannot be paid online.")
    if o.get("stripe_session_id"):
        retired = list(o.get("retired_sessions") or []) + [o["stripe_session_id"]]
        try:
            _stripe("POST", f"/checkout/sessions/{o['stripe_session_id']}/expire", {}, _transport)
        except Exception:  # noqa: BLE001
            pass
        o["retired_sessions"] = retired[-20:]
    sess = create_stripe_session(req, o.get("lines") or [], req.email, base_url)
    o["stripe_session_id"] = sess["id"]
    req.order = o
    db.commit()
    return sess["url"]


def confirm_if_paid(db: Session, req) -> bool:
    """Ask Stripe whether a waiting card order was paid (when the customer comes back). True when it is now paid."""
    o = dict(req.order or {})
    if o.get("status") not in ("awaiting_payment", "invoiced", "invoice_due") or not o.get("stripe_session_id") or not stripe_enabled():
        return False
    try:
        sess = _stripe("GET", f"/checkout/sessions/{o['stripe_session_id']}", None, _transport)
    except CheckoutError:
        return False
    return mark_paid(db, req, sess)


def retire_session(req) -> None:
    """The customer changed the quote or started checkout again: close the old Stripe page so it cannot be paid,
    and remember its id so a payment that slipped through anyway is still matched to this request."""
    o = req.order or {}
    sid = o.get("stripe_session_id")
    if not sid or o.get("status") != "awaiting_payment":
        return
    retired = list(o.get("retired_sessions") or []) + [sid]
    req.order = {"retired_sessions": retired[-20:]}
    try:
        _stripe("POST", f"/checkout/sessions/{sid}/expire", {}, _transport)
    except Exception:  # noqa: BLE001  (already expired or paid; a payment is still caught by the webhook)
        pass


def mark_paid(db: Session, req, sess: dict) -> bool:
    """Record a completed Stripe payment. The amount and currency must match the order exactly; anything that does
    not match (a different amount, an old checkout page) is kept for you to check rather than marked paid."""
    o = dict(req.order or {})
    if sess.get("payment_status") != "paid":
        return False
    sid = sess.get("id")
    if sid != o.get("stripe_session_id"):
        if sid and (sid in (o.get("retired_sessions") or [])) and sid not in [u.get("id") for u in o.get("unmatched_payments") or []]:
            o["unmatched_payments"] = list(o.get("unmatched_payments") or []) + [
                {"id": sid, "amount": (sess.get("amount_total") or 0) / 100, "at": datetime.utcnow().isoformat(timespec="seconds"),
                 "payment_intent": sess.get("payment_intent") or ""}]
            req.order = o
            db.commit()
            _alert(req, f"A card payment came in for {req.ref} on a checkout page the customer had replaced. Check it in Stripe and refund or apply it.")
        return False
    if o.get("status") in ("paid", "payment_review"):
        return False
    want = int(round(float(o.get("amount") or 0) * 100))
    got = sess.get("amount_subtotal")
    got = int(got) if got is not None else int(sess.get("amount_total") or 0)
    paid = (sess.get("amount_total") or 0) / 100
    ok = got == want and str(sess.get("currency") or "usd").lower() == "usd"
    o.update(status="paid" if ok else "payment_review", paid_at=datetime.utcnow().isoformat(timespec="seconds"), paid_amount=paid,
             payment_intent=sess.get("payment_intent") or "", paid_online=True)
    if not ok:
        o["review_reason"] = f"Stripe reported {got / 100:.2f} {sess.get('currency') or ''} for an order of {want / 100:.2f} USD."
        req.order = o
        db.commit()
        _alert(req, f"The card payment for {req.ref} does not match the order total. {o['review_reason']} Check it in Stripe before starting work.")
        return False
    req.order = o
    if req.status in ("draft", "submitted", "reviewing", "confirmed"):
        req.status = "ordered"
    req.submitted_at = req.submitted_at or datetime.utcnow()
    from . import invoicing

    invoicing.mark_paid(db, req, paid, "Paid online through Stripe")
    db.commit()
    return True


def _alert(req, text: str) -> None:
    """Email you about a payment that needs a look (best effort; it also shows on the request)."""
    try:
        from .cli import send_email

        send_email(f"Payment to check: {req.ref}", text)
    except Exception:  # noqa: BLE001
        pass


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
    if not o.get("number"):
        return None
    return {k: o.get(k) for k in ("number", "method", "status", "placed_at", "amount", "lines", "ship_to", "po_number", "paid_at", "lead_days",
                                  "invoice_number", "terms_days", "due_date", "invoice_date")} | {"pay_online": stripe_enabled() and o.get("status") in ("invoiced", "invoice_due"), 
        "status_label": ORDER_LABEL.get(o.get("status"), o.get("status"))}
