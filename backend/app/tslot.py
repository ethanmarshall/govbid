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


def _obb(shape):
    """Oriented box: (sizes sorted small to large, unit axis of the longest side)."""
    from OCP.Bnd import Bnd_OBB
    from OCP.BRepBndLib import BRepBndLib

    o = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, o, True, True, False)
    axes = [(o.XHSize() * 2, o.XDirection()), (o.YHSize() * 2, o.YDirection()), (o.ZHSize() * 2, o.ZDirection())]
    axes.sort(key=lambda t: t[0])
    d = axes[-1][1]
    return [t[0] / 25.4 for t in axes], (d.X(), d.Y(), d.Z())


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
    return {"profile": best["id"], "family": best["family"], "length_in": round(L, 3), "miters": miters, "fill": round(fill, 2)}


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


def load_group_shape(file_id: str):
    from . import cad, cad_quote

    return cad.load_step(Path(cad_quote.CAD_DIR) / f"{file_id}.step")
