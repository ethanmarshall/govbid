"""Should-cost estimator for custom parts: CNC machining, cutting, forming, welding, finishing.

Every number comes from the shop-rate config (`DEFAULT_CONFIG`, editable in the app and over MCP),
so the estimate is only as good as the rates. The defaults are starting points, not market data:
replace them with your own machine rates, your material supplier's prices and your finisher's quotes.

The model:
  one-time per lot  = programming + setups + fixturing + first article + lot charges
  per part          = material + machine/labor time + hardware + outside finishing + packaging
  unit price (qty)  = (lot costs / qty + per-part cost) * (1 + G&A) * (1 + profit)
Each line of the breakdown carries its hours and rate so a person or an agent can see why.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from .inserts import DEFAULT_CONFIG as _INSERTS_DEFAULT

DEFAULT_CONFIG: dict[str, Any] = {
    "currency": "USD",
    "note": "Starting defaults. Replace every rate with your own shop and supplier numbers before quoting.",
    # Burdened hourly rates (labor + machine + overhead), USD per hour
    "rates": {
        "programming": 85.0,
        "cnc_mill": 95.0,
        "cnc_lathe": 85.0,
        "manual_machining": 70.0,
        "laser_cut": 120.0,
        "waterjet": 110.0,
        "press_brake": 75.0,
        "weld_mig": 80.0,
        "weld_tig": 95.0,
        "fabrication": 65.0,
        "assembly": 55.0,
        "deburr": 50.0,
        "inspection": 70.0,
        "print_labor": 45.0,  # 3D print prep, support removal, depowder, post-cure
    },
    # Setup hours per setup / per lot
    "setup_hours": {
        "cnc_mill": 1.0,
        "cnc_lathe": 0.75,
        "manual_machining": 0.5,
        "laser_cut": 0.25,
        "waterjet": 0.35,
        "press_brake": 0.5,
        "weld_fixture": 1.5,
    },
    # Programming hours per setup (CAM), scaled by tolerance
    "programming_hours_per_setup": {"cnc_mill": 1.0, "cnc_lathe": 0.5, "laser_cut": 0.25, "waterjet": 0.25},
    "tolerance_multiplier": {"standard": 1.0, "tight": 1.35, "precision": 1.8},
    # Materials: density lb/in^3, price per lb, machinability (1 = 6061 Al; higher = slower), cut factor for laser/waterjet
    "materials": {
        "6061-T6 aluminum": {"density": 0.0975, "price_per_lb": 4.50, "machinability": 1.0, "cut_factor": 0.8},
        "5052-H32 aluminum": {"density": 0.0968, "price_per_lb": 4.25, "machinability": 1.1, "cut_factor": 0.8},
        "7075-T6 aluminum": {"density": 0.101, "price_per_lb": 8.00, "machinability": 1.05, "cut_factor": 0.85},
        "A36 / 1018 steel": {"density": 0.284, "price_per_lb": 1.20, "machinability": 1.8, "cut_factor": 1.0},
        "4140 steel": {"density": 0.284, "price_per_lb": 2.50, "machinability": 2.2, "cut_factor": 1.05},
        "304 stainless": {"density": 0.289, "price_per_lb": 4.75, "machinability": 2.8, "cut_factor": 1.3},
        "316 stainless": {"density": 0.289, "price_per_lb": 6.00, "machinability": 3.0, "cut_factor": 1.35},
        "brass 360": {"density": 0.307, "price_per_lb": 6.50, "machinability": 0.8, "cut_factor": 1.1},
        "copper 110": {"density": 0.323, "price_per_lb": 9.00, "machinability": 1.6, "cut_factor": 2.0},
        "delrin (acetal)": {"density": 0.0513, "price_per_lb": 7.00, "machinability": 0.7, "cut_factor": 0.6},
        "G10 / FR4": {"density": 0.065, "price_per_lb": 12.00, "machinability": 1.5, "cut_factor": 0.9},
    },
    "scrap_factor": 0.15,  # extra stock for saw kerf, facing, drops
    "sheet_nest_efficiency": 0.80,  # fraction of a sheet used by nested blanks
    # Laser feed in inches/min at 0.125 in thick for cut_factor 1.0; scales down with thickness
    "laser_ipm_at_0125": 150.0,
    "waterjet_ipm_at_0125": 25.0,
    "pierce_minutes": 0.05,
    # Cycle-time model for machining when no cycle time is given (minutes, before machinability and tolerance)
    "mill_minutes": {"base": 3.0, "per_hole": 0.5, "per_tapped_hole": 0.8, "per_pocket": 4.0, "per_inch_profile": 0.15, "per_cubic_inch_removed": 0.6, "per_face": 0.1},
    "lathe_minutes": {"base": 2.0, "per_diameter": 1.0, "per_thread": 1.5, "per_groove": 0.7, "per_cross_hole": 1.0},
    "brake_minutes_per_bend": 0.4,
    "handling_minutes": 0.5,  # load/unload per part per operation
    # Welding: effective travel incl. prep and cleanup, inches/min
    "weld_ipm": {"mig": 4.0, "tig": 1.5},
    "weld_fitup_minutes_per_joint": 1.0,
    # Outside finishing: per part and minimum lot charge
    "finishes": {
        "anodize (Type II)": {"per_part": 4.0, "lot_min": 150.0, "lead_days": 7},
        "hard anodize (Type III)": {"per_part": 8.0, "lot_min": 250.0, "lead_days": 10},
        "chem film (MIL-DTL-5541)": {"per_part": 3.0, "lot_min": 125.0, "lead_days": 5},
        "powder coat": {"per_part": 8.0, "lot_min": 175.0, "lead_days": 7},
        "zinc plate": {"per_part": 3.0, "lot_min": 125.0, "lead_days": 7},
        "passivate (stainless)": {"per_part": 2.0, "lot_min": 100.0, "lead_days": 5},
        "black oxide": {"per_part": 2.5, "lot_min": 100.0, "lead_days": 5},
        "paint (wet)": {"per_part": 10.0, "lot_min": 200.0, "lead_days": 7},
    },
    # 3D printing. Machine rates are $/hour of printer time (machine, power, wear), separate from labor.
    "additive": {
        "technologies": {
            "fdm": {"label": "FDM (filament)", "machine_rate": 6.0, "cm3_per_hour": 12.0, "minutes_per_inch_height": 6.0,
                    "setup_minutes": 10.0, "post_minutes": 6.0, "support_factor": 0.20, "max_in": [13.5, 13.5, 13.5], "packs_build": False},
            "sla": {"label": "SLA (resin)", "machine_rate": 8.0, "cm3_per_hour": 20.0, "minutes_per_inch_height": 25.0,
                    "setup_minutes": 10.0, "post_minutes": 12.0, "support_factor": 0.15, "max_in": [5.7, 5.7, 7.3], "packs_build": False},
            "sls": {"label": "SLS (nylon powder)", "machine_rate": 30.0, "cm3_per_hour": 90.0, "minutes_per_inch_height": 0.0,
                    "setup_minutes": 20.0, "post_minutes": 8.0, "support_factor": 0.0, "max_in": [6.3, 6.3, 12.6], "packs_build": True},
            "mjf": {"label": "MJF (nylon powder)", "machine_rate": 45.0, "cm3_per_hour": 200.0, "minutes_per_inch_height": 0.0,
                    "setup_minutes": 20.0, "post_minutes": 6.0, "support_factor": 0.0, "max_in": [14.9, 11.2, 14.9], "packs_build": True},
        },
        # price per cm3 of printed material (incl. waste), density g/cm3, which technology prints it
        "materials": {
            "PLA": {"tech": "fdm", "price_per_cm3": 0.03, "density": 1.24},
            "PETG": {"tech": "fdm", "price_per_cm3": 0.035, "density": 1.27},
            "ABS": {"tech": "fdm", "price_per_cm3": 0.035, "density": 1.04},
            "ASA (UV stable)": {"tech": "fdm", "price_per_cm3": 0.045, "density": 1.07},
            "Nylon CF (carbon fiber)": {"tech": "fdm", "price_per_cm3": 0.12, "density": 1.15},
            "PC (polycarbonate)": {"tech": "fdm", "price_per_cm3": 0.06, "density": 1.20},
            "TPU 95A (flexible)": {"tech": "fdm", "price_per_cm3": 0.06, "density": 1.21},
            "Standard resin": {"tech": "sla", "price_per_cm3": 0.15, "density": 1.15},
            "Tough resin": {"tech": "sla", "price_per_cm3": 0.22, "density": 1.15},
            "High-temp resin": {"tech": "sla", "price_per_cm3": 0.35, "density": 1.20},
            "Nylon 12 (SLS)": {"tech": "sls", "price_per_cm3": 0.12, "density": 1.01},
            "Nylon 11 (SLS)": {"tech": "sls", "price_per_cm3": 0.15, "density": 1.05},
            "Nylon 12 (MJF)": {"tech": "mjf", "price_per_cm3": 0.10, "density": 1.01},
            "Nylon 12 glass filled (MJF)": {"tech": "mjf", "price_per_cm3": 0.13, "density": 1.30},
        },
        # in-house post-processing, minutes per part, plus purchased consumables per part
        "finishes": {
            "sanded / supports smoothed": {"minutes": 10.0, "per_part": 0.0},
            "vapor smoothed": {"minutes": 4.0, "per_part": 3.0},
            "dyed black": {"minutes": 3.0, "per_part": 1.0},
            "primed and painted": {"minutes": 20.0, "per_part": 4.0},
            "bead blasted": {"minutes": 3.0, "per_part": 0.0},
        },
        "min_part_charge": 5.0,
        "min_lot_charge": 75.0,  # replaces the shop-wide minimum for printed parts
        # Heat-set inserts for printed parts: install minutes, unit cost per thread and the PEM
        # tapered mounting-hole sizes used to convert modeled holes (see app/inserts.py for the source)
        "inserts": _INSERTS_DEFAULT,
    },
    "inspection": {"first_article_hours": 3.0, "per_part_minutes": 2.0, "cert_per_lot": 25.0},
    "packaging": {
        "commercial": {"per_part": 1.0, "per_lot": 0.0},
        "mil_std_2073": {"per_part": 6.0, "per_lot": 50.0},
    },
    "default_freight_per_lot": 45.0,
    # Buying the part from an outside shop (make-or-buy): your markup on their price and your handling costs
    "outsourcing": {"markup": 0.15, "receiving_inspection_per_lot": 35.0, "handling_per_part": 0.75},
    "ga_rate": 0.10,  # general and administrative
    "profit_rate": 0.15,
    "min_lot_charge": 250.0,
    "lead_time": {"base_days": 10, "first_article_days": 10, "parts_per_day": 25},
}

OPERATION_TYPES = {
    "cnc_mill": "CNC milling. Params: setups, cycle_minutes OR features {holes, tapped_holes, pockets, profile_in, volume_removed_in3, faces}, tolerance",
    "cnc_lathe": "CNC turning. Params: setups, cycle_minutes OR features {diameters, threads, grooves, cross_holes}, tolerance",
    "manual_machining": "Manual mill/lathe/drill press. Params: minutes_per_part, setups",
    "laser_cut": "Laser cutting of sheet or plate. Params: cut_length_in, pierces",
    "waterjet": "Waterjet cutting. Params: cut_length_in, pierces",
    "press_brake": "Press brake forming. Params: bends",
    "weld": "Welding. Params: process (mig|tig), weld_length_in, joints, fixture (bool)",
    "hardware_insert": "PEM nuts/studs, helicoils, fasteners. Params: count, unit_cost, minutes_each",
    "assembly": "Assembly or wiring labor. Params: minutes_per_part",
    "deburr": "Deburr and edge break. Params: minutes_per_part",
    "fabrication": "Other fabrication labor (sawing, grinding, fitting). Params: minutes_per_part",
    "additive": "3D printing. Params: technology (fdm|sla|sls|mjf), part_volume_in3, bbox_in [l, w, h], infill (FDM, 0.1 to 1), "
                "support (bool). Material must be a 3D print material from config additive.materials. No stock needed.",
}

STOCK_SHAPES = {
    "plate": "Rectangular plate or block. dims: length, width, thickness (inches)",
    "sheet": "Sheet blank (laser/brake parts). dims: length, width, thickness (inches)",
    "bar_round": "Round bar. dims: diameter, length (inches)",
    "bar_rect": "Rectangular bar. dims: width, thickness, length (inches)",
    "tube_round": "Round tube. dims: od, wall, length (inches)",
    "tube_rect": "Rectangular tube. dims: width, height, wall, length (inches)",
}


class SpecError(ValueError):
    pass


def merged_config(overrides: dict | None) -> dict:
    """Defaults deep-merged with saved overrides, so new default keys still appear after upgrades."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)

    def merge(dst: dict, src: dict) -> None:
        for k, v in (src or {}).items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    merge(cfg, overrides or {})
    return cfg


def _num(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key, default)
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        raise SpecError(f"'{key}' must be a number, got {v!r}")


def stock_volume(stock: dict) -> float:
    """Cubic inches of raw stock for one part."""
    shape = stock.get("shape", "plate")
    d = stock.get("dims") or {}
    if shape in ("plate", "sheet"):
        return _num(d, "length") * _num(d, "width") * _num(d, "thickness")
    if shape == "bar_rect":
        return _num(d, "width") * _num(d, "thickness") * _num(d, "length")
    if shape == "bar_round":
        r = _num(d, "diameter") / 2
        return math.pi * r * r * _num(d, "length")
    if shape == "tube_round":
        od, wall = _num(d, "od"), _num(d, "wall")
        idia = max(od - 2 * wall, 0)
        return math.pi / 4 * (od * od - idia * idia) * _num(d, "length")
    if shape == "tube_rect":
        w, h, wall = _num(d, "width"), _num(d, "height"), _num(d, "wall")
        return (w * h - max(w - 2 * wall, 0) * max(h - 2 * wall, 0)) * _num(d, "length")
    raise SpecError(f"Unknown stock shape '{shape}'. Use one of {list(STOCK_SHAPES)}")


def _line(category: str, item: str, cost: float, *, basis: str = "per_part", hours: float | None = None, rate: float | None = None, note: str = "") -> dict:
    return {"category": category, "item": item, "basis": basis, "hours": None if hours is None else round(hours, 3),
            "rate": rate, "cost": round(cost, 2), "note": note}


def estimate(spec: dict, config: dict | None = None) -> dict:
    """Estimate cost and price for a part spec. See OPERATION_TYPES and STOCK_SHAPES for the shape of `spec`."""
    cfg = merged_config(config)
    rates, warnings, assumptions = cfg["rates"], [], []

    qtys = spec.get("quantities") or [spec.get("quantity") or 1]
    try:
        qtys = sorted({int(q) for q in qtys if int(q) > 0})
    except (TypeError, ValueError):
        raise SpecError("quantities must be positive integers")
    if not qtys:
        raise SpecError("Give at least one quantity")

    ops = spec.get("operations") or []
    additive_ops = [o for o in ops if o.get("type") == "additive"]
    if additive_ops and len(additive_ops) != 1:
        raise SpecError("Give one additive operation per part")
    mat_name = spec.get("material") or ""
    add_cfg = cfg["additive"]
    if additive_ops:
        amat = add_cfg["materials"].get(mat_name)
        if amat is None:
            raise SpecError(f"Unknown 3D print material '{mat_name}'. Known: {sorted(add_cfg['materials'])}")
        mat = {"density": amat["density"] * 0.0361273, "price_per_lb": 0.0, "machinability": 1.0, "cut_factor": 1.0}
    else:
        mat = cfg["materials"].get(mat_name)
    if mat is None:
        raise SpecError(f"Unknown material '{mat_name}'. Known: {sorted(cfg['materials'])}. Add it to the shop rates first.")
    tol = spec.get("tolerance", "standard")
    tol_mult = cfg["tolerance_multiplier"].get(tol)
    if tol_mult is None:
        raise SpecError(f"tolerance must be one of {list(cfg['tolerance_multiplier'])}")
    if tol == "precision":
        warnings.append("Precision tolerances: confirm you can hold and measure them before quoting.")

    per_part: list[dict] = []
    per_lot: list[dict] = []

    # ---------------- material
    stock = spec.get("stock") or {}
    if additive_ops:
        vol = _num(additive_ops[0], "part_volume_in3")
        if vol <= 0:
            raise SpecError("additive operation needs part_volume_in3 > 0")
    else:
        vol = stock_volume(stock)
    if vol <= 0:
        raise SpecError("Stock dimensions are missing or zero")
    weight = vol * mat["density"]
    if additive_ops:
        pass  # printed material is priced in the additive operation
    elif stock.get("shape") == "sheet":
        mat_cost = weight / cfg["sheet_nest_efficiency"] * mat["price_per_lb"]
        mat_note = f"{weight:.2f} lb blank at {cfg['sheet_nest_efficiency']:.0%} nesting"
    else:
        mat_cost = weight * (1 + cfg["scrap_factor"]) * mat["price_per_lb"]
        mat_note = f"{weight:.2f} lb stock + {cfg['scrap_factor']:.0%} scrap"
    if spec.get("material_cost_per_part") is not None:
        mat_cost = _num(spec, "material_cost_per_part")
        mat_note = "material cost given in spec"
    if not additive_ops:
        per_part.append(_line("material", mat_name, mat_cost, rate=mat["price_per_lb"], note=mat_note))
    if spec.get("material_certs_required"):
        per_lot.append(_line("material", "material certifications (mill certs)", 35.0, basis="per_lot"))

    thickness = _num(stock.get("dims") or {}, "thickness", 0.125) or 0.125
    lead_extra_days = 0

    # ---------------- operations
    if not ops:
        warnings.append("No operations listed: estimate covers material, finishing and packaging only.")
    for i, op in enumerate(ops):
        t = op.get("type")
        if t not in OPERATION_TYPES:
            raise SpecError(f"operations[{i}].type '{t}' is not one of {list(OPERATION_TYPES)}")
        op_tol = cfg["tolerance_multiplier"].get(op.get("tolerance", tol), tol_mult)

        if t in ("cnc_mill", "cnc_lathe"):
            setups = max(1, int(_num(op, "setups", 1)))
            prog = cfg["programming_hours_per_setup"][t] * setups * op_tol
            per_lot.append(_line("programming", f"{t} CAM programming, {setups} setup(s)", prog * rates["programming"], basis="per_lot", hours=prog, rate=rates["programming"]))
            su = cfg["setup_hours"][t] * setups
            per_lot.append(_line("setup", f"{t} setup, {setups} setup(s)", su * rates[t], basis="per_lot", hours=su, rate=rates[t]))
            if op.get("cycle_minutes") is not None:
                minutes = _num(op, "cycle_minutes")
                note = "cycle time given"
            else:
                f = op.get("features") or {}
                m = cfg["mill_minutes"] if t == "cnc_mill" else cfg["lathe_minutes"]
                if t == "cnc_mill":
                    raw = (m["base"] + _num(f, "holes") * m["per_hole"] + _num(f, "tapped_holes") * m["per_tapped_hole"]
                           + _num(f, "pockets") * m["per_pocket"] + _num(f, "profile_in") * m["per_inch_profile"]
                           + _num(f, "volume_removed_in3") * m["per_cubic_inch_removed"] + _num(f, "faces") * m.get("per_face", 0))
                else:
                    raw = (m["base"] + _num(f, "diameters") * m["per_diameter"] + _num(f, "threads") * m["per_thread"]
                           + _num(f, "grooves") * m["per_groove"] + _num(f, "cross_holes") * m["per_cross_hole"])
                minutes = raw * mat["machinability"] * op_tol
                note = f"feature model x{mat['machinability']} machinability x{op_tol} tolerance"
                assumptions.append(f"{t} cycle time estimated from features ({minutes:.1f} min/part); replace with your CAM time when known.")
            minutes += cfg["handling_minutes"] * setups
            h = minutes / 60
            per_part.append(_line("machining", f"{t} run time", h * rates[t], hours=h, rate=rates[t], note=note))

        elif t == "manual_machining":
            setups = max(1, int(_num(op, "setups", 1)))
            su = cfg["setup_hours"][t] * setups
            per_lot.append(_line("setup", "manual machining setup", su * rates[t], basis="per_lot", hours=su, rate=rates[t]))
            h = _num(op, "minutes_per_part") / 60
            per_part.append(_line("machining", "manual machining", h * rates[t], hours=h, rate=rates[t]))

        elif t in ("laser_cut", "waterjet"):
            prog = cfg["programming_hours_per_setup"][t]
            per_lot.append(_line("programming", f"{t} nesting/program", prog * rates["programming"], basis="per_lot", hours=prog, rate=rates["programming"]))
            su = cfg["setup_hours"][t]
            per_lot.append(_line("setup", f"{t} setup", su * rates[t], basis="per_lot", hours=su, rate=rates[t]))
            base_ipm = cfg["laser_ipm_at_0125"] if t == "laser_cut" else cfg["waterjet_ipm_at_0125"]
            ipm = base_ipm * (0.125 / thickness) ** 0.8 / mat["cut_factor"]
            if t == "laser_cut" and thickness > 0.75:
                warnings.append(f"Laser cutting {thickness} in plate: confirm your laser's capacity or use waterjet.")
            minutes = _num(op, "cut_length_in") / max(ipm, 0.1) + _num(op, "pierces") * cfg["pierce_minutes"] + cfg["handling_minutes"]
            h = minutes / 60
            per_part.append(_line("cutting", f"{t} at {ipm:.0f} in/min", h * rates[t], hours=h, rate=rates[t], note=f"{_num(op, 'cut_length_in'):.0f} in of cut"))

        elif t == "press_brake":
            bends = int(_num(op, "bends"))
            su = cfg["setup_hours"][t]
            per_lot.append(_line("setup", "press brake tooling setup", su * rates[t], basis="per_lot", hours=su, rate=rates[t]))
            minutes = bends * cfg["brake_minutes_per_bend"] * op_tol + cfg["handling_minutes"]
            h = minutes / 60
            per_part.append(_line("forming", f"press brake, {bends} bend(s)", h * rates[t], hours=h, rate=rates[t]))

        elif t == "weld":
            proc = (op.get("process") or "mig").lower()
            if proc not in cfg["weld_ipm"]:
                raise SpecError(f"weld process must be one of {list(cfg['weld_ipm'])}")
            rate = rates[f"weld_{proc}"]
            if op.get("fixture", True):
                su = cfg["setup_hours"]["weld_fixture"]
                per_lot.append(_line("setup", "weld fixture build/setup", su * rate, basis="per_lot", hours=su, rate=rate))
            minutes = (_num(op, "weld_length_in") / cfg["weld_ipm"][proc] + _num(op, "joints") * cfg["weld_fitup_minutes_per_joint"]) * op_tol + cfg["handling_minutes"]
            h = minutes / 60
            per_part.append(_line("welding", f"{proc.upper()} weld, {_num(op, 'weld_length_in'):.0f} in, {int(_num(op, 'joints'))} joint(s)", h * rate, hours=h, rate=rate))
            if op.get("certified_welder"):
                warnings.append("Certified welding (for example AWS D1.1 or D17.1) is required: confirm a qualified welder and procedure.")

        elif t == "additive":
            tech_name = (op.get("technology") or add_cfg["materials"][mat_name]["tech"]).lower()
            tech = add_cfg["technologies"].get(tech_name)
            if tech is None:
                raise SpecError(f"technology must be one of {list(add_cfg['technologies'])}")
            if add_cfg["materials"][mat_name]["tech"] != tech_name:
                raise SpecError(f"'{mat_name}' is a {add_cfg['materials'][mat_name]['tech'].upper()} material, not {tech_name.upper()}")
            cm3 = vol * 16.387
            bbox = [float(x) for x in (op.get("bbox_in") or [0, 0, 0])][:3]
            infill = min(max(_num(op, "infill", 1.0 if tech_name != "fdm" else 0.4), 0.1), 1.0)
            if tech_name == "fdm":
                printed = cm3 * (0.35 + 0.65 * infill)  # walls and skins are solid, the core is infill
                fill_note = f"{infill:.0%} infill"
            else:
                printed = cm3
                fill_note = "solid"
            support = tech["support_factor"] if op.get("support", True) else 0.0
            printed *= 1 + support
            per_part.append(_line("material", f"{mat_name}, {printed:.1f} cm³ printed", printed * add_cfg["materials"][mat_name]["price_per_cm3"],
                                  rate=add_cfg["materials"][mat_name]["price_per_cm3"], note=f"{cm3:.1f} cm³ part, {fill_note}, {support:.0%} support"))
            hours = printed / tech["cm3_per_hour"] + (bbox[2] if len(bbox) == 3 else 0) * tech["minutes_per_inch_height"] / 60
            per_part.append(_line("printing", f"{tech['label']} printer time", hours * tech["machine_rate"], hours=hours, rate=tech["machine_rate"],
                                  note="nested in a shared build" if tech["packs_build"] else "includes layer time for part height"))
            post = tech["post_minutes"] * op_tol / 60
            per_part.append(_line("labor", "remove supports / depowder / cure", post * rates["print_labor"], hours=post, rate=rates["print_labor"]))
            su = tech["setup_minutes"] / 60
            per_lot.append(_line("setup", f"{tech_name.upper()} build prep and slicing", su * rates["print_labor"], basis="per_lot", hours=su, rate=rates["print_labor"]))
            if len(bbox) == 3 and any(b > 0 for b in bbox):
                if any(b > m for b, m in zip(sorted(bbox, reverse=True), sorted(tech["max_in"], reverse=True))):
                    warnings.append(f"Part ({' x '.join(f'{b:.1f}' for b in bbox)} in) may not fit the {tech_name.upper()} build volume "
                                    f"({' x '.join(str(m) for m in tech['max_in'])} in). Split it or use a bigger machine.")
            assumptions.append(f"3D print time from volume at {tech['cm3_per_hour']} cm³/h; check against your slicer estimate.")

        elif t == "hardware_insert":
            n = _num(op, "count")
            per_part.append(_line("hardware", f"{int(n)} hardware item(s)", n * _num(op, "unit_cost"), note="purchased hardware"))
            h = n * _num(op, "minutes_each", 0.5) / 60
            per_part.append(_line("hardware", "install hardware", h * rates["fabrication"], hours=h, rate=rates["fabrication"]))

        else:  # assembly, deburr, fabrication
            rate = rates[t]
            h = _num(op, "minutes_per_part") / 60
            per_part.append(_line("labor", t, h * rate, hours=h, rate=rate))

    if not any(o.get("type") == "deburr" for o in ops) and ops and not additive_ops:
        h = 2 / 60
        per_part.append(_line("labor", "deburr (default 2 min)", h * rates["deburr"], hours=h, rate=rates["deburr"]))
        assumptions.append("Added 2 minutes of deburr per part; add a deburr operation to override.")

    # ---------------- finishing (outside service)
    finish_lot_mins: list[tuple[str, float, float]] = []
    for f in spec.get("finishes") or []:
        name = f.get("type") if isinstance(f, dict) else f
        afin = add_cfg["finishes"].get(name)
        if afin is not None:  # in-house post-processing for printed parts
            h = afin["minutes"] / 60
            per_part.append(_line("finishing", name, h * rates["print_labor"] + afin["per_part"], hours=h, rate=rates["print_labor"],
                                  note=f"plus ${afin['per_part']:.2f} consumables" if afin["per_part"] else ""))
            continue
        fin = cfg["finishes"].get(name)
        if fin is None:
            raise SpecError(f"Unknown finish '{name}'. Known: {sorted(cfg['finishes']) + sorted(add_cfg['finishes'])}")
        pp = _num(f, "per_part", fin["per_part"]) if isinstance(f, dict) else fin["per_part"]
        lm = _num(f, "lot_min", fin["lot_min"]) if isinstance(f, dict) else fin["lot_min"]
        finish_lot_mins.append((name, pp, lm))
        lead_extra_days += fin.get("lead_days", 7)

    # ---------------- inspection
    insp = spec.get("inspection") or {}
    ins = cfg["inspection"]
    if insp.get("first_article"):
        h = ins["first_article_hours"]
        per_lot.append(_line("inspection", "first article inspection and report", h * rates["inspection"], basis="per_lot", hours=h, rate=rates["inspection"]))
        lead_extra_days += cfg["lead_time"]["first_article_days"]
        warnings.append("First article required: the government must approve it before production ships. Allow for that in delivery days.")
    h = _num(insp, "minutes_per_part", ins["per_part_minutes"]) / 60
    per_part.append(_line("inspection", "in-process and final inspection", h * rates["inspection"], hours=h, rate=rates["inspection"]))
    if insp.get("certificate_of_conformance", True):
        per_lot.append(_line("inspection", "certificate of conformance", ins["cert_per_lot"], basis="per_lot"))

    # ---------------- packaging and freight
    pk_level = (spec.get("packaging") or {}).get("level", "commercial")
    pk = cfg["packaging"].get(pk_level)
    if pk is None:
        raise SpecError(f"packaging.level must be one of {list(cfg['packaging'])}")
    per_part.append(_line("packaging", f"{pk_level} packaging", pk["per_part"]))
    if pk["per_lot"]:
        per_lot.append(_line("packaging", f"{pk_level} lot labels and marking", pk["per_lot"], basis="per_lot"))
    if pk_level == "mil_std_2073":
        assumptions.append("MIL-STD-2073 packaging priced as an average; check the RFQ's packaging codes.")
    freight = _num(spec, "freight_per_lot", cfg["default_freight_per_lot"])
    per_lot.append(_line("freight", "outbound freight", freight, basis="per_lot"))

    # ---------------- totals per quantity
    ga, profit = _num(spec, "ga_rate", cfg["ga_rate"]), _num(spec, "profit_rate", cfg["profit_rate"])
    part_cost = sum(l["cost"] for l in per_part)
    if additive_ops and part_cost < add_cfg["min_part_charge"]:
        per_part.append(_line("printing", "minimum part charge top-up", add_cfg["min_part_charge"] - part_cost))
        part_cost = add_cfg["min_part_charge"]
    lot_cost = sum(l["cost"] for l in per_lot)
    ref = spec.get("reference_unit_price")
    breaks = []
    for q in qtys:
        fin_lot = sum(max(pp * q, lm) for _, pp, lm in finish_lot_mins)
        cost = part_cost * q + lot_cost + fin_lot
        price = cost * (1 + ga) * (1 + profit)
        price = max(price, add_cfg["min_lot_charge"] if additive_ops else cfg["min_lot_charge"])
        days = cfg["lead_time"]["base_days"] + lead_extra_days + math.ceil(q / max(cfg["lead_time"]["parts_per_day"], 1))
        row = {
            "quantity": q,
            "total_cost": round(cost, 2),
            "unit_cost": round(cost / q, 2),
            "unit_price": round(price / q, 2),
            "total_price": round(price, 2),
            "margin_pct": round((price - cost) / price * 100, 1) if price else 0.0,
            "lead_time_days": days,
        }
        if ref is not None:
            r = float(ref)
            row["vs_reference_pct"] = round((row["unit_price"] - r) / r * 100, 1) if r else None
            if row["unit_cost"] > r:
                row["reference_note"] = "Your cost is above the reference price: you cannot match it at a profit."
            elif row["unit_price"] > r:
                row["reference_note"] = f"Price is above the reference; lowest price at break-even is ${row['unit_cost']:.2f}."
            else:
                row["reference_note"] = "Price is at or below the reference."
        breaks.append(row)
    if finish_lot_mins:
        per_lot.append(_line("finishing", ", ".join(n for n, _, _ in finish_lot_mins),
                             sum(max(pp * qtys[0], lm) for _, pp, lm in finish_lot_mins), basis=f"per_lot at qty {qtys[0]}",
                             note="outside service; per part or lot minimum, whichever is more"))
    if ref is not None and breaks and all(b["unit_cost"] > float(ref) for b in breaks):
        warnings.append("At every quantity your cost exceeds the reference price. Recheck rates or pass on this one.")
    if spec.get("approved_source_required", True):
        warnings.append("Most NSN parts are restricted to approved sources: making it to the drawing usually needs a Source Approval Request first, unless the RFQ allows new sources.")

    return {
        "part": {k: spec.get(k) for k in ("name", "part_number", "nsn", "drawing", "revision") if spec.get(k)},
        "material": mat_name,
        "stock_volume_in3": round(vol, 3),
        "part_weight_lb": round(weight, 3),
        "per_part_lines": per_part,
        "per_lot_lines": per_lot,
        "per_part_cost": round(part_cost, 2),
        "per_lot_cost": round(lot_cost, 2),
        "ga_rate": ga,
        "profit_rate": profit,
        "price_breaks": breaks,
        "assumptions": assumptions,
        "warnings": warnings,
        "config_note": cfg.get("note", ""),
    }


EXAMPLE_SPEC = {
    "name": "Mounting bracket",
    "part_number": "12345-001",
    "nsn": "5340-01-000-0000",
    "quantities": [10, 50, 100],
    "material": "6061-T6 aluminum",
    "stock": {"shape": "plate", "dims": {"length": 4.0, "width": 3.0, "thickness": 0.5}},
    "tolerance": "standard",
    "operations": [
        {"type": "cnc_mill", "setups": 2, "features": {"holes": 4, "tapped_holes": 2, "pockets": 1, "profile_in": 14}},
    ],
    "finishes": [{"type": "anodize (Type II)"}],
    "inspection": {"first_article": False},
    "packaging": {"level": "mil_std_2073"},
    "reference_unit_price": 48.00,
}
