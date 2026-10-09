"""Engineering drawing reader for part quotes.

POST a PDF drawing (from a DIBBS technical data package, for example) and get back the title
block fields, material, finish, tolerance class, thread count, cited specs, distribution
statement and export-control markings, plus `quote_options`: the Instant Quote settings the
drawing supports with confidence.

Drawings are saved under UPLOAD_DIR/drawings/ by content hash so a saved quote can point to
its drawing (`drawing_id`). Scanned drawings have no text layer; `use_ai=true` sends the PDF
to Claude when ANTHROPIC_API_KEY is set. Only do that for drawings you are allowed to share
with an outside service: never for ITAR/EAR controlled or limited-distribution drawings.

POST /{drawing_id}/quote prices the part from the drawing alone (no STEP model): see
drawing_quote.py. Save the returned spec with POST /api/pricing/quotes like any other quote.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import drawing, drawing_assembly, drawing_quote, pricing, quotes
from .config import UPLOAD_DIR
from .db import get_db

router = APIRouter(prefix="/api/drawings")
MAX_BYTES = 150 * 1024 * 1024
DRAWING_DIR = UPLOAD_DIR / "drawings"


def drawing_id_for(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _paths(drawing_id: str):
    if not drawing_id or len(drawing_id) != 32 or not all(c in "0123456789abcdef" for c in drawing_id):
        raise HTTPException(400, "Invalid drawing id")
    return DRAWING_DIR / f"{drawing_id}.pdf", DRAWING_DIR / f"{drawing_id}.json"


def _meta(meta_path) -> dict:
    try:
        return json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return {}


@router.post("/read")
async def read(file: UploadFile = File(...), use_ai: bool = Form(False), db: Session = Depends(get_db)):
    """Read a PDF drawing. Returns the parsed fields, drawing_id, filename and quote_options."""
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The drawing is larger than 150 MB.")
    if not data.lstrip()[:5].startswith(b"%PDF"):
        raise HTTPException(400, "That is not a PDF. Upload the drawing as a PDF file.")
    DRAWING_DIR.mkdir(parents=True, exist_ok=True)
    did = drawing_id_for(data)
    pdf_path, meta_path = _paths(did)
    if not pdf_path.exists():
        pdf_path.write_bytes(data)
    meta = _meta(meta_path)
    filename = file.filename or "drawing.pdf"
    names = meta.get("filenames") or []
    if filename not in names:
        names.append(filename)

    cached = meta.get("read") if meta.get("parser_version") == drawing.PARSER_VERSION else None
    # Re-read when there is no current cached read, or the caller now asks for the AI pass on a scanned drawing
    if not cached or (use_ai and not cached.get("text_found") and not cached.get("ai_used")):
        try:
            cached = await run_in_threadpool(drawing.read_drawing, pdf_path, use_ai)
        except drawing.DrawingError as exc:
            raise HTTPException(400, str(exc))
    meta = {"filenames": names, "read": cached, "parser_version": drawing.PARSER_VERSION}
    meta["assembly"] = await run_in_threadpool(_assembly, pdf_path, cached)
    meta_path.write_text(json.dumps(meta))

    cfg = quotes.get_config(db)
    opts = drawing.quote_options(cached, materials=list(cfg["materials"]), finishes=list(cfg["finishes"]))
    return {**cached, "drawing_id": did, "filename": filename, "quote_options": opts, "assembly": meta["assembly"]}


def _assembly(pdf_path, read: dict) -> dict | None:
    """Assembly drawings are quoted as box builds; None for a single part. Never fails the read."""
    try:
        return drawing_assembly.analyze(pdf_path, read)
    except Exception:  # noqa: BLE001
        return None


@router.get("/{drawing_id}")
def info(drawing_id: str):
    """The saved read of a drawing (no file upload needed)."""
    pdf_path, meta_path = _paths(drawing_id)
    if not pdf_path.exists():
        raise HTTPException(404, "Drawing not found. Upload it again.")
    meta = _meta(meta_path)
    return {**(meta.get("read") or {}), "drawing_id": drawing_id, "filename": (meta.get("filenames") or ["drawing.pdf"])[0]}


@router.get("/{drawing_id}/file")
def download(drawing_id: str):
    pdf_path, meta_path = _paths(drawing_id)
    if not pdf_path.exists():
        raise HTTPException(404, "Drawing not found. Upload it again.")
    name = (_meta(meta_path).get("filenames") or ["drawing.pdf"])[0]
    return FileResponse(pdf_path, filename=name, media_type="application/pdf", content_disposition_type="inline")


class DrawingQuoteIn(BaseModel):
    overrides: dict = Field(default_factory=dict)
    quantities: list[int] = Field(default_factory=list)
    use_ai: bool = False
    force: bool = False  # send to Claude even when the drawing is marked export-controlled or limited distribution


def _geometry(pdf_path, meta: dict, read: dict, use_ai: bool, force: bool) -> tuple[dict, list[str]]:
    """Text-based geometry (cached), optionally refined by Claude (cached separately)."""
    warnings: list[str] = []
    geom = meta.get("geometry")
    if not geom:
        text, _ = drawing.extract_pdf_text(pdf_path)
        geom = drawing_quote.extract_geometry(read, text)
        meta["geometry"] = geom
    if not use_ai:
        return geom, warnings
    if meta.get("geometry_ai"):
        return meta["geometry_ai"], warnings
    blocked = drawing_quote.ai_allowed(read)
    if blocked and not force:
        raise HTTPException(400, blocked + " Enter the sizes by hand, or set force only if you are sure you may share it.")
    if not drawing_quote.ANTHROPIC_API_KEY:
        warnings.append("Set ANTHROPIC_API_KEY to read the drawing with Claude. Priced from the text read only.")
        return geom, warnings
    try:
        ai = drawing_quote._claude_extract(pdf_path.read_bytes())
        meta["geometry_ai"] = drawing_quote.merge_ai(geom, ai)
        return meta["geometry_ai"], warnings
    except Exception as exc:  # noqa: BLE001  (network, quota, bad JSON)
        warnings.append(f"The Claude read failed ({exc}). Priced from the text read only.")
        return geom, warnings


@router.post("/{drawing_id}/quote")
async def quote_from_drawing(drawing_id: str, body: DrawingQuoteIn, db: Session = Depends(get_db)):
    """Price a part from its drawing alone. Returns geometry (what was read), inputs (values used),
    spec, estimate, assumptions, confidence and warnings."""
    pdf_path, meta_path = _paths(drawing_id)
    if not pdf_path.exists():
        raise HTTPException(404, "Drawing not found. Upload it again.")
    meta = _meta(meta_path)
    if meta.get("parser_version") != drawing.PARSER_VERSION:  # read with older rules: start over
        meta = {"filenames": meta.get("filenames") or [], "parser_version": drawing.PARSER_VERSION}
    read = meta.get("read")
    if not read:
        try:
            read = await run_in_threadpool(drawing.read_drawing, pdf_path, False)
        except drawing.DrawingError as exc:
            raise HTTPException(400, str(exc))
        meta["read"] = read
    read = {**read, "drawing_id": drawing_id, "filename": (meta.get("filenames") or ["drawing.pdf"])[0]}
    try:
        geom, warnings = await run_in_threadpool(_geometry, pdf_path, meta, read, body.use_ai, body.force)
    except drawing.DrawingError as exc:
        raise HTTPException(400, str(exc))
    if "assembly" not in meta:
        meta["assembly"] = await run_in_threadpool(_assembly, pdf_path, read)
    meta_path.write_text(json.dumps(meta))
    overrides = dict(body.overrides or {})
    if body.quantities:
        overrides["quantities"] = body.quantities
    if "assembly" not in meta:
        meta["assembly"] = await run_in_threadpool(_assembly, pdf_path, read)
        meta_path.write_text(json.dumps(meta))
    try:
        r = drawing_quote.quote(read, geom, overrides, quotes.get_overrides(db), assembly=bool(meta.get("assembly")))
    except pricing.SpecError as exc:
        raise HTTPException(400, str(exc))
    r["assembly"] = meta.get("assembly")
    if r["assembly"]:
        warnings.insert(0, r["assembly"]["message"])
        r["confidence"] = "low"
    r["warnings"] = warnings
    r["export_controlled"] = bool(read.get("export_controlled"))
    r["distribution"] = (read.get("distribution") or {}).get("letter") or ""
    return r
