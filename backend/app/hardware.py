"""Bought hardware lookup: find a library item for a part name, keep McMaster-Carr prices fresh, and cost a quantity.

A part in a customer's model is matched, in order, by:
  1. a McMaster-Carr part number in its name (McMaster CAD downloads are named by part number)
  2. a library item whose part number appears in the name
  3. a library item whose match phrases all appear in the name ("608 bearing", "m5 x 10 socket head")
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import mcmaster
from .models_hardware import HardwareItem

FRESH_DAYS = 30


def _norm(s: str) -> str:
    s = (s or "").lower().replace("_", " ").replace("-", " ")
    s = re.sub(r"(\d)\s*x\s*(\d)", r"\1 x \2", s)
    return re.sub(r"\s+", " ", s).strip()


def item_dict(it: HardwareItem) -> dict:
    return {"id": it.id, "part_number": it.part_number, "vendor": it.vendor, "description": it.description, "match": it.match,
            "unit_price": it.unit_price, "pack_price": it.pack_price, "pack_qty": it.pack_qty, "price_breaks": it.price_breaks or [],
            "source": it.source, "url": it.url, "error": it.error, "priced_at": it.priced_at.isoformat() if it.priced_at else None,
            "stale": bool(it.priced_at and datetime.utcnow() - it.priced_at > timedelta(days=FRESH_DAYS))}


def find(db: Session, name: str) -> tuple[HardwareItem | None, str | None]:
    """(library item, McMaster part number seen in the name). Either may be None."""
    text = _norm(name)
    pns = mcmaster.part_numbers_in(name)
    items = db.scalars(select(HardwareItem)).all()
    for pn in pns:
        for it in items:
            if it.part_number.upper() == pn:
                return it, pn
    for it in items:
        if it.part_number and len(it.part_number) >= 4 and it.part_number.lower() in text.replace(" ", ""):
            return it, None
    best, best_len = None, 0
    for it in items:
        for phrase in (p.strip() for p in (it.match or "").split(",")):
            words = _norm(phrase).split()
            if words and all(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) for w in words) and len(words) > best_len:
                best, best_len = it, len(words)
    return best, (pns[0] if pns else None)


def refresh(db: Session, it: HardwareItem) -> HardwareItem:
    """Update one item's price from McMaster (only McMaster part numbers, only when the API is set up)."""
    if not mcmaster.configured() or not mcmaster.PN_RX.fullmatch((it.part_number or "").upper()):
        return it
    try:
        p = mcmaster.client().product(it.part_number)
    except mcmaster.McMasterError as exc:
        it.error = str(exc)[:500]
        db.commit()
        return it
    it.description = it.description or p["description"]
    it.unit_price, it.pack_price, it.pack_qty, it.price_breaks = p["unit_price"], p["pack_price"], p["pack_qty"], p["price_breaks"]
    it.url, it.source, it.error, it.priced_at = p["url"], "mcmaster", "", datetime.utcnow()
    db.commit()
    return it


def add_from_mcmaster(db: Session, pn: str, match: str = "") -> HardwareItem:
    pn = pn.strip().upper()
    it = db.scalar(select(HardwareItem).where(HardwareItem.part_number == pn))
    if it is None:
        it = HardwareItem(part_number=pn, vendor="McMaster-Carr", match=match, url=f"https://www.mcmaster.com/{pn}/")
        db.add(it)
        db.commit()
    elif match and match not in (it.match or ""):
        it.match = ", ".join(x for x in (it.match, match) if x)
    if not mcmaster.configured():
        raise mcmaster.McMasterError("The McMaster-Carr API is not set up yet; the part was added, enter its price by hand.")
    p = mcmaster.client().product(pn)
    it.description = p["description"] or it.description
    it.unit_price, it.pack_price, it.pack_qty, it.price_breaks = p["unit_price"], p["pack_price"], p["pack_qty"], p["price_breaks"]
    it.url, it.source, it.error, it.priced_at = p["url"], "mcmaster", "", datetime.utcnow()
    db.commit()
    return it


def cost(it: HardwareItem, qty: int) -> dict | None:
    """What buying qty pieces costs: whole packs at the vendor's quantity break. None when there is no price."""
    qty = max(int(qty or 1), 1)
    pack = max(int(it.pack_qty or 1), 1)
    packs = math.ceil(qty / pack)
    amount = it.pack_price if it.pack_price is not None else (it.unit_price * pack if it.unit_price is not None else None)
    for b in it.price_breaks or []:
        if packs >= int(b.get("min_qty") or 1):
            amount = float(b["amount"])
    if amount is None:
        return None
    total = packs * amount
    return {"packs": packs, "pack_qty": pack, "pack_price": amount, "total": round(total, 2), "each": round(total / qty, 4)}


def price_bought(db: Session, raw_name: str, qty: int) -> dict:
    """Price a bought part for the portal. Returns {found, item, part_number, each, total, note}."""
    it, pn = find(db, raw_name)
    if it is None and pn and mcmaster.configured():
        try:
            it = add_from_mcmaster(db, pn)
        except mcmaster.McMasterError:
            it = None
    if it is not None and mcmaster.configured() and (it.priced_at is None or datetime.utcnow() - it.priced_at > timedelta(days=FRESH_DAYS)):
        it = refresh(db, it)
    c = cost(it, qty) if it is not None else None
    if c is None:
        return {"found": it is not None, "item": item_dict(it) if it else None, "part_number": (it.part_number if it else pn) or "",
                "each": None, "total": None}
    return {"found": True, "item": item_dict(it), "part_number": it.part_number, "each": c["each"], "total": c["total"], "packs": c["packs"],
            "pack_qty": c["pack_qty"]}
