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
MAX_BYTES = 60 * 1024 * 1024


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
        raise HTTPException(413, "STEP file is larger than 60 MB.")
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
