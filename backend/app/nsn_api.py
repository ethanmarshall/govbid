"""NSN award history API: reference prices for quoting a part by its National Stock Number.

DIBBS blocks automated access, so this app does not pull award history from it. History comes from
three places the owner controls:
  - DIBBS award search results he saves as CSV/XLSX and imports (POST /api/nsn/import),
  - awards entered by hand, for example from the procurement history on a DIBBS RFQ (POST /api/nsn/records),
  - his own part quotes: won quotes become awards at his price, lost quotes record his losing price
    (synced automatically when history is read, or with POST /api/nsn/sync-quotes).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import nsn_history
from .db import get_db

router = APIRouter(prefix="/api/nsn")
MAX_BYTES = 20 * 1024 * 1024


class RecordIn(BaseModel):
    nsn: str
    part_number: str = ""
    nomenclature: str = ""
    cage: str = ""
    awardee: str = ""
    contract_number: str = ""
    award_date: str = ""
    quantity: int | None = None
    unit_price: float | None = None
    total: float | None = None
    unit_of_issue: str = ""
    source: str = "manual"
    notes: str = ""


def _nsn_or_400(nsn: str) -> dict:
    try:
        return nsn_history.normalize_nsn(nsn)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{nsn}/history")
def get_history(nsn: str, db: Session = Depends(get_db)):
    """Award records for the NSN (newest first) with stats: count, last unit price and date, median, min, max, last awardee."""
    _nsn_or_400(nsn)
    return nsn_history.history(db, nsn)


@router.get("/{nsn}/links")
def links(nsn: str):
    """Verified lookup pages for the NSN (DIBBS award and RFQ search, SAM.gov search, PUB LOG)."""
    _nsn_or_400(nsn)
    return nsn_history.lookup_links(nsn)


@router.post("/records")
def add_record(body: RecordIn, db: Session = Depends(get_db)):
    """Add one award by hand. A row matching an existing award (NSN, contract, date, unit price) is not duplicated."""
    if body.source in ("quote_won", "quote_lost"):
        raise HTTPException(400, "quote_won and quote_lost records come from your saved quotes.")
    try:
        rec, created = nsn_history.add_record(db, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {**nsn_history.to_dict(rec), "duplicate": not created}


@router.delete("/records/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db)):
    if not nsn_history.delete_record(db, record_id):
        raise HTTPException(404, "Record not found")
    return {"ok": True}


@router.post("/import")
async def import_awards(file: UploadFile = File(...), nsn: str = Form(""), source: str = Form("dibbs_import"), db: Session = Depends(get_db)):
    """Import a CSV/XLSX of awards (DIBBS award search results or any sheet with NSN, contract, date and price columns).

    `nsn` fills rows that have no NSN column, such as a procurement history copied for one item.
    """
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 20 MB.")
    name = file.filename or "awards.csv"
    if not name.lower().endswith((".csv", ".tsv", ".txt", ".xlsx", ".xlsm")):
        raise HTTPException(400, "Upload a .csv or .xlsx file.")
    if source in ("quote_won", "quote_lost"):
        raise HTTPException(400, "quote_won and quote_lost records come from your saved quotes.")
    try:
        return nsn_history.import_awards(db, data, name, default_nsn=nsn, source=source)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/sync-quotes")
def sync_quotes(db: Session = Depends(get_db)):
    """Copy every won/lost part quote with an NSN into award history (and drop records for quotes no longer won/lost)."""
    return {"touched": nsn_history.sync_quote_outcomes(db)}
