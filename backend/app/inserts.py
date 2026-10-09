"""Heat-set insert holes for 3D printed parts.

A printed part with threaded holes usually gets brass heat-set inserts instead of tapped
plastic. This module finds the cylindrical holes in a STEP model, guesses the thread each one
was modeled for (tap drill or nominal diameter), and rebuilds the selected holes as the tapered
mounting hole the insert maker specifies. The converted model is written as a new STEP file.

Insert and hole sizes (INSERT_TABLE) come from the PennEngineering SI(R) "Threaded Inserts for
Plastics" bulletin, page SI-5, "Tapered Thru-Threaded, IUA, IUB and IUC Inserts", Hole Size in
Material columns (datasheet linked from https://www.pemnet.com, file
https://damlite.pemnet.com/IUB-440-1_pdf_1.pdf, read 2026-10-08). The mounting hole in that
bulletin is: diameter F at the surface, an 8 degree included taper over the reference taper
length R down to diameter D, then straight at D to the minimum hole depth. The table uses the
-2 (long) length code, which has about twice the pullout of the -1 length in the bulletin's
performance data, except M2 (only a -1 length exists). Values are stored in millimeters; the
unified rows are the bulletin's inch values times 25.4.

Tap drill diameters are the common 75 percent thread drills (for example #36 for 6-32, 2.5 mm
for M3). They are only used to recognize which thread a modeled hole was meant for.

The unit_cost values are placeholders, not supplier prices: replace them with your own in the
shop rates (config key additive.inserts).
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

from . import cad

IN = 25.4
TAPER_HALF_ANGLE_DEG = 4.0  # 8 degree included taper per the PEM mounting hole drawing


def _inch(a, e, f, d, r, depth, tap, nominal, cost, code=2):
    return {"insert_length": round(a * IN, 3), "insert_od": round(e * IN, 3), "entry_d": round(f * IN, 3),
            "bottom_d": round(d * IN, 3), "taper_length": round(r * IN, 3), "min_depth": round(depth * IN, 3),
            "tap_drill": round(tap * IN, 3), "nominal": round(nominal * IN, 3), "unit_cost": cost, "length_code": code}


def _mm(a, e, f, d, r, depth, tap, nominal, cost, code=2):
    return {"insert_length": a, "insert_od": e, "entry_d": f, "bottom_d": d, "taper_length": r, "min_depth": depth,
            "tap_drill": tap, "nominal": nominal, "unit_cost": cost, "length_code": code}


# thread -> insert and hole, all lengths in mm. Columns map to the PEM bulletin: insert_length = A,
# insert_od = E (after knurl), entry_d = F, bottom_d = D, taper_length = R, min_depth = Min. Hole Depth.
INSERT_TABLE: dict[str, dict] = {
    "M2": _mm(2.92, 3.58, 3.12, 3.00, 0.90, 3.94, 1.60, 2.0, 0.15, code=1),
    "M2.5": _mm(5.56, 4.37, 4.04, 3.58, 3.29, 6.58, 2.05, 2.5, 0.15),
    "M3": _mm(5.56, 4.37, 4.04, 3.58, 3.29, 6.58, 2.50, 3.0, 0.15),
    "M4": _mm(7.92, 6.35, 5.94, 5.28, 4.72, 8.94, 3.30, 4.0, 0.20),
    "M5": _mm(9.53, 7.54, 7.03, 6.25, 5.58, 10.55, 4.20, 5.0, 0.25),
    "M6": _mm(12.70, 9.52, 9.22, 8.15, 7.65, 13.72, 5.00, 6.0, 0.35),
    "M8": _mm(14.27, 11.91, 11.38, 10.19, 8.51, 15.29, 6.80, 8.0, 0.60),
    "#2-56": _inch(.188, .141, .123, .107, .114, .228, .0700, .086, 0.15),
    "#4-40": _inch(.219, .172, .159, .141, .129, .259, .0890, .112, 0.15),
    "#6-32": _inch(.250, .219, .206, .185, .150, .290, .1065, .138, 0.18),
    "#8-32": _inch(.312, .250, .234, .208, .186, .352, .1360, .164, 0.20),
    "#10-24": _inch(.375, .297, .277, .246, .222, .415, .1495, .190, 0.25),
    "#10-32": _inch(.375, .297, .277, .246, .222, .415, .1590, .190, 0.25),
    "1/4-20": _inch(.500, .375, .363, .321, .300, .540, .2010, .250, 0.35),
    "5/16-18": _inch(.562, .469, .448, .401, .336, .602, .2570, .3125, 0.50),
    "3/8-16": _inch(.625, .563, .540, .488, .372, .665, .3125, .375, 0.65),
}

DEFAULT_CONFIG = {
    "minutes_each": 0.75,  # heat-set install time per insert
    "default_unit_cost": 0.25,  # used for threaded_holes counts on models that were not converted
    "threads": INSERT_TABLE,
}

MATCH_TOL_MM = 0.15
EXTEND_MM = 0.5  # cutting tools start this far outside the surface
WALL_MM = 0.4  # minimum plastic left around an insert hole before we warn


class InsertError(cad.CadError):
    pass


def table(config: dict | None = None) -> dict[str, dict]:
    """The effective thread table (defaults merged with the shop's overrides)."""
    if config and isinstance(config.get("additive", {}).get("inserts", {}).get("threads"), dict):
        return config["additive"]["inserts"]["threads"]
    return INSERT_TABLE


def thread_system(name: str) -> str:
    return "metric" if name.upper().startswith("M") else "inch"


def guess_thread(hole_diameter_mm: float, prefer: str | None = None, threads: dict | None = None) -> dict | None:
    """Match a modeled hole to a thread by its tap drill or nominal diameter (within 0.15 mm).

    Tap drill matches win over nominal matches (CAD hole wizards model the tap drill), then the
    closest diameter. `prefer` ("metric" or "inch") breaks near-ties between systems.
    Returns {thread, match: "tap_drill"|"nominal", diameter_mm, off_mm} or None.
    """
    best = None
    for name, t in (threads or INSERT_TABLE).items():
        for kind, rank in (("tap_drill", 0), ("nominal", 1)):
            d = float(t.get(kind) or 0)
            off = abs(d - hole_diameter_mm)
            if d and off <= MATCH_TOL_MM:
                pref = 0 if prefer and thread_system(name) == prefer else 1
                key = (rank, round(off, 2), pref, off)
                if best is None or key < best[0]:
                    best = (key, {"thread": name, "match": kind, "diameter_mm": d, "off_mm": round(off, 3)})
    return best[1] if best else None


# ---------------------------------------------------------------- OCP helpers
def _solids(shape):
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    to_solid = getattr(TopoDS, "Solid_s", None) or TopoDS.Solid
    out, ex = [], TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(to_solid(ex.Current()))
        ex.Next()
    return out


def _outside(shape, p) -> bool:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    for s in _solids(shape) or [shape]:
        st = BRepClass3d_SolidClassifier(s, gp_Pnt(*p), 1e-6).State()
        if st in (TopAbs_IN, TopAbs_ON):
            return False
    return True


def volume_mm3(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    vp = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    return abs(vp.Mass())


def _add(p, d, t):
    return tuple(pi + di * t for pi, di in zip(p, d))


def _ax2(p, d):
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    return gp_Ax2(gp_Pnt(*p), gp_Dir(*d))


def _cylinder(p, d, r, h):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

    return BRepPrimAPI_MakeCylinder(_ax2(p, d), r, h).Shape()


def _cone(p, d, r1, r2, h):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone

    return BRepPrimAPI_MakeCone(_ax2(p, d), r1, r2, h).Shape()


def _bool(kind, a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

    op = {"fuse": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "common": BRepAlgoAPI_Common}[kind](a, b)
    if not op.IsDone():
        raise InsertError(f"OpenCascade {kind} failed")
    return op.Shape()


def _clean(shape):
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    u = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
    u.Build()
    return u.Shape()


def is_valid(shape) -> bool:
    from OCP.BRepCheck import BRepCheck_Analyzer

    return bool(BRepCheck_Analyzer(shape).IsValid())


def count_faces(shape, kind: str) -> int:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane

    t = {"cone": GeomAbs_Cone, "cylinder": GeomAbs_Cylinder, "plane": GeomAbs_Plane}[kind]
    return sum(1 for f in cad._faces(shape) if BRepAdaptor_Surface(f).GetType() == t)


# ---------------------------------------------------------------- hole finding
def find_holes(shape) -> list[dict]:
    """Every cylindrical hole (concave, full circle), with split faces merged by axis line and radius.

    Each hole: id, diameter_mm, diameter_in, axis (unit vector), axis_point, start and end (mm, on
    the axis, start + depth*axis = end), depth_mm, through, open_start, open_end, open_end_name
    ("start", "end", "both" or "none"). Ids are stable for the same model.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.gp import gp_Pnt, gp_Vec

    faces = []
    for f in cad._faces(shape):
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_Cylinder:
            continue
        c = s.Cylinder()
        ax = c.Axis()
        p0 = (ax.Location().X(), ax.Location().Y(), ax.Location().Z())
        d = (ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z())
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(f)
        u, v = (umin + umax) / 2, (vmin + vmax) / 2
        pnt, nrm = gp_Pnt(), gp_Vec()
        BRepGProp_Face(f).Normal(u, v, pnt, nrm)
        radial = gp_Vec(pnt.X() - p0[0], pnt.Y() - p0[1], pnt.Z() - p0[2])
        radial = radial - gp_Vec(*d).Multiplied(radial.Dot(gp_Vec(*d)))
        if nrm.Dot(radial) >= 0:  # convex: a boss or shaft, not a hole
            continue
        faces.append({"r": c.Radius(), "p": p0, "d": d, "span": umax - umin, "v": (vmin, vmax)})

    groups: list[dict] = []
    for fc in faces:
        for g in groups:
            if abs(g["r"] - fc["r"]) < 1e-3 and cad._same_line(g["p"], g["d"], fc["p"], fc["d"], 0.01):
                # express this face's axial range on the group's axis
                sign = 1 if cad._dot(g["d"], fc["d"]) > 0 else -1
                off = cad._dot([b - a for a, b in zip(g["p"], fc["p"])], g["d"])
                lo, hi = sorted((off + sign * fc["v"][0], off + sign * fc["v"][1]))
                if lo <= g["hi"] + 1e-3 and hi >= g["lo"] - 1e-3:
                    g["lo"], g["hi"] = min(g["lo"], lo), max(g["hi"], hi)
                    g["span"] += fc["span"]
                    break
        else:
            groups.append({"r": fc["r"], "p": fc["p"], "d": fc["d"], "span": fc["span"], "lo": fc["v"][0], "hi": fc["v"][1]})

    holes = []
    for g in groups:
        if g["span"] < 2 * math.pi - 0.05:
            continue  # fillets, slots and bend radii are partial cylinders
        d = g["d"]
        start, end = _add(g["p"], d, g["lo"]), _add(g["p"], d, g["hi"])
        r = g["r"]
        # Open if points just past the end, and one radius past it, are both outside the solid.
        # The second point keeps a drill-point cone at a blind bottom from reading as open.
        open_start = _outside(shape, _add(start, d, -0.05)) and _outside(shape, _add(start, d, -(r + 0.05)))
        open_end = _outside(shape, _add(end, d, 0.05)) and _outside(shape, _add(end, d, r + 0.05))
        holes.append({
            "diameter_mm": round(2 * r, 4), "diameter_in": round(2 * r / IN, 4),
            "axis": [round(x, 6) for x in d], "axis_point": [round(x, 4) for x in g["p"]],
            "start": [round(x, 4) for x in start], "end": [round(x, 4) for x in end],
            "depth_mm": round(g["hi"] - g["lo"], 4), "through": open_start and open_end,
            "open_start": open_start, "open_end": open_end,
            "open_end_name": "both" if open_start and open_end else "start" if open_start else "end" if open_end else "none",
        })
    holes.sort(key=lambda h: (round(h["diameter_mm"], 2), *[round((a + b) / 2, 2) for a, b in zip(h["start"], h["end"])]))
    for i, h in enumerate(holes, 1):
        h["id"] = f"h{i}"
    return holes


def describe_holes(shape, config: dict | None = None, prefer: str | None = None) -> list[dict]:
    """find_holes plus the guessed thread and its insert hole spec."""
    threads = table(config)
    out = []
    for h in find_holes(shape):
        g = guess_thread(h["diameter_mm"], prefer, threads)
        h = {**h, "guess": g, "insert": dict(threads[g["thread"]], thread=g["thread"]) if g else None}
        out.append(h)
    return out


# ---------------------------------------------------------------- conversion
def _frustum_volume(r1, r2, h):
    return math.pi * h * (r1 * r1 + r1 * r2 + r2 * r2) / 3


def _fill(shape, hole):
    """Fuse a cylinder into the hole. It runs a little past each end; the new hole cuts the excess
    off open ends (the insert hole is wider than the old hole), and past a blind bottom it only
    overlaps material, filling any drill-point cone."""
    d, r = hole["axis"], hole["diameter_mm"] / 2
    lo = -0.1 if hole["open_start"] else -(0.6 * r + 0.1)
    hi = hole["depth_mm"] + (0.1 if hole["open_end"] else 0.6 * r + 0.1)
    return _bool("fuse", shape, _cylinder(_add(hole["start"], d, lo), d, r, hi - lo))


def _inside_fraction(solid, tool) -> float:
    v = volume_mm3(tool)
    return volume_mm3(_bool("common", solid, tool)) / v if v else 1.0


def _plan(hole, spec, from_end):
    """Where the insert hole starts, which way it goes, and how deep."""
    if from_end == "auto":
        from_end = "start" if hole["open_start"] else "end" if hole["open_end"] else None
    if from_end not in ("start", "end"):
        raise InsertError("closed at both ends")
    if from_end == "start" and not hole["open_start"] or from_end == "end" and not hole["open_end"]:
        raise InsertError(f"the {from_end} of this hole is not on an outside surface")
    ax = hole["axis"]
    if from_end == "start":
        top, u = tuple(hole["start"]), tuple(ax)
    else:
        top, u = tuple(hole["end"]), tuple(-x for x in ax)
    length = hole["depth_mm"]
    depth = length if hole["through"] else max(spec["min_depth"], length)
    return top, u, length, depth


def _hole_tool(top, u, spec, depth, through, length):
    """Tapered mounting hole as a list of tool solids: cone from entry_d (extended outside the
    surface) to bottom_d over taper_length, then a straight bore at bottom_d."""
    rf, rd, tl = spec["entry_d"] / 2, spec["bottom_d"] / 2, spec["taper_length"]
    k = (rf - rd) / tl if tl > 0 else 0.0
    tools = [_cone(_add(top, u, -EXTEND_MM), u, rf + k * EXTEND_MM, rd, tl + EXTEND_MM)]
    bottom = length + EXTEND_MM if through else depth
    if bottom > tl:
        tools.append(_cylinder(_add(top, u, tl - 0.01), u, rd, bottom - tl + 0.01))
    vol = _frustum_volume(rf, rd, tl) + math.pi * rd * rd * max((length if through else depth) - tl, 0)
    return tools, vol


def convert(shape, selections: list[dict], config: dict | None = None) -> dict:
    """Rebuild selected holes as tapered heat-set insert holes.

    selections: [{hole_id, thread, from_end: "auto"|"start"|"end"}]. Returns {shape, inserts,
    warnings, skipped, volume_before, volume_after, expected_volume}. Holes that would break out
    of the part are skipped with a warning. Raises InsertError when nothing could be converted.
    """
    threads = table(config)
    holes = {h["id"]: h for h in find_holes(shape)}
    warnings: list[str] = []
    skipped: list[dict] = []
    inserts: list[dict] = []
    v0 = volume_mm3(shape)
    expected = v0
    work = shape
    seen = set()
    for sel in selections or []:
        hid, thread = sel.get("hole_id"), sel.get("thread")
        if not thread:
            continue
        if hid in seen:
            continue
        seen.add(hid)
        hole = holes.get(hid)
        if not hole:
            warnings.append(f"Hole {hid} not found in the model.")
            skipped.append({"hole_id": hid, "reason": "not found"})
            continue
        spec = threads.get(thread)
        if not spec:
            warnings.append(f"No insert size for thread '{thread}' (hole {hid}).")
            skipped.append({"hole_id": hid, "reason": "unknown thread"})
            continue
        label = f"Hole {hid} (Ø{hole['diameter_mm']:.2f} mm)"
        try:
            top, u, length, depth = _plan(hole, spec, sel.get("from_end") or "auto")
        except InsertError as exc:
            warnings.append(f"{label} skipped: {exc}.")
            skipped.append({"hole_id": hid, "reason": str(exc)})
            continue
        if spec["entry_d"] <= hole["diameter_mm"]:
            warnings.append(f"{label} skipped: it is already as wide as the {thread} insert hole.")
            skipped.append({"hole_id": hid, "reason": "hole already larger than the insert hole"})
            continue
        if not hole["through"] and length < spec["min_depth"]:
            warnings.append(f"{label}: blind depth {length:.2f} mm is less than the {spec['min_depth']:.2f} mm the {thread} insert needs; "
                            f"deepened to {depth:.2f} mm.")
        filled = _clean(_fill(work, hole))
        tools, hole_vol = _hole_tool(top, u, spec, depth, hole["through"], length)
        # The insert hole must stay inside the plastic: the part of the tools inside the filled
        # solid should be the whole hole volume (the tools only stick out past open ends).
        inside = sum(volume_mm3(_bool("common", filled, t)) for t in tools)
        if inside < 0.98 * hole_vol:
            warnings.append(f"{label} skipped: a {thread} insert hole would break out of the part (wall too thin).")
            skipped.append({"hole_id": hid, "reason": "wall too thin"})
            continue
        rf = spec["entry_d"] / 2
        span = (length - 0.6) if hole["through"] else (depth - 0.3 + WALL_MM)
        margin = _cylinder(_add(top, u, 0.3), u, rf + WALL_MM, max(span, 0.1))
        if _inside_fraction(filled, margin) < 0.999:
            warnings.append(f"{label}: less than {WALL_MM} mm of plastic around the {thread} insert in places. Check the wall.")
        out = filled
        for t in tools:
            out = _bool("cut", out, t)
        out = _clean(out)
        old_vol = math.pi * (hole["diameter_mm"] / 2) ** 2 * length
        expected += old_vol - hole_vol
        work = out
        inserts.append({"hole_id": hid, "thread": thread, "insert": f"PEM IU{_size_code(thread)}-{int(spec.get('length_code', 2))} size (or equal)",
                        "entry_d": spec["entry_d"], "bottom_d": spec["bottom_d"], "taper_length": spec["taper_length"],
                        "depth": round(depth if not hole["through"] else length, 3), "through": hole["through"],
                        "insert_length": spec["insert_length"], "unit_cost": spec.get("unit_cost", 0)})

    if not inserts:
        raise InsertError("No holes were converted. " + " ".join(warnings) if warnings else "No holes were selected for inserts.")
    solids = _solids(work)
    if len(solids) != 1 or not is_valid(work):
        raise InsertError("The converted model is not a valid single solid; it was not saved. " + " ".join(warnings))
    v1 = volume_mm3(work)
    if v1 >= v0:
        raise InsertError("The converted model did not lose volume as expected; it was not saved.")
    return {"shape": work, "inserts": inserts, "warnings": warnings, "skipped": skipped,
            "volume_before": round(v0, 3), "volume_after": round(v1, 3), "expected_volume": round(expected, 3)}


def _size_code(thread: str) -> str:
    codes = {"#2-56": "B-256", "#4-40": "B-440", "#6-32": "B-632", "#8-32": "B-832", "#10-24": "B-024", "#10-32": "B-032",
             "1/4-20": "B-0420", "5/16-18": "B-0518", "3/8-16": "B-0616"}
    return codes.get(thread, f"B-{thread}")


def auto_selections(shape, config: dict | None = None, prefer: str | None = None) -> list[dict]:
    """Every hole whose diameter matches a known tap drill or nominal size."""
    return [{"hole_id": h["id"], "thread": h["guess"]["thread"], "from_end": "auto"}
            for h in describe_holes(shape, config, prefer) if h["guess"] and h["open_end_name"] != "none"]


def write_step(shape, path: Path) -> None:
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    if w.Write(str(path)) != IFSelect_RetDone:
        raise InsertError("Could not write the converted STEP file.")


# ---------------------------------------------------------------- file level
def holes_for_file(file_id: str, config: dict | None = None) -> dict:
    from . import cad_quote

    d = cad_quote.load(file_id)
    shape = cad.load_step(cad_quote.step_path(file_id))
    holes = describe_holes(shape, config)
    groups: dict[tuple, dict] = {}
    for h in holes:  # same diameter and through/blind: one row in the UI
        key = (round(h["diameter_mm"], 2), h["through"])
        g = groups.setdefault(key, {"diameter_mm": h["diameter_mm"], "diameter_in": h["diameter_in"], "through": h["through"],
                                    "count": 0, "hole_ids": [], "guess": h["guess"]["thread"] if h["guess"] else None,
                                    "match": h["guess"]["match"] if h["guess"] else None})
        g["count"] += 1
        g["hole_ids"].append(h["id"])
    return {"file_id": file_id, "filename": d["filename"], "holes": holes, "groups": list(groups.values()),
            "threads": {k: v for k, v in table(config).items()}, "derived_from": d.get("derived_from"), "inserts": d.get("inserts") or []}


def convert_file(file_id: str, selections: list[dict] | None = None, auto: bool = False, config: dict | None = None) -> dict:
    """Convert holes in a stored STEP file and store the result as a new file with lineage.

    Returns the new file payload (file_id, filename, geometry, mesh, ...) plus inserts, warnings,
    skipped and derived_from. Converting a file that was already converted adds to its insert list
    and keeps derived_from pointing at the original upload.
    """
    import json

    from . import cad_quote

    src = cad_quote.load(file_id)
    shape = cad.load_step(cad_quote.step_path(file_id))
    if auto or not selections:
        selections = auto_selections(shape, config)
        if not selections:
            raise InsertError("No holes in this model match a tap drill or nominal size in the insert table. Pick the thread for each hole.")
    res = convert(shape, selections, config)
    stem = Path(src["filename"]).stem
    if stem.endswith("_inserts"):
        stem = stem[: -len("_inserts")]
    name = f"{stem}_inserts.step"
    with tempfile.TemporaryDirectory(dir=cad_quote.CAD_DIR) as tmp:
        p = Path(tmp) / name
        write_step(res["shape"], p)
        data = p.read_bytes()
    out = cad_quote.store_upload(data, name)
    meta_path = cad_quote.CAD_DIR / f"{out['file_id']}.json"
    meta = json.loads(meta_path.read_text())
    previous = src.get("inserts") or []
    meta["derived_from"] = src.get("derived_from") or file_id
    meta["inserts"] = previous + res["inserts"]
    meta_path.write_text(json.dumps(meta))
    out.update({"derived_from": meta["derived_from"], "inserts": meta["inserts"], "converted": res["inserts"],
                "warnings": res["warnings"], "skipped": res["skipped"], "volume_before_mm3": res["volume_before"],
                "volume_after_mm3": res["volume_after"], "summary": summary(res["inserts"])})
    return out


def summary(inserts: list[dict]) -> str:
    if not inserts:
        return ""
    by: dict[str, int] = {}
    for i in inserts:
        by[i["thread"]] = by.get(i["thread"], 0) + 1
    n = len(inserts)
    return f"Converted {n} hole{'s' if n != 1 else ''} for " + ", ".join(f"{c}x {t}" if len(by) > 1 else t for t, c in by.items()) + " inserts"
