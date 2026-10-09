"""DXF flat parts: read 2D profiles, measure what drives cutting cost, nest on sheets, price.

Reading (parse_dxf):
  - ezdxf reads the file (recover mode, so slightly broken files still load). Units come from the
    $INSUNITS header; a unitless file is read as inches unless the caller picks the units.
  - Blocks (INSERT) are exploded, nested blocks too. LINE, ARC, CIRCLE, LWPOLYLINE and POLYLINE
    (with bulges), SPLINE and ELLIPSE are cut geometry; splines and ellipses are approximated by short
    segments. DIMENSION, TEXT, MTEXT, leaders, hatches and points are ignored, as is anything on a
    layer whose name contains one of the ignore words (dims, notes, title block and so on, configurable).
    Lines on a layer named like "bend" are counted as bend lines, not cut.
  - Pieces are chained end to end (within a tolerance) into closed loops. A loop inside an odd number
    of other loops is a cutout; the rest are part outlines, so one DXF can hold several parts.
Measurements per part, in inches: bounding box, net area (outline minus cutouts), cut length (every
loop), pierces (one per loop), round holes and their diameters, smallest arc radius and smallest cutout.

Pricing (estimate_spec) follows the shop-rate config: laser and waterjet use the same feed model as
pricing.estimate (feed at 0.125 in for cut factor 1.0, scaled by (0.125 / thickness)^0.8 and the
material cut factor), plasma and router use the placeholder numbers under config "flat".
Material is charged on the sheet area each part takes in the nest, or on whole sheets when asked.
"""
from __future__ import annotations

import math
import re
import tempfile
from pathlib import Path

from . import pricing
from .cad_quote import SHEET_GAUGES_IN

MM_PER_IN = 25.4
UNITS = {"in": 1.0, "ft": 12.0, "mm": 1 / MM_PER_IN, "cm": 10 / MM_PER_IN, "m": 1000 / MM_PER_IN}
INSUNITS = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}  # DXF $INSUNITS codes used in shop drawings
PLATE_IN = [0.625, 0.75, 0.875, 1.0, 1.25, 1.5, 2.0]
THICKNESSES_IN = sorted(set(SHEET_GAUGES_IN) | set(PLATE_IN))
DEFAULT_IGNORE_LAYERS = ["dim", "note", "text", "title", "border", "frame", "anno", "center", "hidden", "construction", "defpoints"]
BEND_LAYER = re.compile(r"bend", re.I)
IGNORED_TYPES = {"DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION", "TEXT", "MTEXT", "ATTRIB", "ATTDEF", "LEADER", "MLEADER",
                 "MULTILEADER", "HATCH", "MPOLYGON", "POINT", "VIEWPORT", "IMAGE", "WIPEOUT", "TOLERANCE", "SOLID", "TRACE", "3DFACE",
                 "XLINE", "RAY", "REGION", "3DSOLID", "BODY", "MESH", "OLE2FRAME", "ACAD_TABLE", "TABLE", "SHAPE", "UNDERLAY",
                 "PDFUNDERLAY", "DWFUNDERLAY", "DGNUNDERLAY"}
PROCESSES = {
    "laser_cut": "Laser cutting (fiber for metal, CO2 for acrylic and acetal)",
    "waterjet": "Abrasive waterjet: any material, thick plate, no heat-affected zone",
    "plasma": "Plasma cutting: steel, stainless and aluminum plate, rougher edge",
    "router": "CNC router: plastics, wood, composites and soft aluminum sheet",
}
DEBURR = {"none": "As cut", "hand": "Hand deburr / edge break", "tumble": "Tumble or vibratory deburr"}
DEFAULT_TOL_IN = 0.005


class FlatError(ValueError):
    pass


def material_class(name: str) -> str:
    n = (name or "").lower()
    if any(w in n for w in ("stainless", "steel", "a36", "1018", "4140")):
        return "ferrous"
    if any(w in n for w in ("aluminum", "brass", "copper", "bronze", "titanium")):
        return "nonferrous"
    if any(w in n for w in ("plywood", "mdf", "birch", "wood", "hardboard")):
        return "wood"
    if any(w in n for w in ("g10", "fr4", "carbon", "fiberglass", "garolite")):
        return "composite"
    return "plastic"


# ---------------------------------------------------------------- geometry helpers
def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _poly_len(pts) -> float:
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _signed_area(pts) -> float:
    n = len(pts)
    return sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n)) / 2


def _bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _inside(pt, poly) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi:
            inside = not inside
        j = i
    return inside


def _contains(outer: dict, inner: dict) -> bool:
    """Loop `inner` lies inside loop `outer` (most of a sample of its vertices are inside)."""
    a, b = outer["bbox"], inner["bbox"]
    if b[0] < a[0] - 1e-9 or b[1] < a[1] - 1e-9 or b[2] > a[2] + 1e-9 or b[3] > a[3] + 1e-9:
        return False
    if inner["area"] >= outer["area"]:
        return False
    pts = inner["pts"]
    step = max(1, len(pts) // 7)
    sample = pts[::step][:8]
    hits = sum(1 for p in sample if _inside(p, outer["pts"]))
    return hits * 2 > len(sample)


# ---------------------------------------------------------------- reading the DXF
def _layer_ignored(layer: str, words: list[str]) -> bool:
    lay = (layer or "").lower()
    return any(w and w in lay for w in words)


def _explode(entity, depth: int = 0):
    """Yield drawable entities, expanding block references (nested up to 8 deep)."""
    if entity.dxftype() == "INSERT":
        if depth > 8:
            return
        try:
            subs = list(entity.virtual_entities())
        except Exception:  # noqa: BLE001  (non-uniform scaling of some entities is unsupported)
            return
        for e in subs:
            # entities on layer "0" inside a block take the insert's layer
            if (e.dxf.get("layer", "0") or "0") == "0":
                e.dxf.layer = entity.dxf.get("layer", "0")
            yield from _explode(e, depth + 1)
    else:
        yield entity


def _pieces_from(entity, scale: float, sag: float) -> list[dict]:
    """Turn one entity into pieces: {pts (inches), len, radius, kind, closed, diameter}."""
    t = entity.dxftype()

    def P(v):
        return (v[0] * scale, v[1] * scale)

    if t == "LINE":
        a, b = P(entity.dxf.start), P(entity.dxf.end)
        if _dist(a, b) < 1e-9:
            return []
        return [{"pts": [a, b], "len": _dist(a, b), "radius": None, "kind": "line", "closed": False}]
    if t == "ARC":
        r = entity.dxf.radius * scale
        sweep = (entity.dxf.end_angle - entity.dxf.start_angle) % 360 or 360
        pts = [P(v) for v in entity.flattening(sag / scale)]
        if len(pts) < 2:
            return []
        closed = sweep >= 359.999
        return [{"pts": pts, "len": r * math.radians(sweep), "radius": r, "kind": "arc", "closed": closed,
                 "diameter": 2 * r if closed else None, "center": P(entity.dxf.center) if closed else None}]
    if t == "CIRCLE":
        r = entity.dxf.radius * scale
        pts = [P(v) for v in entity.flattening(sag / scale)]
        if pts and _dist(pts[0], pts[-1]) > 1e-9:
            pts.append(pts[0])
        return [{"pts": pts, "len": 2 * math.pi * r, "radius": r, "kind": "circle", "closed": True, "diameter": 2 * r,
                 "center": P(entity.dxf.center)}]
    if t in ("LWPOLYLINE", "POLYLINE"):
        if t == "POLYLINE" and (entity.is_poly_face_mesh or entity.is_polygon_mesh):
            return []
        out = []
        for sub in entity.virtual_entities():
            out += _pieces_from(sub, scale, sag)
        return out
    if t in ("ELLIPSE", "SPLINE"):
        try:
            pts = [P(v) for v in entity.flattening(sag / scale)]
        except Exception:  # noqa: BLE001
            return []
        if len(pts) < 2:
            return []
        closed = _dist(pts[0], pts[-1]) < 1e-6
        return [{"pts": pts, "len": _poly_len(pts), "radius": None, "kind": "curve", "closed": closed}]
    return []


def _dedupe(pieces: list[dict], tol: float) -> tuple[list[dict], int]:
    """Drop pieces drawn twice (same ends and midpoint) and straight lines lying on top of another line."""
    seen: dict = {}
    out, dups = [], 0
    q = lambda p: (round(p[0] / tol), round(p[1] / tol))  # noqa: E731
    for pc in pieces:
        pts = pc["pts"]
        mid = pts[len(pts) // 2]
        key = (frozenset((q(pts[0]), q(pts[-1]))), q(mid), round(pc["len"] / tol))
        if key in seen:
            dups += 1
            continue
        seen[key] = True
        out.append(pc)
    # collinear overlapping straight lines (partial overlaps): keep the longer one when one covers the other
    lines = [i for i, pc in enumerate(out) if pc["kind"] == "line"]
    drop = set()
    for ii, i in enumerate(lines):
        a0, a1 = out[i]["pts"]
        la = out[i]["len"]
        for j in lines[ii + 1:]:
            if j in drop or i in drop:
                continue
            b0, b1 = out[j]["pts"]
            lb = out[j]["len"]
            dx, dy = (a1[0] - a0[0]) / la, (a1[1] - a0[1]) / la
            off = lambda p: abs((p[0] - a0[0]) * dy - (p[1] - a0[1]) * dx)  # noqa: E731
            if off(b0) > tol or off(b1) > tol:
                continue
            s = lambda p: (p[0] - a0[0]) * dx + (p[1] - a0[1]) * dy  # noqa: E731
            lo, hi = sorted((s(b0), s(b1)))
            if hi <= tol or lo >= la - tol:
                continue  # touching end to end or apart: not an overlap
            if lo >= -tol and hi <= la + tol:
                drop.add(j)
            elif lo <= tol and hi >= la - tol:
                drop.add(i)
            dups += 1
    return [pc for k, pc in enumerate(out) if k not in drop], dups


def _chain(pieces: list[dict], tol: float) -> tuple[list[dict], list[dict]]:
    """Join pieces into loops. Returns (closed loops, open chains); each {pts, len, min_radius, diameter}."""
    loops, opens = [], []
    cell = max(tol, 1e-9)
    grid: dict[tuple, list] = {}

    def key(p):
        return (math.floor(p[0] / cell), math.floor(p[1] / cell))

    rest = []
    for i, pc in enumerate(pieces):
        if pc["closed"] or (len(pc["pts"]) > 2 and _dist(pc["pts"][0], pc["pts"][-1]) <= tol):
            loops.append({"pts": pc["pts"], "len": pc["len"], "min_radius": pc["radius"], "diameter": pc.get("diameter"), "center": pc.get("center")})
            continue
        rest.append(i)
        for end in (0, 1):
            p = pc["pts"][0 if end == 0 else -1]
            grid.setdefault(key(p), []).append((i, end))
    used = set()

    def find(p):
        kx, ky = key(p)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i, end in grid.get((kx + dx, ky + dy), []):
                    if i in used:
                        continue
                    q = pieces[i]["pts"][0 if end == 0 else -1]
                    d = _dist(p, q)
                    if d <= tol and (best is None or d < best[0]):
                        best = (d, i, end)
        return best

    for i in rest:
        if i in used:
            continue
        used.add(i)
        pts = list(pieces[i]["pts"])
        length = pieces[i]["len"]
        radii = [pieces[i]["radius"]] if pieces[i]["radius"] else []
        closed = False
        for direction in ("fwd", "back"):
            while True:
                if len(pts) > 2 and _dist(pts[0], pts[-1]) <= tol and length > 2 * tol:
                    closed = True
                    break
                m = find(pts[-1] if direction == "fwd" else pts[0])
                if not m:
                    break
                _, j, end = m
                used.add(j)
                seg = list(pieces[j]["pts"])
                if direction == "fwd":
                    seg = seg if end == 0 else seg[::-1]
                    pts += seg[1:]
                else:
                    seg = seg if end == 1 else seg[::-1]
                    pts = seg[:-1] + pts
                length += pieces[j]["len"]
                if pieces[j]["radius"]:
                    radii.append(pieces[j]["radius"])
            if closed:
                break
        item = {"pts": pts, "len": length, "min_radius": min(radii) if radii else None, "diameter": None}
        (loops if closed else opens).append(item)
    return loops, opens


def read_doc(path: Path):
    import ezdxf
    from ezdxf import recover

    try:
        doc, auditor = recover.readfile(str(path))
    except IOError as exc:
        raise FlatError("Could not read the file. Upload a DXF (ASCII or binary).") from exc
    except ezdxf.DXFStructureError as exc:
        raise FlatError(f"The DXF is damaged and could not be repaired: {exc}") from exc
    return doc


def parse_dxf(path: str | Path, units: str = "auto", ignore_layers: list[str] | None = None, tol_in: float | None = None,
              filename: str = "") -> dict:
    """Read one DXF file into parts. units: auto (from $INSUNITS, inches when unitless) or in/mm/cm/m/ft."""
    path = Path(path)
    filename = filename or path.name
    doc = read_doc(path)
    header_code = int(doc.header.get("$INSUNITS", 0) or 0)
    if units and units != "auto":
        if units not in UNITS:
            raise FlatError(f"units must be auto or one of {list(UNITS)}")
        unit, units_source = units, "chosen"
    elif header_code in INSUNITS:
        unit, units_source = INSUNITS[header_code], "file header"
    else:
        unit, units_source = "in", "assumed (the file has no units)"
    scale = UNITS[unit]
    tol = tol_in or DEFAULT_TOL_IN
    words = [w.strip().lower() for w in (ignore_layers if ignore_layers is not None else DEFAULT_IGNORE_LAYERS) if w.strip()]
    sag = 0.001  # inches of chord error when approximating arcs and curves

    pieces: list[dict] = []
    bend_lines: list[dict] = []
    ignored: dict[str, int] = {}
    ignored_layers: dict[str, int] = {}
    for top in doc.modelspace():
        for e in _explode(top):
            t = e.dxftype()
            layer = e.dxf.get("layer", "0")
            if t in IGNORED_TYPES:
                ignored[t] = ignored.get(t, 0) + 1
                continue
            if BEND_LAYER.search(layer or "") and t in ("LINE", "LWPOLYLINE", "POLYLINE"):
                for pc in _pieces_from(e, scale, sag):
                    bend_lines.append({"pts": pc["pts"], "len": pc["len"]})
                continue
            if _layer_ignored(layer, words):
                ignored_layers[layer] = ignored_layers.get(layer, 0) + 1
                continue
            got = _pieces_from(e, scale, sag)
            if not got and t not in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE"):
                ignored[t] = ignored.get(t, 0) + 1
            pieces += got

    warnings: list[str] = []
    if units_source.startswith("assumed"):
        warnings.append("The DXF has no units ($INSUNITS is unset). Read as inches: pick the units if that is wrong.")
    pieces, dups = _dedupe(pieces, tol)
    if dups:
        warnings.append(f"{dups} duplicate or overlapping line(s) removed. Clean them up in CAD so the cutter does not cut twice.")
    loops, opens = _chain(pieces, tol)
    for lp in loops:
        pts = lp["pts"]
        if _dist(pts[0], pts[-1]) > 1e-12:
            pts = pts + [pts[0]]
        lp["pts"] = pts[:-1] if len(pts) > 3 else pts
        lp["area"] = abs(_signed_area(lp["pts"]))
        lp["bbox"] = _bbox(lp["pts"])
        if lp.get("diameter") and lp.get("center"):  # exact values for circles (the polygon is inscribed)
            r, (cx, cy) = lp["diameter"] / 2, lp["center"]
            lp["area"] = math.pi * r * r
            lp["bbox"] = (cx - r, cy - r, cx + r, cy + r)
    loops = [lp for lp in loops if lp["area"] > tol * tol]
    loops.sort(key=lambda lp: -lp["area"])
    for i, lp in enumerate(loops):
        parents = [j for j in range(i) if _contains(loops[j], lp)]
        lp["depth"] = len(parents)
        lp["parent"] = max(parents, key=lambda j: loops[j]["depth"]) if parents else None
    parts = []
    for i, lp in enumerate(loops):
        if lp["depth"] % 2:
            continue
        holes = [h for h in loops if h["depth"] == lp["depth"] + 1 and h["parent"] == i]
        parts.append(_part_metrics(lp, holes, bend_lines))
    if opens:
        total = sum(o["len"] for o in opens)
        warnings.append(f"{len(opens)} open contour(s), {total:.2f} in long, are not closed loops and were left out of the parts. "
                        "Close the gaps in CAD (or raise the join tolerance) if they should be cut.")
    if ignored:
        warnings.append("Ignored " + ", ".join(f"{n} {t.lower()}" for t, n in sorted(ignored.items())) + " (text, dimensions and annotation are not cut).")
    if ignored_layers:
        warnings.append("Ignored layers: " + ", ".join(f"{k} ({v})" for k, v in sorted(ignored_layers.items())) + ".")
    if not parts:
        warnings.append("No closed profiles found. Check the units and layers, or export the flat pattern again as DXF.")

    # identical parts drawn several times become one line with a quantity
    grouped: list[dict] = []
    for p in parts:
        for g in grouped:
            if (abs(g["net_area"] - p["net_area"]) <= max(0.002 * p["net_area"], 1e-4) and abs(g["cut_length"] - p["cut_length"]) <= 0.01 * p["cut_length"] + 0.01
                    and _same_dims(g, p)):
                g["qty"] += 1
                g["instances"].append(p["outline"])
                break
        else:
            p["qty"] = 1
            p["instances"] = [p["outline"]]
            grouped.append(p)
    stem = Path(filename).stem
    for n, p in enumerate(grouped, 1):
        p["name"] = stem if len(grouped) == 1 else f"{stem} part {n}"
        p["index"] = n

    svg = render_svg(parts, [h for h in loops if h["depth"] % 2], opens, bend_lines)
    out_parts = [{k: v for k, v in p.items() if k not in ("outline", "instances", "_loop", "_holes")} for p in grouped]
    return {"filename": filename, "units": unit, "units_source": units_source, "insunits": header_code, "scale_to_in": scale,
            "parts": out_parts, "open_contours": len(opens), "duplicates_removed": dups, "ignored": ignored,
            "ignored_layers": ignored_layers, "bend_lines": len(bend_lines), "warnings": warnings, "svg": svg,
            "extents": _extents(loops, opens)}


def _same_dims(a: dict, b: dict) -> bool:
    """Same bounding box within 0.005 in, either way round."""
    return all(abs(x - y) <= 0.005 for x, y in zip(sorted((a["width"], a["height"])), sorted((b["width"], b["height"]))))


def _extents(loops, opens):
    pts = [p for lp in loops for p in lp["pts"]] + [p for o in opens for p in o["pts"]]
    if not pts:
        return None
    x0, y0, x1, y1 = _bbox(pts)
    return {"width": round(x1 - x0, 4), "height": round(y1 - y0, 4)}


def _part_metrics(outer: dict, holes: list[dict], bend_lines: list[dict]) -> dict:
    x0, y0, x1, y1 = outer["bbox"]
    hole_rows = []
    diam: dict[float, int] = {}
    for h in holes:
        hx0, hy0, hx1, hy1 = h["bbox"]
        row = {"length": round(h["len"], 4), "width": round(hx1 - hx0, 4), "height": round(hy1 - hy0, 4), "area": round(h["area"], 4)}
        if h.get("diameter"):
            row["diameter"] = round(h["diameter"], 4)
            diam[round(h["diameter"], 4)] = diam.get(round(h["diameter"], 4), 0) + 1
        hole_rows.append(row)
    radii = [r for r in [outer["min_radius"]] + [h["min_radius"] for h in holes] if r]
    smallest_cutout = min((min(r["width"], r["height"]) for r in hole_rows), default=None)
    bends = 0
    for b in bend_lines:
        mx = (b["pts"][0][0] + b["pts"][-1][0]) / 2
        my = (b["pts"][0][1] + b["pts"][-1][1]) / 2
        if _inside((mx, my), outer["pts"]):
            bends += 1
    net = outer["area"] - sum(h["area"] for h in holes)
    return {
        "width": round(x1 - x0, 4), "height": round(y1 - y0, 4),
        "outer_area": round(outer["area"], 4), "net_area": round(net, 4),
        "cut_length": round(outer["len"] + sum(h["len"] for h in holes), 4),
        "outer_length": round(outer["len"], 4),
        "pierces": 1 + len(holes), "cutouts": len(holes), "round_holes": sum(diam.values()),
        "hole_diameters": [{"diameter": d, "count": c} for d, c in sorted(diam.items())],
        "holes": hole_rows[:200],
        "min_radius": round(min(radii), 4) if radii else None,
        "smallest_cutout": round(smallest_cutout, 4) if smallest_cutout is not None else None,
        "bend_lines": bends, "bends": bends, "pem": 0,
        "outline": outer,
    }


# ---------------------------------------------------------------- SVG preview
def _path_d(pts, x0, y1) -> str:
    return "M" + " L".join(f"{p[0] - x0:.4f},{y1 - p[1]:.4f}" for p in pts) + " Z"


def render_svg(parts: list[dict], hole_loops: list[dict], opens: list[dict], bend_lines: list[dict]) -> str:
    """A self-contained SVG: part outlines filled, cutouts outlined in orange, open contours dashed red,
    bend lines dashed blue. Y is flipped so the drawing reads as in CAD."""
    allpts = [p for pt in parts for p in pt["outline"]["pts"]] + [p for o in opens for p in o["pts"]]
    if not allpts:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 4"><text x="1" y="2.5" font-size="1" fill="#888">No closed profiles</text></svg>'
    x0, y0, x1, y1 = _bbox(allpts)
    w, h = max(x1 - x0, 1e-3), max(y1 - y0, 1e-3)
    pad = 0.04 * max(w, h)
    vb = f"{-pad:.4f} {-pad:.4f} {w + 2 * pad:.4f} {h + 2 * pad:.4f}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" preserveAspectRatio="xMidYMid meet" class="dxf-svg">']
    ns = 'vector-effect="non-scaling-stroke"'
    for i, p in enumerate(parts):
        d = _path_d(p["outline"]["pts"], x0, y1)
        out.append(f'<path d="{d}" fill="#dbe7f3" fill-opacity="0.85" stroke="#1f4e79" stroke-width="1.5" {ns}/>')
    for hl in hole_loops:
        out.append(f'<path d="{_path_d(hl["pts"], x0, y1)}" fill="#ffffff" stroke="#c2410c" stroke-width="1.3" {ns}/>')
    for o in opens:
        pts = " ".join(f"{p[0] - x0:.4f},{y1 - p[1]:.4f}" for p in o["pts"])
        out.append(f'<polyline points="{pts}" fill="none" stroke="#dc2626" stroke-width="2" stroke-dasharray="6 4" {ns}/>')
    for b in bend_lines:
        pts = " ".join(f"{p[0] - x0:.4f},{y1 - p[1]:.4f}" for p in b["pts"])
        out.append(f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="1.2" stroke-dasharray="8 3 2 3" {ns}/>')
    fs = max(w, h) * 0.035
    for p in parts:
        bx0, by0, bx1, by1 = p["outline"]["bbox"]
        label = p.get("index") or ""
        if label:
            out.append(f'<text x="{(bx0 + bx1) / 2 - x0:.4f}" y="{y1 - (by0 + by1) / 2:.4f}" font-size="{fs:.4f}" fill="#1f4e79" '
                       f'text-anchor="middle" dominant-baseline="middle" font-family="sans-serif">{int(label)}</text>')
    out.append("</svg>")
    return "".join(out)


def parse_files(files: list[tuple[str, bytes]], units: str = "auto", ignore_layers: list[str] | None = None, tol_in: float | None = None) -> dict:
    """Parse several DXF uploads. Parts get ids f{file}p{n} and keep their file name."""
    out_files, parts, warnings = [], [], []
    for fi, (name, data) in enumerate(files, 1):
        if not data:
            raise FlatError(f"{name} is empty.")
        if not re.search(r"\.dxf$", name or "", re.I):
            raise FlatError(f"{name}: upload DXF files (.dxf). Export the flat pattern from your CAD tool as DXF.")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "upload.dxf"
            p.write_bytes(data)
            r = parse_dxf(p, units, ignore_layers, tol_in, filename=name)
        # the SVG labels use the per-file index; keep that numbering for the part names
        for prt in r["parts"]:
            prt["id"] = f"f{fi}p{prt['index']}"
            prt["file"] = name
            parts.append(prt)
        warnings += [f"{name}: {w}" for w in r["warnings"]] if len(files) > 1 else r["warnings"]
        out_files.append(r)
    return {"files": out_files, "parts": parts, "warnings": warnings}


# ---------------------------------------------------------------- nesting
def parts_per_sheet(w: float, h: float, sheet_w: float, sheet_l: float, spacing: float, margin: float) -> dict:
    """Grid nest of a part's bounding box on a sheet, best of the two 90 degree orientations."""
    uw, ul = sheet_w - 2 * margin, sheet_l - 2 * margin
    best = {"count": 0, "rotated": False, "cols": 0, "rows": 0}
    if w <= 0 or h <= 0:
        return best
    for rot, (a, b) in ((False, (w, h)), (True, (h, w))):
        cols = math.floor((uw + spacing) / (a + spacing)) if uw >= a else 0
        rows = math.floor((ul + spacing) / (b + spacing)) if ul >= b else 0
        if cols * rows > best["count"]:
            best = {"count": cols * rows, "rotated": rot, "cols": cols, "rows": rows}
    return best


def nest(parts: list[dict], quantities: list[int], sheet: dict, spacing: float, margin: float) -> dict:
    """Per part: parts per sheet and utilization. Per quantity (sets): sheets needed when each part
    type is nested on its own sheets and partial sheets are shared, rounded up."""
    sw, sl = float(sheet["width"]), float(sheet["length"])
    sheet_area = sw * sl
    rows = []
    for p in parts:
        n = parts_per_sheet(p["width"], p["height"], sw, sl, spacing, margin)
        rows.append({"id": p.get("id"), "name": p.get("name"), "per_sheet": n["count"], "rotated": n["rotated"], "grid": f"{n['cols']} x {n['rows']}",
                     "utilization_pct": round(n["count"] * p["net_area"] / sheet_area * 100, 1) if n["count"] else 0.0,
                     "sheet_area_per_part": round(sheet_area / n["count"], 3) if n["count"] else None})
    by_q = {}
    for q in quantities:
        frac = sum(p.get("qty", 1) * q / r["per_sheet"] for p, r in zip(parts, rows) if r["per_sheet"])
        sheets = math.ceil(frac - 1e-9) if frac else 0
        used = sum(p.get("qty", 1) * q * p["net_area"] for p in parts)
        by_q[q] = {"sheets": sheets, "sheet_fraction": round(frac, 3), "utilization_pct": round(used / (sheets * sheet_area) * 100, 1) if sheets else 0.0}
    return {"sheet": {"width": sw, "length": sl}, "spacing_in": spacing, "edge_margin_in": margin, "parts": rows, "by_quantity": by_q}


# ---------------------------------------------------------------- pricing
def _line(category, item, cost, *, basis="per_set", hours=None, rate=None, note=""):
    return {"category": category, "item": item, "basis": basis, "hours": None if hours is None else round(hours, 3),
            "rate": rate, "cost": round(cost, 2), "note": note}


def _f(v, default=0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def materials(cfg: dict) -> dict[str, dict]:
    """Every material a flat part can be cut from: the shop materials plus the sheet goods under flat.materials."""
    out = {k: dict(v) for k, v in cfg["materials"].items()}
    for k, v in (cfg.get("flat") or {}).get("materials", {}).items():
        out[k] = {"machinability": 1.0, **v}
    return out


def cut_speed(process: str, thickness: float, mat: dict, cfg: dict) -> float:
    """Feed in inches per minute. Laser and waterjet match pricing.estimate exactly."""
    fl = cfg["flat"]
    if process == "laser_cut":
        return cfg["laser_ipm_at_0125"] * (0.125 / thickness) ** 0.8 / mat["cut_factor"]
    if process == "waterjet":
        return cfg["waterjet_ipm_at_0125"] * (0.125 / thickness) ** 0.8 / mat["cut_factor"]
    if process == "plasma":
        return fl["plasma_ipm_at_0125"] * (0.125 / thickness) ** 0.8 / mat["cut_factor"]
    passes = max(1, math.ceil(thickness / max(fl["router_max_depth_per_pass_in"], 0.01) - 1e-9))
    return fl["router_ipm"] / mat["cut_factor"] / passes


def _sheet(opts: dict, cfg: dict) -> dict:
    sizes = cfg["flat"]["sheet_sizes"]
    name = opts.get("sheet") or next(iter(sizes))
    if name == "custom":
        w, l = _f(opts.get("sheet_width")), _f(opts.get("sheet_length"))
        if w <= 0 or l <= 0:
            raise pricing.SpecError("Give the custom sheet width and length in inches.")
        return {"name": f"{w:g} x {l:g}", "width": w, "length": l}
    if name not in sizes:
        raise pricing.SpecError(f"sheet must be one of {list(sizes) + ['custom']}")
    return {"name": name, **sizes[name]}


def estimate(parts: list[dict], options: dict, quantities: list[int], config: dict | None = None) -> dict:
    """Price a set of flat parts (each with its qty per set) at each set quantity.

    options: process, material, thickness, sheet ("48 x 96" | custom with sheet_width/sheet_length),
    spacing_in, edge_margin_in, full_sheets (bool), deburr (none|hand|tumble), finishes [names],
    pem_unit_cost, first_article, material_certs, packaging, freight_per_lot, tolerance.
    Each part: width, height, net_area, cut_length, pierces, qty, bends, pem, include.
    """
    cfg = pricing.merged_config(config)
    fl = cfg["flat"]
    rates = cfg["rates"]
    warnings: list[str] = []
    assumptions: list[str] = []
    try:
        qtys = sorted({int(q) for q in (quantities or [1]) if int(q) > 0})
    except (TypeError, ValueError):
        raise pricing.SpecError("quantities must be positive integers")
    if not qtys:
        raise pricing.SpecError("Give at least one quantity")
    process = options.get("process") or "laser_cut"
    if process not in PROCESSES:
        raise pricing.SpecError(f"process must be one of {list(PROCESSES)}")
    mats = materials(cfg)
    mat_name = options.get("material") or "A36 / 1018 steel"
    mat = mats.get(mat_name)
    if mat is None:
        raise pricing.SpecError(f"Unknown material '{mat_name}'. Known: {sorted(mats)}")
    t = _f(options.get("thickness"), 0.125)
    if t <= 0:
        raise pricing.SpecError("thickness must be more than zero")
    cls = material_class(mat_name)
    if process == "plasma" and cls not in ("ferrous", "nonferrous"):
        raise pricing.SpecError("Plasma only cuts conductive metals. Use laser, waterjet or router for this material.")
    if process == "router" and cls == "ferrous":
        raise pricing.SpecError("A CNC router cannot cut steel or stainless. Use laser, plasma or waterjet.")
    if process == "laser_cut" and cls in ("wood", "composite"):
        warnings.append(f"Laser cutting {mat_name} chars or gives off harmful fumes: router or waterjet is usually the better choice.")
    if process == "laser_cut" and cls == "plastic" and "acrylic" not in mat_name.lower() and "delrin" not in mat_name.lower() and "acetal" not in mat_name.lower():
        warnings.append(f"Check that {mat_name} can be laser cut: polycarbonate and PVC cut poorly or give off harmful fumes.")
    if process == "laser_cut" and t > 0.75:
        warnings.append(f"Laser cutting {t} in plate: confirm your laser's capacity or use waterjet or plasma.")
    if process == "plasma" and t < 0.06:
        warnings.append("Thin sheet on a plasma table warps and has a wide kerf: laser is usually better under 0.060 in.")
    tol_name = options.get("tolerance") or "standard"
    tol_mult = cfg["tolerance_multiplier"].get(tol_name)
    if tol_mult is None:
        raise pricing.SpecError(f"tolerance must be one of {list(cfg['tolerance_multiplier'])}")

    use = [p for p in parts if p.get("include", True) is not False and int(_f(p.get("qty"), 1)) > 0]
    if not use:
        raise pricing.SpecError("No parts to price. Upload a DXF with closed profiles or include at least one part.")
    for p in use:
        p["qty"] = int(_f(p.get("qty"), 1))
        for k in ("width", "height", "net_area", "cut_length"):
            if _f(p.get(k)) <= 0:
                raise pricing.SpecError(f"Part '{p.get('name') or p.get('id')}' is missing {k}")
    sheet = _sheet(options, cfg)
    spacing = _f(options.get("spacing_in"), fl["spacing_in"])
    margin = _f(options.get("edge_margin_in"), fl["edge_margin_in"])
    nst = nest(use, qtys, sheet, spacing, margin)
    for p, r in zip(use, nst["parts"]):
        if not r["per_sheet"]:
            raise pricing.SpecError(f"Part '{p.get('name')}' ({p['width']:g} x {p['height']:g} in) does not fit on a {sheet['name']} sheet with the edge margin. Pick a bigger sheet.")
    parts_per_set = sum(p["qty"] for p in use)

    per_set: list[dict] = []
    per_lot: list[dict] = []
    lb_per_in2 = t * mat["density"]
    sheet_cost = sheet["width"] * sheet["length"] * lb_per_in2 * mat["price_per_lb"]
    full_sheets = bool(options.get("full_sheets"))
    weight_set = 0.0
    minutes_cut_set = 0.0
    ipm = cut_speed(process, t, mat, cfg)
    pierce_min = cfg["pierce_minutes"] if process in ("laser_cut", "waterjet") else fl["pierce_minutes"][process]
    rate = rates[process] if process in ("laser_cut", "waterjet") else fl["rates"][process]
    for p, r in zip(use, nst["parts"]):
        weight_set += p["net_area"] * lb_per_in2 * p["qty"]
        if not full_sheets:
            mcost = r["sheet_area_per_part"] * lb_per_in2 * mat["price_per_lb"] * p["qty"]
            per_set.append(_line("material", f"{p.get('name') or p.get('id')} x{p['qty']}", mcost, rate=mat["price_per_lb"],
                                 note=f"{r['per_sheet']} per {sheet['name']} sheet ({r['utilization_pct']}% used), {t:g} in {mat_name}"))
        minutes = p["cut_length"] / max(ipm, 0.1) + int(_f(p.get("pierces"), 1)) * pierce_min + cfg["handling_minutes"]
        minutes_cut_set += minutes * p["qty"]
    if full_sheets:
        assumptions.append(f"Material charged as whole {sheet['name']} sheets at ${sheet_cost:,.2f} each (see nesting).")
    total_cut = sum(p["cut_length"] * p["qty"] for p in use)
    total_pierce = sum(int(_f(p.get("pierces"), 1)) * p["qty"] for p in use)
    h = minutes_cut_set / 60
    per_set.append(_line("cutting", f"{PROCESSES[process].split(':')[0].split(' (')[0]} at {ipm:.0f} in/min", h * rate, hours=h, rate=rate,
                         note=f"{total_cut:.1f} in of cut, {total_pierce} pierces"))
    if process == "router":
        assumptions.append("Router inside corners take the bit radius; sharp inside corners need a relief or a second operation.")

    deburr = options.get("deburr") or "hand"
    db = fl["deburr"]
    if deburr == "hand":
        mins = sum((db["hand_minutes_base"] + db["hand_minutes_per_inch"] * p["cut_length"]) * p["qty"] for p in use) * tol_mult
        per_set.append(_line("labor", "hand deburr / edge break", mins / 60 * rates["deburr"], hours=mins / 60, rate=rates["deburr"]))
    elif deburr == "tumble":
        mins = db["tumble_minutes_per_part"] * parts_per_set
        per_set.append(_line("labor", "tumble deburr", mins / 60 * rates["deburr"], hours=mins / 60, rate=rates["deburr"]))
        per_lot.append(_line("setup", "tumble media and load", db["tumble_lot_hours"] * rates["deburr"], basis="per_lot", hours=db["tumble_lot_hours"], rate=rates["deburr"]))
    elif deburr != "none":
        raise pricing.SpecError(f"deburr must be one of {list(DEBURR)}")

    bends = sum(int(_f(p.get("bends"))) * p["qty"] for p in use)
    if bends:
        mins = bends * cfg["brake_minutes_per_bend"] * tol_mult + cfg["handling_minutes"] * sum(p["qty"] for p in use if _f(p.get("bends")))
        per_set.append(_line("forming", f"press brake, {bends} bend(s) per set", mins / 60 * rates["press_brake"], hours=mins / 60, rate=rates["press_brake"]))
        su = cfg["setup_hours"]["press_brake"]
        per_lot.append(_line("setup", "press brake tooling setup", su * rates["press_brake"], basis="per_lot", hours=su, rate=rates["press_brake"]))
        if t > 0.25:
            warnings.append("Forming plate over 1/4 in: check your brake tonnage and the minimum bend radius for this material.")
    pem = sum(int(_f(p.get("pem"))) * p["qty"] for p in use)
    if pem:
        unit = _f(options.get("pem_unit_cost"), fl["pem"]["unit_cost"])
        per_set.append(_line("hardware", f"{pem} PEM self-clinching fastener(s)", pem * unit, note="purchased hardware, placeholder price" if options.get("pem_unit_cost") in (None, "") else ""))
        hh = pem * fl["pem"]["minutes_each"] / 60
        per_set.append(_line("hardware", "press in PEM hardware", hh * rates["fabrication"], hours=hh, rate=rates["fabrication"]))

    # programming and setup: one program per part type, setup per lot
    if process in ("laser_cut", "waterjet"):
        prog_h, su_h = cfg["programming_hours_per_setup"][process], cfg["setup_hours"][process]
    else:
        prog_h, su_h = fl["programming_hours"][process], fl["setup_hours"][process]
    prog_h *= 1 + 0.25 * (len(use) - 1)
    per_lot.append(_line("programming", f"nest and program, {len(use)} part type(s)", prog_h * rates["programming"], basis="per_lot", hours=prog_h, rate=rates["programming"]))
    per_lot.append(_line("setup", f"{process.replace('_', ' ')} setup", su_h * rate, basis="per_lot", hours=su_h, rate=rate))

    finish_lot: list[tuple[str, float, float, int]] = []
    lead_extra = 0
    for fname in options.get("finishes") or []:
        fin = cfg["finishes"].get(fname)
        if fin is None:
            raise pricing.SpecError(f"Unknown finish '{fname}'. Known: {sorted(cfg['finishes'])}")
        finish_lot.append((fname, fin["per_part"], fin["lot_min"], fin.get("lead_days", 7)))
        lead_extra += fin.get("lead_days", 7)

    ins = cfg["inspection"]
    im = fl["inspection_minutes_per_part"] * parts_per_set
    per_set.append(_line("inspection", "in-process and final inspection", im / 60 * rates["inspection"], hours=im / 60, rate=rates["inspection"]))
    if options.get("first_article"):
        hh = ins["first_article_hours"]
        per_lot.append(_line("inspection", "first article inspection and report", hh * rates["inspection"], basis="per_lot", hours=hh, rate=rates["inspection"]))
        lead_extra += cfg["lead_time"]["first_article_days"]
        warnings.append("First article required: the government must approve it before production ships. Allow for that in delivery days.")
    per_lot.append(_line("inspection", "certificate of conformance", ins["cert_per_lot"], basis="per_lot"))
    if options.get("material_certs"):
        per_lot.append(_line("material", "material certifications (mill certs)", 35.0, basis="per_lot"))
    pk_level = options.get("packaging") or "commercial"
    pk = cfg["packaging"].get(pk_level)
    if pk is None:
        raise pricing.SpecError(f"packaging must be one of {list(cfg['packaging'])}")
    per_set.append(_line("packaging", f"{pk_level} packaging", pk["per_part"] * parts_per_set))
    if pk["per_lot"]:
        per_lot.append(_line("packaging", f"{pk_level} lot labels and marking", pk["per_lot"], basis="per_lot"))
    freight = _f(options.get("freight_per_lot"), cfg["default_freight_per_lot"])
    per_lot.append(_line("freight", "outbound freight", freight, basis="per_lot"))

    ga, profit = cfg["ga_rate"], cfg["profit_rate"]
    set_cost = sum(l["cost"] for l in per_set)
    lot_cost = sum(l["cost"] for l in per_lot)
    breaks = []
    for q in qtys:
        mat_lot = nst["by_quantity"][q]["sheets"] * sheet_cost if full_sheets else 0.0
        fin = sum(max(pp * parts_per_set * q, lm) for _, pp, lm, _ in finish_lot)
        cost = set_cost * q + lot_cost + fin + mat_lot
        price = max(cost * (1 + ga) * (1 + profit), cfg["min_lot_charge"])
        days = cfg["lead_time"]["base_days"] + lead_extra + math.ceil(q * parts_per_set / max(cfg["lead_time"]["parts_per_day"], 1) / 4)
        breaks.append({"quantity": q, "total_cost": round(cost, 2), "unit_cost": round(cost / q, 2), "unit_price": round(price / q, 2),
                       "total_price": round(price, 2), "margin_pct": round((price - cost) / price * 100, 1) if price else 0.0,
                       "lead_time_days": days, "sheets": nst["by_quantity"][q]["sheets"]})
    if full_sheets:
        per_lot.append(_line("material", f"{nst['by_quantity'][qtys[0]]['sheets']} sheet(s) {sheet['name']} {t:g} in {mat_name}",
                             nst["by_quantity"][qtys[0]]["sheets"] * sheet_cost, basis=f"per_lot at qty {qtys[0]}", rate=mat["price_per_lb"]))
    if finish_lot:
        per_lot.append(_line("finishing", ", ".join(n for n, *_ in finish_lot), sum(max(pp * parts_per_set * qtys[0], lm) for _, pp, lm, _ in finish_lot),
                             basis=f"per_lot at qty {qtys[0]}", note="outside service; per part or lot minimum, whichever is more"))
    small = [p for p in use if p.get("min_radius") and p["min_radius"] * 2 < t * fl["min_hole_to_thickness"].get(process, 1.0)]
    if small:
        warnings.append(f"{len(small)} part(s) have holes or radii smaller than {fl['min_hole_to_thickness'].get(process, 1.0):g}x the thickness for {process.replace('_', ' ')}: "
                        "check the cutter can hold them, or drill and ream them after cutting.")
    assumptions.append(f"Cut time from {total_cut:.1f} in of cut per set at {ipm:.0f} in/min plus {pierce_min:g} min per pierce; check it against your machine's estimate.")
    if process in ("plasma", "router"):
        assumptions.append(f"{process.title()} rate, speed and setup are placeholders under the flat-part rates; replace them with your own.")
    return {
        "kind": "flat_dxf",
        "process": process, "material": mat_name, "thickness": t, "sheet": sheet,
        "part_weight_lb": round(weight_set, 3), "parts_per_set": parts_per_set, "cut_length_in": round(total_cut, 2),
        "pierces": total_pierce, "cut_ipm": round(ipm, 1), "cut_minutes_per_set": round(minutes_cut_set, 2),
        "nesting": nst,
        "per_part_lines": per_set, "per_lot_lines": per_lot,
        "per_part_cost": round(set_cost, 2), "per_lot_cost": round(lot_cost, 2),
        "ga_rate": ga, "profit_rate": profit, "price_breaks": breaks,
        "assumptions": assumptions, "warnings": warnings, "config_note": fl.get("note", ""),
    }


def estimate_spec(spec: dict, config: dict | None = None) -> dict:
    """Price a saved flat_dxf spec (used by quotes.save_quote)."""
    r = estimate(spec.get("parts") or [], spec.get("options") or {}, spec.get("quantities") or [1], config)
    r["part"] = {k: spec.get(k) for k in ("name", "part_number", "nsn") if spec.get(k)}
    return r


def clean_part(p: dict) -> dict:
    """The fields of a parsed part kept in a saved quote (no hole lists)."""
    keep = ("id", "file", "name", "index", "qty", "width", "height", "outer_area", "net_area", "cut_length", "outer_length", "pierces",
            "cutouts", "round_holes", "hole_diameters", "min_radius", "smallest_cutout", "bend_lines", "bends", "pem", "include")
    return {k: p[k] for k in keep if k in p}
