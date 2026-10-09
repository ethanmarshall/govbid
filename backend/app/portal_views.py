"""Three-view drawings of a customer's part for the quote page and PDF.

Front, top and right views in third-angle layout plus an isometric view, drawn with hidden-line removal
(OpenCascade HLR), overall dimensions on the views, and hidden edges dashed. The result is a small JSON
"sheet" of 2D polylines that renders to SVG (web) and to a ReportLab drawing (PDF), cached per input.

Sources:
  - a STEP model (single part or assembly): the real geometry
  - a DXF flat part: its outline and cutouts extruded to the sheet thickness
  - a drawing, circuit board or enclosure with only overall sizes: a plain envelope block, labeled as such
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

MM = 25.4

# view name -> (direction toward the viewer, x direction on the page)
VIEWS = {
    "front": ((0, -1, 0), (1, 0, 0)),
    "top": ((0, 0, 1), (1, 0, 0)),
    "right": ((1, 0, 0), (0, 1, 0)),
    "iso": ((1, -1, 1), (1, 1, 0)),
}


class ViewError(Exception):
    pass


# ---------------------------------------------------------------- shapes
def box_shape(length: float, width: float, height: float):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

    dims = [max(float(v or 0), 0.01) * MM for v in (length, width, height)]
    return BRepPrimAPI_MakeBox(*dims).Shape()


def cylinder_shape(diameter: float, length: float):
    """A turned envelope lying along X, so the front view shows its length."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), max(diameter, 0.01) * MM / 2, max(length, 0.01) * MM).Shape()


def _wire(pts: list) -> object:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt

    poly = BRepBuilderAPI_MakePolygon()
    last = None
    for x, y in pts:
        p = (round(x * MM, 4), round(y * MM, 4))
        if p != last:
            poly.Add(gp_Pnt(p[0], p[1], 0))
            last = p
    poly.Close()
    if not poly.IsDone():
        raise ViewError("bad outline")
    return poly.Wire()


def _simplify(pts: list, limit: int = 600) -> list:
    if len(pts) > 1 and tuple(pts[0]) == tuple(pts[-1]):
        pts = pts[:-1]
    if len(pts) <= limit:
        return pts
    step = math.ceil(len(pts) / limit)
    return pts[::step]


def flat_shape(outer: list, holes: list, thickness: float):
    """A flat part: outline with cutouts, extruded to the thickness (all in inches)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec

    mk = BRepBuilderAPI_MakeFace(_wire(_simplify(outer)), True)
    for h in holes[:300]:
        if len(h) >= 3:
            w = _wire(_simplify(h, 200))
            w.Reverse()
            mk.Add(w)
    if not mk.IsDone():
        raise ViewError("could not make the flat face")
    return BRepPrimAPI_MakePrism(mk.Face(), gp_Vec(0, 0, max(thickness, 0.005) * MM)).Shape()


def _face_count(shape) -> int:
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    n, ex = 0, TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        n += 1
        ex.Next()
    return n


# ---------------------------------------------------------------- projection
def _edges(compound) -> list:
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    out = []
    if compound is None or compound.IsNull():
        return out
    ex = TopExp_Explorer(compound, TopAbs_EDGE)
    while ex.More():
        out.append(to_edge(ex.Current()))
        ex.Next()
    return out


def _polyline(edge, defl: float) -> list:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection

    try:
        c = BRepAdaptor_Curve(edge)
    except Exception:  # noqa: BLE001
        return []
    try:
        d = GCPnts_QuasiUniformDeflection(c, defl)
        if d.IsDone() and d.NbPoints() >= 2:
            return [(d.Value(i).X() / MM, d.Value(i).Y() / MM) for i in range(1, d.NbPoints() + 1)]
    except Exception:  # noqa: BLE001
        pass
    a, b = c.FirstParameter(), c.LastParameter()
    return [(c.Value(t).X() / MM, c.Value(t).Y() / MM) for t in (a + (b - a) * i / 8 for i in range(9))]


def project(shape, direction, xdir, diag_mm: float, poly: bool = False, hidden: bool = True, mesh_ratio: float = 0.002) -> dict:
    """Visible and hidden edges of the shape seen from `direction`, as 2D polylines in inches."""
    from OCP.BRepLib import BRepLib
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector

    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*direction), gp_Dir(*xdir))
    if poly:
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.HLRBRep import HLRBRep_PolyAlgo, HLRBRep_PolyHLRToShape

        BRepMesh_IncrementalMesh(shape, diag_mm * mesh_ratio, False, 0.5 if mesh_ratio > 0.002 else 0.3, True)
        algo = HLRBRep_PolyAlgo(shape)
        algo.Projector(HLRAlgo_Projector(ax))
        algo.Update()
        hs = HLRBRep_PolyHLRToShape()
        hs.Update(algo)
    else:
        from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

        algo = HLRBRep_Algo()
        algo.Add(shape)
        algo.Projector(HLRAlgo_Projector(ax))
        algo.Update()
        algo.Hide()
        hs = HLRBRep_HLRToShape(algo)
    defl = diag_mm * 0.0015
    out = {"visible": [], "hidden": []}
    for key, comps in (("visible", (hs.VCompound(), hs.OutLineVCompound())), ("hidden", (hs.HCompound(),) if hidden else ())):
        for comp in comps:
            if comp is None or comp.IsNull():
                continue
            BRepLib.BuildCurves3d_s(comp)
            for e in _edges(comp):
                pl = _polyline(e, defl)
                if len(pl) >= 2:
                    out[key].append(pl)
    return out


def _bounds(lines: list) -> tuple:
    xs = [p[0] for pl in lines for p in pl]
    ys = [p[1] for pl in lines for p in pl]
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_in(shape) -> tuple:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b, False)
    lo, hi = b.CornerMin(), b.CornerMax()
    return ((hi.X() - lo.X()) / MM, (hi.Y() - lo.Y()) / MM, (hi.Z() - lo.Z()) / MM)


def build_sheet(shape, *, kind: str = "model", label: str = "") -> dict:
    """Project the shape into the four views and lay them out. kind: model | flat | envelope."""
    L, W, H = _bbox_in(shape)
    diag = math.sqrt(L * L + W * W + H * H) * MM or 1.0
    faces = _face_count(shape)
    poly = faces > 900  # detailed models: the faster mesh-based hidden lines
    huge = faces > 5000  # very big models (large assemblies): coarse mesh, no hidden lines, tiny edges left out
    views = {}
    for name, (d, x) in VIEWS.items():
        v = project(shape, d, x, diag, poly=poly, hidden=not huge and name != "iso", mesh_ratio=0.01 if huge else 0.002)
        b = _bounds(v["visible"] + v["hidden"])
        span = max(b[2] - b[0], b[3] - b[1], 1e-6)
        vis, hid = _thin(v["visible"], span, huge), _thin(v["hidden"], span, huge)
        views[name] = {"visible": _round(vis), "hidden": _round(hid), "bounds": [round(c, 4) for c in b]}
    return {"kind": kind, "label": label, "size": [round(L, 3), round(W, 3), round(H, 3)], "views": views}


MAX_POINTS = 60_000  # per view: plenty for a drawing a few hundred pixels wide


def _thin(lines: list, span: float, huge: bool) -> list:
    """Leave out edges too small to see at drawing size, and keep each view to a sensible size."""
    min_size = span * (0.004 if huge else 0.0008)

    def size(pl):
        xs, ys = [p[0] for p in pl], [p[1] for p in pl]
        return max(max(xs) - min(xs), max(ys) - min(ys))

    sized = [(size(pl), pl) for pl in lines]
    keep = [(sz, pl) for sz, pl in sized if sz >= min_size]
    total = sum(len(pl) for _, pl in keep)
    if total > MAX_POINTS:  # biggest edges first until the budget is spent
        keep.sort(key=lambda x: -x[0])
        out, n = [], 0
        for sz, pl in keep:
            if n + len(pl) > MAX_POINTS:
                break
            out.append(pl)
            n += len(pl)
        return out
    return [pl for _, pl in keep]


def _round(lines: list) -> list:
    out = []
    for pl in lines:
        r = [(round(x, 4), round(y, 4)) for x, y in pl]
        # drop consecutive duplicates
        r = [p for i, p in enumerate(r) if i == 0 or p != r[i - 1]]
        if len(r) >= 2:
            out.append(r)
    return out


# ---------------------------------------------------------------- layout
def layout(sheet: dict) -> dict:
    """Place the views on a page (third-angle: top above front, right beside front, iso top right).
    Returns page size and per-view placement, in inches of the part (scaled by the renderer)."""
    v = sheet["views"]
    fx0, fy0, fx1, fy1 = v["front"]["bounds"]
    tx0, ty0, tx1, ty1 = v["top"]["bounds"]
    rx0, ry0, rx1, ry1 = v["right"]["bounds"]
    ix0, iy0, ix1, iy1 = v["iso"]["bounds"]
    fw, fh = fx1 - fx0, fy1 - fy0
    th = ty1 - ty0
    rw = rx1 - rx0
    iw, ih = ix1 - ix0, iy1 - iy0
    span = max(fw, fh, th, rw, iw, ih, 1e-3)
    gap = 0.32 * span + 0.0001
    left = 0.3 * span
    # origins: where each view's (x0, y0) lands on the page (y up)
    front = (left, 0.0)
    top = (left, fh + gap)
    right = (left + fw + gap, 0.0)
    iso_scale = 0.9
    iso = (left + fw + gap, fh + gap * 0.6)
    width = max(left + fw + gap + max(rw, iw * iso_scale), 1e-3) + 0.12 * span
    height = max(fh + gap + th, fh + gap * 0.6 + ih * iso_scale) + 0.06 * span
    bottom = 0.26 * span  # room under the front view for its dimension
    return {"width": width, "height": height + bottom, "bottom": bottom, "span": span, "gap": gap,
            "place": {"front": (front, 1.0, (fx0, fy0)), "top": (top, 1.0, (tx0, ty0)), "right": (right, 1.0, (rx0, ry0)),
                      "iso": (iso, iso_scale, (ix0, iy0))}}


def _fmt(v: float) -> str:
    return f"{v:.3f}" if v < 10 else f"{v:.2f}"


def dims(sheet: dict, lay: dict) -> list:
    """Overall dimensions: width under the front view, height right of the front view... placed beside the right view,
    depth beside the top view. Each: (x1, y1, x2, y2, offset_dir, text) in page inches (y up)."""
    L, W, H = sheet["size"]
    v = sheet["views"]
    out = []
    (ox, oy), _, (bx, by) = lay["place"]["front"]
    fx0, fy0, fx1, fy1 = v["front"]["bounds"]
    out.append(("h", ox, oy, ox + (fx1 - fx0), oy, _fmt(L)))
    (tox, toy), _, _ = lay["place"]["top"]
    tx0, ty0, tx1, ty1 = v["top"]["bounds"]
    out.append(("vl", tox, toy, tox, toy + (ty1 - ty0), _fmt(W)))
    out.append(("vl", ox, oy, ox, oy + (fy1 - fy0), _fmt(H)))
    return out


# ---------------------------------------------------------------- SVG
def to_svg(sheet: dict) -> str:
    lay = layout(sheet)
    span = lay["span"]
    k = 300 / span  # page units per part inch: the biggest view is about 300 units wide
    W, Hh = lay["width"] * k, lay["height"] * k
    bottom = lay["bottom"] * k

    def P(x, y):  # part-page inches (y up) -> svg units (y down)
        return x * k, Hh - bottom - y * k + bottom * 0 - 0

    def path(lines, sx, sy, scale, x0, y0):
        parts = []
        for pl in lines:
            pts = []
            for x, y in pl:
                px, py = P(sx + (x - x0) * scale, sy + (y - y0) * scale)
                pts.append(f"{px:.1f},{py:.1f}")
            parts.append("M" + " L".join(pts))
        return " ".join(parts)

    sw = max(1.0, 1.4)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {-8:.0f} {W:.0f} {Hh + 8:.0f}" font-family="Barlow, Arial, sans-serif">']
    out.append('<style>.v{fill:none;stroke:#15212c;stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}'
               '.h{fill:none;stroke:#7c8893;stroke-width:0.9;stroke-dasharray:5 3}'
               '.d{fill:none;stroke:#2356c4;stroke-width:0.9}.t{fill:#2356c4;font-size:12px}.n{fill:#7c8893;font-size:11px}</style>')
    names = {"front": "Front", "top": "Top", "right": "Right", "iso": "Isometric"}
    for name in ("top", "front", "right", "iso"):
        (sx, sy), scale, (x0, y0) = lay["place"][name]
        view = sheet["views"][name]
        if view["hidden"]:
            out.append(f'<path class="h" d="{path(view["hidden"], sx, sy, scale, x0, y0)}"/>')
        out.append(f'<path class="v" d="{path(view["visible"], sx, sy, scale, x0, y0)}"/>')
        bx0, by0, bx1, by1 = view["bounds"]
        lx, ly = P(sx, sy + (by1 - by0) * scale)
        out.append(f'<text class="n" x="{lx:.1f}" y="{ly - 6:.1f}">{names[name]}</text>')
    # dimensions
    gap = 0.11 * span
    for d in dims(sheet, lay):
        kind, x1, y1, x2, y2, text = d
        if kind == "h":
            ya = y1 - gap
            a, b = P(x1, ya), P(x2, ya)
            e1, e2 = P(x1, y1 - gap * 0.2), P(x1, ya - gap * 0.25)
            f1, f2 = P(x2, y1 - gap * 0.2), P(x2, ya - gap * 0.25)
            out.append(f'<path class="d" d="M{e1[0]:.1f},{e1[1]:.1f} L{e2[0]:.1f},{e2[1]:.1f} M{f1[0]:.1f},{f1[1]:.1f} L{f2[0]:.1f},{f2[1]:.1f} '
                       f'M{a[0]:.1f},{a[1]:.1f} L{b[0]:.1f},{b[1]:.1f}"/>')
            out.append(_arrow(a, b) + _arrow(b, a))
            out.append(f'<text class="t" x="{(a[0] + b[0]) / 2:.1f}" y="{a[1] + 15:.1f}" text-anchor="middle">{text}</text>')
        else:
            xa = x1 - gap
            a, b = P(xa, y1), P(xa, y2)
            e1, e2 = P(x1 - gap * 0.2, y1), P(xa - gap * 0.25, y1)
            f1, f2 = P(x1 - gap * 0.2, y2), P(xa - gap * 0.25, y2)
            out.append(f'<path class="d" d="M{e1[0]:.1f},{e1[1]:.1f} L{e2[0]:.1f},{e2[1]:.1f} M{f1[0]:.1f},{f1[1]:.1f} L{f2[0]:.1f},{f2[1]:.1f} '
                       f'M{a[0]:.1f},{a[1]:.1f} L{b[0]:.1f},{b[1]:.1f}"/>')
            out.append(_arrow(a, b) + _arrow(b, a))
            cy = (a[1] + b[1]) / 2
            if abs(a[1] - b[1]) < 46:  # short: write it level, beside the line
                out.append(f'<text class="t" x="{a[0] - 6:.1f}" y="{cy + 4:.1f}" text-anchor="end">{text}</text>')
            else:
                cx = a[0] - 5
                out.append(f'<text class="t" x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" transform="rotate(-90 {cx:.1f} {cy:.1f})">{text}</text>')
    out.append("</svg>")
    return "".join(out)


def _arrow(tip, frm) -> str:
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    s = 7
    p1 = (tip[0] - ux * s - uy * s * 0.35, tip[1] - uy * s + ux * s * 0.35)
    p2 = (tip[0] - ux * s + uy * s * 0.35, tip[1] - uy * s - ux * s * 0.35)
    return f'<path d="M{tip[0]:.1f},{tip[1]:.1f} L{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f} Z" fill="#2356c4"/>'


# ---------------------------------------------------------------- PDF (ReportLab)
def to_drawing(sheet: dict, max_w: float, max_h: float):
    """A ReportLab Drawing of the same views, fitted into max_w x max_h points."""
    from reportlab.graphics.shapes import Drawing, PolyLine, String
    from reportlab.lib import colors

    lay = layout(sheet)
    k = min(max_w / lay["width"], max_h / lay["height"])
    d = Drawing(lay["width"] * k, lay["height"] * k)
    base = lay["bottom"] * k
    ink, grey, dye = colors.HexColor("#15212c"), colors.HexColor("#8a95a0"), colors.HexColor("#2356c4")
    names = {"front": "Front", "top": "Top", "right": "Right", "iso": "Isometric"}
    for name in ("top", "front", "right", "iso"):
        (sx, sy), scale, (x0, y0) = lay["place"][name]
        view = sheet["views"][name]
        for lines, color, width, dash in ((view["hidden"], grey, 0.4, [2.5, 1.5]), (view["visible"], ink, 0.8, None)):
            for pl in lines:
                pts = []
                for x, y in pl:
                    pts += [(sx + (x - x0) * scale) * k, base + (sy + (y - y0) * scale) * k]
                d.add(PolyLine(pts, strokeColor=color, strokeWidth=width, strokeDashArray=dash))
        bx0, by0, bx1, by1 = view["bounds"]
        d.add(String(sx * k, base + (sy + (by1 - by0) * scale) * k + 4, names[name], fontName="Helvetica", fontSize=7, fillColor=grey))
    gap = 0.11 * lay["span"]
    for kind, x1, y1, x2, y2, text in dims(sheet, lay):
        if kind == "h":
            ya = y1 - gap
            d.add(PolyLine([x1 * k, base + ya * k, x2 * k, base + ya * k], strokeColor=dye, strokeWidth=0.5))
            d.add(String((x1 + x2) / 2 * k, base + ya * k - 9, text, fontName="Helvetica", fontSize=7.5, fillColor=dye, textAnchor="middle"))
        else:
            xa = x1 - gap
            d.add(PolyLine([xa * k, base + y1 * k, xa * k, base + y2 * k], strokeColor=dye, strokeWidth=0.5))
            d.add(String(xa * k - 3, base + (y1 + y2) / 2 * k - 3, text, fontName="Helvetica", fontSize=7.5, fillColor=dye, textAnchor="end"))
    return d


# ---------------------------------------------------------------- cache
def cache_key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:20]


def save(folder: Path, key: str, sheet: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(json.dumps(sheet, separators=(",", ":")))


def load(folder: Path, key: str) -> dict | None:
    p = folder / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None
