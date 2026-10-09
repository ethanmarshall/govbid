"""Box builds: custom electromechanical assemblies priced as one unit.

A box build is an enclosure with everything that goes in or on it:
  enclosure    catalog box (priced by type and size), a linked custom quote (sheet metal, machined, printed),
               customer furnished, or none; plus modifications (holes, cutouts, windows, vents, PEMs,
               gaskets), finish and silkscreen
  pcbs         printed circuit board assemblies: estimated (bare board fab + SMT/THT assembly + parts +
               coating, programming and test) or bought from a contract manufacturer at their price breaks
  lines        switches, connectors, indicators, displays, power supplies, fans and other parts, each with
               mounting minutes and wire terminations by type
  peripherals  purchased items installed in the unit or packed with it (computers, cameras, cables, manuals)
  wiring       point-to-point wires (counted, or estimated from the terminations), plus mated cables
  children     any saved quote (harness, panel, labels, machined or sheet metal part, DXF part, extrusion
               frame, STEP assembly, another box build) at a quantity per unit, made at its cost or bought
  labor        integration, fasteners, grounding, firmware, functional and safety test, burn-in, ESS,
               outside lab tests, NRE (work instructions, test procedure, fixtures) and first article

Cost model, per quantity q (the number of assemblies):
  cost(q)  = per-unit lines x q + per-lot lines
  price(q) = cost(q) x (1 + G&A) x (1 + profit), at least the minimum lot charge
Linked quotes are priced with their own model at (qty per unit x q) and rolled in at COST (their G&A
and profit are left out, as are their freight, packaging and CoC lines), so markup is applied once.
Quantity matters inside a lot (PCB lot minimums, tooling, a CM's price breaks), so every price break is
built on its own and the breakdown is kept for each one.

Every rate and price in config "box_build" is a placeholder until you enter your own.
"""
from __future__ import annotations

import copy
import math
import re
from collections import Counter
from pathlib import Path

from . import pricing
from .box_build_catalog import COMPONENT_TYPES, PLACEHOLDER, TERMINATION_METHODS, default_config  # noqa: F401

EXCLUDE_CHILD = ("freight", "packaging")  # charged once on the box build, not on each linked quote
MAX_DEPTH = 3

COMPONENT_PATTERNS = [  # checked in order against "type hint, description, part number"
    ("terminal_block", r"TERMINAL\s*(?:BLOCK|STRIP)|BARRIER\s*STRIP"),
    ("hardware", r"\bSCREW|\bNUT\b|\bNUTS\b|WASHER|STANDOFF|SPACER|\bRIVET|\bBOLT|LOCKWASHER|\bPEM\b|CAPTIVE|THREADED INSERT|GROMMET|CABLE TIE|ZIP TIE|HEAT ?SHRINK"),
    ("cable_assembly", r"CABLE ASS|CABLE,|\bCABLE\b|PATCH CORD|JUMPER CABLE|RIBBON|FFC\b|FPC\b"),
    ("circular_connector", r"D?38999|MIL-?DTL-?26482|MIL-?DTL-?5015|MS3\d{3}|MS27\d{3}|PT0\d|CIRCULAR|BAYONET"),
    ("dsub_connector", r"D-?SUB|\bD[ABCDE]-?\d{1,2}[PS]?\b|\bDB-?\d|MICRO-?D|M24308|M83513|HD-?15"),
    ("test_jack", r"TEST\s*JACK|BANANA|BINDING\s*POST|TIP\s*JACK|\b[24]\s*MM\s*(?:PANEL\s*)?JACK|PIN\s*JACK"),
    ("panel_port", r"\bUSB\b|RJ-?45|ETHERNET JACK|\bBNC\b|\bSMA\b|N-?TYPE|\bTNC\b|FEED-?THRU|FEEDTHROUGH|BULKHEAD|HDMI|DISPLAYPORT"),
    ("power_entry", r"POWER ENTRY|IEC|\bINLET\b|C14|C20|POWER INLET|EMI FILTER|LINE FILTER"),
    ("terminal_block", r"TERMINAL (?:BLOCK|STRIP)|TERM(?:INAL)? BLK|BARRIER STRIP|\bTB\b"),
    ("keyswitch", r"KEY ?SWITCH|KEYLOCK|KEY LOCK"),
    ("rotary_switch", r"ROTARY SW|SELECTOR"),
    ("toggle_switch", r"TOGGLE"),
    ("rocker_switch", r"ROCKER"),
    ("pushbutton", r"PUSH ?-?BUTTON|\bPB\b|MOMENTARY|TACTILE|E-?STOP|EMERGENCY STOP"),
    ("circuit_breaker", r"BREAKER|CIRCUIT PROTECTOR|SUPPLEMENTARY PROTECTOR"),
    ("fuse_holder", r"FUSE ?HOLDER|FUSEHOLDER|\bFUSE\b"),
    ("display", r"\bLCD\b|\bTFT\b|OLED|DISPLAY|TOUCH ?SCREEN|\bHMI\b|MONITOR PANEL|VFD MODULE"),
    ("led_indicator", r"\bLED\b|LIGHT PIPE"),
    ("panel_lamp", r"LAMP|INDICATOR LIGHT|PILOT LIGHT|INDICATOR"),
    ("knob", r"\bKNOB"),
    ("potentiometer", r"POTENTIOMETER|\bPOT\b|ENCODER|RHEOSTAT"),
    ("fan", r"\bFAN\b|BLOWER|FAN GUARD|FAN FILTER"),
    ("power_supply", r"POWER SUPPLY|\bPSU\b|DC-?DC|AC-?DC|CONVERTER|\bSMPS\b|TRANSFORMER"),
    ("relay", r"RELAY|CONTACTOR|\bSSR\b"),
    ("meter", r"\bMETER\b|VOLTMETER|AMMETER|PANEL METER|HOUR METER"),
    ("buzzer", r"BUZZER|BEEPER|SPEAKER|ANNUNCIATOR|SOUNDER"),
    ("battery", r"BATTERY|CELL HOLDER"),
    ("sensor", r"SENSOR|THERMOCOUPLE|\bRTD\b|TRANSDUCER|THERMISTOR|ACCELEROMETER|PRESSURE"),
    ("computer_module", r"RASPBERRY|SINGLE ?-?BOARD|\bSBC\b|COMPUTE MODULE|ARDUINO|BEAGLE|JETSON|\bNUC\b|SOM\b|SYSTEM ON MODULE"),
    ("heatsink", r"HEAT ?SINK"),
    ("circular_connector", r"CONNECTOR,? CIRC"),
    ("dsub_connector", r"\bCONNECTOR|\bCONN\b|\bPLUG\b|\bRECEPTACLE|\bJACK\b|HEADER"),
]
ENCLOSURE_RX = r"ENCLOSURE|CHASSIS|HOUSING|\bCASE\b|\bBOX\b|CABINET|\bRACK ?MOUNT|\bTRANSIT CASE"
PCB_RX = r"\bPCBA?\b|\bPWB\b|\bPWA\b|\bCCA\b|CIRCUIT CARD|PRINTED (?:CIRCUIT|WIRING) (?:BOARD|ASSEMBLY)|\bBOARD ASS|\bPC BOARD"
PERIPHERAL_RX = (r"KEYBOARD|\bMOUSE\b|\bMONITOR\b|CAMERA|ANTENNA|POWER ADAPTER|AC ADAPTER|\bADAPTER\b|CHARGER|MANUAL|POWER CORD|LINE CORD|"
                 r"HEADSET|PRINTER|SCANNER|TABLET|LAPTOP|ROUTER|NETWORK SWITCH|ETHERNET SWITCH|\bHUB\b|FLASH DRIVE|SD CARD|SOFTWARE|LICENSE|CARRY(?:ING)? CASE")

ENCLOSURE_FINISH_KEYS = ("none", "powder_coat", "paint", "anodize", "chem_film")


class BoxBuildError(ValueError):
    pass


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _opt(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _line(category: str, item: str, cost: float, *, basis: str = "per_unit", hours: float | None = None, rate: float | None = None,
          note: str = "", section: str = "") -> dict:
    return {"category": category, "section": section or category, "item": item, "basis": basis, "cost": round(cost, 2),
            "hours": None if hours is None else round(hours, 3), "rate": rate, "note": note}


def _qtys(q) -> list[int]:
    out = sorted({int(x) for x in (q or []) if str(x).strip() not in ("", "0") and _f(x) >= 1})
    if not out:
        raise BoxBuildError("Enter at least one quantity of 1 or more.")
    if len(out) > 12:
        raise BoxBuildError("Use 12 quantities or fewer.")
    return out


def classify_component(part: str, desc: str, hint: str = "") -> str:
    h = re.sub(r"[\s/-]+", "_", (hint or "").strip().lower())
    if h in COMPONENT_TYPES:
        return h
    t = f"{hint} {desc} {part}".upper()
    for k, pat in COMPONENT_PATTERNS:
        if re.search(pat, t):
            return k
    return "other"


# ================================================================ normalize
def blank_line(**kw) -> dict:
    ln = {"ref": "", "type": "", "part_number": "", "manufacturer": "", "description": "", "qty": 1, "unit_price": None,
          "price_source": "", "distributor": "", "terminations": None, "method": "", "mount": "panel", "customer_furnished": False, "notes": ""}
    ln.update({k: v for k, v in kw.items() if k in ln})
    return ln


def blank_peripheral(**kw) -> dict:
    p = {"description": "", "part_number": "", "manufacturer": "", "qty": 1, "unit_price": None, "price_source": "", "distributor": "",
         "installed": True, "minutes": None, "customer_furnished": False}
    p.update({k: v for k, v in kw.items() if k in p})
    return p


def blank_pcb(**kw) -> dict:
    b = {"name": "PCB assembly", "qty_per": 1, "mode": "estimate", "layers": 2, "width_in": None, "height_in": None, "thickness_in": 0.062,
         "finish": "HASL lead-free", "copper_oz": 1, "ipc_class": 2, "impedance": False, "via_in_pad": False, "blind_buried": False,
         "fab_price_each": None, "smt_placements": 0, "smt_unique": 0, "fine_pitch": 0, "bga": 0, "tht_parts": 0, "tht_joints": 0,
         "sides": 1, "aoi": True, "conformal": False, "conformal_masks": 0, "flying_probe": False, "program_minutes": 0, "test_minutes": 0,
         "bom_lines": [], "bom_cost_each": None, "consigned": False, "buy_prices": [], "buy_nre": 0, "buy_lead_days": None,
         "cable_mates": 0, "wire_connections": 0, "source": {}}
    b.update({k: v for k, v in kw.items() if k in b})
    return b


def normalize_lines(lines: list[dict]) -> list[dict]:
    out = []
    for ln in lines or []:
        ln = blank_line(**(ln or {}))
        if ln["type"] not in COMPONENT_TYPES:
            ln["type"] = classify_component(ln["part_number"], ln["description"], ln["type"])
        ln["qty"] = max(_f(ln["qty"], 0), 0)
        ln["unit_price"] = _opt(ln["unit_price"])
        ln["terminations"] = _opt(ln["terminations"])
        if ln["method"] not in TERMINATION_METHODS:
            ln["method"] = ""
        ln["customer_furnished"] = bool(ln["customer_furnished"])
        out.append(ln)
    return out


def normalize_peripherals(items: list[dict]) -> list[dict]:
    out = []
    for p in items or []:
        p = blank_peripheral(**(p or {}))
        p["qty"] = max(_f(p["qty"], 0), 0)
        p["unit_price"] = _opt(p["unit_price"])
        p["minutes"] = _opt(p["minutes"])
        p["installed"], p["customer_furnished"] = bool(p["installed"]), bool(p["customer_furnished"])
        out.append(p)
    return out


def normalize_pcbs(boards: list[dict]) -> list[dict]:
    out = []
    for b in boards or []:
        b = blank_pcb(**(b or {}))
        if b["mode"] not in ("estimate", "buy", "customer"):
            b["mode"] = "estimate"
        for k in ("qty_per", "smt_placements", "smt_unique", "fine_pitch", "bga", "tht_parts", "tht_joints", "conformal_masks",
                  "program_minutes", "test_minutes", "buy_nre", "cable_mates", "wire_connections"):
            b[k] = max(_f(b[k], 0), 0)
        b["qty_per"] = b["qty_per"] or 1
        b["layers"] = int(_f(b["layers"], 2)) or 2
        b["sides"] = 2 if int(_f(b["sides"], 1)) >= 2 else 1
        b["ipc_class"] = 3 if int(_f(b["ipc_class"], 2)) >= 3 else (1 if int(_f(b["ipc_class"], 2)) == 1 else 2)
        b["copper_oz"] = int(_f(b["copper_oz"], 1)) or 1
        b["thickness_in"] = _f(b["thickness_in"], 0.062) or 0.062
        for k in ("width_in", "height_in", "fab_price_each", "bom_cost_each", "buy_lead_days"):
            b[k] = _opt(b[k])
        for k in ("impedance", "via_in_pad", "blind_buried", "aoi", "conformal", "flying_probe", "consigned"):
            b[k] = bool(b[k])
        b["bom_lines"] = [{"ref": str(x.get("ref") or ""), "mpn": str(x.get("mpn") or ""), "manufacturer": str(x.get("manufacturer") or ""),
                           "description": str(x.get("description") or ""), "qty": max(_f(x.get("qty"), 1), 0), "tht": bool(x.get("tht")),
                           "unit_price": _opt(x.get("unit_price")), "price_source": x.get("price_source") or "", "distributor": x.get("distributor") or ""}
                          for x in (b["bom_lines"] or []) if isinstance(x, dict)]
        b["buy_prices"] = sorted([{"quantity": int(_f(x.get("quantity"))), "unit_price": _f(x.get("unit_price"))}
                                  for x in (b["buy_prices"] or []) if isinstance(x, dict) and _f(x.get("quantity")) >= 1 and _f(x.get("unit_price")) > 0],
                                 key=lambda x: x["quantity"])
        out.append(b)
    return out


def normalize_children(children: list[dict]) -> list[dict]:
    out = []
    for c in children or []:
        if not isinstance(c, dict) or not isinstance(c.get("spec"), dict):
            continue
        out.append({"quote_id": c.get("quote_id"), "name": c.get("name") or c["spec"].get("name") or "Linked quote",
                    "kind": c["spec"].get("kind") or c.get("kind") or "part", "qty_per": max(_f(c.get("qty_per"), 1), 0) or 1,
                    "mode": "buy" if c.get("mode") == "buy" else "make", "buy_unit_price": _opt(c.get("buy_unit_price")),
                    "buy_lead_days": _opt(c.get("buy_lead_days")), "section": c.get("section") or "", "spec": c["spec"]})
    return out


def normalize_enclosure(e: dict | None) -> dict:
    e = dict(e or {})
    out = {"source": e.get("source") if e.get("source") in ("catalog", "custom", "customer", "none") else "catalog",
           "type": e.get("type") or "diecast_aluminum", "length_in": _opt(e.get("length_in")), "width_in": _opt(e.get("width_in")),
           "height_in": _opt(e.get("height_in")), "unit_price": _opt(e.get("unit_price")), "part_number": e.get("part_number") or "",
           "manufacturer": e.get("manufacturer") or "", "description": e.get("description") or "", "price_source": e.get("price_source") or "",
           "distributor": e.get("distributor") or "", "finish": e.get("finish") if e.get("finish") in ENCLOSURE_FINISH_KEYS else "none",
           "silkscreen_colors": int(_f(e.get("silkscreen_colors"), 0)), "silkscreen_sides": int(_f(e.get("silkscreen_sides"), 1)) or 1,
           "child": None}
    mods = e.get("mods") or {}
    out["mods"] = {k: max(_f(mods.get(k), 0), 0) for k in ("round_holes", "rect_cutouts", "connector_cutouts", "display_windows", "vent_patterns", "pem_inserts")}
    out["mods"]["gasket"] = bool(mods.get("gasket"))
    out["mods"]["emi_gasket"] = bool(mods.get("emi_gasket"))
    out["mods"]["auto_cutouts"] = mods.get("auto_cutouts", True) is not False
    ch = e.get("child")
    if isinstance(ch, dict) and isinstance(ch.get("spec"), dict):
        out["child"] = normalize_children([{**ch, "qty_per": 1}])[0]
    return out


# ================================================================ linked quotes
def child_costs(child: dict, qtys: list[int], overrides: dict | None, depth: int) -> dict:
    """{q: {"cost": cost for q assemblies, "lead": days, "unit": per-item cost}} for a linked quote made at its own cost."""
    from .quotes import price_spec

    if depth >= MAX_DEPTH:
        raise BoxBuildError(f"Linked quotes are nested more than {MAX_DEPTH} deep.")
    need = {q: max(1, math.ceil(child["qty_per"] * q)) for q in qtys}
    spec = copy.deepcopy(child["spec"])
    spec["quantities"] = sorted(set(need.values()))
    if spec.get("kind") == "box_build":
        spec["_depth"] = depth + 1
    try:
        r = price_spec(spec, overrides)
    except (pricing.SpecError, ValueError) as exc:
        raise BoxBuildError(f"Linked quote '{child['name']}' could not be priced: {exc}") from exc
    ex_unit = sum(l["cost"] for l in r.get("per_part_lines") or [] if l.get("category") in EXCLUDE_CHILD)
    ex_lot = sum(l["cost"] for l in r.get("per_lot_lines") or [] if l.get("category") in EXCLUDE_CHILD
                 or str(l.get("item", "")).startswith("certificate of conformance"))
    by_q = {b["quantity"]: b for b in r["price_breaks"]}
    out = {}
    for q, n in need.items():
        b = by_q.get(n)
        if not b:
            raise BoxBuildError(f"Linked quote '{child['name']}' did not return a price for {n}.")
        cost = max(b["total_cost"] - ex_unit * n - ex_lot, 0.0)
        out[q] = {"cost": cost, "lead": b.get("lead_time_days") or 0, "unit": cost / n, "need": n}
    return out


# ================================================================ PCB
def _fab_each(b: dict, f: dict) -> tuple[float, list[str]]:
    """Bare board fab cost per board (no lot charges) and the factors applied."""
    area = (b["width_in"] or 0) * (b["height_in"] or 0)
    keys = sorted(int(k) for k in f["per_sqin"])
    layer_key = str(next((k for k in keys if k >= b["layers"]), keys[-1]))
    rate = f["per_sqin"][layer_key] * (1 + f["panel_waste"])
    factors = []
    mult = f["finish_factor"].get(b["finish"], 1.0)
    if mult != 1.0:
        factors.append(f"{b['finish']} x{mult:g}")
    cu = f["copper_factor"].get(str(b["copper_oz"]), 1.0)
    if cu != 1.0:
        factors.append(f"{b['copper_oz']} oz copper x{cu:g}")
    mult *= cu
    for flag, key, label in (("ipc_class3", "class3_factor", "IPC-6012 Class 3"), ("impedance", "impedance_factor", "controlled impedance"),
                             ("via_in_pad", "via_in_pad_factor", "via in pad"), ("blind_buried", "blind_buried_factor", "blind / buried vias")):
        on = b["ipc_class"] == 3 if flag == "ipc_class3" else b[flag]
        if on:
            mult *= f[key]
            factors.append(f"{label} x{f[key]:g}")
    if abs(b["thickness_in"] - 0.062) > 0.004:
        mult *= f["nonstandard_thickness_factor"]
        factors.append(f"{b['thickness_in']:g} in thick x{f['nonstandard_thickness_factor']:g}")
    return area * rate * mult + f["etest_each"], factors


def _bom_each(b: dict, a: dict) -> tuple[float, int, str]:
    """Parts cost per board, placeholder-priced line count, basis text."""
    if b["consigned"]:
        return 0.0, 0, "parts furnished by the customer (consigned)"
    if b["bom_lines"]:
        cost, ph = 0.0, 0
        for x in b["bom_lines"]:
            if x["unit_price"] is None:
                ph += 1
                cost += x["qty"] * (a["placeholder_per_tht"] if x["tht"] else a["placeholder_per_smt"])
            else:
                cost += x["qty"] * x["unit_price"]
        return cost * (1 + a["attrition"]), ph, f"{len(b['bom_lines'])} BOM lines + {a['attrition']:.0%} attrition"
    if b["bom_cost_each"] is not None:
        return b["bom_cost_each"] * (1 + a["attrition"]), 0, f"BOM cost entered + {a['attrition']:.0%} attrition"
    guess = b["smt_placements"] * a["placeholder_per_smt"] + b["tht_parts"] * a["placeholder_per_tht"]
    return guess, -1, "PLACEHOLDER: no BOM, so parts are guessed per placement"


def pcb_lines(b: dict, cfg: dict, boards: int, unit_count: int) -> tuple[list[dict], list[dict], int, list[str]]:
    """Per-assembly and per-lot lines for one board design at `boards` total boards (qty_per x assemblies)."""
    f, a = cfg["pcb_fab"], cfg["pcba"]
    per: list[dict] = []
    lot: list[dict] = []
    warn: list[str] = []
    name = b["name"] or "PCB assembly"
    n = b["qty_per"]
    sec = "pcbs"
    if b["mode"] == "customer":
        per.append(_line("pcb", f"{name}: customer furnished, {n:g} per unit", 0.0, section=sec, note="no cost; receiving inspection only"))
        return per, lot, 0, warn
    if b["mode"] == "buy":
        if not b["buy_prices"]:
            raise BoxBuildError(f"{name}: enter the contract manufacturer's price breaks or switch to estimate.")
        brk = [x for x in b["buy_prices"] if x["quantity"] <= boards]
        use = brk[-1] if brk else b["buy_prices"][0]
        if not brk:
            warn.append(f"{name}: {boards} boards is below the CM's lowest break ({use['quantity']}); their lowest-quantity price is used. Ask for a quote at {boards}.")
        per.append(_line("pcb", f"{name}: CM price {n:g} x ${use['unit_price']:,.2f} (break {use['quantity']})", n * use["unit_price"], section=sec,
                         rate=use["unit_price"], note="bought, turnkey"))
        if b["buy_nre"]:
            lot.append(_line("pcb", f"{name}: CM NRE (stencil, programming, fixtures)", b["buy_nre"], basis="per_lot", section=sec))
        return per, lot, int(b["buy_lead_days"] if b["buy_lead_days"] is not None else f["lead_days"] + a["lead_days"]), warn
    # ---- estimate
    if not (b["width_in"] and b["height_in"]) and b["fab_price_each"] is None:
        warn.append(f"{name}: no board size, so bare board fab is not priced. Add the Gerbers or enter the size.")
    cls3 = b["ipc_class"] == 3
    if b["fab_price_each"] is not None:
        fab_each, factors = b["fab_price_each"], ["your fab price"]
        tooling = 0.0
    else:
        fab_each, factors = _fab_each(b, f) if b["width_in"] and b["height_in"] else (0.0, [])
        keys = sorted(int(k) for k in f["tooling_per_lot"])
        tooling = f["tooling_per_lot"][str(next((k for k in keys if k >= b["layers"]), keys[-1]))] + (f["impedance_nre"] if b["impedance"] else 0.0)
    per.append(_line("pcb", f"{name}: bare board, {b['layers']} layer, {b['width_in'] or 0:g} x {b['height_in'] or 0:g} in, {n:g} per unit",
                     fab_each * n, section=sec, rate=round(fab_each, 3), note=", ".join(factors) or "standard build"))
    if tooling:
        lot.append(_line("pcb", f"{name}: fab tooling and setup", tooling, basis="per_lot", section=sec))
    if b["fab_price_each"] is None and fab_each:
        topup = f["lot_min"] - fab_each * boards
        if topup > 0:
            lot.append(_line("pcb", f"{name}: fab lot minimum top-up (${f['lot_min']:g} minimum)", topup, basis="per_lot", section=sec))
    parts_each, ph, basis = _bom_each(b, a)
    if ph == -1:
        warn.append(f"{name}: no BOM or BOM cost, so parts are a placeholder guess. Add the BOM.")
    elif ph:
        warn.append(f"{name}: {ph} BOM line(s) have no price and use a placeholder. Fetch live prices or enter them.")
    per.append(_line("pcb", f"{name}: components", parts_each * n, section=sec, note=basis))
    k3 = a["class3_factor"] if cls3 else 1.0
    smt_each = (b["smt_placements"] * a["smt_per_placement"] + b["fine_pitch"] * a["fine_pitch_each"] + b["bga"] * a["bga_each"]
                + (a["xray_per_board"] if b["bga"] else 0) + (a["aoi_per_board"] if b["aoi"] and b["smt_placements"] else 0)) * k3
    if smt_each:
        per.append(_line("pcb", f"{name}: SMT assembly ({b['smt_placements']:g} placements, {b['fine_pitch']:g} fine pitch, {b['bga']:g} BGA"
                         f"{', AOI' if b['aoi'] else ''}{', X-ray' if b['bga'] else ''})", smt_each * n, section=sec,
                         note="Class 3 factor" if cls3 else ""))
    tht_min = (b["tht_joints"] * a["tht_minutes_per_joint"] + b["tht_parts"] * a["tht_minutes_per_part"]) * k3
    if tht_min:
        per.append(_line("pcb", f"{name}: through-hole assembly ({b['tht_parts']:g} parts, {b['tht_joints']:g} joints)",
                         tht_min / 60 * a["hand_rate"] * n, section=sec, hours=tht_min / 60 * n, rate=a["hand_rate"]))
    if b["conformal"]:
        area = (b["width_in"] or 0) * (b["height_in"] or 0) * 2
        cm = a["conformal_minutes"] + b["conformal_masks"] * a["conformal_mask_minutes"]
        per.append(_line("pcb", f"{name}: conformal coat ({b['conformal_masks']:g} masked areas)", (cm / 60 * a["hand_rate"] + area * a["conformal_per_sqin"]) * n,
                         section=sec, hours=cm / 60 * n, rate=a["hand_rate"], note="IPC-CC-830 coating, both sides"))
    insp = a["inspection_minutes"] * k3
    per.append(_line("pcb", f"{name}: inspection", insp / 60 * cfg["test_rate"] * n, section=sec, hours=insp / 60 * n, rate=cfg["test_rate"]))
    if b["flying_probe"]:
        per.append(_line("pcb", f"{name}: flying probe test", a["flying_probe_each"] * n, section=sec))
        lot.append(_line("pcb", f"{name}: flying probe program", a["flying_probe_nre"], basis="per_lot", section=sec))
    if b["program_minutes"]:
        per.append(_line("test", f"{name}: program firmware ({b['program_minutes']:g} min)", b["program_minutes"] / 60 * cfg["test_rate"] * n, section=sec,
                         hours=b["program_minutes"] / 60 * n, rate=cfg["test_rate"]))
        lot.append(_line("test", f"{name}: programming setup", a["program_setup_minutes"] / 60 * cfg["test_rate"], basis="per_lot", section=sec,
                         hours=a["program_setup_minutes"] / 60, rate=cfg["test_rate"]))
    if b["test_minutes"]:
        per.append(_line("test", f"{name}: board functional test ({b['test_minutes']:g} min)", b["test_minutes"] / 60 * cfg["test_rate"] * n, section=sec,
                         hours=b["test_minutes"] / 60 * n, rate=cfg["test_rate"]))
        lot.append(_line("test", f"{name}: board test setup", a["test_setup_minutes"] / 60 * cfg["test_rate"], basis="per_lot", section=sec,
                         hours=a["test_setup_minutes"] / 60, rate=cfg["test_rate"]))
    if b["smt_placements"]:
        lot.append(_line("pcb", f"{name}: SMT setup and stencils ({b['sides']} side(s), {b['smt_unique']:g} unique parts)",
                         b["sides"] * (a["setup_per_side"] + a["stencil_per_side"]) + b["smt_unique"] * a["feeder_per_unique"], basis="per_lot", section=sec))
    lead = f["lead_days"] + (f["class3_lead_days"] if cls3 else 0) + a["lead_days"]
    return per, lot, int(lead), warn


# ================================================================ main estimate
def counts(spec: dict, cfg: dict) -> dict:
    """Terminations, mates, wires and fasteners, given or estimated, with the basis spelled out."""
    lines = normalize_lines(spec.get("lines"))
    pcbs = normalize_pcbs(spec.get("pcbs"))
    children = normalize_children(spec.get("children"))
    w = spec.get("wiring") or {}
    lab = spec.get("labor") or {}
    comp = cfg["components"]
    terms = Counter()
    mates = 0.0
    for ln in lines:
        c = comp.get(ln["type"], comp["other"])
        each = ln["terminations"] if ln["terminations"] is not None else c["terminations"]
        method = ln["method"] or COMPONENT_TYPES[ln["type"]][1]
        if method != "none" and each:
            terms[method] += each * ln["qty"]
        mates += c["mates"] * ln["qty"]
    mates += sum(b["cable_mates"] * b["qty_per"] for b in pcbs)
    harnesses = [c for c in children if c["kind"] == "harness"]
    mates += sum(2 * c["qty_per"] for c in harnesses)  # each linked harness plugs in at both ends (assumption)
    board_wires = sum(b["wire_connections"] * b["qty_per"] for b in pcbs)
    given = _opt(w.get("wires"))
    total_terms = sum(terms.values())
    if given is not None:
        wires, basis = int(given), "wire count given"
    elif harnesses:
        wires, basis = int(board_wires), "linked harness quotes carry the wiring; only PCB wire connections are added as loose wires"
    else:
        wires = math.ceil((total_terms + board_wires) / 2)
        basis = f"estimated: {total_terms:g} component terminations + {board_wires:g} PCB wire connections, / 2 (each wire has two ends)"
    if _opt(w.get("mates")) is not None:
        mates = _opt(w.get("mates"))
    enc = normalize_enclosure(spec.get("enclosure"))
    fasteners_given = _opt(lab.get("fasteners"))
    est_fast = (cfg["enclosure_mods"]["assembly_fasteners"] if enc["source"] != "none" else 0) + 4 * sum(b["qty_per"] for b in pcbs)
    return {"terminations": dict(terms), "termination_total": total_terms, "mates": mates, "wires": wires, "wire_basis": basis,
            "fasteners": fasteners_given if fasteners_given is not None else est_fast, "fasteners_estimated": fasteners_given is None,
            "ground_points": _f(lab.get("ground_points"), 2), "boards": sum(b["qty_per"] for b in pcbs)}


def _auto_cutouts(lines: list[dict]) -> dict:
    out = Counter()
    for ln in lines:
        if ln["mount"] != "panel":
            continue
        t = ln["type"]
        if t in ("toggle_switch", "pushbutton", "rotary_switch", "keyswitch", "led_indicator", "panel_lamp", "potentiometer", "fuse_holder", "buzzer", "test_jack"):
            out["round_holes"] += ln["qty"]
        elif t in ("circular_connector", "dsub_connector", "panel_port"):
            out["connector_cutouts"] += ln["qty"]
        elif t in ("rocker_switch", "power_entry", "circuit_breaker", "meter"):
            out["rect_cutouts"] += ln["qty"]
        elif t == "display":
            out["display_windows"] += ln["qty"]
        elif t == "fan":
            out["vent_patterns"] += ln["qty"]
    return dict(out)


def price(spec: dict, config: dict | None = None) -> dict:
    cfg_all = pricing.merged_config(config)
    cfg = cfg_all["box_build"]
    opts = dict(spec.get("options") or {})
    qtys = _qtys(spec.get("quantities") or [1, 5, 10])
    depth = int(_f(spec.get("_depth"), 0))
    enc = normalize_enclosure(spec.get("enclosure"))
    lines = normalize_lines(spec.get("lines"))
    periph = normalize_peripherals(spec.get("peripherals"))
    pcbs = normalize_pcbs(spec.get("pcbs"))
    children = normalize_children(spec.get("children"))
    lab = dict(spec.get("labor") or {})
    w = dict(spec.get("wiring") or {})
    if not (lines or periph or pcbs or children or enc["source"] in ("catalog", "custom")):
        raise BoxBuildError("Add an enclosure, a board, a component or a linked quote.")
    warnings: list[str] = []
    assumptions: list[str] = []
    rate, trate, erate = float(cfg["labor_rate"]), float(cfg["test_rate"]), float(cfg["engineering_rate"])
    cls3 = int(_f(lab.get("ipc_class"), 2)) >= 3
    kfac = cfg["class3_labor_factor"] if cls3 else 1.0
    c = counts(spec, cfg)
    comp = cfg["components"]

    # ---- fixed per-unit and per-lot lines (same at every quantity)
    per: list[dict] = []
    lot: list[dict] = []
    bought = 0.0  # per-unit bought material, for the burden line
    ph_count = 0
    lead_parts = 0
    # enclosure
    if enc["source"] == "catalog":
        et = cfg["enclosures"].get(enc["type"]) or next(iter(cfg["enclosures"].values()))
        vol = (enc["length_in"] or 0) * (enc["width_in"] or 0) * (enc["height_in"] or 0)
        if enc["unit_price"] is not None:
            ep = enc["unit_price"]
            note = f"live {enc['distributor']}".strip() if enc["price_source"] == "live" else "your price"
        else:
            ep, note = et["base"] + vol * et["per_in3"], "PLACEHOLDER price by type and size"
            ph_count += 1
            if not vol:
                warnings.append("Enclosure has no size, so its placeholder price is the base only. Enter the size or a price.")
        size = f", {enc['length_in']:g} x {enc['width_in'] or 0:g} x {enc['height_in'] or 0:g} in" if enc["length_in"] else ""
        pn = f", {enc['part_number']}" if enc["part_number"] else ""
        per.append(_line("enclosure", f"{et['label']}{pn}{size}", ep, note=note))
        bought += ep
        lead_parts = max(lead_parts, int(et["lead_days"]))
    elif enc["source"] == "custom" and not enc["child"]:
        warnings.append("Custom enclosure selected but no saved quote is linked. Link the enclosure's part quote.")
    elif enc["source"] == "customer":
        assumptions.append("The enclosure is customer furnished; only receiving and integration are priced.")
    mods = dict(enc["mods"])
    auto = _auto_cutouts(lines) if mods["auto_cutouts"] and enc["source"] == "catalog" else {}
    em = cfg["enclosure_mods"]
    mod_min = 0.0
    mod_text = []
    for k, key in (("round_holes", "round_hole_minutes"), ("rect_cutouts", "rect_cutout_minutes"), ("connector_cutouts", "connector_cutout_minutes"),
                   ("display_windows", "display_window_minutes"), ("vent_patterns", "vent_pattern_minutes")):
        n = mods[k] or auto.get(k, 0)
        if n:
            mod_min += n * em[key]
            mod_text.append(f"{n:g} {k.replace('_', ' ')}{' (from panel parts)' if not mods[k] else ''}")
    if mods["pem_inserts"]:
        mod_min += mods["pem_inserts"] * em["pem_minutes"]
        per.append(_line("enclosure", f"PEM inserts x {mods['pem_inserts']:g}", mods["pem_inserts"] * em["pem_each"]))
        mod_text.append(f"{mods['pem_inserts']:g} PEM inserts")
    for flag, each, mins, label in (("gasket", "gasket_each", "gasket_minutes", "environmental gasket"), ("emi_gasket", "emi_gasket_each", "emi_gasket_minutes", "EMI gasket")):
        if mods[flag]:
            per.append(_line("enclosure", label, em[each]))
            mod_min += em[mins]
            mod_text.append(label)
    if mod_min:
        per.append(_line("enclosure", f"enclosure modifications: {', '.join(mod_text)}", mod_min / 60 * rate * kfac, hours=mod_min / 60, rate=rate))
        lot.append(_line("enclosure", "cutout layout and setup", em["setup_minutes_per_lot"] / 60 * rate, basis="per_lot", hours=em["setup_minutes_per_lot"] / 60, rate=rate))
        if enc["source"] == "custom":
            warnings.append("Enclosure modifications are added on top of the linked custom enclosure. Leave them at zero if the model already has the holes.")
    fin = cfg["finishes"].get(enc["finish"]) if enc["finish"] != "none" else None
    if fin:
        per.append(_line("enclosure", f"{fin['label']} (outside service)", fin["per_unit"], note=f"lot minimum ${fin['lot_min']:g}"))
        if enc["source"] == "custom":
            warnings.append("A finish is selected and the enclosure is a linked quote: make sure that quote does not already include the finish.")
    ss = cfg["silkscreen"]
    if enc["silkscreen_colors"]:
        cs = enc["silkscreen_colors"] * enc["silkscreen_sides"]
        per.append(_line("enclosure", f"silkscreen legends, {enc['silkscreen_colors']} color(s) x {enc['silkscreen_sides']} side(s)",
                         cs * ss["per_color_side"] + cs * ss["minutes_per_color_side"] / 60 * rate, hours=cs * ss["minutes_per_color_side"] / 60, rate=rate))
        lot.append(_line("enclosure", "silkscreen screens and setup", cs * ss["setup_per_color_side"], basis="per_lot"))
    # components
    mount_min = Counter()
    for ln in lines:
        cc = comp.get(ln["type"], comp["other"])
        label = " ".join(x for x in (ln["ref"], ln["part_number"] or ln["description"]) if x) or cc["label"]
        if ln["customer_furnished"]:
            per.append(_line("components", f"{label} x {ln['qty']:g} (customer furnished)", 0.0, section="components"))
        else:
            if ln["unit_price"] is None:
                p, src = cc["price"], "PLACEHOLDER price"
                ph_count += 1
            else:
                p, src = ln["unit_price"], (f"live {ln['distributor']}".strip() if ln["price_source"] == "live" else "your price")
            per.append(_line("components", f"{label} x {ln['qty']:g}", p * ln["qty"], rate=p, note=src, section="components"))
            bought += p * ln["qty"]
            lead_parts = max(lead_parts, int(cfg["component_lead_days"]))
        mount_min[ln["type"]] += cc["minutes"] * ln["qty"]
    if any(mount_min.values()):
        total = sum(mount_min.values())
        detail = ", ".join(f"{comp[t]['label'].split(' (')[0].lower()} {m:g} min" for t, m in sorted(mount_min.items(), key=lambda x: -x[1]) if m)
        per.append(_line("integration", f"mount components ({total:g} min)", total / 60 * rate * kfac, hours=total / 60 * kfac, rate=rate, note=detail[:240],
                         section="integration"))
    # peripherals
    ig = cfg["integration"]
    pmin = 0.0
    for p in periph:
        lbl = p["description"] or p["part_number"] or "Peripheral"
        if p["customer_furnished"]:
            per.append(_line("peripherals", f"{lbl} x {p['qty']:g} (customer furnished)", 0.0, section="peripherals"))
        else:
            if p["unit_price"] is None:
                warnings.append(f"Peripheral '{lbl}' has no price. Enter one.")
                ph_count += 1
            pp = p["unit_price"] or 0.0
            per.append(_line("peripherals", f"{lbl} x {p['qty']:g}{'' if p['installed'] else ' (packed with the unit)'}", pp * p["qty"], rate=pp,
                             note=(f"live {p['distributor']}".strip() if p["price_source"] == "live" else "your price" if p["unit_price"] is not None else "no price"),
                             section="peripherals"))
            bought += pp * p["qty"]
            lead_parts = max(lead_parts, int(cfg["component_lead_days"]))
        pmin += (p["minutes"] if p["minutes"] is not None else (ig["peripheral_install_minutes"] if p["installed"] else ig["peripheral_kit_minutes"])) * p["qty"]
    if pmin:
        per.append(_line("integration", f"install, configure and pack peripherals ({pmin:g} min)", pmin / 60 * rate, hours=pmin / 60, rate=rate, section="integration"))
    # wiring
    wc = cfg["wiring"]
    tm = cfg["termination_minutes"]
    term_min = sum(n * tm.get(m, 1.0) for m, n in c["terminations"].items())
    if term_min:
        per.append(_line("wiring", "terminate wires at devices: " + ", ".join(f"{n:g} {m.replace('_', ' ')}" for m, n in c["terminations"].items()),
                         term_min / 60 * rate * kfac, hours=term_min / 60 * kfac, rate=rate, section="wiring"))
    if c["wires"]:
        length = _f(w.get("avg_length_in"), wc["default_length_in"])
        wm = c["wires"] * (wc["minutes_per_wire"] + wc["dress_minutes_per_wire"] + (wc["marker_minutes"] if w.get("mark_wires", True) else 0))
        per.append(_line("wiring", f"cut, strip, mark, route and dress {c['wires']} wires", wm / 60 * rate * kfac, hours=wm / 60 * kfac, rate=rate,
                         note=c["wire_basis"], section="wiring"))
        mat = c["wires"] * (length / 12 * wc["wire_per_ft"] + wc["ties_per_wire"] * wc["tie_each"] + (2 * wc["marker_each"] if w.get("mark_wires", True) else 0))
        per.append(_line("wiring", f"wire, ties and markers ({c['wires']} x {length:g} in average)", mat, section="wiring"))
        bought += mat
    if c["mates"]:
        per.append(_line("wiring", f"connect cables and harnesses ({c['mates']:g} mates)", c["mates"] * wc["mate_minutes"] / 60 * rate,
                         hours=c["mates"] * wc["mate_minutes"] / 60, rate=rate, section="wiring"))
    # integration
    if c["boards"]:
        bm = c["boards"] * cfg["pcba"]["mount_minutes"]
        per.append(_line("integration", f"mount {c['boards']:g} board(s) on standoffs", bm / 60 * rate * kfac, hours=bm / 60 * kfac, rate=rate, section="integration"))
        per.append(_line("integration", "ESD handling (ANSI/ESD S20.20 controls)", ig["esd_per_unit"], section="integration"))
    if c["fasteners"]:
        per.append(_line("integration", f"fasteners and final assembly ({c['fasteners']:g}{' estimated' if c['fasteners_estimated'] else ''})",
                         c["fasteners"] * (ig["fastener_each"] + ig["fastener_minutes"] / 60 * rate * kfac), hours=c["fasteners"] * ig["fastener_minutes"] / 60, rate=rate,
                         section="integration"))
    if c["ground_points"]:
        per.append(_line("integration", f"grounding and bonding points ({c['ground_points']:g})",
                         c["ground_points"] * (ig["ground_point_each"] + ig["ground_point_minutes"] / 60 * rate), hours=c["ground_points"] * ig["ground_point_minutes"] / 60,
                         rate=rate, section="integration"))
    if lab.get("serialize", True):
        per.append(_line("integration", "serialize and label", ig["serial_label_each"] + ig["serialize_minutes"] / 60 * rate, hours=ig["serialize_minutes"] / 60, rate=rate,
                         section="integration"))
    fi = _f(lab.get("final_inspection_minutes"), ig["final_inspection_minutes"])
    if fi:
        per.append(_line("test", f"final inspection ({fi:g} min)", fi / 60 * trate * kfac, hours=fi / 60, rate=trate, section="test"))
    # test
    ts = cfg["test"]
    fw = _f(lab.get("firmware_minutes"))
    if fw:
        per.append(_line("test", f"load firmware and configure ({fw:g} min)", fw / 60 * trate, hours=fw / 60, rate=trate, section="test"))
        lot.append(_line("test", "firmware load setup", ts["firmware_setup_minutes"] / 60 * trate, basis="per_lot", hours=ts["firmware_setup_minutes"] / 60, rate=trate, section="test"))
    ft = _f(lab.get("functional_test_minutes"))
    if ft:
        per.append(_line("test", f"functional test ({ft:g} min)", ft / 60 * trate, hours=ft / 60, rate=trate, section="test"))
        lot.append(_line("test", "functional test setup", ts["functional_setup_minutes"] / 60 * trate, basis="per_lot", hours=ts["functional_setup_minutes"] / 60,
                         rate=trate, section="test"))
    safety = [(k, lbl, ts[m]) for k, lbl, m in (("hipot", "dielectric withstand (hipot)", "hipot_minutes"), ("ground_bond", "ground bond", "ground_bond_minutes")) if lab.get(k)]
    if safety:
        sm = sum(x[2] for x in safety)
        per.append(_line("test", "safety test: " + ", ".join(x[1] for x in safety), sm / 60 * trate, hours=sm / 60, rate=trate, section="test"))
        lot.append(_line("test", "safety test setup", ts["safety_setup_minutes"] / 60 * trate, basis="per_lot", hours=ts["safety_setup_minutes"] / 60, rate=trate, section="test"))
    burn = _f(lab.get("burn_in_hours"))
    if burn:
        per.append(_line("test", f"burn-in {burn:g} h (rack, power, monitoring, handling)", burn * ts["burn_in_rack_per_hour"] + ts["burn_in_handling_minutes"] / 60 * trate,
                         hours=ts["burn_in_handling_minutes"] / 60, rate=trate, section="test"))
    ess_days = 0
    for k, key, label in (("ess_thermal", "ess_thermal_per_unit", "ESS thermal cycling"), ("ess_vibration", "ess_vibration_per_unit", "ESS random vibration")):
        if lab.get(k):
            per.append(_line("test", f"{label} (outside service)", ts[key], note="placeholder", section="test"))
            ess_days = int(ts["ess_days"])
    if ess_days:
        lot.append(_line("test", "ESS fixture and setup", ts["ess_lot_setup"], basis="per_lot", note="placeholder", section="test"))
    lab_days = 0
    for k in lab.get("lab_tests") or []:
        lt = cfg["lab_tests"].get(k)
        if lt:
            lot.append(_line("lab", f"{lt['label']} (outside lab)", lt["per_lot"], basis="per_lot", note="placeholder: get a lab quote", section="test"))
            lab_days = max(lab_days, int(lt["days"]))
    if lab_days:
        warnings.append("Outside lab qualification (MIL-STD-461, MIL-STD-810, MIL-STD-167-1, MIL-DTL-901) prices are placeholders and vary widely. "
                        "Get a lab quote, and check whether the contract wants it on the first article only or charged as its own CLIN.")
    # NRE
    nre = cfg["nre"]
    nre_lines = []
    for k, key, label in (("work_instructions", "work_instructions_hours", "work instructions and traveler"),
                          ("test_procedure", "test_procedure_hours", "test procedure and data sheet"),
                          ("drawing_package", "drawing_package_hours", "assembly drawings and parts list")):
        if lab.get(k):
            nre_lines.append(_line("nre", label, nre[key] * erate, basis="per_lot", hours=nre[key], rate=erate, section="nre"))
    for k, label in (("test_fixture_nre", "test fixture"), ("other_nre", "other NRE")):
        if _f(lab.get(k)):
            nre_lines.append(_line("nre", label, _f(lab.get(k)), basis="per_lot", section="nre"))
    nre_total = sum(l["cost"] for l in nre_lines)
    if lab.get("nre_in_price", True):
        lot += nre_lines
        if nre_total:
            assumptions.append(f"NRE (${nre_total:,.2f}) is included in every price break. If the customer pays NRE on its own CLIN, turn that off and quote it separately.")
    elif nre_total:
        assumptions.append(f"NRE of ${nre_total:,.2f} is quoted separately and left out of the unit prices.")
    lot.append(_line("setup", "kitting and work order", ig["kitting_hours_per_lot"] * rate, basis="per_lot", hours=ig["kitting_hours_per_lot"], rate=rate, section="integration"))
    # first article, CoC, packaging, freight
    fa_days = 0
    if opts.get("first_article"):
        lot.append(_line("inspection", "first article inspection and report (AS9102 format)", nre["first_article_hours"] * trate, basis="per_lot",
                         hours=nre["first_article_hours"], rate=trate, section="test"))
        fa_days = int(cfg_all["lead_time"]["first_article_days"])
        warnings.append("First article required: the government must approve it before production ships. Allow for that in delivery days.")
    lot.append(_line("inspection", "certificate of conformance", cfg_all["inspection"]["cert_per_lot"], basis="per_lot", section="shipping"))
    level = opts.get("packaging_level") or "commercial"
    pk = cfg_all["packaging"].get(level)
    if pk is None:
        raise BoxBuildError(f"packaging_level must be one of {list(cfg_all['packaging'])}")
    if pk["per_part"]:
        per.append(_line("packaging", f"{level} packaging", pk["per_part"], section="shipping"))
    if pk["per_lot"]:
        lot.append(_line("packaging", f"{level} lot labels and marking", pk["per_lot"], basis="per_lot", section="shipping"))
    if opts.get("crate"):
        per.append(_line("packaging", "crate or shipping case", cfg["crate_per_unit"], section="shipping"))
    lot.append(_line("freight", "outbound freight", _f(opts.get("freight_per_lot"), cfg["freight_per_lot"]), basis="per_lot", section="shipping"))

    # ---- quantity-dependent: PCBs, linked quotes, finish lot minimum
    child_res = []
    for ch in children:
        if ch["mode"] == "buy":
            child_res.append(None)
            continue
        child_res.append(child_costs(ch, qtys, config, depth))
    enc_child = child_costs(enc["child"], qtys, config, depth) if enc["source"] == "custom" and enc["child"] and enc["child"]["mode"] == "make" else None

    out_breaks = []
    breakdowns = {}
    ga = _f(opts.get("ga_rate"), cfg_all["ga_rate"])
    profit = _f(opts.get("profit_rate"), cfg_all["profit_rate"])
    burden = _f(opts.get("material_burden"), cfg["material_burden"])
    pcb_warn: list[str] = []
    labor_hours_unit = sum(l["hours"] or 0 for l in per if l["category"] in ("integration", "wiring", "enclosure", "test"))
    for q in qtys:
        pq = list(per)
        lq = list(lot)
        bought_q = bought
        leads = [lead_parts]
        for b in pcbs:
            bp, bl, blead, bw = pcb_lines(b, cfg, int(math.ceil(b["qty_per"] * q)), q)
            pq += bp
            lq += bl
            leads.append(blead)
            if q == qtys[0]:
                pcb_warn += bw
            bought_q += sum(l["cost"] for l in bp if l["category"] == "pcb" and ("components" in l["item"] or "CM price" in l["item"] or "bare board" in l["item"]))
        for ch, res in zip(children, child_res):
            sec = "wiring" if ch["kind"] == "harness" else ch["section"] or "linked"
            if res is None:
                p = ch["buy_unit_price"]
                if p is None:
                    raise BoxBuildError(f"Linked quote '{ch['name']}' is set to buy: enter the vendor's unit price.")
                pq.append(_line("linked", f"{ch['name']} ({ch['kind'].replace('_', ' ')}), bought: {ch['qty_per']:g} x ${p:,.2f}", p * ch["qty_per"], section=sec,
                                note="vendor price"))
                bought_q += p * ch["qty_per"]
                leads.append(int(ch["buy_lead_days"] or cfg["component_lead_days"]))
            else:
                r = res[q]
                pq.append(_line("linked", f"{ch['name']} ({ch['kind'].replace('_', ' ')}), made: {ch['qty_per']:g} per unit", r["cost"] / q, section=sec,
                                note=f"your cost at {r['need']} pcs, lot costs spread over {q}" + (f"; quote #{ch['quote_id']}" if ch["quote_id"] else "")))
                leads.append(int(r["lead"]))
        if enc["source"] == "custom" and enc["child"]:
            ch = enc["child"]
            if enc_child:
                r = enc_child[q]
                pq.append(_line("enclosure", f"{ch['name']} (custom enclosure, made)", r["cost"] / q, section="enclosure",
                                note=f"your cost at {r['need']} pcs" + (f"; quote #{ch['quote_id']}" if ch["quote_id"] else "")))
                leads.append(int(r["lead"]))
            else:
                p = ch["buy_unit_price"]
                if p is None:
                    raise BoxBuildError("The custom enclosure is set to buy: enter the vendor's unit price.")
                pq.append(_line("enclosure", f"{ch['name']} (custom enclosure, bought)", p, section="enclosure", note="vendor price"))
                bought_q += p
                leads.append(int(ch["buy_lead_days"] or cfg["component_lead_days"]))
        if fin:
            topup = fin["lot_min"] - fin["per_unit"] * q
            if topup > 0:
                lq.append(_line("enclosure", f"{fin['label']} lot minimum top-up", topup, basis="per_lot"))
            leads.append(max(leads) + int(fin["lead_days"]))
        if burden and bought_q:
            pq.append(_line("material", f"material burden {burden:.0%} on bought material (purchasing, receiving, handling)", bought_q * burden, section="material"))
        unit_cost = sum(l["cost"] for l in pq)
        lot_cost = sum(l["cost"] for l in lq)
        cost = unit_cost * q + lot_cost
        price_q = max(cost * (1 + ga) * (1 + profit), cfg_all["min_lot_charge"])
        build_days = math.ceil(q * max(labor_hours_unit, 0.5) / max(ig["hours_per_day"] * ig["techs"], 1))
        days = max(leads) + build_days + math.ceil(burn / 24) + ess_days + lab_days + fa_days + 2
        out_breaks.append({"quantity": q, "total_cost": round(cost, 2), "unit_cost": round(cost / q, 2), "unit_price": round(price_q / q, 2),
                           "total_price": round(price_q, 2), "margin_pct": round((price_q - cost) / price_q * 100, 1) if price_q else 0.0,
                           "lead_time_days": int(days)})
        sections = Counter()
        for l in pq:
            sections[l["section"]] += l["cost"]
        for l in lq:
            sections[l["section"]] += l["cost"] / q
        breakdowns[str(q)] = {"per_part_lines": pq, "per_lot_lines": lq, "per_part_cost": round(unit_cost, 2), "per_lot_cost": round(lot_cost, 2),
                              "sections": {k: round(v, 2) for k, v in sections.items()}}
    warnings += pcb_warn
    # ---- compliance and sanity notes
    if pcbs and any(b["mode"] == "estimate" for b in pcbs):
        if any(b["ipc_class"] == 3 for b in pcbs) or cls3:
            warnings.append("Class 3 build: IPC-A-610 and J-STD-001 Class 3 assembly and IPC-6012 Class 3 bare boards. Confirm your fab house and assembler build to Class 3.")
        if any(b["finish"] != "HASL tin-lead" for b in pcbs if b["mode"] == "estimate"):
            warnings.append("Lead-free build: many military programs require tin-lead solder or a lead-free control plan (GEIA-STD-0005-1) "
                            "with tin whisker mitigation. Check the drawing notes before quoting lead-free.")
    if pcbs or any(ln["type"] in ("display", "computer_module", "power_supply", "sensor") for ln in lines):
        warnings.append("Electronic parts on DoD work: DFARS 252.246-7008 wants them bought from the original manufacturer or its authorized "
                        "distributors (or a trusted supplier) with traceability. Keep the distributor's certificate of conformance.")
    if ph_count:
        warnings.append(f"{ph_count} item(s) use placeholder prices. Fetch live prices or enter real ones before quoting.")
    if c["wires"] and "estimated" in c["wire_basis"]:
        assumptions.append(f"Wires: {c['wire_basis']}. Enter a wire count to override.")
    if c["fasteners_estimated"] and c["fasteners"]:
        assumptions.append(f"Fasteners estimated at {cfg['enclosure_mods']['assembly_fasteners']:g} for the enclosure plus 4 standoffs per board ({c['fasteners']:g}).")
    if cls3:
        assumptions.append(f"Class 3 workmanship: integration and wiring labor x{cfg['class3_labor_factor']:g} (your assumption, not a figure from the standard).")
    if any(ch["kind"] == "harness" for ch in children):
        assumptions.append("Each linked harness is counted as plugging in at both ends (2 mates per harness).")
        if c["termination_total"]:
            assumptions.append("Component terminations are counted on top of the linked harnesses. If a harness already terminates into a part "
                               "(its contacts are in the panel connector, say), set that line's terminations to 0.")
    if children or enc_child:
        assumptions.append("Linked quotes are rolled in at your cost (no G&A or profit, freight, packaging or CoC), so markup is applied once on the box build.")
    assumptions.append(f"Lead time: longest material lead + {labor_hours_unit:.1f} labor hours per unit at {ig['techs']:g} tech(s) x {ig['hours_per_day']:g} h/day"
                       + (", plus burn-in" if burn else "") + (", ESS" if ess_days else "") + (", outside lab" if lab_days else "") + (", first article" if fa_days else "") + ".")
    first = breakdowns[str(qtys[0])]
    return {"kind": "box_build", "part": {k: spec.get(k) for k in ("name", "part_number", "nsn") if spec.get(k)}, "material": "Box build",
            "part_weight_lb": 0.0, "stock_volume_in3": 0.0,
            "per_part_lines": first["per_part_lines"], "per_lot_lines": first["per_lot_lines"], "per_part_cost": first["per_part_cost"],
            "per_lot_cost": first["per_lot_cost"], "breakdowns": breakdowns, "ga_rate": ga, "profit_rate": profit, "price_breaks": out_breaks,
            "counts": c, "auto_cutouts": auto, "nre_total": round(nre_total, 2), "labor_hours_per_unit": round(labor_hours_unit, 2),
            "assumptions": assumptions, "warnings": list(dict.fromkeys(warnings)), "config_note": cfg.get("note", "")}


def estimate_spec(spec: dict, config: dict | None = None) -> dict:
    try:
        return price(spec, config)
    except BoxBuildError as exc:
        raise pricing.SpecError(str(exc)) from exc


def build_spec(body: dict) -> dict:
    return {"kind": "box_build", "name": body.get("name") or "Box build", "part_number": body.get("part_number") or "", "nsn": body.get("nsn") or "",
            "quantities": body.get("quantities") or [1], "options": body.get("options") or {}, "source": body.get("source") or {},
            "enclosure": normalize_enclosure(body.get("enclosure")), "pcbs": normalize_pcbs(body.get("pcbs")),
            "lines": normalize_lines(body.get("lines")), "peripherals": normalize_peripherals(body.get("peripherals")),
            "children": normalize_children(body.get("children")), "wiring": dict(body.get("wiring") or {}), "labor": dict(body.get("labor") or {})}


# ================================================================ assembly BOM import
def _row(rec: dict, heads: dict) -> dict | None:
    part, desc = rec.get("part", ""), rec.get("desc", "")
    if not (part or desc):
        return None
    try:
        qty = float(re.sub(r"[^\d.]", "", rec.get("qty") or "1") or 1)
    except ValueError:
        return None
    price = None
    if rec.get("price"):
        try:
            price = float(re.sub(r"[$,\s]", "", rec["price"]))
        except ValueError:
            price = None
    return {"ref": (rec.get("ref") or "").upper(), "part_number": part, "manufacturer": rec.get("manufacturer", ""), "description": desc,
            "qty": qty, "unit_price": price, "hint": rec.get("device_type", ""), "raw": " | ".join(v for v in rec.values() if v)}


def sort_rows(rows: list[dict]) -> dict:
    """Assembly BOM rows -> enclosure, boards, components, peripherals."""
    enclosure = None
    pcbs, lines, periph = [], [], []
    for r in rows:
        text = f"{r['hint']} {r['description']} {r['part_number']}".upper()
        price_kw = {"unit_price": r["unit_price"], "price_source": "manual" if r["unit_price"] is not None else ""}
        if re.search(PCB_RX, text) and not re.search(r"STANDOFF|SPACER|GUIDE|HOLDER|BRACKET", text):
            pcbs.append(blank_pcb(name=r["description"] or r["part_number"] or "PCB assembly", qty_per=r["qty"] or 1,
                                  mode="buy" if r["unit_price"] is not None else "estimate",
                                  buy_prices=[{"quantity": 1, "unit_price": r["unit_price"]}] if r["unit_price"] is not None else []))
        elif enclosure is None and re.search(ENCLOSURE_RX, text) and not re.search(r"FUSE ?BOX|BOX ?HEADER|CASE SCREW", text):
            enclosure = {"source": "catalog", "type": _guess_enclosure_type(text), "part_number": r["part_number"], "manufacturer": r["manufacturer"],
                         "description": r["description"], **price_kw, **_size3(r["description"])}
        elif re.search(PERIPHERAL_RX, text) and not re.search(r"\bSWITCH\b", text.replace("NETWORK SWITCH", "").replace("ETHERNET SWITCH", "")):
            periph.append(blank_peripheral(description=r["description"] or r["part_number"], part_number=r["part_number"], manufacturer=r["manufacturer"],
                                           qty=r["qty"], installed=not re.search(r"MANUAL|CORD|ADAPTER|CHARGER|CASE|SOFTWARE|LICENSE", text), **price_kw))
        else:
            t = classify_component(r["part_number"], r["description"], r["hint"])
            lines.append(blank_line(ref=r["ref"], type=t, part_number=r["part_number"], manufacturer=r["manufacturer"], description=r["description"],
                                    qty=r["qty"], mount="internal" if t in ("power_supply", "relay", "terminal_block", "hardware", "heatsink", "computer_module",
                                                                            "cable_assembly", "battery", "sensor") else "panel", **price_kw))
    return {"enclosure": enclosure, "pcbs": pcbs, "lines": lines, "peripherals": periph}


def _size3(text: str) -> dict:
    """'4.7 x 3.7 x 1.2 in' or '120 x 80 x 55 mm' -> length/width/height in inches (largest first)."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\"|IN|MM)?\s*[X×]\s*(\d+(?:\.\d+)?)\s*(?:\"|IN|MM)?\s*[X×]\s*(\d+(?:\.\d+)?)\s*(\"|IN\b|INCH|MM\b)?", text or "", re.I)
    if not m:
        return {}
    vals = [float(m.group(i)) for i in (1, 2, 3)]
    unit = (m.group(4) or "").upper()
    if unit == "MM" or re.search(r"\bMM\b", text, re.I) and not unit.startswith(("IN", '"')):
        vals = [v / 25.4 for v in vals]
    vals = sorted((round(v, 3) for v in vals), reverse=True)
    return {"length_in": vals[0], "width_in": vals[1], "height_in": vals[2]}


def _guess_enclosure_type(text: str) -> str:
    for k, pat in (("rack_chassis", r"RACK|\b\dU\b|19 ?(?:IN|\")"), ("stainless_nema4x", r"STAINLESS|\bSS\b|304|316"),
                   ("polycarbonate", r"POLYCARB|\bPC\b|FIBERGLASS|NEMA ?4X"), ("abs_plastic", r"\bABS\b|PLASTIC"),
                   ("rugged_case", r"TRANSIT|RUGGED|PELICAN|HARD CASE"), ("extruded_aluminum", r"EXTRUD"),
                   ("diecast_aluminum", r"DIE ?-?CAST|ALUMINUM|ALUMINIUM"), ("sheet_steel", r"STEEL|NEMA ?1?2?\b")):
        if re.search(pat, text):
            return k
    return "diecast_aluminum"


def parse_assembly_bom(path: str | Path, filename: str = "") -> dict:
    """A top-level assembly BOM (CSV, XLSX or a drawing PDF with the parts list as text) sorted into box build sections."""
    from .electrical import BOM_COLS, ElectricalError, _pdf, _rows_from_sheet, _rows_from_text, _scan

    path = Path(path)
    filename = filename or path.name
    ok = lambda keys: bool(({"part", "desc"} & keys) and ({"qty", "ref", "item"} & keys))  # noqa: E731
    try:
        if filename.lower().endswith(".pdf"):
            text, pages, drawing, warnings = _pdf(path)
            found = _scan(_rows_from_text(text), {"bom": (BOM_COLS, ok, _row)}, positional=False)
            source = {"filename": filename, "type": "pdf", "pages": pages}
        else:
            found = _scan(_rows_from_sheet(filename, path.read_bytes()), {"bom": (BOM_COLS, ok, _row)}, positional=True)
            drawing, warnings, source = {}, [], {"filename": filename, "type": "table"}
    except ElectricalError as exc:
        raise BoxBuildError(str(exc)) from exc
    rows = found.get("bom", [])
    if not rows:
        raise BoxBuildError("No parts list found. The file needs Part number or Description columns and a Qty, Ref or Item column.")
    out = sort_rows(rows)
    other = sum(1 for ln in out["lines"] if ln["type"] == "other")
    if other:
        warnings.append(f"{other} line(s) did not match a part type. Pick a type so mounting and wiring time are right.")
    if not out["enclosure"]:
        warnings.append("No enclosure line found. Pick the enclosure below.")
    out.update(warnings=warnings, source=source, drawing=drawing, rows=len(rows))
    return out


# ================================================================ purchase list
def purchase_rows(spec: dict, builds: int, config: dict | None = None) -> list[list]:
    cfg = pricing.merged_config(config)["box_build"]
    rows: list[list] = []
    enc = normalize_enclosure(spec.get("enclosure"))
    if enc["source"] == "catalog":
        et = cfg["enclosures"].get(enc["type"], {})
        rows.append(["Enclosure", enc["part_number"], enc["manufacturer"], enc["description"] or et.get("label", ""), 1, builds, enc["unit_price"], ""])
    for ln in normalize_lines(spec.get("lines")):
        if not ln["customer_furnished"]:
            rows.append([COMPONENT_TYPES[ln["type"]][0], ln["part_number"], ln["manufacturer"], ln["description"], ln["qty"], ln["qty"] * builds,
                         ln["unit_price"], ln["distributor"]])
    for p in normalize_peripherals(spec.get("peripherals")):
        if not p["customer_furnished"]:
            rows.append(["Peripheral", p["part_number"], p["manufacturer"], p["description"], p["qty"], p["qty"] * builds, p["unit_price"], p["distributor"]])
    for b in normalize_pcbs(spec.get("pcbs")):
        if b["mode"] == "buy":
            rows.append(["PCB assembly (CM)", "", "", b["name"], b["qty_per"], math.ceil(b["qty_per"] * builds), None, ""])
        elif b["mode"] == "estimate":
            rows.append(["Bare PCB", "", "", f"{b['name']} ({b['layers']} layer)", b["qty_per"], math.ceil(b["qty_per"] * builds), b["fab_price_each"], ""])
            if not b["consigned"]:
                for x in b["bom_lines"]:
                    need = x["qty"] * b["qty_per"] * builds
                    rows.append([f"PCB part ({b['name']})", x["mpn"], x["manufacturer"], x["description"], x["qty"] * b["qty_per"],
                                 math.ceil(need * (1 + cfg["pcba"]["attrition"])), x["unit_price"], x["distributor"]])
    for ch in normalize_children(spec.get("children")):
        rows.append([f"Linked {ch['kind'].replace('_', ' ')} ({ch['mode']})", ch["spec"].get("part_number", ""), "", ch["name"], ch["qty_per"],
                     math.ceil(ch["qty_per"] * builds), ch["buy_unit_price"], ""])
    return rows


def purchase_xlsx(spec: dict, builds: int, config: dict | None = None, title: str = "") -> bytes:
    from .extrusion import _xlsx

    header = ["Type", "Part number / MPN", "Manufacturer", "Description", "Qty per unit", f"Qty for {builds}", "Unit price", "Source"]
    return _xlsx([("Purchase list", header, purchase_rows(spec, builds, config))], title)
