"""The customer's copy of a portal quote as a PDF. Built only from what the customer may see (public_view + public_info)."""
from __future__ import annotations

import io
from datetime import date, timedelta
from xml.sax.saxutils import escape


def _money(n, cents=True) -> str:
    if n is None:
        return ""
    return f"${n:,.2f}" if cents else f"${n:,.0f}"


def _range(lo, hi) -> str:
    return f"{_money(lo, lo < 100)} to {_money(hi, hi < 100)}"


def render(view: dict, info: dict, link: str, keep_days: int = 30, sheets: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink, mute, dye, rule = colors.HexColor("#15212c"), colors.HexColor("#5b6773"), colors.HexColor("#2356c4"), colors.HexColor("#c5cecb")
    st = {
        "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=ink),
        "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=9.5, leading=13, textColor=mute),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=ink, spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13, textColor=ink),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=11, textColor=mute),
        "big": ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=dye),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=12, textColor=ink),
        "lab": ParagraphStyle("lab", fontName="Helvetica", fontSize=7.5, leading=9, textColor=mute),
    }
    P = lambda t, s="p": Paragraph(escape(str(t)), st[s])  # noqa: E731
    res = view.get("result") or {}
    kind = res.get("kind")
    q = res.get("quantity") or view.get("quantity") or 1
    created = view.get("created") or date.today().isoformat()
    try:
        until = (date.fromisoformat(created) + timedelta(days=keep_days)).isoformat()
    except ValueError:
        until = ""

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            title=f"Quote {view['ref']}", author=info.get("name", ""))
    width = letter[0] - 1.4 * inch
    story = []

    co = info.get("company") or {}
    codes = ", ".join(x for x in (co.get("uei") and f"UEI {co['uei']}", co.get("cage") and f"CAGE {co['cage']}") if x)
    contact = "   ".join(x for x in (info.get("contact_email"), info.get("contact_phone"), codes) if x)
    head = Table([[[P(info.get("name") or "Quote", "name"), P(info.get("tagline") or "", "sub")],
                   [P("QUOTE" if kind == "instant" else "ESTIMATE" if kind == "estimate" else "QUOTE REQUEST", "lab"), P(view["ref"], "name")]]],
                 colWidths=[width * 0.66, width * 0.34])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, ink), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [head]
    if contact:
        story += [Spacer(1, 4), P(contact, "sub")]
    story += [Spacer(1, 10)]

    def cell(label, value):
        return [P(label, "lab"), P(value or "", "cell")]

    status = view.get("status_label") or ""
    block = Table([
        [cell("Date", created), cell("Parts" if len(res.get("items") or []) > 1 else "Quantity",
                                     f"{len(res['items'])}" if len(res.get("items") or []) > 1 else f"{((res.get('items') or [{}])[0].get('qty') or q):,}"),
         cell("Status", status)],
        [cell("Material", "Per line, below" if len(res.get("items") or []) > 1 else ((res.get("items") or [{}])[0].get("material") or view.get("material") or "From your files")),
         cell("Finish", "Per line, below" if len(res.get("items") or []) > 1 else (view.get("finish") or "From your files")),
         cell("Price valid until" if kind == "instant" else "Saved until", until)],
    ], colWidths=[width / 3] * 3)
    block.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, ink), ("INNERGRID", (0, 0), (-1, -1), 0.6, ink), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [block, Spacer(1, 12)]

    items = res.get("items") or []
    many = len(items) > 1
    if kind == "instant":
        story += [P("Instant quote", "h")]
        story += ([Paragraph(f"{_money(res.get('total'))} total", st["big"]), P(f"{len(items)} parts" + (f", {_money(res.get('unit_price'))} per set of {q:,}" if q > 1 else ""))]
                  if many else [Paragraph(f"{_money(items[0].get('unit_price') if items else res.get('unit_price'))} each", st["big"]),
                                P(f"{_money(res.get('total'))} for {(items[0].get('qty') if items else q):,}")])
    elif kind == "estimate":
        story += [P("Estimate, confirmed after review", "h")]
        if many or not items or items[0].get("unit_low") is None:
            story += [Paragraph(f"{_range(res.get('total_low'), res.get('total_high'))} total", st["big"]),
                      P(f"{len(items)} parts" + (f", {res['unpriced_lines']} priced by an engineer" if res.get("unpriced_lines") else ""))]
        else:
            story += [Paragraph(f"{_range(items[0]['unit_low'], items[0]['unit_high'])} each", st["big"]),
                      P(f"{_range(res.get('total_low'), res.get('total_high'))} for {items[0].get('qty', q):,}")]
    elif kind == "needs_input":
        story += [P("Not priced yet", "h")]
    else:
        story += [P("Priced by an engineer", "h")]
    if res.get("lead_days"):
        story += [P(f"Ships in about {res['lead_days']} days after the order is confirmed.")]
    if res.get("message"):
        story += [Spacer(1, 6), P(res["message"])]

    items = res.get("items") or []
    if items:
        rows = [[P("Item", "lab"), P("Description", "lab"), P("Qty", "lab"), P("Each", "lab"), P("Line total", "lab")]]
        for it in items:
            price = (_money(it.get("unit_price")) if it.get("unit_price") is not None else
                     _range(it.get("unit_low"), it.get("unit_high")) if it.get("unit_low") is not None else "By review")
            total = (_money(it.get("total")) if it.get("total") is not None else
                     _range(it.get("total_low"), it.get("total_high")) if it.get("total_low") is not None else "")
            desc = it.get("desc") or ""
            if it.get("finish") and it["finish"] != "none":
                desc = f"{desc}, {it['finish']}"
            if it.get("note"):
                desc = f"{desc}. {it['note']}" if desc else it["note"]
            name = (it.get("name") or "") + (f" ({it['group']})" if it.get("group") else "")
            rows.append([P(name, "cell"), P(desc, "cell"), P(f"{int(it.get('qty') or 1):,}", "cell"), P(price, "cell"), P(total, "cell")])
        t = Table(rows, colWidths=[width * 0.24, width * 0.38, width * 0.08, width * 0.15, width * 0.15], repeatRows=1)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1, ink), ("LINEBELOW", (0, 1), (-1, -1), 0.4, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
        story += [P("What we priced", "h"), t]

        # per item: what we read from the files and the three-view drawing, so a misread is easy to spot
        from reportlab.platypus import KeepTogether

        from . import portal_views

        flag_txt = {"assumed": "  (assumed, please check)", "check": "  (please check)"}
        for it in items:
            facts = it.get("facts") or []
            sheet = (sheets or {}).get((it.get("view") or {}).get("key"))
            if not facts and not sheet:
                continue
            block = [P(f"What we read: {it.get('name') or ''}", "h")]
            if facts:
                fr = [[P(f["label"], "lab"), Paragraph(escape(f["value"]) + (f'<font color="#9a6410">{flag_txt[f["flag"]]}</font>' if f.get("flag") in flag_txt else ""), st["cell"])]
                      for f in facts]
                ft = Table(fr, colWidths=[width * 0.26, width * 0.74])
                ft.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                                        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
                block.append(ft)
            if sheet:
                try:
                    dr = portal_views.to_drawing(sheet, width, 3.6 * inch)
                    box = Table([[dr]], colWidths=[width])
                    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, ink), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 8),
                                             ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
                    block += [Spacer(1, 6), box, P((it.get("view") or {}).get("note") or "", "small")]
                except Exception:  # noqa: BLE001  (a drawing problem never stops the PDF)
                    pass
            story.append(KeepTogether(block))

    files = [f for f in view.get("files") or []]
    if files:
        story += [P("Your files", "h")] + [P(f"{f['name']}{' (not kept: export-controlled)' if f.get('removed') else ''}", "cell") for f in files]
    if view.get("notes"):
        story += [P("Your notes", "h"), P(view["notes"])]

    story += [Spacer(1, 14), P("Terms", "h"), P(info.get("terms") or "", "small")]
    if contact:
        story += [Spacer(1, 8), P(f"Questions about this quote? Contact {info.get('name') or 'us'}: "
                                  + ", ".join(x for x in (info.get("contact_email"), info.get("contact_phone")) if x) + f". Mention {view['ref']}.", "small")]
    if link:
        story += [Spacer(1, 8), P("Open this quote online, change the quantity, or send it to us:", "small"),
                  Paragraph(f'<link href="{escape(link)}" color="#2356c4">{escape(link)}</link>', st["small"])]
        if not view.get("submitted"):
            story += [P(f"Quotes you have not sent to us are kept for {keep_days} days.", "small")]
    doc.build(story)
    return buf.getvalue()
