"""Bid score, amendment watch, calendar feed and make-or-buy endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import bidding, make_or_buy, quotes
from .connectors import sam_gov
from .db import get_db
from .models import Opportunity, OpportunityChange, PartQuote
from .models_crm import Organization, VendorQuote
from .services import get_profile

router = APIRouter(prefix="/api")


@router.get("/opportunities/{opp_id}/score")
def score(opp_id: int, db: Session = Depends(get_db)):
    o = db.get(Opportunity, opp_id)
    if not o:
        raise HTTPException(404, "Opportunity not found")
    return bidding.bid_score(db, o, get_profile(db))


# ------------------------------------------------------------------ amendment watch
@router.get("/watch")
def watch_status(db: Session = Depends(get_db), unseen_only: bool = False, limit: int = 50):
    stmt = select(OpportunityChange).order_by(OpportunityChange.detected_at.desc(), OpportunityChange.id.desc())
    if unseen_only:
        stmt = stmt.where(OpportunityChange.seen.is_(False))
    rows = db.scalars(stmt.limit(limit)).all()
    return {"tracked": len(bidding.watch_candidates(db)),
            "unseen": db.query(OpportunityChange).filter(OpportunityChange.seen.is_(False)).count(),
            "changes": [bidding.change_dict(c, db.get(Opportunity, c.opportunity_id)) for c in rows]}


@router.post("/watch/check")
def watch_check(db: Session = Depends(get_db)):
    try:
        return bidding.check_amendments(db)
    except sam_gov.SamApiError as exc:
        raise HTTPException(400, str(exc))


@router.post("/watch/seen")
def watch_seen(opportunity_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(OpportunityChange).filter(OpportunityChange.seen.is_(False))
    if opportunity_id:
        q = q.filter(OpportunityChange.opportunity_id == opportunity_id)
    n = q.update({OpportunityChange.seen: True})
    db.commit()
    return {"marked": n}


# ------------------------------------------------------------------ calendar
@router.get("/calendar.ics")
def calendar(db: Session = Depends(get_db)):
    ics = bidding.to_ics(bidding.calendar_events(db, get_profile(db)))
    return Response(ics, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": 'inline; filename="govbid-pro.ics"'})


@router.get("/calendar")
def calendar_json(db: Session = Depends(get_db)):
    return [{**e, "date": e["date"].isoformat()} for e in bidding.calendar_events(db, get_profile(db))]


# ------------------------------------------------------------------ make or buy
class PriceRow(BaseModel):
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)


class VendorQuoteIn(BaseModel):
    organization_id: int | None = None
    vendor_name: str = ""
    prices: list[PriceRow] = Field(min_length=1)
    tooling_charge: float = Field(0, ge=0)
    freight: float = Field(0, ge=0)
    lead_days: int | None = Field(None, ge=0)
    quote_ref: str = ""
    valid_until: str = ""
    notes: str = ""


def _pq(db: Session, qid: int) -> PartQuote:
    q = db.get(PartQuote, qid)
    if not q:
        raise HTTPException(404, "Quote not found")
    return q


@router.get("/pricing/quotes/{qid}/make-or-buy")
def mob(qid: int, db: Session = Depends(get_db)):
    return make_or_buy.compare(db, _pq(db, qid), quotes.get_overrides(db))


def _apply(v: VendorQuote, body: VendorQuoteIn, db: Session) -> None:
    org = db.get(Organization, body.organization_id) if body.organization_id else None
    if body.organization_id and not org:
        raise HTTPException(400, "Vendor organization not found")
    name = body.vendor_name.strip() or (org.name if org else "")
    if not name:
        raise HTTPException(400, "Give a vendor name or pick a saved vendor")
    v.organization_id = org.id if org else None
    v.vendor_name = name
    v.prices = [p.model_dump() for p in sorted(body.prices, key=lambda p: p.quantity)]
    for f in ("tooling_charge", "freight", "lead_days", "quote_ref", "valid_until", "notes"):
        setattr(v, f, getattr(body, f))


@router.post("/pricing/quotes/{qid}/vendor-quotes")
def add_vq(qid: int, body: VendorQuoteIn, db: Session = Depends(get_db)):
    _pq(db, qid)
    v = VendorQuote(part_quote_id=qid)
    _apply(v, body, db)
    db.add(v)
    db.commit()
    return make_or_buy.compare(db, _pq(db, qid), quotes.get_overrides(db))


@router.put("/pricing/quotes/{qid}/vendor-quotes/{vid}")
def put_vq(qid: int, vid: int, body: VendorQuoteIn, db: Session = Depends(get_db)):
    v = db.get(VendorQuote, vid)
    if not v or v.part_quote_id != qid:
        raise HTTPException(404, "Vendor quote not found")
    _apply(v, body, db)
    db.commit()
    return make_or_buy.compare(db, _pq(db, qid), quotes.get_overrides(db))


@router.delete("/pricing/quotes/{qid}/vendor-quotes/{vid}")
def del_vq(qid: int, vid: int, db: Session = Depends(get_db)):
    v = db.get(VendorQuote, vid)
    if not v or v.part_quote_id != qid:
        raise HTTPException(404, "Vendor quote not found")
    db.delete(v)
    db.commit()
    return make_or_buy.compare(db, _pq(db, qid), quotes.get_overrides(db))
