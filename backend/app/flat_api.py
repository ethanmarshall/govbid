"""REST endpoints for DXF flat-part quotes (the "DXF flat parts" tab of Part quotes).

Reading, nesting and pricing live in app/flat.py; plasma, router, deburr, PEM and sheet-goods numbers
live in the shop-rate config under "flat" (PUT /api/pricing/config). Saved quotes are ordinary
PartQuote rows whose spec carries "kind": "flat_dxf", the measured parts and the options, so the
saved quotes list, opportunity link and status tracking work as for other part quotes.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import flat, pricing, quotes
from .db import get_db

router = APIRouter(prefix="/api/flat")
MAX_BYTES = 20 * 1024 * 1024
MAX_SVG_SAVED = 400_000  # characters of preview kept with a saved quote


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (flat.FlatError, pricing.SpecError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/options")
def options(db: Session = Depends(get_db)):
    cfg = quotes.get_config(db)
    mats = flat.materials(cfg)
    return {
        "processes": flat.PROCESSES,
        "materials": {k: flat.material_class(k) for k in sorted(mats)},
        "thicknesses": flat.THICKNESSES_IN,
        "sheet_gauges": flat.SHEET_GAUGES_IN,
        "plate_thicknesses": flat.PLATE_IN,
        "sheet_sizes": cfg["flat"]["sheet_sizes"],
        "deburr": flat.DEBURR,
        "finishes": sorted(cfg["finishes"]),
        "packaging_levels": list(cfg["packaging"]),
        "tolerances": list(cfg["tolerance_multiplier"]),
        "units": ["auto", *flat.UNITS],
        "ignore_layers": flat.DEFAULT_IGNORE_LAYERS,
        "join_tolerance_in": flat.DEFAULT_TOL_IN,
        "config": cfg["flat"],
    }


@router.post("/parse")
async def parse(files: list[UploadFile] = File(...), units: str = Form("auto"), ignore_layers: str = Form(""),
                tolerance_in: float = Form(0.0)):
    """Read one or more DXF files. Returns per-file results (units, warnings, SVG preview) and every part."""
    payload = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"{f.filename} is larger than 20 MB.")
        payload.append((f.filename or "part.dxf", data))
    words = [w for w in re.split(r"[,\s]+", ignore_layers) if w] if ignore_layers.strip() else None
    try:
        return await run_in_threadpool(flat.parse_files, payload, units, words, tolerance_in or None)
    except flat.FlatError as exc:
        raise HTTPException(400, str(exc))


class QuoteIn(BaseModel):
    parts: list[dict] = Field(default_factory=list)
    quantities: list[int] = Field(default_factory=lambda: [1])
    options: dict = Field(default_factory=dict)


@router.post("/quote")
def quote(body: QuoteIn, db: Session = Depends(get_db)):
    return _guard(flat.estimate, [dict(p) for p in body.parts], body.options, body.quantities, quotes.get_overrides(db))


class SaveIn(QuoteIn):
    name: str = ""
    part_number: str = ""
    nsn: str = ""
    source: dict = Field(default_factory=dict)  # {files: [{filename, units, units_source, svg, warnings}]}
    opportunity_id: int | None = None
    status: str = "draft"
    quoted_quantity: int | None = None
    quoted_unit_price: float | None = None
    notes: str = ""
    quote_id: int | None = None


def build_spec(body: SaveIn) -> dict:
    """The PartQuote spec for a flat-part quote. Reopening the quote restores these parts, options and previews."""
    files = []
    budget = MAX_SVG_SAVED
    for f in (body.source or {}).get("files") or []:
        svg = f.get("svg") or ""
        keep = svg if len(svg) <= budget else ""
        budget -= len(keep)
        files.append({k: f.get(k) for k in ("filename", "units", "units_source", "warnings")} | {"svg": keep})
    return {"kind": "flat_dxf", "name": body.name or "Flat parts", "part_number": body.part_number, "nsn": body.nsn,
            "quantities": body.quantities, "parts": [flat.clean_part(p) for p in body.parts], "options": body.options,
            "material": body.options.get("material") or "", "source": {"files": files}}


@router.post("/save")
def save(body: SaveIn, db: Session = Depends(get_db)):
    spec = build_spec(body)
    return _guard(quotes.save_quote, db, spec, opportunity_id=body.opportunity_id, status=body.status,
                  quoted_quantity=body.quoted_quantity, quoted_unit_price=body.quoted_unit_price, notes=body.notes,
                  quote_id=body.quote_id)


@router.get("/quotes/{qid}")
def restore(qid: int, db: Session = Depends(get_db)):
    q = _guard(quotes.get_quote, db, qid)
    if (q.get("spec") or {}).get("kind") != "flat_dxf":
        raise HTTPException(400, f"Quote {qid} is not a DXF flat-part quote. Open it from the part quote tabs.")
    return q
