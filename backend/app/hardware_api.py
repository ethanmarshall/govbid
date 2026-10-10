"""Hardware library and McMaster-Carr connection (login required).

GET    /api/hardware                 items and the McMaster connection status
POST   /api/hardware                 add or update an item {id?, part_number, vendor, description, match, pack_price, pack_qty, unit_price}
DELETE /api/hardware/{id}
POST   /api/hardware/mcmaster        {part_number, match} add a McMaster part and price it from the API
POST   /api/hardware/{id}/refresh    price again from McMaster
POST   /api/hardware/test            {name, qty} which item a part name matches and what it costs
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import hardware, mcmaster
from .db import get_db
from .models_hardware import HardwareItem

router = APIRouter(prefix="/api/hardware")


@router.get("")
def list_items(db: Session = Depends(get_db)):
    items = db.scalars(select(HardwareItem).order_by(HardwareItem.vendor, HardwareItem.part_number)).all()
    return {"items": [hardware.item_dict(i) for i in items], "mcmaster": mcmaster.status()}


class ItemIn(BaseModel):
    id: int | None = None
    part_number: str = ""
    vendor: str = "McMaster-Carr"
    description: str = ""
    match: str = ""
    pack_price: float | None = None
    pack_qty: int = 1
    unit_price: float | None = None
    url: str = ""


@router.post("")
def save_item(body: ItemIn, db: Session = Depends(get_db)):
    if not (body.part_number.strip() or body.description.strip()):
        raise HTTPException(400, "Give a part number or a description.")
    it = db.get(HardwareItem, body.id) if body.id else None
    if it is None:
        it = HardwareItem()
        db.add(it)
    it.part_number = body.part_number.strip()[:40]
    it.vendor = body.vendor.strip()[:40] or "McMaster-Carr"
    it.description = body.description.strip()[:300]
    it.match = body.match.strip()[:400]
    it.pack_qty = max(int(body.pack_qty or 1), 1)
    if body.pack_price is not None:
        it.pack_price = float(body.pack_price)
        it.unit_price = round(it.pack_price / it.pack_qty, 4)
    elif body.unit_price is not None:
        it.unit_price = float(body.unit_price)
        it.pack_price = round(it.unit_price * it.pack_qty, 4)
    if body.pack_price is not None or body.unit_price is not None:
        it.source, it.priced_at, it.price_breaks = "manual", datetime.utcnow(), []
    it.url = body.url.strip()[:300] or (f"https://www.mcmaster.com/{it.part_number}/" if mcmaster.PN_RX.fullmatch(it.part_number.upper()) else "")
    db.commit()
    return hardware.item_dict(it)


@router.delete("/{iid}")
def delete_item(iid: int, db: Session = Depends(get_db)):
    it = db.get(HardwareItem, iid)
    if it:
        db.delete(it)
        db.commit()
    return {"ok": True}


class McIn(BaseModel):
    part_number: str
    match: str = ""


@router.post("/mcmaster")
def add_mcmaster(body: McIn, db: Session = Depends(get_db)):
    try:
        it = hardware.add_from_mcmaster(db, body.part_number, body.match)
    except mcmaster.McMasterError as exc:
        it = db.scalar(select(HardwareItem).where(HardwareItem.part_number == body.part_number.strip().upper()))
        raise HTTPException(400, str(exc) + ("" if it is None else " (The part is in your library.)"))
    return hardware.item_dict(it)


@router.post("/{iid}/refresh")
def refresh_item(iid: int, db: Session = Depends(get_db)):
    it = db.get(HardwareItem, iid)
    if not it:
        raise HTTPException(404, "Not found")
    if not mcmaster.configured():
        raise HTTPException(400, "The McMaster-Carr API is not set up.")
    it = hardware.refresh(db, it)
    if it.error:
        raise HTTPException(400, it.error)
    return hardware.item_dict(it)


class TestIn(BaseModel):
    name: str
    qty: int = 1


@router.post("/test")
def test_match(body: TestIn, db: Session = Depends(get_db)):
    return hardware.price_bought(db, body.name, body.qty)
