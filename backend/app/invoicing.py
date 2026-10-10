"""Invoices for website orders.

A customer who chooses "Invoice my company" at checkout gets an invoice straight away:
  - accounts you approved for terms (Customer accounts, net 15/30/45/60): we start the work and they pay within the term;
  - everyone else: the invoice is due on receipt and we start when it is paid (bank transfer, check, or online through
    Stripe when it is set up).
Card orders get a paid invoice (a receipt) once Stripe confirms the payment.

Every invoice is also an invoice in Invoices and finance (one numbering sequence, one list of what is owed), with the
customer order number in its delivery order field. The customer downloads it as a PDF from their order page.
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

TERMS_CHOICES = (0, 15, 30, 45, 60)


def terms_label(days: int) -> str:
    return f"Net {days}" if days else "Due on receipt"


def terms_for(customer) -> int:
    d = int(getattr(customer, "net_terms_days", 0) or 0) if customer else 0
    return d if d in TERMS_CHOICES else 0


def _lines(order: dict) -> list[dict]:
    out = []
    for l in order.get("lines") or []:
        desc = l["name"] + (f" ({l['group']})" if l.get("group") else "")
        extra = ", ".join(x for x in (l.get("process"), l.get("material"), l.get("finish") if l.get("finish") not in ("", "none") else "") if x)
        out.append({"description": desc + (f": {extra}" if extra else ""), "quantity": l["qty"], "unit": "EA", "unit_price": l["unit_price"]})
    return out


def create(db: Session, req, order: dict, terms_days: int, paid_amount: float | None = None):
    """Make the invoice for an order in Invoices and finance. Returns it (already there: the existing one)."""
    from .finance_api import _next_number, clean_lines, get_settings
    from .models_finance import Invoice

    if order.get("invoice_id"):
        inv = db.get(Invoice, order["invoice_id"])
        if inv:
            return inv
    fs = get_settings(db)
    today = date.today()
    bill = req.company or req.contact_name
    who = "\n".join(x for x in (bill, req.contact_name if req.company else "", order.get("billing_email") or req.email) if x)
    inv = Invoice(number=_next_number(db, fs), doc_type="invoice", customer=who[:300], contract_number=(order.get("po_number") or "")[:80],
                  delivery_order=req.ref, lines=clean_lines(_lines(order)), invoice_date=today.isoformat(), submitted_date=today.isoformat(),
                  due_date_override=(today + timedelta(days=terms_days)).isoformat(), acceptance_period_days=0,
                  notes=f"Website order {req.ref}. Terms: {terms_label(terms_days)}.", status="submitted",
                  history=[{"date": today.isoformat(), "status": "submitted", "note": f"Created from website order {req.ref}"}])
    if paid_amount is not None:
        inv.status, inv.paid_date, inv.amount_paid = "paid", today.isoformat(), round(paid_amount, 2)
        inv.history = inv.history + [{"date": today.isoformat(), "status": "paid", "note": "Paid by card through Stripe"}]
    db.add(inv)
    db.flush()
    order.update(invoice_id=inv.id, invoice_number=inv.number, terms_days=terms_days, invoice_date=inv.invoice_date,
                 due_date=inv.due_date_override)
    return inv


def mark_paid(db: Session, req, amount: float | None = None, note: str = "") -> None:
    """The order was paid: record it on its invoice (or make a paid invoice for a card order that has none)."""
    from .models_finance import Invoice

    o = dict(req.order or {})
    inv = db.get(Invoice, o["invoice_id"]) if o.get("invoice_id") else None
    if inv is None:
        create(db, req, o, 0, paid_amount=amount if amount is not None else o.get("amount"))
        req.order = o
        return
    if inv.status != "paid":
        today = date.today().isoformat()
        inv.status, inv.paid_date = "paid", today
        inv.amount_paid = round(float(amount if amount is not None else o.get("amount") or 0), 2)
        inv.history = [*(inv.history or []), {"date": today, "status": "paid", "note": note or "Marked paid"}]


def cancel(db: Session, req) -> None:
    """The order was cancelled: an unpaid invoice is removed from Invoices and finance (a paid one stays: refund it)."""
    from .models_finance import Invoice

    o = dict(req.order or {})
    inv = db.get(Invoice, o["invoice_id"]) if o.get("invoice_id") else None
    if inv is not None and inv.status != "paid":
        db.delete(inv)
        o["invoice_void"] = o.pop("invoice_number", "")
        o.pop("invoice_id", None)
        req.order = o


# ------------------------------------------------------------------ the PDF
def render(req, order: dict, info: dict, remit_to: str, pay_text: str, pay_url: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink, mute, rule, dye, ok = (colors.HexColor(c) for c in ("#15212c", "#5b6773", "#c5cecb", "#2356c4", "#2e7a4c"))
    st = {
        "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=ink),
        "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13, textColor=ink),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=mute),
        "lab": ParagraphStyle("lab", fontName="Helvetica", fontSize=7.5, leading=9, textColor=mute),
        "labr": ParagraphStyle("labr", fontName="Helvetica", fontSize=7.5, leading=9, textColor=mute, alignment=2),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=ink, spaceBefore=12, spaceAfter=4),
        "big": ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=ink),
        "paid": ParagraphStyle("paid", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=ok),
        "r": ParagraphStyle("r", fontName="Helvetica", fontSize=9.5, leading=13, textColor=ink, alignment=2),
        "rb": ParagraphStyle("rb", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=ink, alignment=2),
    }

    def P(t, s="p"):
        return Paragraph(escape(str(t or "")).replace("\n", "<br/>"), st[s])

    o = order
    paid = o.get("status") == "paid"
    card = o.get("method") == "card"
    title = "RECEIPT" if (paid and card) else "INVOICE"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            title=f"{title.title()} {o.get('invoice_number', '')}", author=info.get("name", ""))
    w = letter[0] - 1.4 * inch
    co = info.get("company") or {}
    codes = ", ".join(x for x in (co.get("uei") and f"UEI {co['uei']}", co.get("cage") and f"CAGE {co['cage']}") if x)
    seller = "\n".join(x for x in (remit_to or "", info.get("contact_email") or "", info.get("contact_phone") or "", codes) if x)
    head = Table([[[P(info.get("name") or "", "name"), P(seller, "small")], [P(title, "lab"), P(o.get("invoice_number") or "", "name")]]],
                 colWidths=[w * 0.62, w * 0.38])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, ink), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    a = o.get("ship_to") or {}
    bill = "\n".join(x for x in (req.company, req.contact_name, o.get("billing_email") or req.email) if x)
    ship = "\n".join(x for x in (a.get("name"), a.get("company"), a.get("line1"), a.get("line2"),
                                 f"{a.get('city', '')}, {a.get('state', '')} {a.get('zip', '')}".strip(", ")) if x)
    terms = "Paid by card" if card else terms_label(int(o.get("terms_days") or 0))

    def cell(label, value):
        return [P(label, "lab"), P(value)]

    meta = Table([[cell("Bill to", bill), cell("Ship to", ship),
                   [*cell("Invoice date", o.get("invoice_date") or ""), *cell("Order", req.ref),
                    *(cell("Your PO", o["po_number"]) if o.get("po_number") else []), *cell("Terms", terms),
                    *([] if paid else cell("Due", o.get("due_date") or ""))]]],
                 colWidths=[w * 0.36, w * 0.36, w * 0.28])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 10)]))
    rows = [[P("Item", "lab"), P("Qty", "labr"), P("Unit price", "labr"), P("Amount", "labr")]]
    for l in _lines(o):
        rows.append([P(l["description"]), P(f"{l['quantity']:,}", "r"), P(f"${l['unit_price']:,.2f}", "r"), P(f"${l['quantity'] * l['unit_price']:,.2f}", "r")])
    total = float(o.get("amount") or 0)
    rows.append(["", "", P("Total (USD)", "rb"), P(f"${total:,.2f}", "rb")])
    if paid:
        rows.append(["", "", P("Paid", "r"), P(f"-${float(o.get('paid_amount') or total):,.2f}", "r")])
        rows.append(["", "", P("Balance due", "rb"), P("$0.00", "rb")])
    t = Table(rows, colWidths=[w * 0.55, w * 0.1, w * 0.17, w * 0.18], repeatRows=1)
    n = len(rows)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1, ink), ("LINEBELOW", (0, 1), (-1, n - (4 if paid else 2)), 0.4, rule),
                           ("LINEABOVE", (2, n - (3 if paid else 1)), (-1, n - (3 if paid else 1)), 1, ink),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    story = [head, meta, Spacer(1, 14), t, Spacer(1, 14)]
    if paid:
        story += [Paragraph(f"PAID {escape(str(o.get('paid_at') or '')[:10])}", st["paid"])]
    else:
        story += [Paragraph(f"${total:,.2f} due {escape('on receipt' if not o.get('terms_days') else 'by ' + str(o.get('due_date') or ''))}", st["big"])]
        if not o.get("terms_days"):
            story += [P("We start your order when this invoice is paid.")]
        story += [P("How to pay", "h")]
        if pay_url:
            story += [Paragraph(f'Online by bank transfer or card: <link href="{escape(pay_url)}" color="#2356c4">{escape(pay_url)}</link>', st["p"]), Spacer(1, 4)]
        story += [P(pay_text or "Contact us for payment instructions.")]
        story += [Spacer(1, 4), P(f"Please put {o.get('invoice_number') or req.ref} on your payment.", "small")]
    if o.get("notes"):
        story += [P("Order notes", "h"), P(o["notes"])]
    story += [Spacer(1, 16), P("Sales tax and shipping are not included unless listed above.", "small")]
    doc.build(story)
    return buf.getvalue()
