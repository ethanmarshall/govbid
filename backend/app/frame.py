"""T-slot extrusion frames (carts, stands, enclosures, tables) for "Design a part".

A frame spec describes the build the way a customer would: outside size, which profile the corner posts and the
rails are, horizontal rings (always a bottom and top ring, plus any shelf levels), casters or feet, inset doors and
panels. From that this module works out every member with butt-joint cut lengths, the hardware and panels, builds a
3D assembly (each profile with its T-slots), and turns it into extrusion lines priced by app/extrusion.py.

Coordinates (inches): X across the width (front face at Y = 0), Y front to back, Z up from the bottom of the frame.
Corner posts run the full height. Rails butt into the posts: front and back rails span the width between posts,
side rails span the depth between posts. Rings sit with their bottom at z (bottom ring at 0, top ring at the top).

Panel sizes add the slot engagement on each edge; they are close but must be checked against the supplier's chart
before ordering. Door latches are not in the catalog and are left as a note.
"""
from __future__ import annotations

import math
import re

from .extrusion_catalog import LEGACY_PANELS, PANELS, profile_rows

FACES = ("front", "back", "left", "right")
# panel edge in the slot, inches per side: half of what 80/20 says to add to the visible opening (catalog 24, 4-5:
# 10 Series .500 in, 15 Series .750 in, 20 Series 10 mm, 40 Series 22 mm)
ENGAGE = {"10": 0.25, "15": 0.375, "MS": 5 / 25.4, "ML": 11 / 25.4}
# thread tapped into the post ends for the base (80/20 stem casters and leveling feet, 5-4 and 5-24)
BASE_THREAD = {("casters", "15"): "7/16-14", ("feet", "15"): "3/8-16", ("casters", "10"): "1/4-20", ("feet", "10"): "1/4-20"}
SLOT = {"10": (0.26, 0.2), "15": (0.32, 0.26), "MS": (0.24, 0.18), "ML": (0.32, 0.26)}  # slot opening, depth (drawing only)
MODULE = {"10": 1.0, "15": 1.5, "MS": None, "ML": None}


class FrameError(ValueError):
    pass


def _profiles() -> dict:
    out = {}
    for r in profile_rows():
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", r["size"])[:2]]
        if len(nums) < 2:
            continue
        k = 1 / 25.4 if "mm" in r["size"] else 1.0
        a, b = sorted((nums[0] * k, nums[1] * k))
        out[r["id"]] = {"id": r["id"], "family": r["family"], "small": round(a, 4), "large": round(b, 4), "label": f"{r['id']} ({r['size']})"}
    return out


PROFILES = _profiles()

DEFAULTS = {"width": 36.0, "depth": 26.0, "height": 33.75, "post_profile": "1530", "rail_profile": "1515", "door_profile": "",
            "post_wide_along": "depth", "joints": "anchor", "base": "casters", "caster_height": 5.0, "locking_casters": 2,
            "levels": [], "doors": [], "panels": {}, "top_panel": "", "bottom_panel": "", "door_gap": 0.125}


def _n(v, what, lo, hi, k):
    try:
        f = float(v) * k
    except (TypeError, ValueError):
        raise FrameError(f"{what} must be a number.")
    if not math.isfinite(f) or f < lo - 1e-9 or f > hi + 1e-9:
        raise FrameError(f"{what} must be between {lo / k:g} and {hi / k:g}.")
    return f


def _panel(v, what):
    v = str(v or "").strip()
    if v and v not in PANELS:
        raise FrameError(f"{what}: choose a panel from the list ({', '.join(k for k in PANELS if k not in LEGACY_PANELS)}) or none.")
    return v


def clean(p: dict, units: str = "in") -> dict:
    """Check frame params (in the spec's units) and return them in inches."""
    k = 1 / 25.4 if units == "mm" else 1.0
    p = {**DEFAULTS, **{a: b for a, b in (p or {}).items() if b is not None}}
    out = {"width": _n(p["width"], "Width", 6, 240, k), "depth": _n(p["depth"], "Depth", 6, 240, k), "height": _n(p["height"], "Height", 6, 240, k)}
    for key, label in (("post_profile", "Corner post profile"), ("rail_profile", "Rail profile")):
        if p[key] not in PROFILES:
            raise FrameError(f"{label}: use one of {', '.join(PROFILES)}.")
        out[key] = p[key]
    door = p.get("door_profile") or p["rail_profile"]
    if door not in PROFILES:
        raise FrameError(f"Door profile: use one of {', '.join(PROFILES)}.")
    out["door_profile"] = door
    fams = {PROFILES[out["post_profile"]]["family"], PROFILES[out["rail_profile"]]["family"], PROFILES[door]["family"]}
    if len(fams) > 1:
        raise FrameError("Use profiles from one series (for example all 15 series) so the hardware fits.")
    out["family"] = fams.pop()
    out["post_wide_along"] = "width" if p.get("post_wide_along") == "width" else "depth"
    out["joints"] = "bracket" if p.get("joints") == "bracket" else "anchor"
    out["base"] = p.get("base") if p.get("base") in ("casters", "feet", "none") else "casters"
    out["caster_height"] = _n(p.get("caster_height") or 5, "Caster height", 1, 12, k) if out["base"] == "casters" else (1.0 if out["base"] == "feet" else 0.0)
    out["locking_casters"] = max(0, min(4, int(float(p.get("locking_casters") or 0)))) if out["base"] == "casters" else 0
    out["door_gap"] = _n(p.get("door_gap") or 0.125, "Door gap", 0.03, 0.5, 1.0)
    post, rail = PROFILES[out["post_profile"]], PROFILES[out["rail_profile"]]
    px, py = (post["large"], post["small"]) if out["post_wide_along"] == "width" else (post["small"], post["large"])
    out["_post"] = (px, py)
    r = rail["small"]
    if out["width"] <= 2 * px + 2 or out["depth"] <= 2 * py + 2:
        raise FrameError("The frame is too small for its corner posts.")
    if out["height"] < 2 * r + 1:
        raise FrameError("The frame is too short for a bottom and top ring.")
    levels = []
    for i, lv in enumerate((p.get("levels") or [])[:12], 1):
        lv = lv if isinstance(lv, dict) else {"z": lv}
        z = _n(lv.get("z"), f"Level {i} height", r + 0.5, out["height"] - r - 0.5, k)
        levels.append({"z": z, "shelf": _panel(lv.get("shelf"), f"Level {i} shelf")})
    out["levels"] = sorted(levels, key=lambda x: x["z"])
    doors, seen = [], set()
    for i, d in enumerate((p.get("doors") or [])[:4], 1):
        if not isinstance(d, dict) or d.get("face") not in FACES:
            raise FrameError(f"Door {i}: say which face it is on ({', '.join(FACES)}).")
        if d["face"] in seen:
            raise FrameError(f"Door {i}: there is already a door on the {d['face']}.")
        seen.add(d["face"])
        doors.append({"face": d["face"], "leaves": 2 if int(float(d.get("leaves") or 1)) == 2 else 1,
                      "panel": _panel(d.get("panel") if d.get("panel") is not None else "PANEL-PC-250", f"Door {i} panel")})
    out["doors"] = doors
    pan = p.get("panels") if isinstance(p.get("panels"), dict) else {}
    out["panels"] = {f: _panel(pan.get(f), f"{f.title()} panel") for f in FACES if pan.get(f) and f not in seen}
    out["top_panel"] = _panel(p.get("top_panel"), "Top panel")
    out["bottom_panel"] = _panel(p.get("bottom_panel"), "Bottom panel")
    # door leaves must fit their profile
    dp = PROFILES[door]["small"]
    for d in doors:
        ow = (out["width"] if d["face"] in ("front", "back") else out["depth"]) - 2 * (px if d["face"] in ("front", "back") else py)
        lw = (ow - (d["leaves"] + 1) * out["door_gap"]) / d["leaves"]
        if lw < 2 * dp + 2:
            raise FrameError(f"The {d['face']} opening is too narrow for {d['leaves']} door(s) of {door}.")
    return out


# ------------------------------------------------------------------ members
def _m(role, profile, axis, x, y, z, length, sa, sb, machining=None):
    """A member: role, profile, axis it runs along, min corner, length, and its cross-section sizes on the other two axes (in X, Y, Z order)."""
    return {"role": role, "profile": profile, "axis": axis, "at": (x, y, z), "length": round(length, 4), "cross": (sa, sb), "machining": machining or []}


def members(f: dict) -> dict:
    """Every member, panel and hardware item, positioned (inches)."""
    W, D, H = f["width"], f["depth"], f["height"]
    px, py = f["_post"]
    rp = PROFILES[f["rail_profile"]]
    r = rp["small"]
    joint_ops = [{"op": "counterbore", "count": 2}] if f["joints"] == "anchor" else []
    base_ops = ([{"op": "end_tap", "count": 1, **({"thread": BASE_THREAD[(f["base"], f["family"])]} if (f["base"], f["family"]) in BASE_THREAD else {})}]
                if f["base"] in ("casters", "feet") else [])
    out = []
    for name, x, y in (("front left", 0, 0), ("front right", W - px, 0), ("back left", 0, D - py), ("back right", W - px, D - py)):
        out.append(_m(f"Corner post, {name}", f["post_profile"], "z", x, y, 0, H, px, py, base_ops))
    door_faces = {d["face"] for d in f["doors"]}
    rings = [{"z": 0.0, "name": "bottom", "shelf": f["bottom_panel"]}] + [{"z": lv["z"] - r, "name": f"level {i}", "shelf": lv["shelf"], "level": True}
                                                                         for i, lv in enumerate(f["levels"], 1)] + [{"z": H - r, "name": "top", "shelf": f["top_panel"]}]
    for ring in rings:
        z = ring["z"]
        mid = ring.get("level")
        faces = [fc for fc in FACES if not (mid and fc in door_faces)]  # a shelf ring skips the rail across a door opening
        if "front" in faces:
            out.append(_m(f"Front rail, {ring['name']}", f["rail_profile"], "x", px, 0, z, W - 2 * px, r, r, joint_ops))
        if "back" in faces:
            out.append(_m(f"Back rail, {ring['name']}", f["rail_profile"], "x", px, D - r, z, W - 2 * px, r, r, joint_ops))
        if "left" in faces:
            out.append(_m(f"Left rail, {ring['name']}", f["rail_profile"], "y", 0, py, z, D - 2 * py, r, r, joint_ops))
        if "right" in faces:
            out.append(_m(f"Right rail, {ring['name']}", f["rail_profile"], "y", W - r, py, z, D - 2 * py, r, r, joint_ops))
        ring["faces"] = faces
    e = ENGAGE.get(f["family"], 0.25)
    panels, hardware = [], []

    def panel(role, pid, size_a, size_b, box):
        th = PANELS[pid][2]
        panels.append({"role": role, "panel": pid, "width": round(size_a + 2 * e, 3), "height": round(size_b + 2 * e, 3), "box": box, "t": th})

    # shelves (top, bottom, levels): in the ring, between its rails
    for ring in rings:
        if ring.get("shelf"):
            th = PANELS[ring["shelf"]][2]
            zc = ring["z"] + r / 2 - th / 2
            panel(f"{ring['name'].title()} panel", ring["shelf"], W - 2 * r, D - 2 * r, (r - e, r - e, zc, W - 2 * r + 2 * e, D - 2 * r + 2 * e, th))
    # side panels: one per bay between the rings that have a rail on that face
    for fc, pid in f["panels"].items():
        zs = [rg["z"] for rg in rings if fc in rg["faces"]]
        th = PANELS[pid][2]
        span = (W - 2 * px) if fc in ("front", "back") else (D - 2 * py)
        for a, b in zip(zs, zs[1:]):
            h = b - (a + r)
            if fc in ("front", "back"):
                y = r / 2 - th / 2 if fc == "front" else D - r / 2 - th / 2
                box = (px - e, y, a + r - e, span + 2 * e, th, h + 2 * e)
            else:
                x = r / 2 - th / 2 if fc == "left" else W - r / 2 - th / 2
                box = (x, py - e, a + r - e, th, span + 2 * e, h + 2 * e)
            panel(f"{fc.title()} panel", pid, span, h, box)
    # doors: inset in the opening between the posts and between the bottom and top rings
    dp = PROFILES[f["door_profile"]]
    d = dp["small"]
    g = f["door_gap"]
    leaves_total = 0
    for door in f["doors"]:
        fc, n = door["face"], door["leaves"]
        along_x = fc in ("front", "back")
        span = (W - 2 * px) if along_x else (D - 2 * py)
        lw = (span - (n + 1) * g) / n
        lh = (H - 2 * r) - 2 * g
        z0 = r + g
        for i in range(n):
            leaves_total += 1
            s = (px if along_x else py) + g + i * (lw + g)
            tag = f"{fc} door" + (f" {'left' if i == 0 else 'right'}" if n == 2 else "")
            if along_x:
                y = 0.0 if fc == "front" else D - d
                out.append(_m(f"Door stile, {tag}", f["door_profile"], "z", s, y, z0, lh, d, d))
                out.append(_m(f"Door stile, {tag}", f["door_profile"], "z", s + lw - d, y, z0, lh, d, d))
                out.append(_m(f"Door rail, {tag}", f["door_profile"], "x", s + d, y, z0, lw - 2 * d, d, d, joint_ops))
                out.append(_m(f"Door rail, {tag}", f["door_profile"], "x", s + d, y, z0 + lh - d, lw - 2 * d, d, d, joint_ops))
            else:
                x = 0.0 if fc == "left" else W - d
                out.append(_m(f"Door stile, {tag}", f["door_profile"], "z", x, s, z0, lh, d, d))
                out.append(_m(f"Door stile, {tag}", f["door_profile"], "z", x, s + lw - d, z0, lh, d, d))
                out.append(_m(f"Door rail, {tag}", f["door_profile"], "y", x, s + d, z0, lw - 2 * d, d, d, joint_ops))
                out.append(_m(f"Door rail, {tag}", f["door_profile"], "y", x, s + d, z0 + lh - d, lw - 2 * d, d, d, joint_ops))
            if door["panel"]:
                th = PANELS[door["panel"]][2]
                if along_x:
                    yy = (d / 2 - th / 2) if fc == "front" else D - d / 2 - th / 2
                    box = (s + d - e, yy, z0 + d - e, lw - 2 * d + 2 * e, th, lh - 2 * d + 2 * e)
                else:
                    xx = (d / 2 - th / 2) if fc == "left" else W - d / 2 - th / 2
                    box = (xx, s + d - e, z0 + d - e, th, lw - 2 * d + 2 * e, lh - 2 * d + 2 * e)
                panel(f"Door panel, {tag}", door["panel"], lw - 2 * d, lh - 2 * d, box)
            hinges = 3 if lh > 36 else 2
            hardware.append(("HINGE", hinges, f"lift-off hinges, {tag} (mounting hardware included)"))
            hardware.append(("HANDLE", 1, f"handle with its screws and T-nuts, {tag}"))
    rail_ends = sum(2 for m in out if m["role"].startswith(("Front rail", "Back rail", "Left rail", "Right rail", "Door rail")))
    if f["joints"] == "anchor":
        hardware.append(("ANCHOR", rail_ends, "anchor fasteners, one per rail end"))
    else:
        hardware.append(("BRKT-4H", rail_ends, "inside corner brackets with screws and T-nuts, one per rail end"))
    if f["base"] == "casters":
        lock = f["locking_casters"]
        if lock:
            hardware.append(("CASTER-LOCK", lock, "swivel casters with brakes"))
        if 4 - lock:
            hardware.append(("CASTER", 4 - lock, "swivel casters"))
    elif f["base"] == "feet":
        hardware.append(("FOOT", 4, "leveling feet"))
    if not f["top_panel"]:
        hardware.append(("ENDCAP", 4, "end caps on the tops of the posts"))
    return {"members": out, "panels": panels, "hardware": hardware, "doors": leaves_total}


# ------------------------------------------------------------------ cut list, lines for pricing, words
def _frac(v: float) -> str:
    """Inches to the nearest 1/16 as a fraction (33.75 -> 33 3/4)."""
    n = round(v * 16)
    whole, rem = divmod(n, 16)
    if not rem:
        return f"{whole}"
    g = math.gcd(rem, 16)
    return f"{whole} {rem // g}/{16 // g}" if whole else f"{rem // g}/{16 // g}"


def cut_list(parts: dict) -> list[dict]:
    groups: dict = {}
    for m in parts["members"]:
        role = re.sub(r",.*$", "", m["role"])
        key = (m["profile"], round(m["length"] * 16) / 16, tuple((o["op"], o["count"]) for o in m["machining"]))
        g = groups.setdefault(key, {"profile": m["profile"], "length": key[1], "qty": 0, "roles": [], "machining": m["machining"]})
        g["qty"] += 1
        if role not in g["roles"]:
            g["roles"].append(role)
    return sorted(groups.values(), key=lambda g: (g["profile"], -g["length"]))


def extrusion_lines(parts: dict, family: str) -> list[dict]:
    """The build as lines for extrusion.price_build."""
    lines = []
    for g in cut_list(parts):
        lines.append({"kind": "profile", "catalog_id": g["profile"], "qty": g["qty"], "length_in": g["length"],
                      "machining": [dict(o) for o in g["machining"]], "description": ", ".join(g["roles"])})
    hw: dict = {}
    for base, qty, why in parts["hardware"]:
        hid = f"{base}-{family}"
        h = hw.setdefault(hid, {"kind": "hardware", "catalog_id": hid, "qty": 0, "notes": []})
        h["qty"] += qty
        h["notes"].append(why)
    lines += [{**h, "notes": "; ".join(h["notes"])} for h in hw.values()]
    pg: dict = {}
    for p in parts["panels"]:
        key = (p["panel"], p["width"], p["height"])
        pg.setdefault(key, {"kind": "panel", "catalog_id": p["panel"], "qty": 0, "width_in": p["width"], "height_in": p["height"], "description": p["role"]})
        pg[key]["qty"] += 1
    lines += list(pg.values())
    return lines


HW_LABEL = {"ANCHOR": "Anchor fasteners", "BRKT-4H": "Corner brackets", "BRKT-2H": "Corner brackets", "BUTT": "Butt fasteners", "ENDFAST": "End fasteners", "TNUT-DROP": "Drop-in T-nuts", "SCREW-BHSCS": "Button head screws",
            "CASTER": "Swivel casters", "CASTER-LOCK": "Swivel casters with brakes", "FOOT": "Leveling feet", "HINGE": "Hinges",
            "HANDLE": "Handles", "ENDCAP": "End caps", "CASTER-PLATE": "Caster base plates"}


def summary(f: dict, parts: dict, units: str) -> list[tuple[str, str]]:
    k = 25.4 if units == "mm" else 1.0

    def L(v):
        return f"{v * k:.0f} mm" if units == "mm" else f"{_frac(v)} in"
    rows = [("Frame (outside)", f"{L(f['width'])} wide x {L(f['depth'])} deep x {L(f['height'])} tall"
             + (f", plus about {L(f['caster_height'])} of casters" if f["base"] == "casters" else ""))]
    rows.append(("Profiles", f"Corner posts {f['post_profile']}" + (f" (wide face along the {f['post_wide_along']})" if PROFILES[f["post_profile"]]["large"] != PROFILES[f["post_profile"]]["small"] else "")
                 + f", rails {f['rail_profile']}" + (f", doors {f['door_profile']}" if f["doors"] else "")))
    rows.append(("Joints", "Butt joints with anchor fasteners (counterbored rail ends)" if f["joints"] == "anchor" else "Butt joints with corner brackets"))
    if f["levels"]:
        rows.append(("Shelf levels", "; ".join(f"{L(lv['z'])} up" + (f", {PANELS[lv['shelf']][0]}" if lv["shelf"] else ", no panel") for lv in f["levels"])))
    if f["doors"]:
        rows.append(("Doors", "; ".join(f"{d['face']}: {'two doors' if d['leaves'] == 2 else 'one door'}, inset, {PANELS[d['panel']][0] if d['panel'] else 'open frame'}" for d in f["doors"])))
    sides = [f"{fc}: {PANELS[pid][0]}" for fc, pid in f["panels"].items()] + ([f"top: {PANELS[f['top_panel']][0]}"] if f["top_panel"] else []) + \
            ([f"bottom: {PANELS[f['bottom_panel']][0]}"] if f["bottom_panel"] else [])
    if sides:
        rows.append(("Panels", "; ".join(sides)))
    for g in cut_list(parts):
        ops = ", ".join(f"{o['count']} {o['op'].replace('_', ' ')}" + (f" {o['thread']}" if o.get("thread") else "") for o in g["machining"])
        rows.append((f"Cut {g['profile']}", f"{g['qty']} x {L(g['length'])}: {', '.join(g['roles']).lower()}" + (f" ({ops} each)" if ops else "")))
    hw: dict = {}
    for base, qty, _ in parts["hardware"]:
        hw[base] = hw.get(base, 0) + qty
    rows.append(("Hardware", ", ".join(f"{q} {HW_LABEL.get(b, b).lower()}" for b, q in hw.items())))
    pc: dict = {}
    for p in parts["panels"]:
        key = (PANELS[p["panel"]][0], p["width"], p["height"])
        pc[key] = pc.get(key, 0) + 1
    if pc:
        rows.append(("Panel sizes (with slot engagement)", "; ".join(f"{q} x {L(w)} x {L(h)} {name.lower()}" for (name, w, h), q in pc.items())))
    if f["doors"]:
        rows.append(("Not included", "Door latches or catches (tell us which you want)"))
    return rows


# ------------------------------------------------------------------ 3D (millimeters)
def _member_shape(m, family):
    from . import design

    (x, y, z), L = m["at"], m["length"]
    sa, sb = m["cross"]
    if m["axis"] == "x":
        dims, at = (L, sa, sb), (x, y, z)
    elif m["axis"] == "y":
        dims, at = (sa, L, sb), (x, y, z)
    else:
        dims, at = (sa, sb, L), (x, y, z)
    solid = design._box(*at, *dims)
    # T-slots on each long face, one per module (1.5 in on 15 series), for the look of the profile
    w, dep = SLOT.get(family, (0.3, 0.2))
    mod = MODULE.get(family) or min(sa, sb)
    tools = []
    ax = "xyz".index(m["axis"])
    for face_axis, size, other in (((ax + 1) % 3, dims[(ax + 1) % 3], dims[(ax + 2) % 3]), ((ax + 2) % 3, dims[(ax + 2) % 3], dims[(ax + 1) % 3])):
        n = max(1, round(other / mod))
        for side in (0, 1):
            for i in range(n):
                c = (i + 0.5) * other / n
                lo = list(at)
                d = [0.0, 0.0, 0.0]
                d[ax] = dims[ax] + 0.02
                lo[ax] = at[ax] - 0.01
                d[face_axis] = dep
                lo[face_axis] = at[face_axis] + (size - dep if side else 0) + (0.001 if side else -0.001)
                oth = 3 - ax - face_axis
                d[oth] = w
                lo[oth] = at[oth] + c - w / 2
                tools.append(design._box(*lo, *d))
    return design._cut(solid, tools)


def build(f: dict, parts: dict | None = None):
    from . import design

    parts = parts or members(f)
    shapes = [_member_shape(m, f["family"]) for m in parts["members"]]
    for p in parts["panels"]:
        shapes.append(design._box(*p["box"]))
    if f["base"] in ("casters", "feet"):
        px, py = f["_post"]
        hgt = f["caster_height"]
        for cx, cy in ((px / 2, py / 2), (f["width"] - px / 2, py / 2), (px / 2, f["depth"] - py / 2), (f["width"] - px / 2, f["depth"] - py / 2)):
            wheel = min(hgt * 0.7, 6)
            ey = max(1.25, wheel / 2) if f["base"] == "casters" else 0.75
            cx, cy = min(max(cx, 1.25), f["width"] - 1.25), min(max(cy, ey), f["depth"] - ey)  # keep the casters under the frame
            if f["base"] == "casters":
                shapes.append(design._box(cx - 1.25, cy - 1.25, -0.25, 2.5, 2.5, 0.25))  # mounting plate
                shapes.append(design._box(cx - 0.9, cy - 0.6, -(hgt - wheel / 2), 1.8, 1.2, hgt - wheel / 2 - 0.25))  # fork
                shapes.append(design._cyl((cx - 0.5, cy, -(hgt - wheel / 2)), (1, 0, 0), wheel / 2, 1.0))  # wheel
            else:
                shapes.append(design._cyl((cx, cy, -hgt), (0, 0, 1), 0.75, hgt))
    return design._compound(shapes)
