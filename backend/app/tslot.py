"""Recognize T-slot aluminum extrusion (80/20 and similar) and catalog hardware inside an uploaded assembly, so a
cart or frame is priced as cut-to-length extrusion plus hardware (app/extrusion.py) instead of each member being
machined from solid bar.

A body counts as an extrusion when its cross-section (from an oriented bounding box, so diagonal braces work too)
matches a catalog profile, it is long for its section, and either its shape is mostly hollow like a T-slot profile
(25 to 92 percent of the section's box is metal) or its name says it is a frame member (post, rail, brace, 1515 ...).
Plates, panels and handles are never extrusions. Angled end faces count as miter cuts.

Bought parts shown for fit are matched to catalog hardware by name (hinge, handle, caster, foot, anchor, end cap,
T-nut, bracket). The pieces of one caster drawn as separate bodies (plate, swivel, fork, wheel) count as one caster.
Joining hardware is not usually modeled, so it is estimated at one anchor fastener and counterbore per member end;
the price is an estimate for an engineer to confirm.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .extrusion_catalog import profile_rows

MEMBER_WORDS = re.compile(r"\b(post|rail|stile|upright|crossbeam|cross[ _-]?member|beam|brace|strut|leg|riser|member|extrusion|profile|"
                          r"8020|80[ _-]?20|t[ _-]?slot|frame[ _-]?member|stringer|header|runner)\b", re.I)
NOT_MEMBER = re.compile(r"\b(plate|panel|infill|sheet|handle|pull|hinge|caster|wheel|foot|cover|skin|door[ _-]?panel|bracket)\b", re.I)
HARDWARE = [  # (pattern, catalog base)
    (re.compile(r"\bcaster\b.*\b(lock|brake|locking|braked)\b|\b(lock|brake|locking|braked)\b.*\bcaster\b", re.I), "CASTER-LOCK"),
    (re.compile(r"\bcaster", re.I), "CASTER"),
    (re.compile(r"\bhinge", re.I), "HINGE"),
    (re.compile(r"\b(handle|pull)\b", re.I), "HANDLE"),
    (re.compile(r"\b(latch|deadbolt)", re.I), "LATCH"),
    (re.compile(r"\b(lev(el|eling|eller)?[ _-]?foot|feet|foot)\b", re.I), "FOOT"),
    (re.compile(r"\banchor\b", re.I), "ANCHOR"),
    (re.compile(r"\bend[ _-]?cap\b", re.I), "ENDCAP"),
    (re.compile(r"\bt[ _-]?nut\b", re.I), "TNUT-DROP"),
    (re.compile(r"\bgusset", re.I), "BRKT-GUSSET"),
    (re.compile(r"\b(corner[ _-]?bracket|bracket)\b", re.I), "BRKT-4H"),
]
CASTER_PART = re.compile(r"[ _-]*(adapter|plate|top[ _-]?plate|swivel|fork|yoke|wheel|axle|stem|brake|bearing|housing|body|mount)(?![a-z]).*$", re.I)


def _profiles():
    out = []
    for r in profile_rows():
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", r["size"])[:2]]
        if len(nums) == 2:
            k = 1 / 25.4 if "mm" in r["size"] else 1.0
            a, b = sorted((nums[0] * k, nums[1] * k))
            out.append({"id": r["id"], "family": r["family"], "a": a, "b": b, "lite": "Lite" in r["size"]})
    return out


PROFILES = _profiles()


def _points(shape):
    """Points on the shape's surface (mesh nodes), in mm."""
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    BRepMesh_IncrementalMesh(shape, 0.3, False, 0.5, True)
    F = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    pts = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        loc = TopLoc_Location()
        t = BRep_Tool.Triangulation_s(F(ex.Current()), loc)
        if t is not None:
            tr = loc.Transformation()
            for i in range(1, t.NbNodes() + 1):
                q = t.Node(i).Transformed(tr)
                pts.append((q.X(), q.Y(), q.Z()))
        ex.Next()
    return np.array(pts, dtype=float)


def _hull(p):
    """Convex hull of 2D points (monotone chain)."""
    import numpy as np

    p = np.unique(np.round(p, 4), axis=0)
    if len(p) < 3:
        return p
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def half(pts):
        h = []
        for q in pts:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h
    lo, up = half(p), half(p[::-1])
    return np.array(lo[:-1] + up[:-1])


def _frame_for_axis(pts, a) -> dict:
    """Smallest rectangle around the cross-section of points seen along axis a."""
    import numpy as np

    a = a / np.linalg.norm(a)
    t0 = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(a, t0)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    s_ = pts @ a
    h = _hull(np.stack([pts @ e1, pts @ e2], axis=1))
    best = None
    for i in range(len(h)):
        ed = h[(i + 1) % len(h)] - h[i]
        n = np.linalg.norm(ed)
        if n < 1e-9:
            continue
        c, sn = ed / n
        rot = h @ np.array([[c, -sn], [sn, c]])
        mn, mx = rot.min(axis=0), rot.max(axis=0)
        area = (mx[0] - mn[0]) * (mx[1] - mn[1])
        if best is None or area < best[0]:
            best = (area, c, sn, mn, mx)
    area, c, sn, mn, mx = best
    du, dv = e1 * c + e2 * sn, -e1 * sn + e2 * c
    w = mx - mn
    mid = (mn + mx) / 2
    centre = a * (s_.min() + s_.max()) / 2 + du * mid[0] + dv * mid[1]
    if w[0] > w[1]:
        du, dv, w = dv, du, w[::-1]
    return {"center": centre, "axis": a, "u": du, "v": dv, "half": ((s_.max() - s_.min()) / 2, w[0] / 2, w[1] / 2), "area": area}


def _principal_axes(shape):
    import numpy as np
    from OCP.Bnd import Bnd_OBB
    from OCP.BRepBndLib import BRepBndLib

    o = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, o, True, True, False)
    axes = sorted([(o.XHSize(), o.XDirection()), (o.YHSize(), o.YDirection()), (o.ZHSize(), o.ZDirection())], key=lambda t: t[0])
    return [np.array([d.X(), d.Y(), d.Z()]) for _, d in axes]


def section_frame(shape) -> dict:
    """A member's long axis and the smallest rectangle around its cross-section: exact for a bar turned at any angle
    about its length (a principal-axis box of a square section can come out too big) and for a slightly tilted axis
    (a bar with one mitered end), by trying small tilts of the axis and keeping the smallest section.
    Returns {center, axis, u, v (unit vectors), half: (hL, hu, hv)} in mm, u along the narrow side."""
    import numpy as np

    a = _principal_axes(shape)[-1]
    pts = _points(shape)
    if len(pts) < 4:
        raise ValueError("no mesh")
    best = _frame_for_axis(pts, a)
    for step in (0.02, 0.006, 0.002):  # radians
        improved = True
        while improved:
            improved = False
            base = best["axis"]
            p1 = best["u"]
            p2 = best["v"]
            for d1, d2 in ((step, 0), (-step, 0), (0, step), (0, -step)):
                f = _frame_for_axis(pts, base + p1 * d1 + p2 * d2)
                if f["area"] < best["area"] * 0.9995:
                    best, improved = f, True
    return best


def tight_box(shape) -> list[float]:
    """Sizes (small to large, inches) of the tightest box around a part: the section frame tried along each principal
    axis, so thin plates and small blocks turned in the model still measure true."""
    pts = _points(shape)
    best = None
    for a in _principal_axes(shape):
        f = _frame_for_axis(pts, a)
        vol = f["half"][0] * f["half"][1] * f["half"][2]
        if best is None or vol < best[0]:
            best = (vol, f)
    hL, hu, hv = best[1]["half"]
    return sorted([hL * 2 / 25.4, hu * 2 / 25.4, hv * 2 / 25.4])


def _obb(shape):
    """(sizes small to large in inches, unit axis of the longest side), with an exact cross-section."""
    f = section_frame(shape)
    hL, hu, hv = f["half"]
    return [hu * 2 / 25.4, hv * 2 / 25.4, hL * 2 / 25.4], tuple(f["axis"])


def _angled_ends(shape, axis) -> int:
    """Planar faces that cut across the member at an angle (miter cuts)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    n = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        s = BRepAdaptor_Surface((getattr(TopoDS, "Face_s", None) or TopoDS.Face)(ex.Current()))
        if s.GetType() == GeomAbs_Plane:
            nd = s.Plane().Axis().Direction()
            c = abs(nd.X() * axis[0] + nd.Y() * axis[1] + nd.Z() * axis[2])
            if 0.15 < c < 0.985:
                n += 1
        ex.Next()
    return min(n, 2)


def classify(shape, name: str, volume_in3: float | None = None) -> dict | None:
    """{profile, family, length_in, miters} when the body is a T-slot extrusion member, else None."""
    if NOT_MEMBER.search((name or "").replace("_", " ")):
        return None
    try:
        (a, b, L), axis = _obb(shape)
    except Exception:  # noqa: BLE001
        return None
    if L < 2.0 or L < 2.5 * b:
        return None
    best = None
    for p in PROFILES:
        tol = max(0.03, p["b"] * 0.02)
        if abs(a - p["a"]) <= tol and abs(b - p["b"]) <= tol:
            if best is None or (best["lite"] and not p["lite"]):
                best = p
    if not best:
        return None
    vol = volume_in3
    if vol is None:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, g)
        vol = g.Mass() / 25.4 ** 3
    miters = _angled_ends(shape, axis)
    box = a * b * L
    fill = vol / box if box else 1
    if miters:  # a mitered bar fills less of its box; judge it by name or by its section alone
        fill = min(1.0, fill / 0.75)
    named = bool(MEMBER_WORDS.search((name or "").replace("_", " ")))
    if not (0.25 <= fill <= 0.92 or named):
        return None
    return {"profile": best["id"], "family": best["family"], "length_in": round(float(L), 3), "miters": int(miters), "fill": round(float(fill), 2)}


def hardware_for(names: list[str]) -> tuple[str | None, int]:
    """(catalog base, count) for a group of bought bodies, counting a multi-body caster once."""
    joined = " ".join(n.replace("_", " ") for n in names)
    base = next((b for rx, b in HARDWARE if rx.search(joined)), None)
    if not base:
        return None, 0
    if base.startswith("CASTER"):
        ids = {CASTER_PART.sub("", n).strip("_ -").lower() for n in names}
        return base, max(1, len(ids))
    return base, len(names)


INSTANCE = re.compile(r"\s*<\d+>\s*$")


def unit_count(groups: list[dict]) -> int:
    """How many units a set of bought body groups makes. Onshape names each body after its sub-assembly instance
    ("Hinge Subassembly <3>"), so the bodies of one unit share a name: 24 hinge bodies named for 8 instances are 8
    hinges, not 24. A "... Hardware" sub-assembly next to its part (hinge screws next to the hinges) comes with the
    part. Without instance names, every body counts."""
    from collections import Counter

    bodies = sum(int(g.get("qty", 1)) for g in groups)
    names = [n for g in groups for n in (g.get("body_names") or [])]
    if not names or len(names) != bodies or not all(INSTANCE.search(n) for n in names):
        return bodies
    stems: dict[str, list[str]] = {}
    for n in names:
        stems.setdefault(INSTANCE.sub("", n).strip().lower(), []).append(n)
    main = {k: v for k, v in stems.items() if not re.search(r"\bhardware\b|\bfasteners?\b", k)} or stems
    total = 0
    for v in main.values():
        per = Counter(Counter(v).values()).most_common(1)[0][0]  # bodies in one unit
        total += max(1, round(len(v) / per))
    return total


def fastener_base(names: list[str], bb: dict) -> str | None:
    """Loose screws and T-nuts in a "... Hardware" sub-assembly: a long body is a screw, a short one a T-nut."""
    if not re.search(r"\b(hardware|fasteners?|screws?|bolts?|nuts?|t[ _-]?nuts?|washers?)\b", " ".join(names).replace("_", " "), re.I):
        return None
    d = sorted(float(bb.get(k) or 0) for k in ("length", "width", "height"))
    if not d[2] or d[2] > 3:
        return None
    return "SCREW-BHSCS" if d[1] and d[2] / d[1] >= 1.8 else "TNUT-DROP"


def load_group_shape(file_id: str):
    from . import cad, cad_quote

    return cad.load_step(Path(cad_quote.CAD_DIR) / f"{file_id}.step")


def _obb_box(shape):
    """A tight oriented box (the member's length and exact cross-section)."""
    from OCP.Bnd import Bnd_OBB
    from OCP.gp import gp_Dir, gp_Pnt

    f = section_frame(shape)
    c, a, u, v = f["center"], f["axis"], f["u"], f["v"]
    hL, hu, hv = f["half"]
    return Bnd_OBB(gp_Pnt(*map(float, c)), gp_Dir(*map(float, a)), gp_Dir(*map(float, u)), gp_Dir(*map(float, v)), float(hL), float(hu), float(hv))


def measure_joints(solids: list, members: list[tuple[int, dict]], tol_in: float = 0.06) -> dict:
    """Which member ends butt into another member. members: [(body index, classify() result)].
    Returns {body index: {"joined_ends": n, "anchors": n}}: an end is joined when its center touches another member;
    each joined end takes one anchor fastener per 1.5 in module of its own section (a 1530 end takes two)."""
    from OCP.gp import gp_Pnt

    boxes, grown = {}, {}
    for i, c in members:
        boxes[i] = _obb_box(solids[i])
        g = _obb_box(solids[i])
        g.Enlarge((tol_in if not c.get("miters") else 0.2) * 25.4)  # a mitered end meets the other member on a slant
        grown[i] = g
    out = {}
    for i, c in members:
        o = boxes[i]
        axes = [(o.XHSize(), o.XDirection()), (o.YHSize(), o.YDirection()), (o.ZHSize(), o.ZDirection())]
        half, d = max(axes, key=lambda t: t[0])
        ctr = o.Center()
        ends = 0
        for sgn in (1, -1):
            p = gp_Pnt(ctr.X() + sgn * half * d.X(), ctr.Y() + sgn * half * d.Y(), ctr.Z() + sgn * half * d.Z())
            if any(j != i and not grown[j].IsOut(p) for j, _ in members):
                ends += 1
        prof = next((p for p in PROFILES if p["id"] == c["profile"]), None)
        modules = max(1, round(prof["b"] / prof["a"])) if prof else 1
        out[i] = {"joined_ends": ends, "anchors": ends * modules}
    return out


PANEL_WORDS = re.compile(r"\b(infill|panel|window|glazing|lexan|polycarb\w*|acrylic|plexi\w*|acm|dibond|composite|guard[ _-]?panel)\b", re.I)
PANEL_HINTS = [(re.compile(r"polycarb|lexan|makrolon|\bpc\b", re.I), "PC"), (re.compile(r"acrylic|plexi|\bacr\b", re.I), "ACR"),
               (re.compile(r"\bacm\b|dibond|composite", re.I), "ACM")]


def panel_for(name: str, thickness_in: float, default_material: str = "PC") -> str | None:
    """Catalog panel id for an infill panel (by name hint, else the default material), nearest in thickness."""
    from .extrusion_catalog import LEGACY_PANELS, PANELS

    n = (name or "").replace("_", " ")
    if not PANEL_WORDS.search(n):
        return None
    if re.search(r"\b(alum\w*|6061|5052|steel|stainless)\b", n, re.I):
        return None  # a metal panel is priced as sheet metal
    mat = next((m for rx, m in PANEL_HINTS if rx.search(n)), default_material)
    opts = [(k, v) for k, v in PANELS.items() if v[1] == mat and k not in LEGACY_PANELS] or [(k, v) for k, v in PANELS.items() if k not in LEGACY_PANELS]
    return min(opts, key=lambda kv: abs(kv[1][2] - thickness_in))[0]


# Standard 80/20 parts recognized by size when a model names them only "Part 12": (sizes small to large in inches,
# volume range in cubic inches or None, catalog base, family, 80/20 part number). Sizes from catalog 24 pages 3-76,
# 3-87, 3-88 and 8-11; brackets are told apart from gusseted ones by volume (weight / .0975 lb per cubic inch).
STANDARD_SHAPES = [
    ((0.188, 1.5, 1.5), None, "ENDCAP", "15", "2030"),
    ((0.188, 1.5, 3.0), None, "ENDCAP", "15", "2045"),
    ((0.188, 1.5, 4.5), None, "ENDCAP", "15", "2046"),
    ((0.188, 3.0, 3.0), None, "ENDCAP", "15", "2050"),
    ((0.125, 1.0, 1.0), None, "ENDCAP", "10", "2015"),
    ((0.125, 1.0, 2.0), None, "ENDCAP", "10", "2025"),
    ((1.31, 1.5, 1.5), (0.6, 1.0), "BRKT-2H", "15", "4302"),
    ((1.312, 1.5, 1.5), (1.0, 1.4), "BRKT-GUSSET", "15", "4332"),
    ((1.5, 1.5, 2.81), None, "BRKT-4H", "15", "4303"),
    ((1.31, 3.0, 3.0), None, "BRKT-4H", "15", "4301"),
    ((0.875, 1.0, 1.0), (0.15, 0.32), "BRKT-2H", "10", "4119"),
    ((0.875, 1.0, 1.0), (0.32, 0.5), "BRKT-GUSSET", "10", "4132"),
    ((1.0, 1.0, 1.875), None, "BRKT-4H", "10", "4113"),
    ((0.875, 2.0, 2.0), None, "BRKT-4H", "10", "4115"),
]


def standard_part(shape, volume_in3: float | None = None) -> tuple[str, str, str] | None:
    """(catalog base, family, 80/20 part number) when a part has the size of a standard 80/20 part."""
    try:
        dims = tight_box(shape)
    except Exception:  # noqa: BLE001
        return None
    if volume_in3 is None:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, g)
        volume_in3 = g.Mass() / 25.4 ** 3
    for size, vol, base, fam, pn in STANDARD_SHAPES:
        if all(abs(a - b) <= max(0.03, b * 0.02) for a, b in zip(dims, size)) and (vol is None or vol[0] <= volume_in3 <= vol[1]):
            return base, fam, pn
    return None


def ends_touching(solids: list, members: list[tuple[int, dict]], others: list[int], tol_in: float = 0.1) -> dict:
    """{member body: number of its ends that touch one of the `others` bodies} (a caster plate or stem on a post end)."""
    from OCP.gp import gp_Pnt

    grown = []
    for i in others:
        if i is None or i >= len(solids):
            continue
        try:
            b = _obb_box(solids[i])
        except Exception:  # noqa: BLE001
            continue
        b.Enlarge(tol_in * 25.4)
        grown.append(b)
    out = {}
    if not grown:
        return out
    for i, _ in members:
        f = section_frame(solids[i])
        hL = f["half"][0]
        n = 0
        for sgn in (1, -1):
            p = f["center"] + f["axis"] * hL * sgn
            if any(not b.IsOut(gp_Pnt(*map(float, p))) for b in grown):
                n += 1
        if n:
            out[i] = n
    return out
