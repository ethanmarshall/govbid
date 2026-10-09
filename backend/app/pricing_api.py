"""REST endpoints for the Part Quotes page."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import pricing, quotes
from .db import get_db
from .models import QUOTE_STATUSES

router = APIRouter(prefix="/api/pricing")


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except pricing.SpecError as exc:
        raise HTTPException(400, str(exc))


@router.get("/meta")
def pricing_meta(db: Session = Depends(get_db)):
    cfg = quotes.get_config(db)
    return {
        "operation_types": pricing.OPERATION_TYPES,
        "stock_shapes": pricing.STOCK_SHAPES,
        "materials": sorted(cfg["materials"]),
        "finishes": sorted(cfg["finishes"]),
        "tolerances": list(cfg["tolerance_multiplier"]),
        "packaging_levels": list(cfg["packaging"]),
        "statuses": QUOTE_STATUSES,
        "example_spec": pricing.EXAMPLE_SPEC,
    }


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    return {"config": quotes.get_config(db), "overrides": quotes.get_overrides(db), "defaults": pricing.DEFAULT_CONFIG}


class ConfigIn(BaseModel):
    changes: dict
    replace: bool = False


@router.put("/config")
def put_config(body: ConfigIn, db: Session = Depends(get_db)):
    return {"config": _guard(quotes.update_config, db, body.changes, body.replace)}


@router.post("/config/reset")
def reset_config(db: Session = Depends(get_db)):
    return {"config": quotes.reset_config(db)}


@router.post("/estimate")
def estimate(spec: dict, db: Session = Depends(get_db)):
    return _guard(quotes.run_estimate, db, spec)


class QuoteIn(BaseModel):
    spec: dict
    opportunity_id: int | None = None
    status: str = "draft"
    quoted_quantity: int | None = None
    quoted_unit_price: float | None = None
    notes: str = ""


@router.get("/quotes")
def list_quotes(status: str = "", opportunity_id: int | None = None, q: str = "", db: Session = Depends(get_db)):
    return quotes.list_quotes(db, status=status, opportunity_id=opportunity_id, q=q, limit=200)


@router.post("/quotes")
def create_quote(body: QuoteIn, db: Session = Depends(get_db)):
    return _guard(quotes.save_quote, db, body.spec, opportunity_id=body.opportunity_id, status=body.status,
                  quoted_quantity=body.quoted_quantity, quoted_unit_price=body.quoted_unit_price, notes=body.notes)


@router.get("/quotes/{qid}")
def read_quote(qid: int, db: Session = Depends(get_db)):
    return _guard(quotes.get_quote, db, qid)


@router.put("/quotes/{qid}")
def update_quote(qid: int, body: QuoteIn, db: Session = Depends(get_db)):
    return _guard(quotes.save_quote, db, body.spec, opportunity_id=body.opportunity_id, status=body.status,
                  quoted_quantity=body.quoted_quantity, quoted_unit_price=body.quoted_unit_price, notes=body.notes, quote_id=qid)


@router.delete("/quotes/{qid}")
def delete_quote(qid: int, db: Session = Depends(get_db)):
    quotes.delete_quote(db, qid)
    return {"ok": True}
