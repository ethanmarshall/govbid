"""Assemblies and weldments from one STEP file.

A STEP file with several solids is split into bodies. Each body gets its own analysis (cad.analyze),
a small mesh for a thumbnail, and identical bodies (same volume, surface area and bounding box within
tolerance) are grouped with a quantity per assembly. Bodies that touch are joints: the boundary of
the contact patch comes from an OpenCascade section of the two bodies, and the weld estimate is two
fillet welds along the patch's long side (one each side of the joint). That is a starting number to
edit, not a weld map: stitch welds, one-sided fillets and plug welds change it.

Splitting writes each distinct body to its own STEP file and stores it like an upload
(cad_quote.store_upload), so every body can be quoted, checked for manufacturability or converted
like any other part.

Assembly pricing = for each body, cad_quote.quote at (body qty x assemblies) with its own process,
material and finishes (or a bought-out price), plus joining (weld, fasteners, assembly labor),
inspection, packaging and freight for the assembly. Body quotes are run without their own freight and
with commercial packaging so those are charged once, at the assembly.
"""
from __future__ import annotations

import json
import re
import math
import tempfile
from pathlib import Path

from . import cad, cad_quote, inserts, pricing

IN = 25.4
SAME_REL = 0.005  # identical bodies: volume and area within 0.5 percent
SAME_DIM_IN = 0.005


def _cache_path(file_id: str) -> Path:
    return cad_quote.CAD_DIR / f"{file_id}.bodies.json"


def _bbox_mm(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, b, False, False)  # exact extents, without edge tolerances
    lo, hi = b.CornerMin(), b.CornerMax()
    return (lo.X(), lo.Y(), lo.Z()), (hi.X(), hi.Y(), hi.Z())


def _boxes_touch(a, b, gap=0.05) -> bool:
    return all(a[0][k] - gap <= b[1][k] and b[0][k] - gap <= a[1][k] for k in range(3))


def _joint(sa, sb) -> dict | None:
    """Contact between two bodies: None if apart, else the contact patch size and a weld estimate."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    d = BRepExtrema_DistShapeShape(sa, sb)
    if not d.IsDone() or d.Value() > 0.01:
        return None
    sec = BRepAlgoAPI_Section(sa, sb)
    sec.Build()
    perimeter, dims = 0.0, [0.0, 0.0, 0.0]
    if sec.IsDone():
        shape = sec.Shape()
        gp = GProp_GProps()
        BRepGProp.LinearProperties_s(shape, gp)
        perimeter = gp.Mass()
        if perimeter > 0:
            lo, hi = _bbox_mm(shape)
            dims = sorted((hi[k] - lo[k] for k in range(3)), reverse=True)
    length = dims[0] / IN
    return {"contact_length_in": round(length, 3), "contact_width_in": round(dims[1] / IN, 3),
            "contact_perimeter_in": round(perimeter / IN, 3), "weld_estimate_in": round(2 * length, 2),
            "touch_only": perimeter <= 0}


def _same(a: dict, b: dict) -> bool:
    ga, gb = a["geometry"], b["geometry"]
    if abs(ga["volume"] - gb["volume"]) > SAME_REL * max(ga["volume"], 1e-9):
        return False
    if abs(ga["surface_area"] - gb["surface_area"]) > SAME_REL * max(ga["surface_area"], 1e-9) + 0.002:
        return False
    da = sorted(ga["bounding_box"].values())
    db = sorted(gb["bounding_box"].values())
    return all(abs(x - y) <= SAME_DIM_IN for x, y in zip(da, db))


def _load_solids(file_id: str, with_names: bool = False):
    shape, names = cad.load_step_named(cad_quote.step_path(file_id))
    solids = inserts._solids(shape)
    if with_names:
        return solids, (names if len(names) == len(solids) else [""] * len(solids))
    return solids


# Parts the model shows only for fit (bearings, fasteners, references): bought, not made.
BOUGHT = re.compile(r"\b(reference|ref|bearing|608|6\d\dzz|bolt|screw|nut|washer|dowel|pin|o-?ring|spring|insert|standoff|"
                    r"fastener|rivet|bushing|seal|circlip|retaining ring|hardware|purchased|cots|mcmaster)\b", re.I)


MADE = re.compile(r"\b(spacer|housing|cover|retainer|boss|cap|holder|mount|seat|block|plate|bracket|tunnel|shaft|sleeve|frame|carrier)\b", re.I)


def is_bought(raw: str) -> bool:
    """A part shown for fit that we buy: '08_bearing_608_reference' yes, '07_rear_bearing_spacer' no."""
    n = (raw or "").replace("_", " ")
    if re.search(r"\breference\b|\bref\b|\bpurchased\b|\bcots\b|\bmcmaster\b", n, re.I):
        return True
    return bool(BOUGHT.search(n)) and not MADE.search(n)


def part_name(raw: str) -> str:
    """'04_compressor_outlet_guide_vanes' -> 'compressor outlet guide vanes'."""
    n = re.sub(r"^\s*\d+[\s_.-]+", "", raw or "")
    n = re.sub(r"[_]+", " ", n).strip()
    return n[:80]


def bodies(file_id: str, with_mesh: bool = True) -> dict:
    """Every solid in the file with its own analysis, groups of identical bodies and the joints between them."""
    src = cad_quote.load(file_id)
    cache = _cache_path(file_id)
    if cache.exists():
        data = json.loads(cache.read_text())
        if not with_mesh:
            for b in data["bodies"]:
                b.pop("mesh", None)
        return data
    solids, solid_names = _load_solids(file_id, with_names=True)
    if not solids:
        raise cad.CadError("No solid bodies found in this file.")
    rows = []
    for i, s in enumerate(solids):
        try:
            g = cad.analyze(s)
        except cad.CadError as exc:
            rows.append({"index": i, "error": str(exc)})
            continue
        lo, hi = _bbox_mm(s)
        rows.append({"index": i, "geometry": g, "center_in": [round((lo[k] + hi[k]) / 2 / IN, 3) for k in range(3)],
                     "mesh": cad.mesh(s, max_triangles=20_000)})
    good = [r for r in rows if "geometry" in r]
    groups: list[dict] = []
    for r in good:
        for g in groups:
            if _same(g["_first"], r):
                g["bodies"].append(r["index"])
                break
        else:
            groups.append({"_first": r, "bodies": [r["index"]]})
    stem = Path(src["filename"]).stem
    out_groups = []
    for n, g in enumerate(groups, 1):
        geo = g["_first"]["geometry"]
        bb = geo["bounding_box"]
        named = [part_name(solid_names[i]) for i in g["bodies"] if solid_names[i]]
        name = max(set(named), key=named.count) if named else f"{stem} body {n}"
        raw = [solid_names[i] for i in g["bodies"] if solid_names[i]]
        for i in g["bodies"]:
            next(r for r in rows if r["index"] == i)["group"] = n
        out_groups.append({"group": n, "name": name, "qty": len(g["bodies"]), "bodies": g["bodies"], "representative": g["bodies"][0],
                           "bought": bool(raw) and all(is_bought(x) for x in raw),
                           "suggested_process": geo["suggested_process"], "volume": geo["volume"], "bounding_box": bb,
                           "holes": len(geo["holes"]), "sheet_thickness": (geo.get("sheet_metal") or {}).get("thickness")})
    joints = []
    boxes = {i: _bbox_mm(s) for i, s in enumerate(solids)}
    good_idx = [r["index"] for r in good]
    faces = sum(sum((r["geometry"].get("faces") or {}).values()) for r in good)
    # Contact checks between detailed parts (blades, threads, nested turned parts) can take hours, and they only
    # feed the weld estimate. Big mechanical assemblies skip them; the weld length can be entered by hand.
    skip_joints = len(good_idx) > 25 or faces > 4000
    for a_k, a in enumerate([] if skip_joints else good_idx):
        for b in good_idx[a_k + 1:]:
            if not _boxes_touch(boxes[a], boxes[b]):
                continue
            j = _joint(solids[a], solids[b])
            if j:
                joints.append({"a": a, "b": b, **j})
    data = {"file_id": file_id, "filename": src["filename"], "count": len(solids), "bodies": rows, "groups": out_groups,
            "joints": joints, "weld_estimate_in": round(sum(j["weld_estimate_in"] for j in joints), 2),
            "weld_note": ("Not estimated: this is a large assembly, so contacts between parts were not checked. Enter the weld length if it is welded."
                          if skip_joints else "Estimate: two fillet welds along the long side of each contact patch. Edit it to match the weld symbols."),
            "joints_checked": not skip_joints}
    cache.write_text(json.dumps(data))
    if not with_mesh:
        for b in data["bodies"]:
            b.pop("mesh", None)
    return data


def split(file_id: str) -> dict:
    """Store one STEP file per group of identical bodies. Returns the groups with their new file_ids."""
    data = bodies(file_id, with_mesh=False)
    cache = _cache_path(file_id)
    full = json.loads(cache.read_text())
    if full.get("split"):
        return {"file_id": file_id, "filename": data["filename"], "groups": full["split"], "joints": data["joints"],
                "weld_estimate_in": data["weld_estimate_in"], "weld_note": data["weld_note"]}
    solids = _load_solids(file_id)
    out = []
    for g in data["groups"]:
        name = f"{g['name'].replace(' ', '_')}.step"
        with tempfile.TemporaryDirectory(dir=cad_quote.CAD_DIR) as tmp:
            p = Path(tmp) / name
            inserts.write_step(solids[g["representative"]], p)
            stored = cad_quote.store_upload(p.read_bytes(), name)
        meta_path = cad_quote.CAD_DIR / f"{stored['file_id']}.json"
        meta = json.loads(meta_path.read_text())
        meta["split_from"] = file_id
        meta_path.write_text(json.dumps(meta))
        out.append({**g, "file_id": stored["file_id"], "filename": stored["filename"],
                    "suggested_process": stored["geometry"]["suggested_process"]})
    full["split"] = out
    cache.write_text(json.dumps(full))
    return {"file_id": file_id, "filename": data["filename"], "groups": out, "joints": data["joints"],
            "weld_estimate_in": data["weld_estimate_in"], "weld_note": data["weld_note"]}


# ---------------------------------------------------------------- pricing
def _line(category, item, cost, *, basis="per_assembly", hours=None, rate=None, note=""):
    return {"category": category, "item": item, "basis": basis, "hours": None if hours is None else round(hours, 3),
            "rate": rate, "cost": round(cost, 2), "note": note}


def _f(v, d=0.0) -> float:
    try:
        return float(v) if v not in (None, "") else d
    except (TypeError, ValueError):
        return d


def quote_assembly(bodies_in: list[dict], joining: dict | None, quantities: list[int], config: dict | None = None,
                   packaging: str = "commercial", freight_per_lot: float | None = None) -> dict:
    """Combined price breaks for an assembly.

    bodies_in: [{file_id, name, qty (per assembly), process, material, finishes, options, skip, buy, buy_unit_price}]
    joining: {weld_process (mig|tig), weld_length_in, weld_joints, fasteners, fastener_unit_cost,
              assembly_minutes, inspection_minutes, first_article, certified_welder}
    quantities: assemblies.
    """
    cfg = pricing.merged_config(config)
    rates = cfg["rates"]
    joining = joining or {}
    try:
        qtys = sorted({int(q) for q in (quantities or [1]) if int(q) > 0})
    except (TypeError, ValueError):
        raise pricing.SpecError("quantities must be positive integers")
    if not qtys:
        raise pricing.SpecError("Give at least one quantity")
    warnings: list[str] = []
    assumptions: list[str] = []
    lines = []
    totals = {q: 0.0 for q in qtys}
    costs = {q: 0.0 for q in qtys}
    leads = {q: 0 for q in qtys}
    incomplete = False
    markup = cfg["outsourcing"]["markup"]
    for b in bodies_in:
        n = max(int(_f(b.get("qty"), 1)), 0)
        name = b.get("name") or b.get("file_id") or "body"
        row = {"file_id": b.get("file_id"), "name": name, "qty": n, "process": b.get("process") or "auto", "material": b.get("material") or "",
               "skip": bool(b.get("skip")), "buy": bool(b.get("buy")), "breaks": []}
        if row["skip"] or n == 0:
            lines.append(row)
            continue
        if row["buy"]:
            unit = _f(b.get("buy_unit_price"))
            if unit <= 0:
                row["error"] = "Enter the bought-out unit price."
                incomplete = True
                lines.append(row)
                continue
            for q in qtys:
                c = unit * n * q
                p = c * (1 + markup)
                row["breaks"].append({"quantity": q, "parts": n * q, "unit_price": round(p / (n * q), 2), "total_price": round(p, 2)})
                totals[q] += p
                costs[q] += c
            lines.append(row)
            continue
        opts = dict(b.get("options") or {})
        opts.update({k: b[k] for k in ("process", "material", "finishes") if b.get(k) not in (None, "")})
        opts.update(quantities=sorted({n * q for q in qtys}), freight_per_lot=0, packaging="commercial", approved_source_required=False, name=name)
        try:
            r = cad_quote.quote(b.get("file_id") or "", opts, config)
        except (cad.CadError, pricing.SpecError) as exc:
            row["error"] = str(exc)
            incomplete = True
            lines.append(row)
            continue
        row["process"] = r["process"]
        by = {x["quantity"]: x for x in r["estimate"]["price_breaks"]}
        for q in qtys:
            x = by[n * q]
            row["breaks"].append({"quantity": q, "parts": n * q, "unit_price": x["unit_price"], "total_price": x["total_price"]})
            totals[q] += x["total_price"]
            costs[q] += x["total_cost"]
            leads[q] = max(leads[q], x["lead_time_days"])
        row["warnings"] = [w for w in r["estimate"]["warnings"] if "approved source" not in w.lower()]
        lines.append(row)
    if incomplete:
        warnings.append("Some bodies are not priced (see their errors): the totals leave them out.")

    per_assy: list[dict] = []
    per_lot: list[dict] = []
    weld_len = _f(joining.get("weld_length_in"))
    if weld_len > 0:
        proc = (joining.get("weld_process") or "mig").lower()
        if proc not in cfg["weld_ipm"]:
            raise pricing.SpecError(f"weld_process must be one of {list(cfg['weld_ipm'])}")
        joints = max(int(_f(joining.get("weld_joints"), 1)), 1)
        rate = rates[f"weld_{proc}"]
        minutes = weld_len / cfg["weld_ipm"][proc] + joints * cfg["weld_fitup_minutes_per_joint"] + cfg["handling_minutes"]
        per_assy.append(_line("welding", f"{proc.upper()} weld, {weld_len:g} in, {joints} joint(s)", minutes / 60 * rate, hours=minutes / 60, rate=rate))
        su = cfg["setup_hours"]["weld_fixture"]
        per_lot.append(_line("setup", "weld fixture build/setup", su * rate, basis="per_lot", hours=su, rate=rate))
        if joining.get("certified_welder"):
            warnings.append("Certified welding (for example AWS D1.1 or D17.1) is required: confirm a qualified welder and procedure.")
    nf = int(_f(joining.get("fasteners")))
    if nf > 0:
        unit = _f(joining.get("fastener_unit_cost"), 0.25)
        per_assy.append(_line("hardware", f"{nf} fastener(s)", nf * unit, note="purchased hardware" + (", placeholder price" if joining.get("fastener_unit_cost") in (None, "") else "")))
        h = nf * 0.5 / 60
        per_assy.append(_line("hardware", "install fasteners (0.5 min each)", h * rates["assembly"], hours=h, rate=rates["assembly"]))
    am = _f(joining.get("assembly_minutes"))
    if am > 0:
        per_assy.append(_line("labor", "assembly", am / 60 * rates["assembly"], hours=am / 60, rate=rates["assembly"]))
    im = _f(joining.get("inspection_minutes"), cfg["inspection"]["per_part_minutes"] * 2)
    per_assy.append(_line("inspection", "assembly inspection", im / 60 * rates["inspection"], hours=im / 60, rate=rates["inspection"]))
    if joining.get("first_article"):
        h = cfg["inspection"]["first_article_hours"]
        per_lot.append(_line("inspection", "first article inspection and report", h * rates["inspection"], basis="per_lot", hours=h, rate=rates["inspection"]))
        warnings.append("First article required: the government must approve it before production ships. Allow for that in delivery days.")
    pk = cfg["packaging"].get(packaging)
    if pk is None:
        raise pricing.SpecError(f"packaging must be one of {list(cfg['packaging'])}")
    per_assy.append(_line("packaging", f"{packaging} packaging", pk["per_part"]))
    if pk["per_lot"]:
        per_lot.append(_line("packaging", f"{packaging} lot labels and marking", pk["per_lot"], basis="per_lot"))
    per_lot.append(_line("freight", "outbound freight", _f(freight_per_lot, cfg["default_freight_per_lot"]), basis="per_lot"))

    ga, profit = cfg["ga_rate"], cfg["profit_rate"]
    assy_cost = sum(l["cost"] for l in per_assy)
    lot_cost = sum(l["cost"] for l in per_lot)
    breaks = []
    for q in qtys:
        j_cost = assy_cost * q + lot_cost
        j_price = j_cost * (1 + ga) * (1 + profit)
        total = totals[q] + j_price
        cost = costs[q] + j_cost
        days = max(leads[q], cfg["lead_time"]["base_days"]) + 2 + math.ceil(q / max(cfg["lead_time"]["parts_per_day"], 1))
        if joining.get("first_article"):
            days += cfg["lead_time"]["first_article_days"]
        breaks.append({"quantity": q, "unit_price": round(total / q, 2), "total_price": round(total, 2), "unit_cost": round(cost / q, 2),
                       "total_cost": round(cost, 2), "margin_pct": round((total - cost) / total * 100, 1) if total else 0.0,
                       "lead_time_days": days, "bodies_price": round(totals[q], 2), "joining_price": round(j_price, 2)})
    assumptions.append("Each body is priced at its quantity per assembly times the number of assemblies; body prices include their own G&A and profit.")
    assumptions.append("Body quotes leave out freight and use commercial packaging; both are charged once on the assembly.")
    if any(r.get("buy") and not r.get("error") for r in lines):
        assumptions.append(f"Bought-out bodies carry your {markup:.0%} outsourcing markup.")
    return {"kind": "assembly", "bodies": lines, "per_part_lines": per_assy, "per_lot_lines": per_lot,
            "per_part_cost": round(assy_cost, 2), "per_lot_cost": round(lot_cost, 2), "ga_rate": ga, "profit_rate": profit,
            "price_breaks": breaks, "warnings": warnings, "assumptions": assumptions, "incomplete": incomplete,
            "config_note": cfg.get("note", "")}


def build_spec(file_id: str, body: dict, filename: str = "") -> dict:
    """The PartQuote spec for an assembly quote (spec.kind "assembly"); spec.cad keeps the source file so
    the saved quote reopens in the instant quote."""
    return {"kind": "assembly", "name": body.get("name") or Path(filename or "assembly").stem, "part_number": body.get("part_number") or "",
            "nsn": body.get("nsn") or "", "quantities": body.get("quantities") or [1],
            "bodies": body.get("bodies") or [], "joining": body.get("joining") or {},
            "packaging": body.get("packaging") or "commercial", "freight_per_lot": body.get("freight_per_lot"),
            "cad": {"file_id": file_id, "filename": filename, "notes": [], "options": {"assembly": True}}}


def estimate_spec(spec: dict, config: dict | None = None) -> dict:
    """Price a saved assembly spec (used by quotes.save_quote)."""
    r = quote_assembly(spec.get("bodies") or [], spec.get("joining"), spec.get("quantities") or [1], config,
                       spec.get("packaging") or "commercial", spec.get("freight_per_lot"))
    r["part"] = {k: spec.get(k) for k in ("name", "part_number", "nsn") if spec.get(k)}
    return r


def quote_file(file_id: str, body: dict, config: dict | None = None) -> dict:
    src = cad_quote.load(file_id)
    r = quote_assembly(body.get("bodies") or [], body.get("joining"), body.get("quantities") or [1], config,
                       body.get("packaging") or "commercial", body.get("freight_per_lot"))
    r["spec"] = build_spec(file_id, body, src["filename"])
    return r
