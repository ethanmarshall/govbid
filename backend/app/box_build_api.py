"""REST endpoints for box builds (custom electromechanical assemblies) on the Part quotes page.

Pricing lives in app/box_build.py, PCB file reading in app/pcb_files.py, and rates in the shop-rate
config under "box_build" (PUT /api/pricing/config). Saved quotes are PartQuote rows with spec.kind
"box_build". Linked quotes are copied into the spec when linked (GET /link/{id}), so the box build
keeps pricing the same way if the original quote is later edited; relink to pick up changes.
"""
from __future__ import annotations

import copy
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import box_build, pcb_files, pricing, quotes
from .box_build_catalog import COMPONENT_TYPES
from .db import get_db

router = APIRouter(prefix="/api/box-build")

MAX_UPLOAD = 50 * 1024 * 1024
MAX_FILES = 25
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (box_build.BoxBuildError, pricing.SpecError, pcb_files.PcbFileError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)):
    cfg = quotes.get_config(db)
    b = cfg["box_build"]
    return {
        "config": copy.deepcopy(b),
        "component_types": {k: v[0] for k, v in COMPONENT_TYPES.items()},
        "default_methods": {k: v[1] for k, v in COMPONENT_TYPES.items()},
        "termination_methods": list(box_build.TERMINATION_METHODS),
        "enclosures": {k: v["label"] for k, v in b["enclosures"].items()},
        "finishes": {"none": "None", **{k: v["label"] for k, v in b["finishes"].items()}},
        "lab_tests": {k: v["label"] for k, v in b["lab_tests"].items()},
        "pcb_finishes": list(b["pcb_fab"]["finish_factor"]),
        "packaging_levels": list(cfg["packaging"]),
    }


@router.post("/parse")
async def parse_bom(file: UploadFile = File(...)):
    """Top-level assembly BOM (CSV, XLSX or drawing PDF) sorted into enclosure, boards, components and peripherals."""
    name = Path(file.filename or "upload").name
    if not re.search(r"\.(pdf|csv|xlsx|xlsm|tsv|txt)$", name, re.I):
        raise HTTPException(400, "Upload a BOM spreadsheet (CSV or XLSX) or a drawing PDF with the parts list.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "File is larger than 50 MB.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.write_bytes(data)
        return await run_in_threadpool(_guard, box_build.parse_assembly_bom, path, name)


@router.post("/pcb-parse")
async def parse_pcb(files: list[UploadFile] = File(...)):
    """Gerbers (or a zip of fab outputs), drill, pick-and-place and BOM files for one board."""
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload {MAX_FILES} files or fewer (or one zip).")
    got = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(400, f"{f.filename} is larger than 50 MB.")
        if data:
            got.append((Path(f.filename or "file").name, data))
    if not got:
        raise HTTPException(400, "The files are empty.")
    r = await run_in_threadpool(_guard, pcb_files.parse_files, got)
    r["source"] = {"files": [n for n, _ in got]}
    return r


class QuoteIn(BaseModel):
    enclosure: dict = Field(default_factory=dict)
    pcbs: list[dict] = Field(default_factory=list)
    lines: list[dict] = Field(default_factory=list)
    peripherals: list[dict] = Field(default_factory=list)
    children: list[dict] = Field(default_factory=list)
    wiring: dict = Field(default_factory=dict)
    labor: dict = Field(default_factory=dict)
    quantities: list[int] = Field(default_factory=lambda: [1])
    options: dict = Field(default_factory=dict)
    name: str = ""
    part_number: str = ""
    nsn: str = ""


@router.post("/quote")
def quote(body: QuoteIn, db: Session = Depends(get_db)):
    return _guard(box_build.price, body.model_dump(), quotes.get_overrides(db))


class SaveIn(QuoteIn):
    source: dict = Field(default_factory=dict)
    opportunity_id: int | None = None
    status: str = "draft"
    quoted_quantity: int | None = None
    quoted_unit_price: float | None = None
    notes: str = ""
    quote_id: int | None = None


def _saved(db: Session, qid: int) -> dict:
    q = _guard(quotes.get_quote, db, qid)
    if (q.get("spec") or {}).get("kind") != "box_build":
        raise HTTPException(400, f"Quote {qid} is not a box build. Open it from its own tab.")
    return q


@router.post("/save")
def save(body: SaveIn, db: Session = Depends(get_db)):
    if body.quote_id:
        _saved(db, body.quote_id)
        linked = {c.get("quote_id") for c in body.children} | {(body.enclosure.get("child") or {}).get("quote_id")}
        if body.quote_id in linked:
            raise HTTPException(400, "A box build cannot link to itself.")
    spec = _guard(box_build.build_spec, body.model_dump())
    return _guard(quotes.save_quote, db, spec, opportunity_id=body.opportunity_id, status=body.status, quoted_quantity=body.quoted_quantity,
                  quoted_unit_price=body.quoted_unit_price, notes=body.notes, quote_id=body.quote_id)


@router.get("/quotes/{qid}")
def restore(qid: int, db: Session = Depends(get_db)):
    return _saved(db, qid)


@router.get("/link/{qid}")
def link(qid: int, db: Session = Depends(get_db)):
    """A copy of a saved quote's spec to link into a box build, with its current price breaks for reference."""
    q = _guard(quotes.get_quote, db, qid)
    spec = copy.deepcopy(q.get("spec") or {})
    if not spec:
        raise HTTPException(400, f"Quote {qid} has no spec to link.")
    spec.pop("_depth", None)
    return {"quote_id": qid, "name": q["name"], "kind": q["kind"], "part_number": q.get("part_number") or "", "spec": spec,
            "price_breaks": q.get("price_breaks") or []}


class SheetIn(QuoteIn):
    builds: int | None = None
    title: str = ""


def _sheet(spec: dict, db: Session, builds: int, title: str) -> Response:
    if builds < 1:
        raise HTTPException(400, "builds must be at least 1")
    data = _guard(box_build.purchase_xlsx, spec, builds, quotes.get_overrides(db), title)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", title or "box-build").strip("-")[:60] or "box-build"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{slug}-purchase-list.xlsx"'})


@router.post("/sheet.xlsx")
def sheet(body: SheetIn, db: Session = Depends(get_db)):
    return _sheet(body.model_dump(), db, body.builds or min(body.quantities or [1]), body.title)


@router.get("/sheet.xlsx")
def sheet_saved(quote_id: int, builds: int | None = None, db: Session = Depends(get_db)):
    q = _saved(db, quote_id)
    spec = q["spec"]
    return _sheet(spec, db, builds or q.get("quoted_quantity") or min(spec.get("quantities") or [1]), spec.get("name") or "")
