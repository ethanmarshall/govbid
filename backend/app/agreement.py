"""The order agreement a customer signs before an invoice order starts.

Card orders are paid before any work, so they need no agreement. An invoice order is held at "Sign the order
agreement" until the customer signs it online; only then is the invoice made and the order released to you. That way
nothing is bought or cut for an order whose buyer has not agreed, in writing, to pay for it, including the material
already bought if they cancel.

The agreement is your terms (Portal settings, Order agreement; blank uses DEFAULT_TEMPLATE below) filled in with the
order: parties, price, payment terms, and a schedule of every line. The customer signs by typing their name and title,
confirming they can bind their company, and agreeing to sign electronically (the U.S. ESIGN Act and state UETA laws
give an electronic signature the same effect as ink when the signer intends to sign and agrees to do business
electronically). When email is set up, a six-digit code sent to the order's email address confirms who signed.

The exact text they saw is kept with the order with its SHA-256 fingerprint, and the signed PDF carries an audit
trail: name, title, company, email, time (UTC), IP address, browser, and whether the email code was confirmed.

DEFAULT_TEMPLATE is a starting point written for a small job shop, not legal advice. Have a business attorney in
your state review it before you rely on it.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import secrets
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

SIGN_DAYS = 30  # an unsigned agreement (and the price in it) is good for this long

STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
          "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
          "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
          "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
          "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
          "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
          "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
          "WY": "Wyoming", "DC": "the District of Columbia"}

PLACEHOLDERS = {"seller": "your company name", "seller_state": "your state (Company profile)", "buyer": "the customer's company or name",
                "order": "order number", "date": "today's date", "total": "order total", "payment_terms": "Net 30 or Due on receipt",
                "lead_days": "estimated days to ship"}

DEFAULT_TEMPLATE = """1. The order. {buyer} ("Buyer") orders from {seller} ("Seller") the parts and services listed in Schedule A for {total}, under order {order}. This agreement is binding when Buyer signs it. This agreement, Schedule A and the files Buyer provided are the whole agreement. Terms in Buyer's purchase order or other documents that add to or conflict with this agreement do not apply unless Seller agrees to them in writing.

2. Payment. Payment terms: {payment_terms}. If an order is due on receipt, Seller starts work when the invoice is paid. Amounts not paid when due accrue a late charge of 1.5% per month, or the highest rate allowed by law if lower, from the due date until paid. Buyer pays Seller's reasonable costs of collecting past-due amounts, including collection agency and attorney fees. Prices do not include sales tax or shipping unless listed in Schedule A.

3. Stopping work. If any amount Buyer owes Seller is past due, Seller may stop work and hold shipments on this and any other order until it is paid, and delivery dates move by the length of the delay.

4. Cancellations and changes. Parts are made to Buyer's design and cannot be returned or resold. Buyer may cancel only in writing. If Buyer cancels after signing, Buyer pays for (a) all work done up to the cancellation at the prices in Schedule A, prorated for parts in process, (b) all material bought or committed for the order, and (c) any cancellation charges from Seller's suppliers, up to the order total. Changes to drawings, quantities, materials or dates after signing need a written change order and may change the price and delivery date.

5. Title and security. Title passes to Buyer when Seller is paid in full. Until then Buyer grants Seller a security interest in the parts and any material bought for the order, and Seller may file a financing statement to record it.

6. Delivery. Estimated shipping is about {lead_days} days after work starts. Dates are estimates; Seller will tell Buyer promptly of any delay. Risk of loss passes to Buyer when the parts are handed to the carrier.

7. Inspection. Buyer will inspect the parts within 10 days of delivery and tell Seller in writing of any part that does not meet Buyer's drawings or specifications. Seller will repair, remake or credit nonconforming parts, at Seller's choice. Parts not rejected in writing within 10 days are accepted. A claim about some parts does not delay payment for the rest.

8. Design. Seller makes parts to the files and specifications Buyer provided. Buyer is responsible for the design, its fitness for Buyer's use, and for having the right to use it.

9. Warranty and limits. Seller warrants that parts will conform to Buyer's drawings and specifications for 90 days after delivery. THIS IS SELLER'S ONLY WARRANTY. SELLER MAKES NO OTHER WARRANTIES, EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE. SELLER'S TOTAL LIABILITY FOR THIS ORDER IS LIMITED TO THE PRICE OF THE ORDER, AND SELLER IS NOT LIABLE FOR INDIRECT, INCIDENTAL OR CONSEQUENTIAL DAMAGES, INCLUDING LOST PROFITS.

10. Export control. Buyer confirms that the files Buyer uploaded contain no export-controlled (ITAR or EAR) technical data, and will tell Seller in writing before sharing any.

11. Law. The laws of {seller_state} govern this agreement, and Buyer agrees to the jurisdiction of its courts.

12. Signing. Buyer agrees to sign electronically. An electronic signature and electronic copies of this agreement have the same effect as a signed paper original. The person signing confirms that they are authorized to sign for Buyer."""


class AgreementError(ValueError):
    pass


def template(s) -> str:
    return (getattr(s, "agreement_template", "") or "").strip() or DEFAULT_TEMPLATE


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def _money(n) -> str:
    return f"${float(n or 0):,.2f}"


def build(req, order: dict, s, seller: str, seller_state_code: str) -> dict:
    """The full agreement text for this order, and its fingerprint."""
    from .invoicing import terms_label

    state = STATES.get((seller_state_code or "").upper(), "") or "the state where Seller is located"
    buyer = req.company or req.contact_name or "Buyer"
    terms = terms_label(int(order.get("terms_days") or 0))
    values = _Safe(seller=seller, seller_state=state if state.startswith("the ") else f"the State of {state}", buyer=buyer,
                   order=req.ref, date=date.today().isoformat(), total=_money(order.get("amount")), payment_terms=terms,
                   lead_days=order.get("lead_days") or "the time quoted")
    body = template(s).format_map(values)
    a = order.get("ship_to") or {}
    sched = [f"Schedule A: order {req.ref}", ""]
    for i, l in enumerate(order.get("lines") or [], 1):
        extra = ", ".join(x for x in (l.get("process"), l.get("material"), l.get("finish") if l.get("finish") not in ("", "none") else "") if x)
        sched.append(f"{i}. {l['name']}{' (' + l['group'] + ')' if l.get('group') else ''}{': ' + extra if extra else ''}. "
                     f"Quantity {l['qty']:,} at {_money(l['unit_price'])} each = {_money(l['total'])}")
    sched += ["", f"Total: {_money(order.get('amount'))}. Payment terms: {terms}."]
    if order.get("po_number"):
        sched.append(f"Buyer's purchase order: {order['po_number']}.")
    sched.append("Ship to: " + ", ".join(x for x in (a.get("name"), a.get("company"), a.get("line1"), a.get("line2"),
                                                     f"{a.get('city', '')}, {a.get('state', '')} {a.get('zip', '')}") if x))
    head = (f"ORDER AGREEMENT\n\nSeller: {seller}\nBuyer: {buyer}" + (f", attention {req.contact_name}" if req.company else "")
            + f", {req.email}\nOrder: {req.ref}\nDate: {date.today().isoformat()}")
    text = head + "\n\n" + body + "\n\n" + "\n".join(sched)
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "template": hashlib.sha256(template(s).encode()).hexdigest()[:12]}


def start(order: dict, built: dict) -> None:
    order["agreement"] = {"status": "pending", "text": built["text"], "sha256": built["sha256"], "template": built["template"],
                          "sent_at": datetime.utcnow().isoformat(timespec="seconds")}


def public(order: dict) -> dict | None:
    a = order.get("agreement") or {}
    if not a:
        return None
    sig = a.get("signed") or {}
    from .customers import email_enabled

    return {"status": a.get("status"), "text": a.get("text") if a.get("status") == "pending" else None, "sha256": a.get("sha256"),
            "needs_code": a.get("status") == "pending" and email_enabled(),
            "expired": a.get("status") == "pending" and expired(a),
            "signed": {k: sig.get(k) for k in ("name", "title", "company", "at")} if sig else None}


def expired(a: dict) -> bool:
    try:
        return datetime.fromisoformat(a["sent_at"]) + timedelta(days=SIGN_DAYS) < datetime.utcnow()
    except (KeyError, ValueError):
        return False


# ------------------------------------------------------------------ email code (when email is set up)
_codes: dict[str, tuple[str, float]] = {}
_sends: dict[str, deque] = defaultdict(deque)


def send_code(req, email_enabled: bool) -> None:
    from .cli import send_email

    if not email_enabled:
        raise AgreementError("Email is not set up, so no code is needed. Sign below.")
    q = _sends[req.ref]
    now = time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= 5:
        raise AgreementError("Too many codes sent. Try again in an hour.")
    q.append(now)
    code = f"{secrets.randbelow(10 ** 6):06d}"
    _codes[req.ref] = (hashlib.sha256(code.encode()).hexdigest(), now + 900)
    send_email(f"Your signing code for order {req.ref}", f"Your code to sign the order agreement for {req.ref} is {code}.\n\n"
               "It works for 15 minutes. If you did not ask for it, you can ignore this email.", to=req.email, allow_customer=True)


def _code_ok(ref: str, code: str) -> bool:
    h, until = _codes.get(ref, ("", 0))
    ok = bool(h) and time.time() < until and hmac.compare_digest(h, hashlib.sha256((code or "").strip().encode()).hexdigest())
    if ok:
        _codes.pop(ref, None)
    return ok


def sign(order: dict, req, data: dict, ip: str, ua: str, email_enabled: bool) -> None:
    a = dict(order.get("agreement") or {})
    if a.get("status") != "pending":
        raise AgreementError("This agreement is already signed.")
    if expired(a):
        raise AgreementError(f"This agreement was not signed within {SIGN_DAYS} days and has expired. Contact us for a new one.")
    if str(data.get("sha256") or "") != a.get("sha256"):
        raise AgreementError("The agreement changed since you opened it. Reload the page and read it again.")
    name = str(data.get("name") or "").strip()[:120]
    title = str(data.get("title") or "").strip()[:120]
    company = str(data.get("company") or "").strip()[:160]
    if len(name) < 3 or " " not in name:
        raise AgreementError("Type your full name to sign.")
    if not title:
        raise AgreementError("Enter your title.")
    if not (data.get("authority") and data.get("consent") and data.get("agree")):
        raise AgreementError("Check all three boxes to sign.")
    verified = False
    if email_enabled:
        if not _code_ok(req.ref, str(data.get("code") or "")):
            raise AgreementError("That code is not right or has expired. Send a new one.")
        verified = True
    a["status"] = "signed"
    a["signed"] = {"name": name, "title": title, "company": company or req.company or "", "email": req.email, "email_verified": verified,
                   "at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "ip": ip[:64], "user_agent": (ua or "")[:300]}
    order["agreement"] = a


def waive(order: dict, note: str, by: str = "staff") -> None:
    a = dict(order.get("agreement") or {})
    a.update(status="waived", waived={"note": note[:500], "at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "by": by})
    order["agreement"] = a


# ------------------------------------------------------------------ the PDF
def render(req, order: dict, info: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    a = order.get("agreement") or {}
    ink, mute, rule = colors.HexColor("#15212c"), colors.HexColor("#5b6773"), colors.HexColor("#c5cecb")
    p = ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13.2, textColor=ink, spaceAfter=6)
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=ink, spaceAfter=8)
    small = ParagraphStyle("s", fontName="Helvetica", fontSize=8, leading=10.5, textColor=mute)
    lab = ParagraphStyle("l", fontName="Helvetica", fontSize=7.5, leading=9, textColor=mute)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title=f"Order agreement {req.ref}", author=info.get("name", ""))
    w = letter[0] - 1.6 * inch
    story = []
    paras = (a.get("text") or "").split("\n\n")
    story.append(Paragraph(escape(paras[0].split("\n")[0].title()), h))
    first = paras[0].split("\n")[1:]
    story.append(Paragraph("<br/>".join(escape(x) for x in first), p))
    for para in paras[1:]:
        story.append(Paragraph(escape(para).replace("\n", "<br/>"), p))
    status = a.get("status")
    sig = a.get("signed") or {}
    if status == "signed":
        rows = [[Paragraph("Signed for Buyer", lab)],
                [Paragraph(f'<font name="Times-Italic" size="16">{escape(sig.get("name", ""))}</font>', p)],
                [Paragraph(escape(f"{sig.get('name', '')}, {sig.get('title', '')}") + "<br/>" + escape(sig.get("company") or "") + "<br/>" + escape(sig.get("at", "")), small)]]
        t = Table(rows, colWidths=[w * 0.55], hAlign="LEFT")
        t.setStyle(TableStyle([("LINEABOVE", (0, 2), (-1, 2), 0.8, ink), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        audit = [f"Signed electronically by {sig.get('name')} ({sig.get('title')}) for {sig.get('company') or req.company or req.contact_name}.",
                 f"Time: {sig.get('at')} (UTC). IP address: {sig.get('ip')}. Email on the order: {sig.get('email')}"
                 f"{', confirmed with a one-time code' if sig.get('email_verified') else ' (not confirmed by code; email was not set up)'}.",
                 f"Browser: {sig.get('user_agent') or 'unknown'}.",
                 "The signer confirmed authority to sign for Buyer, agreed to sign and receive records electronically, and agreed to this agreement.",
                 f"SHA-256 of the agreement text: {a.get('sha256')}"]
        story += [Spacer(1, 10), KeepTogether([t, Spacer(1, 12), Paragraph("Signature record", lab)] + [Paragraph(escape(x), small) for x in audit])]
    elif status == "waived":
        wv = a.get("waived") or {}
        story += [Spacer(1, 10), Paragraph(escape(f"Online signature not used: {wv.get('note') or 'signed separately'} ({wv.get('at', '')})."), small)]
    else:
        story += [Spacer(1, 10), Paragraph("NOT SIGNED. Sign online from the order page.", ParagraphStyle("u", parent=p, fontName="Helvetica-Bold")),
                  Paragraph(escape(f"SHA-256 of the agreement text: {a.get('sha256')}"), small)]

    def foot(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(mute)
        canvas.drawString(0.8 * inch, 0.45 * inch, f"Order agreement {req.ref}")
        canvas.drawRightString(letter[0] - 0.8 * inch, 0.45 * inch, f"Page {doc_.page}")
        canvas.setStrokeColor(rule)
        canvas.restoreState()

    doc.build(story, onFirstPage=foot, onLaterPages=foot)
    return buf.getvalue()
