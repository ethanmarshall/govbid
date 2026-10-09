"""Instant-quote endpoints: upload a STEP file, get geometry and a 3D mesh, price it with selections.

Heat-set inserts: GET /{file_id}/holes lists the model's holes with the guessed thread, and
POST /{file_id}/inserts rebuilds the chosen holes as tapered insert holes in a new STEP file.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import cad, cad_quote, inserts, pricing, quotes
from .db import get_db

router = APIRouter(prefix="/api/cad")
MAX_BYTES = 150 * 1024 * 1024


@router.get("/options")
def options(db: Session = Depends(get_db)):
    cfg = quotes.get_config(db)
    return {
        "processes": cad_quote.PROCESSES,
        "materials": sorted(cfg["materials"]),
        "finishes": sorted(cfg["finishes"]),
        "tolerances": list(cfg["tolerance_multiplier"]),
        "packaging_levels": list(cfg["packaging"]),
        "sheet_gauges": cad_quote.SHEET_GAUGES_IN,
        "print_technologies": {k: v["label"] for k, v in cfg["additive"]["technologies"].items()},
        "print_materials": {k: v["tech"] for k, v in cfg["additive"]["materials"].items()},
        "print_finishes": sorted(cfg["additive"]["finishes"]),
    }


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "STEP file is larger than 150 MB.")
    try:
        # OpenCascade work is CPU-bound; keep the server responsive
        return await run_in_threadpool(cad_quote.store_upload, data, file.filename or "part.step")
    except cad.CadError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{file_id}")
def get_file(file_id: str):
    try:
        return cad_quote.load(file_id)
    except cad.CadError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{file_id}/download")
def download(file_id: str):
    try:
        d = cad_quote.load(file_id)
        return FileResponse(cad_quote.step_path(file_id), filename=d["filename"], media_type="application/step")
    except cad.CadError as exc:
        raise HTTPException(404, str(exc))


class QuoteIn(BaseModel):
    file_id: str
    options: dict = Field(default_factory=dict)


@router.post("/quote")
def quote(body: QuoteIn, db: Session = Depends(get_db)):
    try:
        r = cad_quote.quote(body.file_id, body.options, quotes.get_overrides(db))
    except (cad.CadError, pricing.SpecError) as exc:
        raise HTTPException(400, str(exc))
    r.pop("geometry", None)  # the client already has it
    return r


@router.get("/{file_id}/holes")
async def holes(file_id: str, db: Session = Depends(get_db)):
    """Every cylindrical hole with diameter, depth, through/blind, open end, guessed thread and its insert hole."""
    cfg = quotes.get_config(db)
    try:
        return await run_in_threadpool(inserts.holes_for_file, file_id, cfg)
    except cad.CadError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() or "invalid" in str(exc).lower() else 400, str(exc))


class InsertsIn(BaseModel):
    selections: list[dict] = Field(default_factory=list)  # [{hole_id, thread, from_end: auto|start|end}]
    auto: bool = False


@router.post("/{file_id}/inserts")
async def convert_inserts(file_id: str, body: InsertsIn, db: Session = Depends(get_db)):
    """Convert holes to heat-set insert holes. Returns the new file (file_id, filename, geometry, mesh),
    the inserts, a summary line and warnings. The original file is unchanged."""
    cfg = quotes.get_config(db)
    try:
        cad_quote.load(file_id)
    except cad.CadError as exc:
        raise HTTPException(404, str(exc))
    if not body.auto and not any(s.get("thread") for s in body.selections):
        raise HTTPException(400, "Pick a thread for at least one hole, or use auto.")
    try:
        return await run_in_threadpool(inserts.convert_file, file_id, body.selections, body.auto, cfg)
    except cad.CadError as exc:
        raise HTTPException(400, str(exc))


# ---------------------------------------------------------------- manufacturability
@router.get("/{file_id}/dfm")
async def dfm_check(file_id: str, process: str = "auto", material: str = "", db: Session = Depends(get_db)):
    """Manufacturability findings for the chosen process (auto = the detected one). See app/dfm.py for the rules and sources."""
    from . import dfm

    cfg = quotes.get_config(db)
    try:
        cad_quote.load(file_id)
    except cad.CadError as exc:
        raise HTTPException(404, str(exc))
    try:
        return await run_in_threadpool(dfm.check_file, file_id, process, material, cfg)
    except cad.CadError as exc:
        raise HTTPException(400, str(exc))


# ---------------------------------------------------------------- assemblies and weldments
@router.get("/{file_id}/bodies")
async def list_bodies(file_id: str, mesh: bool = True):
    """Each solid with its own analysis and thumbnail mesh, groups of identical bodies, and contact joints."""
    from . import assembly

    try:
        cad_quote.load(file_id)
    except cad.CadError as exc:
        raise HTTPException(404, str(exc))
    try:
        return await run_in_threadpool(assembly.bodies, file_id, mesh)
    except cad.CadError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{file_id}/split")
async def split_bodies(file_id: str):
    """Store each distinct body as its own CAD file. Returns the groups with file_id and quantity per assembly."""
    from . import assembly

    try:
        cad_quote.load(file_id)
    except cad.CadError as exc:
        raise HTTPException(404, str(exc))
    try:
        return await run_in_threadpool(assembly.split, file_id)
    except cad.CadError as exc:
        raise HTTPException(400, str(exc))


class AssemblyIn(BaseModel):
    bodies: list[dict] = Field(default_factory=list)  # [{file_id, name, qty, process, material, finishes, options, skip, buy, buy_unit_price}]
    joining: dict = Field(default_factory=dict)  # {weld_process, weld_length_in, weld_joints, fasteners, fastener_unit_cost, assembly_minutes, inspection_minutes, first_article}
    quantities: list[int] = Field(default_factory=lambda: [1, 10])
    packaging: str = "commercial"
    freight_per_lot: float | None = None
    name: str = ""
    part_number: str = ""
    nsn: str = ""


@router.post("/{file_id}/assembly-quote")
async def assembly_quote(file_id: str, body: AssemblyIn, db: Session = Depends(get_db)):
    """Combined price breaks: every body at its quantity per assembly, plus joining, assembly labor and inspection.
    Returns per-body lines and a spec (kind "assembly") to save with POST /api/pricing/quotes."""
    from . import assembly

    try:
        cad_quote.load(file_id)
    except cad.CadError as exc:
        raise HTTPException(404, str(exc))
    try:
        return await run_in_threadpool(assembly.quote_file, file_id, body.model_dump(), quotes.get_overrides(db))
    except (cad.CadError, pricing.SpecError) as exc:
        raise HTTPException(400, str(exc))
