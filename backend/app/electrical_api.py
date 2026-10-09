"""REST endpoints for the electrical quoters on the Part quotes page: cable harness, control panel, labels and plates.

Parsing and pricing live in app/electrical.py; rates and placeholder prices live in the shop-rate
config under "harness", "panel" and "labels" (PUT /api/pricing/config). Saved quotes are ordinary
PartQuote rows whose spec carries "kind" ("harness", "panel" or "labels") plus the lines, so the
saved quotes list, opportunity link and status tracking work as for other part quotes.
Live distributor prices come from POST /api/distributors/price-bom (another module); the UI calls it
directly and keeps manual prices when it is missing or not configured.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import electrical, pricing, quotes
from .db import get_db
from .electrical_catalog import harness_catalog, labels_catalog, panel_catalog

router = APIRouter(prefix="/api/electrical")

MAX_UPLOAD = 25 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _kind(kind: str) -> str:
    if kind not in electrical.KINDS:
        raise HTTPException(404, f"Unknown quote kind '{kind}'. Use harness, panel or labels.")
    return kind


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (electrical.ElectricalError, pricing.SpecError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/catalog")
def get_catalog(db: Session = Depends(get_db)):
    """Rates, placeholder prices and reference tables for all three quoters."""
    cfg = quotes.get_config(db)
    return {"harness": harness_catalog(cfg), "panel": panel_catalog(cfg), "labels": labels_catalog(cfg),
            "packaging_levels": list(cfg["packaging"]), "ul508a_note": electrical.UL508A_NOTE}


@router.post("/{kind}/parse")
async def parse(kind: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _kind(kind)
    name = Path(file.filename or "upload").name
    if not re.search(r"\.(pdf|csv|xlsx|xlsm|tsv|txt)$", name, re.I):
        raise HTTPException(400, "Upload a drawing PDF or a spreadsheet (CSV or XLSX).")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "File is larger than 25 MB.")
    if not data:
        raise HTTPException(400, "The file is empty.")
    cfg = quotes.get_config(db)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.write_bytes(data)
        try:
            return await run_in_threadpool(electrical.parse_file, kind, path, name, cfg)
        except electrical.ElectricalError as exc:
            raise HTTPException(400, str(exc))


class QuoteIn(BaseModel):
    wires: list[dict] = Field(default_factory=list)  # harness
    bom: list[dict] = Field(default_factory=list)  # harness connectors, contacts, backshells, accessories
    lines: list[dict] = Field(default_factory=list)  # panel BOM or label lines
    quantities: list[int] = Field(default_factory=lambda: [1, 5, 10])
    options: dict = Field(default_factory=dict)
    name: str = ""
    part_number: str = ""
    nsn: str = ""


@router.post("/{kind}/validate")
def validate(kind: str, body: QuoteIn):
    """Warnings only (harness: missing connectors, duplicate pins, contact size vs gauge)."""
    _kind(kind)
    if kind == "harness":
        return {"warnings": _guard(electrical.validate_harness, body.wires, body.bom)}
    if kind == "panel":
        return {"warnings": _guard(electrical.panel_warnings, body.lines)}
    return {"warnings": _guard(electrical.label_warnings, body.lines)}


@router.post("/{kind}/quote")
def quote(kind: str, body: QuoteIn, db: Session = Depends(get_db)):
    _kind(kind)
    return _guard(electrical.price, kind, body.model_dump(), quotes.get_config(db))


class SaveIn(QuoteIn):
    source: dict = Field(default_factory=dict)
    opportunity_id: int | None = None
    status: str = "draft"
    quoted_quantity: int | None = None
    quoted_unit_price: float | None = None
    notes: str = ""
    quote_id: int | None = None


@router.post("/{kind}/save")
def save(kind: str, body: SaveIn, db: Session = Depends(get_db)):
    _kind(kind)
    if body.quote_id:
        _saved(db, kind, body.quote_id)  # do not overwrite a different kind of quote
    spec = _guard(electrical.build_spec, kind, body.model_dump())
    return _guard(quotes.save_quote, db, spec, opportunity_id=body.opportunity_id, status=body.status, quoted_quantity=body.quoted_quantity,
                  quoted_unit_price=body.quoted_unit_price, notes=body.notes, quote_id=body.quote_id)


def _saved(db: Session, kind: str, qid: int) -> dict:
    q = _guard(quotes.get_quote, db, qid)
    if (q.get("spec") or {}).get("kind") != kind:
        raise HTTPException(400, f"Quote {qid} is not a {kind} quote. Open it from its own tab.")
    return q


@router.get("/{kind}/quotes/{qid}")
def restore(kind: str, qid: int, db: Session = Depends(get_db)):
    _kind(kind)
    return _saved(db, kind, qid)


class SheetIn(QuoteIn):
    builds: int | None = None
    title: str = ""


def _sheet_response(kind: str, spec: dict, db: Session, builds: int, title: str) -> Response:
    if builds < 1:
        raise HTTPException(400, "builds must be at least 1")
    data, suffix = _guard(electrical.sheet, kind, spec, quotes.get_config(db), builds, title)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", title or kind).strip("-")[:60] or kind
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{slug}-{suffix}.xlsx"'})


@router.post("/{kind}/sheet.xlsx")
def sheet(kind: str, body: SheetIn, db: Session = Depends(get_db)):
    """Harness: cut list + pin-out + BOM. Panel: purchase list. Labels: plate schedule."""
    _kind(kind)
    return _sheet_response(kind, body.model_dump(), db, body.builds or min(body.quantities or [1]), body.title)


@router.get("/{kind}/sheet.xlsx")
def sheet_saved(kind: str, quote_id: int, builds: int | None = None, db: Session = Depends(get_db)):
    _kind(kind)
    q = _saved(db, kind, quote_id)
    spec = q["spec"]
    n = builds or q.get("quoted_quantity") or min(spec.get("quantities") or [1])
    return _sheet_response(kind, spec, db, n, spec.get("name") or "")
