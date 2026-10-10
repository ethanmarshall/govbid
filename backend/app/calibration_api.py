"""Calibration (login required): real prices against the tool's, and the correction factor per process.

GET    /api/calibration                    samples and factors
POST   /api/calibration/benchmark          multipart: file (STEP), material, process, name, vendor, note,
                                           quantities (comma list), prices (comma list, the real unit prices)
POST   /api/calibration/sample             JSON sample (process, tool_unit_price, actual_unit_price, quantity, ...)
PUT    /api/calibration/{id}               {active, actual_unit_price, note}
DELETE /api/calibration/{id}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import cad, cad_quote, calibration, pricing, quotes
from .db import get_db
from .models_hardware import CalibrationSample

router = APIRouter(prefix="/api/calibration")


@router.get("")
def overview(db: Session = Depends(get_db)):
    rows = db.scalars(select(CalibrationSample).order_by(CalibrationSample.id.desc())).all()
    return {"samples": [calibration.sample_dict(s) for s in rows], "factors": calibration.factors(db),
            "materials": sorted(quotes.get_config(db)["materials"]) + sorted(quotes.get_config(db)["additive"]["materials"])}


def _nums(text: str, kind=float) -> list:
    out = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip().replace("$", "")
        if part:
            try:
                out.append(kind(float(part)))
            except ValueError:
                raise HTTPException(400, f"'{part}' is not a number.")
    return out


@router.post("/benchmark")
async def benchmark(file: UploadFile = File(...), material: str = Form("6061-T6 aluminum"), process: str = Form("auto"),
                    name: str = Form(""), vendor: str = Form(""), note: str = Form(""), quantities: str = Form("1"), prices: str = Form(""),
                    db: Session = Depends(get_db)):
    qs, ps = _nums(quantities, int), _nums(prices)
    if not qs or len(qs) != len(ps):
        raise HTTPException(400, "Give one real unit price for each quantity, for example quantities 1, 10, 60 and prices 120, 45, 30.")
    data = await file.read()
    try:
        stored = await run_in_threadpool(cad_quote.store_upload, data, file.filename or "part.step")
        r = await run_in_threadpool(cad_quote.quote, stored["file_id"], {"material": material, "process": process, "quantities": qs},
                                    quotes.get_overrides(db))
    except (cad.CadError, pricing.SpecError) as exc:
        raise HTTPException(400, str(exc))
    proc = r["spec"].get("process_label") or r["spec"]["process"]
    breaks = {b["quantity"]: b["unit_price"] for b in r["estimate"]["price_breaks"]}
    added = []
    for q, p in zip(qs, ps):
        added.append(calibration.add(db, source="benchmark", process=proc, name=name or stored["filename"], material=material, quantity=q,
                                     tool_unit_price=breaks[q], actual_unit_price=p, vendor=vendor, note=note, file_id=stored["file_id"]))
    return {"added": [calibration.sample_dict(s) for s in added], "factors": calibration.factors(db)}


class SampleIn(BaseModel):
    process: str
    tool_unit_price: float
    actual_unit_price: float
    quantity: int = 1
    name: str = ""
    material: str = ""
    vendor: str = ""
    note: str = ""
    ref: str = ""
    source: str = "benchmark"


@router.post("/sample")
def add_sample(body: SampleIn, db: Session = Depends(get_db)):
    if body.tool_unit_price <= 0 or body.actual_unit_price <= 0:
        raise HTTPException(400, "Prices must be above zero.")
    s = calibration.add(db, **body.model_dump())
    return {"sample": calibration.sample_dict(s), "factors": calibration.factors(db)}


class EditIn(BaseModel):
    active: bool | None = None
    actual_unit_price: float | None = None
    note: str | None = None


@router.put("/{sid}")
def edit(sid: int, body: EditIn, db: Session = Depends(get_db)):
    s = db.get(CalibrationSample, sid)
    if not s:
        raise HTTPException(404, "Not found")
    if body.active is not None:
        s.active = 1 if body.active else 0
    if body.actual_unit_price is not None and body.actual_unit_price > 0:
        s.actual_unit_price = body.actual_unit_price
    if body.note is not None:
        s.note = body.note[:2000]
    db.commit()
    return {"sample": calibration.sample_dict(s), "factors": calibration.factors(db)}


@router.delete("/{sid}")
def delete(sid: int, db: Session = Depends(get_db)):
    s = db.get(CalibrationSample, sid)
    if s:
        db.delete(s)
        db.commit()
    return {"factors": calibration.factors(db)}
