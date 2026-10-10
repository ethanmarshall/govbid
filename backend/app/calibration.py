"""Calibrate the tool's prices against real ones.

Each sample is a part's real price (a vendor quote, or the price you settled on in a review) next to the tool's raw
price for the same part and quantity. The correction factor for a process is the median of real / tool over its
samples. With fewer than 2 samples for a process, the median over all samples is used (once there are 3); with
fewer, no correction. Factors are limited to 0.3 to 3 so one bad sample cannot wreck every price.
"""
from __future__ import annotations

import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models_hardware import CalibrationSample

MIN_PER_PROCESS = 2
MIN_OVERALL = 3
LIMITS = (0.3, 3.0)
PROCESS_LABEL = {"cnc_mill": "CNC milling", "cnc_5axis": "5-axis milling", "cnc_lathe": "CNC turning", "sheet_metal": "Sheet metal",
                 "3d_print": "3D printing", "flat": "Flat parts (DXF)", "drawing": "Parts priced from drawings", "assembly": "Assembly labor"}


def _ratio(s: CalibrationSample) -> float | None:
    if not s.tool_unit_price or s.tool_unit_price <= 0 or not s.actual_unit_price or s.actual_unit_price <= 0:
        return None
    return s.actual_unit_price / s.tool_unit_price


def factors(db: Session) -> dict:
    samples = db.scalars(select(CalibrationSample).where(CalibrationSample.active == 1)).all()
    by: dict[str, list[float]] = {}
    allr: list[float] = []
    for s in samples:
        r = _ratio(s)
        if r is None:
            continue
        by.setdefault(s.process, []).append(r)
        allr.append(r)
    overall = statistics.median(allr) if len(allr) >= MIN_OVERALL else None
    out = {"overall": {"factor": _clamp(overall) if overall else 1.0, "samples": len(allr), "used": overall is not None}, "processes": {}}
    for p, rs in by.items():
        f = statistics.median(rs) if len(rs) >= MIN_PER_PROCESS else None
        out["processes"][p] = {"factor": _clamp(f) if f else None, "samples": len(rs), "label": PROCESS_LABEL.get(p, p),
                               "spread": [round(min(rs), 2), round(max(rs), 2)]}
    return out


def _clamp(f: float) -> float:
    return round(min(max(f, LIMITS[0]), LIMITS[1]), 3)


def factor_for(fs: dict, process: str) -> tuple[float, str]:
    """(factor, where it came from) for a process, using factors(db) output."""
    p = fs["processes"].get(process)
    if p and p.get("factor"):
        return p["factor"], f"{p['samples']} real prices for {p['label'].lower()}"
    if fs["overall"]["used"]:
        return fs["overall"]["factor"], f"{fs['overall']['samples']} real prices across all processes"
    return 1.0, ""


def add(db: Session, **kw) -> CalibrationSample:
    s = CalibrationSample(**{k: v for k, v in kw.items() if hasattr(CalibrationSample, k)})
    db.add(s)
    db.commit()
    return s


def sample_dict(s: CalibrationSample) -> dict:
    r = _ratio(s)
    return {"id": s.id, "source": s.source, "process": s.process, "process_label": PROCESS_LABEL.get(s.process, s.process), "name": s.name,
            "material": s.material, "quantity": s.quantity, "tool_unit_price": s.tool_unit_price, "actual_unit_price": s.actual_unit_price,
            "ratio": round(r, 3) if r else None, "vendor": s.vendor, "note": s.note, "ref": s.ref, "active": bool(s.active),
            "created_at": s.created_at.isoformat() if s.created_at else None}
