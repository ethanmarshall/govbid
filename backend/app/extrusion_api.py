"""REST endpoints for T-slot extrusion build quotes (the "Extrusion builds" tab of Part quotes).

Parsing and pricing live in app/extrusion.py; rates and placeholder catalog prices live in the
shop-rate config under "extrusion" (PUT /api/pricing/config). Saved builds are ordinary PartQuote
rows whose spec carries "kind": "extrusion_build" plus the lines, so the saved quotes list, the
opportunity link and status tracking all work as for other part quotes.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import extrusion, pricing, quotes
from .config import ANTHROPIC_API_KEY
from .db import get_db

router = APIRouter(prefix="/api/extrusion")

MAX_UPLOAD = 25 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (extrusion.ExtrusionError, pricing.SpecError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/catalog")
def get_catalog(db: Session = Depends(get_db)):
    cfg = quotes.get_config(db)
    out = extrusion.catalog(cfg)
    out["config"] = cfg["extrusion"]
    out["packaging_levels"] = list(cfg["packaging"])
    out["ai_configured"] = bool(ANTHROPIC_API_KEY)
    return out


@router.post("/parse")
async def parse(file: UploadFile = File(...), use_ai: bool = Form(False), force: bool = Form(False), db: Session = Depends(get_db)):
    name = Path(file.filename or "upload").name
    if not re.search(r"\.(pdf|csv|xlsx|xlsm|tsv|txt)$", name, re.I):
        raise HTTPException(400, "Upload a drawing PDF or a BOM spreadsheet (CSV or XLSX).")
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
            out = await run_in_threadpool(extrusion.parse_file, path, name, use_ai, force, cfg)
        except extrusion.ExtrusionError as exc:
            raise HTTPException(400, str(exc))
    return out


class QuoteIn(BaseModel):
    lines: list[dict] = Field(default_factory=list)
    quantities: list[int] = Field(default_factory=lambda: [1])
    options: dict = Field(default_factory=dict)


@router.post("/quote")
def quote(body: QuoteIn, db: Session = Depends(get_db)):
    return _guard(extrusion.price_build, body.lines, quotes.get_config(db), body.quantities, body.options)


class SaveIn(QuoteIn):
    name: str = ""
    part_number: str = ""
    nsn: str = ""
    source: dict = Field(default_factory=dict)
    opportunity_id: int | None = None
    status: str = "draft"
    quoted_quantity: int | None = None
    quoted_unit_price: float | None = None
    notes: str = ""
    quote_id: int | None = None


def build_spec(body: SaveIn) -> dict:
    """The PartQuote spec for an extrusion build. Reopening the quote restores these lines and options."""
    return {"kind": "extrusion_build", "name": body.name or "Extrusion build", "part_number": body.part_number, "nsn": body.nsn,
            "quantities": body.quantities, "lines": extrusion.normalize_lines(body.lines), "options": body.options, "source": body.source}


@router.post("/save")
def save(body: SaveIn, db: Session = Depends(get_db)):
    spec = _guard(build_spec, body)
    return _guard(quotes.save_quote, db, spec, opportunity_id=body.opportunity_id, status=body.status,
                  quoted_quantity=body.quoted_quantity, quoted_unit_price=body.quoted_unit_price, notes=body.notes,
                  quote_id=body.quote_id)


def _saved_spec(db: Session, qid: int) -> dict:
    q = _guard(quotes.get_quote, db, qid)
    if (q.get("spec") or {}).get("kind") != "extrusion_build":
        raise HTTPException(400, f"Quote {qid} is not an extrusion build. Open it from the part quote tabs.")
    return q


@router.get("/quotes/{qid}")
def restore(qid: int, db: Session = Depends(get_db)):
    return _saved_spec(db, qid)


class SheetIn(QuoteIn):
    builds: int | None = None
    title: str = ""


def _sheet(kind: str, lines: list[dict], cfg: dict, builds: int, title: str, mode: str | None) -> Response:
    if builds < 1:
        raise HTTPException(400, "builds must be at least 1")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", title or "extrusion-build").strip("-")[:60] or "extrusion-build"
    if kind == "cut":
        data = _guard(extrusion.cut_list_xlsx, lines, cfg, builds, title)
        fname = f"{slug}-cut-list.xlsx"
    else:
        data = _guard(extrusion.purchase_list_xlsx, lines, cfg, builds, title, mode)
        fname = f"{slug}-purchase-list.xlsx"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _from_saved(db: Session, quote_id: int, builds: int | None) -> tuple[list[dict], int, str, str | None]:
    q = _saved_spec(db, quote_id)
    spec = q["spec"]
    qtys = spec.get("quantities") or [1]
    return spec.get("lines") or [], builds or q.get("quoted_quantity") or min(qtys), spec.get("name") or "", (spec.get("options") or {}).get("pricing_mode")


@router.get("/cutlist.xlsx")
def cutlist_saved(quote_id: int, builds: int | None = None, db: Session = Depends(get_db)):
    lines, n, title, mode = _from_saved(db, quote_id, builds)
    return _sheet("cut", lines, quotes.get_config(db), n, title, mode)


@router.post("/cutlist.xlsx")
def cutlist(body: SheetIn, db: Session = Depends(get_db)):
    return _sheet("cut", body.lines, quotes.get_config(db), body.builds or min(body.quantities or [1]), body.title, body.options.get("pricing_mode"))


@router.get("/purchase.xlsx")
def purchase_saved(quote_id: int, builds: int | None = None, db: Session = Depends(get_db)):
    lines, n, title, mode = _from_saved(db, quote_id, builds)
    return _sheet("purchase", lines, quotes.get_config(db), n, title, mode)


@router.post("/purchase.xlsx")
def purchase(body: SheetIn, db: Session = Depends(get_db)):
    return _sheet("purchase", body.lines, quotes.get_config(db), body.builds or min(body.quantities or [1]), body.title, body.options.get("pricing_mode"))
