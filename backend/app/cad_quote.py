"""Instant quote from a STEP file: geometry + customer selections -> pricing spec -> price.

Works like an online instant-quote shop: upload the model, pick process, material, finish and
extra features, get price breaks. The STEP file and its analysis are cached by content hash.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import cad, pricing
from .config import UPLOAD_DIR

CAD_DIR = UPLOAD_DIR / "cad"
CAD_DIR.mkdir(parents=True, exist_ok=True)

PROCESSES = {
    "auto": "Use the process detected from the geometry",
    "cnc_mill": "CNC milling from plate or block",
    "cnc_lathe": "CNC turning from round bar",
    "sheet_metal": "Laser or waterjet cut, then formed on a press brake",
    "3d_print": "3D printing: FDM, SLA, SLS or MJF",
}

SHEET_GAUGES_IN = [0.020, 0.025, 0.032, 0.036, 0.040, 0.048, 0.050, 0.060, 0.063, 0.075, 0.080, 0.090, 0.100, 0.105, 0.120, 0.125,
                   0.135, 0.160, 0.188, 0.190, 0.250, 0.313, 0.375, 0.500]
STOCK_ALLOWANCE_IN = 0.125  # added to each bounding-box dimension for machining stock


def store_upload(data: bytes, filename: str) -> dict:
    """Save the STEP file, analyze it once, cache the result. Returns file_id, filename, geometry, mesh."""
    if not data:
        raise cad.CadError("The file is empty.")
    head = data[:2000].decode("latin-1", "replace").upper()
    if "ISO-10303" not in head:
        raise cad.CadError("That is not a STEP file. Upload a .step or .stp file.")
    fid = cad.file_id_for(data)
    step_path = CAD_DIR / f"{fid}.step"
    meta_path = CAD_DIR / f"{fid}.json"
    if not step_path.exists():
        step_path.write_bytes(data)
    if meta_path.exists():
        cached = json.loads(meta_path.read_text())
    else:
        cached = cad.analyze_file(step_path)
        meta_path.write_text(json.dumps(cached))
    cached.setdefault("filenames", [])
    if filename and filename not in cached["filenames"]:
        cached["filenames"].append(filename)
        meta_path.write_text(json.dumps(cached))
    name = filename or (cached["filenames"][0] if cached["filenames"] else "part.step")
    return {"file_id": fid, "filename": name, **cached}


def load(file_id: str) -> dict:
    if not file_id or not all(c in "0123456789abcdef" for c in file_id):
        raise cad.CadError("Invalid file id")
    meta_path = CAD_DIR / f"{file_id}.json"
    if not meta_path.exists():
        raise cad.CadError("CAD file not found. Upload it again.")
    d = json.loads(meta_path.read_text())
    return {"file_id": file_id, "filename": (d.get("filenames") or ["part.step"])[0], **d}


def step_path(file_id: str) -> Path:
    load(file_id)  # validates
    return CAD_DIR / f"{file_id}.step"


def _snap_gauge(t: float) -> float:
    return min(SHEET_GAUGES_IN, key=lambda g: abs(g - t))


def build_spec(geometry: dict, opts: dict, inserts_used: list[dict] | None = None, config: dict | None = None) -> tuple[dict, list[str]]:
    """Turn measured geometry and the customer's selections into a pricing spec.

    inserts_used: the heat-set inserts recorded on a converted model (see inserts.convert_file);
    for 3D printing they are priced from config additive.inserts instead of threaded_holes.
    """
    notes: list[str] = []
    ins_cfg = pricing.merged_config(config)["additive"]["inserts"]
    g = geometry
    process = opts.get("process") or "auto"
    if process not in PROCESSES:
        raise pricing.SpecError(f"process must be one of {list(PROCESSES)}")
    if process == "auto":
        process = g["suggested_process"]
    bb = g["bounding_box"]
    holes = g.get("holes") or []
    threaded = max(0, int(opts.get("threaded_holes") or 0))
    inserts = max(0, int(opts.get("inserts") or 0))

    spec: dict = {
        "name": opts.get("name") or "",
        "part_number": opts.get("part_number") or "",
        "nsn": opts.get("nsn") or "",
        "quantities": opts.get("quantities") or [1],
        "material": opts.get("material") or "",
        "tolerance": opts.get("tolerance") or "standard",
        "finishes": [{"type": f} for f in (opts.get("finishes") or [])],
        "inspection": {"first_article": bool(opts.get("first_article"))},
        "packaging": {"level": opts.get("packaging") or "commercial"},
        "material_certs_required": bool(opts.get("material_certs")),
        "approved_source_required": bool(opts.get("approved_source_required", False)),
        "operations": [],
    }
    for key in ("reference_unit_price", "freight_per_lot"):
        if opts.get(key) not in (None, ""):
            spec[key] = float(opts[key])

    if process == "3d_print":
        op = {"type": "additive", "part_volume_in3": g["volume"],
              "bbox_in": [bb["length"], bb["width"], bb["height"]], "support": opts.get("support", True) is not False}
        if opts.get("technology"):
            op["technology"] = opts["technology"]
        if opts.get("infill") not in (None, ""):
            op["infill"] = float(opts["infill"])
        spec["operations"].append(op)
        minutes_each = float(ins_cfg.get("minutes_each", 0.75))
        if inserts_used:
            threads = ins_cfg.get("threads") or {}
            costs = [float((threads.get(i["thread"]) or {}).get("unit_cost", i.get("unit_cost") or ins_cfg.get("default_unit_cost", 0.25)))
                     for i in inserts_used]
            n = len(costs)
            extra = max(threaded - n, 0)
            total = sum(costs) + extra * float(ins_cfg.get("default_unit_cost", 0.25))
            count = n + extra
            spec["operations"].append({"type": "hardware_insert", "count": count, "unit_cost": round(total / count, 4), "minutes_each": minutes_each})
            by: dict[str, int] = {}
            for i in inserts_used:
                by[i["thread"]] = by.get(i["thread"], 0) + 1
            notes.append(f"{n} heat-set insert(s) in the converted model: " + ", ".join(f"{c}x {t}" for t, c in by.items())
                         + f" (PEM tapered IU-type hole sizes), ${total / count:.2f} average each, {minutes_each:g} min to install.")
            if extra:
                notes.append(f"{extra} more threaded hole(s) than converted holes, priced at the default insert cost.")
        elif threaded:
            unit = float(ins_cfg.get("default_unit_cost", 0.25))
            spec["operations"].append({"type": "hardware_insert", "count": threaded, "unit_cost": unit, "minutes_each": minutes_each})
            notes.append(f"{threaded} threaded hole(s) priced as heat-set brass inserts.")
        if opts.get("weld_length_in"):
            notes.append("Weld length ignored for a printed part.")
            opts = {**opts, "weld_length_in": 0}
    elif process == "sheet_metal":
        sm = g.get("sheet_metal")
        if not sm:
            raise pricing.SpecError("This part does not look like sheet metal (no constant thickness found). Choose CNC milling or turning.")
        t = float(opts.get("thickness") or _snap_gauge(sm["thickness"]))
        if abs(t - sm["thickness"]) > 0.01:
            notes.append(f"Thickness set to {t} in; the model measures {sm['thickness']} in.")
        blank = math.sqrt(sm["flat_area"] * 1.15)  # flat pattern plus trim, as a square-equivalent blank
        spec["stock"] = {"shape": "sheet", "dims": {"length": round(blank, 3), "width": round(blank, 3), "thickness": t}}
        cutter = opts.get("cut_process") or ("waterjet" if t > 0.5 else "laser_cut")
        spec["operations"].append({"type": cutter, "cut_length_in": sm["cut_length"], "pierces": sm["holes_through_thickness"] + 1})
        if sm["bends"]:
            spec["operations"].append({"type": "press_brake", "bends": sm["bends"]})
        if threaded:
            spec["operations"].append({"type": "fabrication", "minutes_per_part": round(threaded * 0.75, 2)})
            notes.append(f"{threaded} tapped hole(s) at 0.75 min each.")
        if t > 0.25:
            notes.append("Plate over 1/4 in: check that your brake can form it, or quote as a machined part.")
    elif process == "cnc_lathe":
        tr = g.get("turned")
        if not tr:
            raise pricing.SpecError("No turned diameters found. Choose CNC milling instead.")
        spec["stock"] = {"shape": "bar_round", "dims": {"diameter": round(tr["max_diameter"] + STOCK_ALLOWANCE_IN, 3), "length": round(tr["length"] + 2 * STOCK_ALLOWANCE_IN, 3)}}
        axis = tr.get("axis") or [1, 0, 0]
        cross = [h for h in holes if not cad._parallel(h["axis"], axis, 0.05)]
        bores = len(holes) - len(cross)  # holes on the turning axis are drilled or bored on the lathe
        spec["operations"].append({
            "type": "cnc_lathe",
            "setups": int(opts.get("setups") or 2),
            "features": {"diameters": len(tr["diameters"]) + bores, "threads": threaded, "grooves": int(opts.get("grooves") or 0), "cross_holes": len(cross)},
        })
        if cross:
            notes.append(f"{len(cross)} hole(s) priced as cross holes; assumes live tooling or a secondary operation.")
    else:  # cnc_mill
        stock = sorted((bb["length"], bb["width"], bb["height"]), reverse=True)
        sl, sw, st = (round(d + STOCK_ALLOWANCE_IN, 3) for d in stock)
        stock_vol = sl * sw * st
        removed = max(stock_vol - g["volume"], 0)
        plain = max(len(holes) - threaded, 0)
        spec["stock"] = {"shape": "plate", "dims": {"length": sl, "width": sw, "thickness": st}}
        spec["operations"].append({
            "type": "cnc_mill",
            "setups": int(opts.get("setups") or g.get("estimated_setups") or 2),
            "features": {"holes": plain, "tapped_holes": min(threaded, len(holes)) if holes else threaded,
                         "volume_removed_in3": round(removed, 3), "faces": g.get("face_total", 0)},
        })
        if threaded > len(holes):
            notes.append(f"{threaded} tapped holes requested but {len(holes)} holes found in the model.")
        if (g.get("faces") or {}).get("freeform"):
            notes.append("The model has freeform (3D contoured) surfaces: this estimate is likely low. Use your CAM time, or consider 3D printing.")
        if g.get("fill_ratio") and g["fill_ratio"] < 0.25:
            notes.append(f"Only {g['fill_ratio']:.0%} of the stock block remains in the part: heavy material removal.")

    if inserts:
        spec["operations"].append({"type": "hardware_insert", "count": inserts, "unit_cost": float(opts.get("insert_unit_cost") or 0.40), "minutes_each": 0.5})
    if float(opts.get("weld_length_in") or 0) > 0:
        spec["operations"].append({"type": "weld", "process": opts.get("weld_process") or "mig", "weld_length_in": float(opts["weld_length_in"]),
                                   "joints": int(opts.get("weld_joints") or 1), "fixture": True})
    if float(opts.get("assembly_minutes") or 0) > 0:
        spec["operations"].append({"type": "assembly", "minutes_per_part": float(opts["assembly_minutes"])})

    if g.get("solids", 1) > 1:
        notes.append(f"The file has {g['solids']} bodies. Quote each part separately, or add weld/assembly time for a weldment.")
    if max(bb.values()) > 40:
        notes.append(f"Longest dimension {max(bb.values()):.1f} in: confirm it fits your machine travel or brake length.")
    spec["process"] = process
    return spec, notes


def quote(file_id: str, opts: dict, config: dict | None = None) -> dict:
    d = load(file_id)
    geometry = d["geometry"]
    spec, notes = build_spec(geometry, opts, d.get("inserts"), config)
    spec["cad"] = {"file_id": file_id, "filename": opts.get("filename") or d["filename"],
                   "options": {k: v for k, v in opts.items() if k not in ("name", "part_number", "nsn", "filename")}}
    if d.get("derived_from"):
        spec["cad"]["derived_from"] = d["derived_from"]
        spec["cad"]["inserts"] = d.get("inserts") or []
    if not spec["name"]:
        spec["name"] = Path(spec["cad"]["filename"]).stem
    spec["cad"]["notes"] = notes
    result = pricing.estimate(spec, config)
    result["assumptions"] = notes + result["assumptions"]
    return {"process": spec["process"], "geometry": geometry, "spec": spec, "estimate": result}
