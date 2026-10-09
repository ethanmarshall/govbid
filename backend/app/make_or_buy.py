"""Make-or-buy: compare your in-house estimate with outside shop quotes, and check the nonmanufacturer rule.

Buying a part and reselling it makes you a nonmanufacturer for that item. On small business set-asides with a
manufacturing NAICS, SBA's nonmanufacturer rule (13 CFR 121.406(b)) then requires, among other things, that you
supply the end item of a small business manufacturer made in the United States, unless a waiver applies.
13 CFR 121.406(c): the nonmanufacturer rule and the limitations on subcontracting do not apply to small business
set-aside acquisitions with an estimated value between the micro-purchase threshold and the simplified
acquisition threshold.
"""
from __future__ import annotations

from .bidding import MICRO, SAT, SMALL_BUSINESS_SET_ASIDES
from .models import Opportunity, PartQuote
from .models_crm import VendorQuote
from .pricing import merged_config


def vendor_unit_price(prices: list[dict], q: int) -> tuple[float | None, int | None]:
    """The vendor's price at the largest break at or below q (or their smallest break if q is below all)."""
    rows = sorted((int(p["quantity"]), float(p["unit_price"])) for p in prices or [] if p.get("quantity") and p.get("unit_price") is not None)
    if not rows:
        return None, None
    at_or_below = [r for r in rows if r[0] <= q]
    qty, price = (at_or_below[-1] if at_or_below else rows[0])
    return price, qty


def buy_cost(vq: VendorQuote, q: int, spec: dict, cfg: dict) -> dict | None:
    unit, basis_qty = vendor_unit_price(vq.prices, q)
    if unit is None:
        return None
    out = cfg["outsourcing"]
    pk = cfg["packaging"].get((spec.get("packaging") or {}).get("level", "commercial"), {"per_part": 0, "per_lot": 0})
    lot = (vq.tooling_charge or 0) + (vq.freight or 0) + out["receiving_inspection_per_lot"] + pk.get("per_lot", 0) \
        + cfg["inspection"]["cert_per_lot"] + float(spec.get("freight_per_lot", cfg["default_freight_per_lot"]))
    per_part = unit + out["handling_per_part"] + pk.get("per_part", 0)
    cost = per_part * q + lot
    ga = float(spec.get("ga_rate", cfg["ga_rate"]))
    price = cost * (1 + ga) * (1 + out["markup"])
    return {"vendor_unit": round(unit, 2), "vendor_break_qty": basis_qty, "unit_cost": round(cost / q, 2),
            "unit_price": round(price / q, 2), "total_price": round(price, 2), "markup": out["markup"],
            "lead_time_days": (vq.lead_days or 0) + 5 if vq.lead_days is not None else None,
            "note": f"{'below' if basis_qty and basis_qty > q else 'at'} their {basis_qty} pc break" if basis_qty != q else ""}


def nonmanufacturer_check(opp: Opportunity | None, vq: VendorQuote | None, total_value: float | None) -> list[dict]:
    """Plain-language notes on whether buying this part works for the set-aside. Not legal advice."""
    notes: list[dict] = []
    if opp is None:
        return [{"level": "info", "text": "Link the quote to an opportunity to check set-aside rules."}]
    sa = (opp.set_aside_code or "").upper()
    if sa not in SMALL_BUSINESS_SET_ASIDES:
        return [{"level": "ok", "text": "Not a small business set-aside, so the nonmanufacturer rule does not apply."}]
    naics = opp.naics or ""
    if not (naics[:2] in ("31", "32", "33") or naics[:2] in ("42", "44", "45")):
        notes.append({"level": "info", "text": f"NAICS {naics or '(none)'} is not a manufacturing or supply code: the nonmanufacturer rule applies only to supply buys. Check the limitations on subcontracting instead."})
        return notes
    value = opp.estimated_value or total_value
    if value is not None and MICRO < value <= SAT:
        notes.append({"level": "ok", "text": f"Estimated value ${value:,.0f} is between the micro-purchase threshold and the simplified acquisition threshold: SBA rules say the nonmanufacturer rule and limitations on subcontracting do not apply to small business set-asides in that range (13 CFR 121.406(c)). Confirm with the contracting officer, especially for SDVOSB set-asides."})
        return notes
    if value is None:
        notes.append({"level": "warn", "text": "No estimated value, so it is unclear whether the simplified acquisition exemption applies."})
    if vq is None:
        notes.append({"level": "warn", "text": "Buying this part makes you a nonmanufacturer: you must supply the end item of a U.S. small business manufacturer (13 CFR 121.406(b)) unless SBA has waived the rule for this item."})
        return notes
    org = vq.organization
    bt = (org.business_types or {}) if org else {}
    small = bool(bt.get("SB") or bt.get("SDVOSB") or bt.get("VOSB") or bt.get("WOSB") or bt.get("HUBZone") or bt.get("8A"))
    mfr = bool(org.is_manufacturer) if org else False
    name = vq.vendor_name or (org.name if org else "this vendor")
    if org is None:
        notes.append({"level": "warn", "text": f"{name} is not in Contacts, so its size and manufacturer status are unknown. Save it as a vendor and record both."})
    elif small and mfr:
        notes.append({"level": "ok", "text": f"{name} is recorded as a small business manufacturer, which fits the nonmanufacturer rule if the part is made in the U.S. Keep their size representation on file."})
    else:
        missing = [x for x, ok in (("small business", small), ("manufacturer", mfr)) if not ok]
        notes.append({"level": "bad", "text": f"{name} is not recorded as a {' and '.join(missing)}. Supplying their part on this set-aside likely breaks the nonmanufacturer rule unless a waiver applies."})
    if sa.startswith("SDVOSB") and not bt.get("SDVOSB"):
        notes.append({"level": "info", "text": "On an SDVOSB set-aside, work done by another SDVOSB counts toward your share; work by others does not. Check FAR 52.219-14."})
    notes.append({"level": "info", "text": "SBA also expects a nonmanufacturer to be primarily engaged in retail or wholesale trade and normally sell this type of item (13 CFR 121.406(b)(1)). Talk to your APEX Accelerator before relying on resale."})
    return notes


def compare(db, pq: PartQuote, overrides: dict | None) -> dict:
    cfg = merged_config(overrides)
    spec = pq.spec or {}
    breaks = (pq.result or {}).get("price_breaks") or []
    vqs = db.query(VendorQuote).filter(VendorQuote.part_quote_id == pq.id).order_by(VendorQuote.id).all()
    rows = []
    for b in breaks:
        q = b["quantity"]
        options = []
        for vq in vqs:
            bc = buy_cost(vq, q, spec, cfg)
            if bc:
                options.append({"vendor_quote_id": vq.id, "vendor": vq.vendor_name, **bc})
        best_buy = min(options, key=lambda x: x["unit_price"]) if options else None
        choice = "make"
        if best_buy and best_buy["unit_price"] < b["unit_price"]:
            choice = "buy"
        rows.append({"quantity": q, "make": {"unit_price": b["unit_price"], "unit_cost": b["unit_cost"], "lead_time_days": b["lead_time_days"]},
                     "buy": options, "best_buy": best_buy, "cheaper": choice})
    opp = pq.opportunity
    total = (pq.quoted_unit_price or 0) * (pq.quoted_quantity or 0) or None
    checks = {vq.id: nonmanufacturer_check(opp, vq, total) for vq in vqs}
    return {"vendor_quotes": [vq_dict(v) for v in vqs], "comparison": rows, "nmr": checks,
            "nmr_general": nonmanufacturer_check(opp, None, total), "markup": cfg["outsourcing"]["markup"]}


def vq_dict(v: VendorQuote) -> dict:
    org = v.organization
    return {"id": v.id, "part_quote_id": v.part_quote_id, "organization_id": v.organization_id, "vendor_name": v.vendor_name,
            "prices": v.prices, "tooling_charge": v.tooling_charge, "freight": v.freight, "lead_days": v.lead_days,
            "quote_ref": v.quote_ref, "valid_until": v.valid_until, "notes": v.notes,
            "vendor": {"small_business": bool(org and any((org.business_types or {}).values())), "manufacturer": bool(org and org.is_manufacturer),
                       "business_types": (org.business_types or {}) if org else {}} if org else None}
