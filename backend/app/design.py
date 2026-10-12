"""Design a part on the website: a customer describes a simple part (or fills in its sizes) and gets a 3D model with
dimensions, a three-view drawing, and a price.

A design is a small JSON "spec": one of a few part types with its sizes, plus features such as holes, slots and
pockets. The server checks every number, then builds a real solid with OpenCascade, so the model can be priced by the
same quoting pipeline as an uploaded STEP file and handed to the shop as a STEP file. Nothing a customer or the AI
writes is ever run as code: the spec is data, checked against the limits below.

Part types (all sizes in the spec's units, "in" or "mm"):
  plate     flat plate or laser-cut part: length (X), width (Y), thickness (Z), corner_radius
  block     machined block: same as plate, thickness is its height
  l_bracket bent or machined angle: leg_a (base, along X), leg_b (upright, along Z), width (Y), thickness, bend_radius
  u_channel bent channel: length (X), base (outside width, Y), height (outside, Z), thickness, bend_radius
  box       open-top box or tray: length, width, height, wall, floor
  round     turned part along X: sections [{diameter, length}, ...] from the left end, optional bore
  flange    round flange or disk on the XY plane: diameter, thickness, bore, bolt circle, optional hub

Features (plate, block, box floor):  holes [{x, y, diameter, depth}] (depth 0 = through), slots [{x, y, length,
width, angle}] (center, angle 0 or 90), pockets [{x, y, length, width, depth, corner_radius}] (center; depth 0 = cut
through). x and y are measured from the lower-left corner. l_bracket: holes_a on the base and holes_b on the upright,
x along the leg from the outside corner, y across the width. u_channel: holes_base (x along, y across from one outside
edge) and holes_flange (x along, z up from the bottom; through both flanges).
"""
from __future__ import annotations

import math
import re
import tempfile
from pathlib import Path

MM = 25.4
TYPES = ("plate", "block", "l_bracket", "u_channel", "box", "round", "flange", "frame")
TYPE_LABEL = {"plate": "Flat plate", "block": "Machined block", "l_bracket": "L bracket", "u_channel": "U channel",
              "box": "Open box or tray", "round": "Turned part (shaft, spacer, pin)", "flange": "Round flange or disk",
              "frame": "T-slot extrusion frame (cart, stand, enclosure)"}
MAX_IN = 48.0  # the largest size anywhere, inches
MIN_IN = 0.01
MAX_FEATURES = 200

# field: (label, default inches); the form on the page is built from this
FIELDS = {
    "plate": [("length", "Length", 6.0), ("width", "Width", 4.0), ("thickness", "Thickness", 0.25), ("corner_radius", "Corner radius", 0.0)],
    "block": [("length", "Length", 3.0), ("width", "Width", 2.0), ("thickness", "Height", 1.0), ("corner_radius", "Corner radius", 0.0)],
    "l_bracket": [("leg_a", "Base leg", 2.0), ("leg_b", "Upright leg", 2.0), ("width", "Width", 1.5), ("thickness", "Thickness", 0.125),
                  ("bend_radius", "Inside bend radius", 0.125)],
    "u_channel": [("length", "Length", 6.0), ("base", "Outside width", 2.0), ("height", "Outside height", 1.5), ("thickness", "Thickness", 0.125),
                  ("bend_radius", "Inside bend radius", 0.125)],
    "box": [("length", "Length", 6.0), ("width", "Width", 4.0), ("height", "Height", 2.0), ("wall", "Wall", 0.125), ("floor", "Floor", 0.125)],
    "round": [],
    "flange": [("diameter", "Diameter", 4.0), ("thickness", "Thickness", 0.375), ("bore", "Center bore", 1.0)],
    "frame": [("width", "Width (outside)", 36.0), ("depth", "Depth (outside)", 26.0), ("height", "Height (frame only)", 33.75)],
}


class DesignError(ValueError):
    pass


# ------------------------------------------------------------------ checking
def _num(v, what: str, lo: float, hi: float, k: float, allow_zero: bool = False) -> float:
    """A size in the spec's units, returned in inches. k: inches per unit."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise DesignError(f"{what} must be a number.")
    if not math.isfinite(f):
        raise DesignError(f"{what} must be a number.")
    inches = f * k
    if allow_zero and inches == 0:
        return 0.0
    if inches < lo - 1e-9 or inches > hi + 1e-9:
        u = "in" if k == 1 else "mm"
        raise DesignError(f"{what} must be between {lo / k:g} and {hi / k:g} {u}.")
    return inches


def _list(v, what: str) -> list:
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise DesignError(f"{what} must be a list.")
    if len(v) > MAX_FEATURES:
        raise DesignError(f"Use {MAX_FEATURES} {what} or fewer.")
    return [x for x in v if isinstance(x, dict)]


def clean(spec: dict) -> dict:
    """Check a spec and return it normalized (all sizes in inches, plus the units to show them in)."""
    if not isinstance(spec, dict):
        raise DesignError("The design is missing.")
    t = spec.get("type")
    if t not in TYPES:
        raise DesignError("Choose a part type: " + ", ".join(TYPE_LABEL[x] for x in TYPES) + ".")
    units = "mm" if spec.get("units") == "mm" else "in"
    k = 1 / MM if units == "mm" else 1.0
    p = spec.get("params") if isinstance(spec.get("params"), dict) else {}
    out = {"type": t, "units": units, "name": re.sub(r"[^\w .,()+-]", "", str(spec.get("name") or TYPE_LABEL[t]))[:60].strip() or TYPE_LABEL[t],
           "material": str(spec.get("material") or "")[:60], "notes": str(spec.get("notes") or "")[:500], "params": {}}
    P = out["params"]
    if t == "frame":
        from . import frame

        try:
            out["params"] = frame.clean(p, units)
        except frame.FrameError as exc:
            raise DesignError(str(exc)) from exc
        return out

    def n(key, label, lo=MIN_IN, hi=MAX_IN, zero=False, default=None):
        v = p.get(key, default)
        if v is None:
            raise DesignError(f"{label} is missing.")
        P[key] = _num(v, label, lo, hi, k, zero)
        return P[key]

    def holes(key, what, span_x, span_y, dia_max):
        res = []
        for i, h in enumerate(_list(p.get(key), what), 1):
            d = _num(h.get("diameter"), f"{what} {i} diameter", 0.02, dia_max, k)
            x = _num(h.get("x"), f"{what} {i} position", -MAX_IN, MAX_IN, k, True)
            y = _num(h.get("y"), f"{what} {i} position", -MAX_IN, MAX_IN, k, True)
            if not (d / 2 - 1e-6 <= x <= span_x - d / 2 + 1e-6 and d / 2 - 1e-6 <= y <= span_y - d / 2 + 1e-6):
                raise DesignError(f"{what} {i} ({_fmt(d / k)} wide at {_fmt(x / k)}, {_fmt(y / k)}) runs off the edge of the part.")
            depth = _num(h.get("depth", 0), f"{what} {i} depth", MIN_IN, MAX_IN, k, True)
            res.append({"x": x, "y": y, "diameter": d, "depth": depth})
        P[key] = res

    if t in ("plate", "block"):
        L, W, T = n("length", "Length"), n("width", "Width"), n("thickness", "Thickness" if t == "plate" else "Height")
        r = n("corner_radius", "Corner radius", 0, MAX_IN, True, 0)
        if r * 2 > min(L, W) + 1e-9:
            raise DesignError("The corner radius is more than half the width.")
        holes("holes", "Hole", L, W, min(L, W))
        sl = []
        for i, s in enumerate(_list(p.get("slots"), "Slot"), 1):
            ln, wd = _num(s.get("length"), f"Slot {i} length", 0.02, MAX_IN, k), _num(s.get("width"), f"Slot {i} width", 0.02, MAX_IN, k)
            if wd > ln:
                ln, wd = wd, ln
            x, y = _num(s.get("x"), f"Slot {i} position", 0, MAX_IN, k, True), _num(s.get("y"), f"Slot {i} position", 0, MAX_IN, k, True)
            ang = 90 if int(float(s.get("angle") or 0)) % 180 == 90 else 0
            hx, hy = (ln / 2, wd / 2) if ang == 0 else (wd / 2, ln / 2)
            if x - hx < -1e-6 or x + hx > L + 1e-6 or y - hy < -1e-6 or y + hy > W + 1e-6:
                raise DesignError(f"Slot {i} runs off the edge of the part.")
            sl.append({"x": x, "y": y, "length": ln, "width": wd, "angle": ang})
        P["slots"] = sl
        pk = []
        for i, s in enumerate(_list(p.get("pockets"), "Pocket"), 1):
            ln, wd = _num(s.get("length"), f"Pocket {i} length", 0.02, MAX_IN, k), _num(s.get("width"), f"Pocket {i} width", 0.02, MAX_IN, k)
            x, y = _num(s.get("x"), f"Pocket {i} position", 0, MAX_IN, k, True), _num(s.get("y"), f"Pocket {i} position", 0, MAX_IN, k, True)
            dep = _num(s.get("depth", 0), f"Pocket {i} depth", MIN_IN, MAX_IN, k, True)
            if dep >= T - 1e-6:
                dep = 0.0
            cr = _num(s.get("corner_radius", 0), f"Pocket {i} corner radius", 0, MAX_IN, k, True)
            if cr * 2 > min(ln, wd) + 1e-9:
                raise DesignError(f"Pocket {i} corner radius is more than half its width.")
            if x - ln / 2 < -1e-6 or x + ln / 2 > L + 1e-6 or y - wd / 2 < -1e-6 or y + wd / 2 > W + 1e-6:
                raise DesignError(f"Pocket {i} runs off the edge of the part.")
            pk.append({"x": x, "y": y, "length": ln, "width": wd, "depth": dep, "corner_radius": cr})
        P["pockets"] = pk
        for h in P["holes"]:
            if h["depth"] >= T - 1e-6:
                h["depth"] = 0.0
    elif t == "l_bracket":
        A, B, W, T = n("leg_a", "Base leg"), n("leg_b", "Upright leg"), n("width", "Width"), n("thickness", "Thickness", MIN_IN, 2)
        R = n("bend_radius", "Inside bend radius", 0, 4, True, T)
        if min(A, B) <= R + T + 0.02:
            raise DesignError("Each leg must be longer than the bend (inside radius plus thickness).")
        holes("holes_a", "Base hole", A, W, W)
        holes("holes_b", "Upright hole", B, W, W)
        for key, leg in (("holes_a", "base"), ("holes_b", "upright")):
            for i, h in enumerate(P[key], 1):
                h["depth"] = 0.0
                if h["x"] - h["diameter"] / 2 < R + T - 1e-6:
                    raise DesignError(f"Hole {i} on the {leg} is in the bend. Move it at least {_fmt((R + T + h['diameter'] / 2) / k)} from the outside corner.")
    elif t == "u_channel":
        L, B, H, T = n("length", "Length"), n("base", "Outside width"), n("height", "Outside height"), n("thickness", "Thickness", MIN_IN, 2)
        R = n("bend_radius", "Inside bend radius", 0, 4, True, T)
        if B <= 2 * (R + T) + 0.02 or H <= R + T + 0.02:
            raise DesignError("The channel is too small for its bends: make it wider or taller, or use a smaller bend radius.")
        holes("holes_base", "Base hole", L, B, B)
        holes("holes_flange", "Side hole", L, H, H)
        for h in P["holes_base"] + P["holes_flange"]:
            h["depth"] = 0.0
        for i, h in enumerate(P["holes_flange"], 1):
            if h["y"] - h["diameter"] / 2 < R + T - 1e-6:
                raise DesignError(f"Side hole {i} is in the bend. Raise it at least {_fmt((R + T + h['diameter'] / 2) / k)} from the bottom.")
    elif t == "box":
        L, W, H = n("length", "Length"), n("width", "Width"), n("height", "Height")
        wall, fl = n("wall", "Wall", MIN_IN, 4), n("floor", "Floor", MIN_IN, 4)
        if 2 * wall >= min(L, W) - 0.02 or fl >= H - 0.02:
            raise DesignError("The walls or floor are too thick for the box size.")
        holes("holes", "Floor hole", L, W, min(L, W))
        for h in P["holes"]:
            h["depth"] = 0.0
    elif t == "round":
        secs = _list(p.get("sections"), "Section")
        if not secs:
            raise DesignError("Give at least one diameter and length.")
        if len(secs) > 20:
            raise DesignError("Use 20 sections or fewer.")
        P["sections"] = [{"diameter": _num(s.get("diameter"), f"Section {i} diameter", 0.02, 24, k), "length": _num(s.get("length"), f"Section {i} length", MIN_IN, MAX_IN, k)}
                         for i, s in enumerate(secs, 1)]
        if sum(s["length"] for s in P["sections"]) > MAX_IN:
            raise DesignError(f"The total length must be {MAX_IN / k:g} {units} or less.")
        bore = p.get("bore") if isinstance(p.get("bore"), dict) else None
        if bore and float(bore.get("diameter") or 0):
            d = _num(bore.get("diameter"), "Bore diameter", 0.02, 24, k)
            if d >= min(s["diameter"] for s in P["sections"][:1]) - 0.02:
                raise DesignError("The bore is as big as the part.")
            dep = _num(bore.get("depth", 0), "Bore depth", MIN_IN, MAX_IN, k, True)
            total = sum(s["length"] for s in P["sections"])
            if dep >= total - 1e-6:
                dep = 0.0
            if dep == 0 and d >= min(s["diameter"] for s in P["sections"]) - 0.02:
                raise DesignError("A through bore must be smaller than every diameter.")
            P["bore"] = {"diameter": d, "depth": dep}
    elif t == "flange":
        D, T = n("diameter", "Diameter", 0.1, 36), n("thickness", "Thickness")
        bore = n("bore", "Center bore", 0, 34, True, 0)
        if bore >= D - 0.1:
            raise DesignError("The bore is as big as the flange.")
        bc = p.get("bolt_circle") if isinstance(p.get("bolt_circle"), dict) else None
        if bc and int(float(bc.get("count") or 0)):
            cnt = int(float(bc.get("count")))
            if not 1 <= cnt <= 72:
                raise DesignError("Bolt holes: use 1 to 72.")
            bcd = _num(bc.get("diameter"), "Bolt circle diameter", 0.1, 36, k)
            hd = _num(bc.get("hole_diameter"), "Bolt hole diameter", 0.02, 4, k)
            if bcd + hd > D - 0.02 or bcd - hd < bore + 0.02:
                raise DesignError("The bolt holes run into the edge or the bore. Change the bolt circle diameter.")
            if cnt > 1 and math.pi * bcd / cnt < hd + 0.02:
                raise DesignError("The bolt holes overlap. Use fewer or smaller holes.")
            P["bolt_circle"] = {"count": cnt, "diameter": bcd, "hole_diameter": hd}
        hub = p.get("hub") if isinstance(p.get("hub"), dict) else None
        if hub and float(hub.get("diameter") or 0):
            hdia = _num(hub.get("diameter"), "Hub diameter", 0.1, 36, k)
            hh = _num(hub.get("height"), "Hub height", MIN_IN, MAX_IN, k)
            if hdia <= bore + 0.04 or hdia >= D:
                raise DesignError("The hub must be bigger than the bore and smaller than the flange.")
            if P.get("bolt_circle") and P["bolt_circle"]["diameter"] - P["bolt_circle"]["hole_diameter"] < hdia:
                raise DesignError("The bolt holes run into the hub.")
            P["hub"] = {"diameter": hdia, "height": hh}
    return out


# ------------------------------------------------------------------ describing
def _fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.1f}"


def summary(spec: dict) -> list[tuple[str, str]]:
    """Every size in plain words, in the customer's units: for the page, the PDF and the shop."""
    k = MM if spec["units"] == "mm" else 1.0
    u = spec["units"]
    f = lambda v: f"{_fmt(v * k)} {u}"  # noqa: E731
    P, t = spec["params"], spec["type"]
    if t == "frame":
        from . import frame

        return [("Build", spec["name"] if spec["name"] != TYPE_LABEL[t] else "T-slot frame")] + frame.summary(P, frame.members(P), spec["units"])
    rows = [("Part", TYPE_LABEL[t] if spec["name"] == TYPE_LABEL[t] else f"{spec['name']} ({TYPE_LABEL[t][0].lower() + TYPE_LABEL[t][1:] if not TYPE_LABEL[t].startswith(('L ', 'U ')) else TYPE_LABEL[t]})")]
    for key, label, _ in FIELDS.get(t, []):
        if key in P and not (key == "corner_radius" and not P[key]) and not (key == "bore" and not P[key]):
            rows.append((label, f(P[key])))

    def hl(items, label):
        if items:
            rows.append((label, "; ".join(f"{f(h['diameter'])} at {_fmt(h['x'] * k)}, {_fmt(h['y'] * k)}" + (f", {f(h['depth'])} deep" if h.get("depth") else "")
                                          for h in items)))
    if t in ("plate", "block", "box"):
        hl(P.get("holes"), "Holes (from lower-left corner)" if t != "box" else "Floor holes")
        if P.get("slots"):
            rows.append(("Slots", "; ".join(f"{f(s['length'])} x {f(s['width'])} at {_fmt(s['x'] * k)}, {_fmt(s['y'] * k)}{', vertical' if s['angle'] else ''}" for s in P["slots"])))
        if P.get("pockets"):
            rows.append(("Pockets", "; ".join(f"{f(s['length'])} x {f(s['width'])} at {_fmt(s['x'] * k)}, {_fmt(s['y'] * k)}, " + (f"{f(s['depth'])} deep" if s["depth"] else "cut through")
                                              for s in P["pockets"])))
    if t == "l_bracket":
        hl(P.get("holes_a"), "Base holes (from outside corner, edge)")
        hl(P.get("holes_b"), "Upright holes (from outside corner, edge)")
    if t == "u_channel":
        hl(P.get("holes_base"), "Base holes (along, across)")
        hl(P.get("holes_flange"), "Side holes, both sides (along, up)")
    if t == "round":
        rows.append(("Diameters", "; ".join(f"{f(s['diameter'])} for {f(s['length'])}" for s in P["sections"])))
        rows.append(("Overall length", f(sum(s["length"] for s in P["sections"]))))
        if P.get("bore"):
            rows.append(("Bore", f"{f(P['bore']['diameter'])}, " + (f"{f(P['bore']['depth'])} deep" if P["bore"]["depth"] else "through")))
    if t == "flange":
        if P.get("bolt_circle"):
            b = P["bolt_circle"]
            rows.append(("Bolt holes", f"{b['count']} x {f(b['hole_diameter'])} on a {f(b['diameter'])} circle"))
        if P.get("hub"):
            rows.append(("Hub", f"{f(P['hub']['diameter'])} diameter, {f(P['hub']['height'])} tall"))
    if spec.get("material"):
        rows.append(("Material", spec["material"]))
    if spec.get("notes"):
        rows.append(("Notes", spec["notes"]))
    return rows


def to_customer_units(spec: dict) -> dict:
    """The spec back in the customer's units (what the page and the AI edit)."""
    k = MM if spec["units"] == "mm" else 1.0
    nonlen = {"count", "angle", "leaves", "locking_casters"}

    def conv(v, key=""):
        if isinstance(v, dict):
            return {a: conv(b, a) for a, b in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, (int, float)) and not isinstance(v, bool) and key not in nonlen:
            return round(v * k, 4)
        return v
    params = {a: b for a, b in spec["params"].items() if not a.startswith("_") and a != "family"}
    return {**{a: b for a, b in spec.items() if a != "params"}, "params": conv(params)}


# ------------------------------------------------------------------ building (OpenCascade, millimeters)
def _o():
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    return BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, gp_Ax2, gp_Dir, gp_Pnt


def _box(x, y, z, dx, dy, dz):
    _, _, MakeBox, _, _, _, Pnt = _o()
    return MakeBox(Pnt(x * MM, y * MM, z * MM), dx * MM, dy * MM, dz * MM).Shape()


def _cyl(p, d, r, h, xdir=None, angle=None):
    _, _, _, MakeCyl, Ax2, Dir, Pnt = _o()
    ax = Ax2(Pnt(*(c * MM for c in p)), Dir(*d), Dir(*xdir)) if xdir else Ax2(Pnt(*(c * MM for c in p)), Dir(*d))
    return (MakeCyl(ax, r * MM, h * MM, angle) if angle else MakeCyl(ax, r * MM, h * MM)).Shape()


def _fuse(shapes):
    _, Fuse, *_ = _o()
    out = shapes[0]
    for s in shapes[1:]:
        out = Fuse(out, s).Shape()
    return out


def _compound(shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    b, c = BRep_Builder(), TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def _cut(base, tools):
    if not tools:
        return base
    Cut, *_ = _o()
    op = Cut(base, _compound(tools))
    if not op.IsDone():
        raise DesignError("The features could not be cut into the part. Check that they do not overlap oddly.")
    return op.Shape()


def _rrect(x0, y0, z0, L, W, H, r):
    """A box with rounded vertical corners."""
    if r <= 1e-6:
        return _box(x0, y0, z0, L, W, H)
    parts = [b for b, ok in ((lambda: _box(x0 + r, y0, z0, L - 2 * r, W, H), L - 2 * r > 1e-5), (lambda: _box(x0, y0 + r, z0, L, W - 2 * r, H), W - 2 * r > 1e-5)) if ok]
    parts = [b() for b in parts]
    for cx, cy in ((x0 + r, y0 + r), (x0 + L - r, y0 + r), (x0 + r, y0 + W - r), (x0 + L - r, y0 + W - r)):
        parts.append(_cyl((cx, cy, z0), (0, 0, 1), r, H))
    return _fuse([p for p in parts if p is not None])


def _slot_tool(s, z0, H):
    ln, wd = s["length"], s["width"]
    r = wd / 2
    if s["angle"]:
        return _rrect(s["x"] - r, s["y"] - ln / 2, z0, wd, ln, H, r - 1e-4)
    return _rrect(s["x"] - ln / 2, s["y"] - r, z0, ln, wd, H, r - 1e-4)


def build(spec: dict):
    """The solid for a checked spec (from clean). A part is always one piece: crumbs a cut left behind are dropped,
    and features that cut the part in two are refused (otherwise it would be quoted as an assembly of pieces)."""
    shape = _build(spec)
    return shape if spec["type"] == "frame" else _one_piece(shape)


def _one_piece(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    solids = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(ex.Current(), g)
        solids.append((abs(g.Mass()), ex.Current()))
        ex.Next()
    if len(solids) <= 1:
        return shape
    solids.sort(key=lambda t: -t[0])
    big = solids[0][0]
    keep = [sh for v, sh in solids if v >= big * 0.02]
    if len(keep) > 1:
        raise DesignError("The holes, slots or pockets cut the part into separate pieces. Move or shrink them so the part stays in one piece.")
    return keep[0]


def _build(spec: dict):
    t, P = spec["type"], spec["params"]
    eps = 0.01
    if t == "frame":
        from . import frame

        return frame.build(P)
    if t in ("plate", "block"):
        L, W, T = P["length"], P["width"], P["thickness"]
        shape = _rrect(0, 0, 0, L, W, T, P.get("corner_radius", 0))
        tools = []
        for h in P["holes"]:
            dep = h["depth"] or T
            tools.append(_cyl((h["x"], h["y"], T - dep - (eps if not h["depth"] else 0)), (0, 0, 1), h["diameter"] / 2, dep + 2 * eps))
        for s in P["slots"]:
            tools.append(_slot_tool(s, -eps, T + 2 * eps))
        for s in P["pockets"]:
            dep = s["depth"] or T
            z0 = T - dep - (eps if not s["depth"] else 0)
            x0, y0, x1, y1 = s["x"] - s["length"] / 2, s["y"] - s["width"] / 2, s["x"] + s["length"] / 2, s["y"] + s["width"] / 2
            # a notch open to an edge: run the cutter past that edge, so its rounded corners fall outside the part
            # (only the inside corners are rounded, and no thin slivers are left along the edge)
            out = s["corner_radius"] + 0.05
            x0, y0 = (x0 - out if x0 <= 1e-3 else x0), (y0 - out if y0 <= 1e-3 else y0)
            x1, y1 = (x1 + out if x1 >= L - 1e-3 else x1), (y1 + out if y1 >= W - 1e-3 else y1)
            tools.append(_rrect(x0, y0, z0, x1 - x0, y1 - y0, dep + 2 * eps, s["corner_radius"]))
        return _cut(shape, tools)
    if t == "l_bracket":
        A, B, W, T, R = P["leg_a"], P["leg_b"], P["width"], P["thickness"], P["bend_radius"]
        Ro = R + T
        parts = [_box(Ro, 0, 0, A - Ro, W, T), _box(0, 0, Ro, T, W, B - Ro)]
        if Ro > 1e-6:
            outer = _cyl((Ro, 0, Ro), (0, 1, 0), Ro, W, (0, 0, -1), math.pi / 2)
            parts.append(_cut(outer, [_cyl((Ro, -eps, Ro), (0, 1, 0), R, W + 2 * eps)]) if R > 1e-6 else outer)
        shape = _fuse(parts)
        tools = [_cyl((h["x"], h["y"], -eps), (0, 0, 1), h["diameter"] / 2, T + 2 * eps) for h in P["holes_a"]]
        tools += [_cyl((-eps, h["y"], h["x"]), (1, 0, 0), h["diameter"] / 2, T + 2 * eps) for h in P["holes_b"]]
        return _cut(shape, tools)
    if t == "u_channel":
        L, B, H, T, R = P["length"], P["base"], P["height"], P["thickness"], P["bend_radius"]
        Ro = R + T
        parts = [_box(0, Ro, 0, L, B - 2 * Ro, T), _box(0, 0, Ro, L, T, H - Ro), _box(0, B - T, Ro, L, T, H - Ro)]
        if Ro > 1e-6:
            for cy, xd in ((Ro, (0, -1, 0)), (B - Ro, (0, 0, -1))):
                outer = _cyl((0, cy, Ro), (1, 0, 0), Ro, L, xd, math.pi / 2)
                parts.append(_cut(outer, [_cyl((-eps, cy, Ro), (1, 0, 0), R, L + 2 * eps)]) if R > 1e-6 else outer)
        shape = _fuse(parts)
        tools = [_cyl((h["x"], h["y"], -eps), (0, 0, 1), h["diameter"] / 2, T + 2 * eps) for h in P["holes_base"]]
        tools += [_cyl((h["x"], -eps, h["y"]), (0, 1, 0), h["diameter"] / 2, B + 2 * eps) for h in P["holes_flange"]]
        return _cut(shape, tools)
    if t == "box":
        L, W, H, w, f = P["length"], P["width"], P["height"], P["wall"], P["floor"]
        shape = _cut(_box(0, 0, 0, L, W, H), [_box(w, w, f, L - 2 * w, W - 2 * w, H)])
        return _cut(shape, [_cyl((h["x"], h["y"], -eps), (0, 0, 1), h["diameter"] / 2, f + 2 * eps) for h in P["holes"]])
    if t == "round":
        x, parts = 0.0, []
        for s in P["sections"]:
            parts.append(_cyl((x, 0, 0), (1, 0, 0), s["diameter"] / 2, s["length"]))
            x += s["length"]
        shape = _fuse(parts)
        b = P.get("bore")
        if b:
            dep = b["depth"] or x
            shape = _cut(shape, [_cyl((-eps, 0, 0), (1, 0, 0), b["diameter"] / 2, dep + (2 * eps if not b["depth"] else eps))])
        return shape
    if t == "flange":
        D, T = P["diameter"], P["thickness"]
        parts = [_cyl((0, 0, 0), (0, 0, 1), D / 2, T)]
        hub = P.get("hub")
        if hub:
            parts.append(_cyl((0, 0, T - eps / 10), (0, 0, 1), hub["diameter"] / 2, hub["height"] + eps / 10))
        shape = _fuse(parts)
        top = T + (hub["height"] if hub else 0)
        tools = []
        if P.get("bore"):
            tools.append(_cyl((0, 0, -eps), (0, 0, 1), P["bore"] / 2, top + 2 * eps))
        bc = P.get("bolt_circle")
        if bc:
            for i in range(bc["count"]):
                a = 2 * math.pi * i / bc["count"]
                tools.append(_cyl((bc["diameter"] / 2 * math.cos(a), bc["diameter"] / 2 * math.sin(a), -eps), (0, 0, 1), bc["hole_diameter"] / 2, T + 2 * eps))
        return _cut(shape, tools)
    raise DesignError("Unknown part type.")


def step_bytes(shape, name: str) -> bytes:
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    from OCP.Message import Message, Message_Gravity

    for pr in Message.DefaultMessenger_s().Printers():  # the writer prints transfer statistics to the console
        pr.SetTraceLevel(Message_Gravity.Message_Fail)
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetCVal_s("write.step.product.name", name[:60] or "part")
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "part.step"
        if w.Write(str(p)) != IFSelect_RetDone:
            raise DesignError("The model could not be saved.")
        return p.read_bytes()


def _valid(shape) -> bool:
    from OCP.BRepCheck import BRepCheck_Analyzer

    return BRepCheck_Analyzer(shape).IsValid()


def render(spec_in: dict) -> dict:
    """Check, build and draw a design: the normalized spec, its sizes in words, the 3D mesh and the three-view drawing."""
    from . import cad, portal_views

    spec = clean(spec_in)
    shape = build(spec)
    if spec["type"] != "frame" and not _valid(shape):
        raise DesignError("Those features make an invalid part (for example, holes that overlap or cut it apart). Check the positions.")
    L, W, H = portal_views._bbox_in(shape)
    sheet = portal_views.build_sheet(shape, kind="model", label=spec["name"])
    k = MM if spec["units"] == "mm" else 1.0
    return {"spec": to_customer_units(spec), "summary": [{"label": a, "text": b} for a, b in summary(spec)],
            "size": [round(L * k, 3), round(W * k, 3), round(H * k, 3)], "units": spec["units"],
            "mesh": cad.mesh(shape, 60_000), "drawing": portal_views.to_svg(sheet)}


def step_for(spec_in: dict) -> tuple[str, bytes, dict]:
    """(file name, STEP bytes, normalized spec) for pricing or attaching to a project idea."""
    spec = clean(spec_in)
    shape = build(spec)
    if spec["type"] != "frame" and not _valid(shape):
        raise DesignError("Those features make an invalid part. Check the positions.")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", spec["name"]).strip("_")[:40] or "part"
    return f"{slug}.step", step_bytes(shape, spec["name"]), spec


def templates() -> list[dict]:
    """The part types and their fields with defaults, for the form on the page (inches)."""
    out = []
    for t in TYPES:
        d = {"type": t, "label": TYPE_LABEL[t], "fields": [{"key": a, "label": b, "default": c} for a, b, c in FIELDS[t]]}
        if t == "round":
            d["default_params"] = {"sections": [{"diameter": 1.0, "length": 2.0}, {"diameter": 0.75, "length": 1.0}], "bore": {"diameter": 0.25, "depth": 0}}
        elif t == "flange":
            d["default_params"] = {"diameter": 4.0, "thickness": 0.375, "bore": 1.0, "bolt_circle": {"count": 4, "diameter": 3.0, "hole_diameter": 0.266}}
        elif t == "frame":
            from . import frame

            d["default_params"] = {k: v for k, v in frame.DEFAULTS.items() if k != "door_profile"}
            d["default_params"]["doors"] = [{"face": "front", "leaves": 1, "panel": "PANEL-PC-250"}]
            d["profiles"] = [{"id": p["id"], "label": p["label"], "family": p["family"]} for p in frame.PROFILES.values()]
            d["panels"] = [{"id": k, "label": v[0]} for k, v in frame.PANELS.items()]
        else:
            d["default_params"] = {a: c for a, _, c in FIELDS[t]}
        out.append(d)
    return out
