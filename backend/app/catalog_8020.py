"""80/20 Inc. catalog knowledge for T-slot builds: real part numbers, profile data and the design rules.

Source: 80/20 Product Catalog 24 (2023). The numbers in catalog_8020.json and the tables below were read from the
catalog; each carries the catalog page label (for example 3-12) so a person can check it. The catalog has no prices,
so prices still come from the Extrusion rates (shop config) or a distributor quote entered on the request.

What this module gives the rest of the app:
- profile(pn): weight, moments of inertia, stock lengths, the cut-to-length service number and the end tap services
- op_number(op, profile, thread): the 80/20 machining service number for one of our generic operations
- hardware_parts(base, family, qty): the 80/20 part numbers (and the extra bolts and T-nuts) for a hardware line
- order_list(lines): an order list in 80/20 part numbers with the machining callouts per piece
- check(lines): design checks against the catalog rules (machining that each fastener needs, end taps for casters
  and feet, panel thickness for the slot, stock length, shipping length)
- deflection(pn, length, load, case): the catalog's simple beam formulas (page 2-10)
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

E_PSI = 10_200_000  # modulus of elasticity, 6005A-T61 (2-10)
STOCK_MAX_IN = {"fractional": 242.0, "metric": 238.19}  # 242 in sticks; metric 6.050 m (2-16, 2-58)
UPS_MAX_IN = 95.0  # longer packages ship by commercial carrier (1-28)
CUT_TOLERANCE = {"fractional": "+/- .015 in length, +/- .002 in per inch squareness", "metric": "+/- .38 mm length, +/- .02 mm per cm squareness"}  # 10-2
# Panel sizing: add this to the visible opening so the panel edges sit in the T-slots (4-5); thickness that fits the
# slot with panel gasket (4-6)
PANEL_ADD_IN = {"10": 0.5, "15": 0.75, "20": 10 / 25.4, "25": 14 / 25.4, "30": 15 / 25.4, "40": 22 / 25.4, "45": 24 / 25.4}
PANEL_GASKET_THICKNESS_IN = {"10": (0.177, 0.177), "15": (0.220, 0.236), "20": (0.118, 0.118), "25": (0.177, 0.177),
                             "30": (0.220, 0.236), "40": (0.220, 0.236), "45": (0.220, 0.236)}
FAMILY_SERIES = {"10": "10", "15": "15", "MS": None, "ML": "40"}


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads((Path(__file__).with_name("catalog_8020.json")).read_text())


def series_of(pn: str) -> str | None:
    p = profile(pn)
    return p["series"] if p else None


def profile(pn: str) -> dict | None:
    """Catalog data for a profile part number; black and per-inch variants (1515-Black-FB) resolve to the base part."""
    P = data()["profiles"]
    pn = str(pn or "").strip()
    if pn in P:
        return {**P[pn], "part_no": pn}
    base = re.sub(r"-(Black|Yellow)(-FB)?$|-FB$", "", pn, flags=re.I)
    return {**P[base], "part_no": base} if base in P else None


def metric(pn: str) -> bool:
    s = series_of(pn)
    return bool(s) and s not in ("10", "15")


# ------------------------------------------------------------------ machining service numbers
_OP_KEY = {"counterbore": "anchor_counterbore", "butt_counterbore": "butt_counterbore", "access_hole": "access_hole",
           "drill_thru_cbore": "drill_thru_counterbore", "central_connector_cbore": "central_connector_counterbore"}
OP_PAGES = {"end_tap": "10-3", "counterbore": "10-7", "butt_counterbore": "10-7", "access_hole": "10-5", "drill_thru_cbore": "10-8",
            "miter_cut": "10-10", "miter_cbore": "10-12", "central_connector_cbore": "10-20", "cut": "10-2"}


def end_tap(pn: str, thread: str | None = None) -> dict | None:
    """The end tap service for a profile: the given thread, else the standard fastener thread of its series."""
    p = profile(pn)
    if not p or not p.get("end_taps"):
        return None
    want = thread or {"10": "1/4-20", "15": "5/16-18"}.get(p["series"], "M8 x 1.25")
    norm = lambda s: re.sub(r"\s+", "", str(s or "")).lower()
    return next((t for t in p["end_taps"] if norm(t["tap"]) == norm(want)), None)


def op_number(op: str, pn: str, thread: str | None = None) -> str | None:
    """80/20 service number for one of our generic operations on a profile."""
    p = profile(pn)
    if not p:
        return None
    if op == "cut":
        return p.get("cut_op")
    if op == "end_tap":
        t = end_tap(pn, thread)
        return t["op"] if t else None
    if op == "miter_cut":
        return p.get("miter_op")
    if op == "miter_cbore":
        return p.get("miter_cbore_op")
    key = _OP_KEY.get(op)
    ser = p["series"] if p["series"] in ("10", "15", "40") else None
    if not key or not ser:
        return None
    o = data()["ops"].get(f"{ser}:{key}")
    return o["op"] if o else None


# ------------------------------------------------------------------ hardware: our catalog ids to 80/20 parts
# (part number, description, quantity per unit of our line, page). Extra rows are the bolts and T-nuts a part needs.
# Families "MS" and "ML" (metric) are left to the generic catalog: part numbers there depend on the exact series.
HARDWARE: dict[tuple[str, str], list[tuple[str, str, float, str]]] = {
    ("ANCHOR", "15"): [("3360", "15 Series standard anchor fastener assembly (5/16-18 x 1.30 SHCS, cam, T-nut)", 1, "3-12")],
    ("ANCHOR", "10"): [("3395", "10 Series standard anchor fastener assembly (10-32 x .75 SHCS, cam, T-nut)", 1, "3-12")],
    ("ANCHOR", "ML"): [("40-3897", "40 Series standard anchor fastener assembly (M8 x 30 SHCS)", 1, "3-12")],
    ("BUTT", "15"): [("3370", "15 Series butt fastener assembly (5/16 x 1.75 SHCS)", 1, "3-15")],
    ("BUTT", "10"): [("3369", "10 Series butt fastener assembly (10-32 x 1.03 SHCS)", 1, "3-15")],
    ("ENDFAST", "15"): [("3380", "15 Series standard end fastener assembly, 5/16-18", 1, "3-16")],
    ("ENDFAST", "10"): [("3381", "10 Series standard end fastener assembly, 1/4-20", 1, "3-16")],
    ("BRKT-2H", "15"): [("4302", "15 Series 2 hole inside corner bracket", 1, "3-76"),
                        ("3320", "5/16-18 x 11/16 FBHSCS and economy T-nut", 2, "3-116")],
    ("BRKT-2H", "10"): [("4119", "10 Series 2 hole inside corner bracket", 1, "3-76"),
                        ("3393", "1/4-20 x 1/2 BHSCS and economy T-nut", 2, "3-116")],
    ("BRKT-4H", "15"): [("4303", "15 Series 4 hole wide inside corner bracket", 1, "3-87"),
                        ("3320", "5/16-18 x 11/16 FBHSCS and economy T-nut", 4, "3-88")],
    ("BRKT-4H", "10"): [("4113", "10 Series 4 hole wide inside corner bracket", 1, "3-87"),
                        ("3393", "1/4-20 x 1/2 BHSCS and economy T-nut", 4, "3-88")],
    ("BRKT-GUSSET", "15"): [("4332", "15 Series 2 hole gusseted inside corner bracket", 1, "3-116"),
                            ("3320", "5/16-18 x 11/16 FBHSCS and economy T-nut", 2, "3-116")],
    ("BRKT-GUSSET", "10"): [("4132", "10 Series 2 hole gusseted inside corner bracket", 1, "3-116"),
                            ("3393", "1/4-20 x 1/2 BHSCS and economy T-nut", 2, "3-116")],
    ("TNUT-ECON", "15"): [("3320", "5/16-18 x 11/16 FBHSCS and economy T-nut (screw included)", 1, "2-11")],
    ("TNUT-ECON", "10"): [("3393", "1/4-20 x 1/2 BHSCS and economy T-nut (screw included)", 1, "3-116")],
    ("TNUT-SLIDE", "15"): [("3203", "15 Series standard slide-in T-nut, 5/16-18", 1, "3-158")],
    ("TNUT-SLIDE", "10"): [("3204", "10 Series standard slide-in T-nut, 1/4-20", 1, "3-158")],
    ("TNUT-DROP", "15"): [("3933", "15 Series standard drop-in T-nut, 1/4-20", 1, "3-172")],
    ("SCREW-BHSCS", "15"): [("3114", "5/16-18 x 3/4 BHSCS", 1, "4-103")],
    ("SCREW-BHSCS", "10"): [("3061", "1/4-20 x 1/2 BHSCS", 1, "3-177")],
    # standard lift-off hinge assembly: two hinges (one long pin, one short pin) with mounting hardware (4-70, 4-76)
    ("HINGE", "15"): [("2104", "15 Series standard lift-off hinge assembly, right hand (2104) or left hand (2105): 2 hinges, hardware included", 0.5, "4-76")],
    ("HINGE", "10"): [("2064", "10 Series standard lift-off hinge assembly, right hand (2064) or left hand (2065): 2 hinges, hardware included", 0.5, "4-76")],
    ("HANDLE", "15"): [("2061", "Plastic door handle, 5/16 mount, black", 1, "4-108"),
                       ("3454", "5/16-18 x 5/8 SHCS and economy T-nut (handle mount)", 2, "4-108")],
    ("HANDLE", "10"): [("2062", "Plastic door handle, 1/4 mount, black", 1, "4-108"),
                       ("3491", "1/4-20 x 1/2 SHCS and economy T-nut (handle mount)", 2, "4-108")],
    # threaded stem swivel caster, 5 in soft rubber wheel, side brake, 7/16-14 stem, 125 lb each: threads into an
    # end-tapped profile (5-4). 80/20's 3 in and larger stem casters all have a side brake.
    ("CASTER", "15"): [("2306", "Threaded stem swivel caster, 5 in soft rubber, side brake, 7/16-14 stem, 125 lb", 1, "5-4")],
    ("CASTER-LOCK", "15"): [("2306", "Threaded stem swivel caster, 5 in soft rubber, side brake, 7/16-14 stem, 125 lb", 1, "5-4")],
    # 10 Series ends only tap to 1/4-20 (10-3), so a 3/8-16 stem caster goes on a center tap base plate (5-40)
    ("CASTER", "10"): [("2300", "Threaded stem swivel caster, 3 in soft rubber, side brake, 3/8-16 stem, 100 lb", 1, "5-4"),
                       ("2129", "3 hole center tap base plate, 1 in, 3/8-16 center (mounts with 1/4 SHCS)", 1, "5-40")],
    ("CASTER-LOCK", "10"): [("2300", "Threaded stem swivel caster, 3 in soft rubber, side brake, 3/8-16 stem, 100 lb", 1, "5-4"),
                            ("2129", "3 hole center tap base plate, 1 in, 3/8-16 center (mounts with 1/4 SHCS)", 1, "5-40")],
    ("FOOT", "15"): [("2191", "Economy leveling foot, 3/8-16, 2550 lb", 1, "5-24")],
    # flange mount caster base plate: mounts to the profile end (end tap 5/16-18) and takes a flanged caster with 4 bolts
    ("CASTER-PLATE", "15"): [("2420", "Flange mount caster base plate, 15 Series", 1, "5-36"),
                             ("3110", "5/16-18 x 5/8 SHCS (caster to base plate)", 4, "5-6")],
    ("CASTER-PLATE", "10"): [("2418", "Flange mount caster base plate, 10 Series", 1, "5-36"),
                             ("3110", "5/16-18 x 5/8 SHCS (caster to base plate)", 4, "5-6")],
    ("FOOT", "10"): [("2193", "Economy leveling foot, 1/4-20, 1050 lb", 1, "5-24")],
}
# thread each base part needs in the end of a profile (for the end tap service)
END_THREAD = {("CASTER", "15"): "7/16-14", ("CASTER-LOCK", "15"): "7/16-14", ("FOOT", "15"): "3/8-16", ("FOOT", "10"): "1/4-20",
              ("ENDFAST", "15"): "5/16-18", ("ENDFAST", "10"): "1/4-20"}
END_CAPS = {"1010": "2015", "1020": "2025", "1030": "2026", "2020": "2028", "1515": "2030", "1530": "2045", "1545": "2046", "3030": "2050"}  # 8-11
# machining each fastener needs: (our op, on which member, page)
NEEDS = {"ANCHOR": ("counterbore", "the member whose end butts into the other", "3-12, 10-7"),
         "BUTT": ("butt_counterbore", "each mounting profile", "3-15, 10-7"),
         "ENDFAST": ("end_tap", "the mounting profile end, plus an access hole in the mating profile", "3-16, 10-3, 10-5")}


def _base_family(catalog_id: str) -> tuple[str, str]:
    m = re.match(r"^(.*)-(10|15|MS|ML)$", catalog_id or "")
    return (m.group(1), m.group(2)) if m else (catalog_id or "", "")


def hardware_parts(catalog_id: str, qty: int) -> list[dict]:
    """80/20 parts for one of our hardware lines (empty when there is no 80/20 equivalent here)."""
    base, fam = _base_family(catalog_id)
    if base == "ENDCAP":
        return []  # end caps are per profile (see order_list)
    rows = []
    for pn, desc, per, page in HARDWARE.get((base, fam), []):
        rows.append({"part_number": pn, "description": desc, "qty": int(math.ceil(qty * per - 1e-9)), "page": page})
    return rows


# ------------------------------------------------------------------ deflection (2-10)
def deflection(pn: str, length_in: float, load_lb: float, case: str = "A", strong_axis: bool = True) -> float | None:
    """A: simply supported, center load; B: simply supported, uniform load (total W); C: cantilever, end load."""
    p = profile(pn)
    i = p and (p.get("i_strong") if strong_axis else p.get("i_weak"))
    if not i or not length_in:
        return None
    k = {"A": 48, "B": 384 / 5, "C": 3}[case]
    return length_in ** 3 * load_lb / (k * E_PSI * i)


# ------------------------------------------------------------------ order list and checks
def _thread_of(ln: dict) -> str | None:
    for o in ln.get("machining") or []:
        if o.get("op") == "end_tap" and o.get("thread"):
            return o["thread"]
    return None


def order_list(lines: list[dict], builds: int = 1) -> dict:
    """What to order from 80/20 for `builds` builds: rows {part_number, description, qty, unit, callout, page}.
    Profiles are ordered cut to length with their machining services listed in the callout."""
    rows, unknown = [], []
    caps = Counter()
    for ln in lines:
        q = int(ln.get("qty") or 0) * builds
        if q <= 0:
            continue
        kind = ln.get("kind")
        if kind == "profile":
            p = profile(ln.get("catalog_id"))
            if not p:
                unknown.append(ln.get("catalog_id"))
                continue
            L = float(ln.get("length_in") or 0)
            calls = [f"#{p.get('cut_op') or '?'} cut to {L:.3f} in"]
            for o in ln.get("machining") or []:
                num = op_number(o["op"], p["part_no"], o.get("thread"))
                what = o["op"].replace("_", " ")
                if o["op"] == "end_tap":
                    t = end_tap(p["part_no"], o.get("thread"))
                    what = f"end tap {t['tap']}" if t else f"end tap {o.get('thread') or ''}".strip()
                calls.append(f"#{num or '?'} {what} x{o['count']}")
            rows.append({"part_number": p["part_no"], "description": f"{p['desc']}, {L:.3f} in", "qty": q, "unit": "piece",
                         "callout": "; ".join(calls), "page": p.get("page"), "kind": "profile"})
            caps[p["part_no"]] += 0  # end caps are added only when the build lists them
        elif kind == "hardware":
            base, fam = _base_family(ln.get("catalog_id"))
            pn = str(ln.get("part_number") or "").strip()
            if pn and pn in PART_DESC:  # the model or BOM named the exact 80/20 part
                extra = HARDWARE.get((base, fam), [])[1:] if base not in ("CASTER", "CASTER-LOCK") else []
                rows.append({"part_number": pn, "description": PART_DESC[pn], "qty": q, "unit": "each", "callout": "", "kind": "hardware"})
                rows += [{"part_number": e[0], "description": e[1], "qty": int(math.ceil(q * e[2] - 1e-9)), "unit": "each", "callout": "",
                          "page": e[3], "kind": "hardware"} for e in extra]
                continue
            parts = hardware_parts(ln.get("catalog_id"), q)
            if base == "ENDCAP":
                caps["__qty__"] += q
                continue
            if not parts:
                unknown.append(ln.get("catalog_id"))
            rows += [{**r, "unit": "each", "callout": "", "kind": "hardware"} for r in parts]
        elif kind == "panel":
            pn = panel_part(ln.get("catalog_id"))
            w, h = ln.get("width_in"), ln.get("height_in")
            rows.append({"part_number": pn or ln.get("catalog_id"), "description": f"{panel_label(ln.get('catalog_id'))}, cut to {w:.3f} x {h:.3f} in",
                         "qty": q, "unit": "panel", "callout": "cut to size (10-26), +/- .060 in; a drawing is required", "page": "4-12", "kind": "panel"})
    if caps.get("__qty__"):
        # put end caps on the profiles that are posts first: the longest pieces
        need = caps["__qty__"]
        for ln in sorted((l for l in lines if l.get("kind") == "profile"), key=lambda l: -(l.get("length_in") or 0)):
            pn = (profile(ln.get("catalog_id")) or {}).get("part_no")
            cap = END_CAPS.get(pn)
            if cap and need > 0:
                rows.append({"part_number": cap, "description": f"End cap for {pn} with push-in fastener", "qty": need, "unit": "each",
                             "callout": "", "page": "8-11", "kind": "hardware"})
                need = 0
    # merge identical hardware rows
    merged: dict = {}
    out = []
    for r in rows:
        if r["kind"] == "hardware":
            k = r["part_number"]
            if k in merged:
                merged[k]["qty"] += r["qty"]
                continue
            merged[k] = r
        out.append(r)
    return {"rows": out, "unknown": sorted({u for u in unknown if u}), "notes": assembly_notes(lines)}


def assembly_notes(lines: list[dict]) -> list[str]:
    fams = {_base_family(l.get("catalog_id"))[1] for l in lines if l.get("kind") == "hardware"}
    notes = []
    T = {r["part_no"]: r for r in data()["torque"]}
    bases = {_base_family(l.get("catalog_id"))[0] for l in lines if l.get("kind") == "hardware"}
    nuts = bases & {"TNUT-ECON", "BRKT-2H", "BRKT-4H", "BRKT-GUSSET"}
    for fam, anchor, nut in (("15", "3360", "3320"), ("10", "3395", "3321")):
        if fam not in fams:
            continue
        parts = []
        if "ANCHOR" in bases:
            parts.append(f"{anchor} anchors {T[anchor]['min_torque_ft_lb']:g} to {T[anchor]['max_torque_ft_lb']:g} ft-lb")
        if nuts:
            parts.append(f"{nut}-type screw and economy T-nut {T[nut]['min_torque_ft_lb']:g} to {T[nut]['max_torque_ft_lb']:g} ft-lb (sets the drop-lock)")
        if parts:
            notes.append("Torque: " + "; ".join(parts) + " (2-11).")
    notes.append(f"Cut tolerance from 80/20: {CUT_TOLERANCE['fractional']} (10-2).")
    if any(o.get("op") in ("miter_cut", "miter_cbore") for l in lines for o in l.get("machining") or []):
        notes.append("Miter cuts need a drawing with the order; 1515 family cuts 0 to 75 degrees, 1530, 1545 and 3030 families 0 to 60 (10-10).")
    return notes


# panels: our catalog ids to 80/20 panel part numbers (4-10 .. 4-22)
PANELS_8020 = {
    "PANEL-PC-118": ("2643", "Polycarbonate, clear, .118 in (3 mm)"),
    "PANEL-PC-125": ("2643", "Polycarbonate, clear, .118 in (3 mm)"),
    "PANEL-PC-177": ("2610", "Polycarbonate, clear, .177 in (4.5 mm)"),
    "PANEL-PC-187": ("2610", "Polycarbonate, clear, .177 in (4.5 mm)"),
    "PANEL-PC-236": ("2609", "Polycarbonate, clear, .220 - .236 in (6 mm)"),
    "PANEL-PC-250": ("2609", "Polycarbonate, clear, .220 - .236 in (6 mm)"),
    "PANEL-ACR-177": ("2602", "Acrylic, clear, .177 in (4.5 mm)"),
    "PANEL-ACR-125": ("2602", "Acrylic, clear, .177 in (4.5 mm)"),
    "PANEL-ACR-187": ("2602", "Acrylic, clear, .177 in (4.5 mm)"),
    "PANEL-ACR-236": ("2601", "Acrylic, clear, .220 - .236 in (6 mm)"),
    "PANEL-ACR-250": ("2601", "Acrylic, clear, .220 - .236 in (6 mm)"),
    "PANEL-ACM-236": ("2650", "Aluminum composite, platinum, .236 in (6 mm)"),
    "PANEL-ACM-118": ("2650", "Aluminum composite, platinum, .236 in (6 mm)"),
    "PANEL-ACM-157": ("2650", "Aluminum composite, platinum, .236 in (6 mm)"),
    "PANEL-AL-125": ("2453", "Aluminum plate 6061-T6, .125 in"),
    "PANEL-AL-187": ("2454", "Aluminum plate 6061-T6, .187 in"),
    "PANEL-AL-250": ("2455", "Aluminum plate 6061-T6, .250 in"),
}


def panel_part(catalog_id: str) -> str | None:
    return (PANELS_8020.get(catalog_id) or (None,))[0]


def panel_label(catalog_id: str) -> str:
    return (PANELS_8020.get(catalog_id) or (None, catalog_id))[1]


def check(lines: list[dict], panel_thickness: dict | None = None) -> list[dict]:
    """Design checks against the 80/20 catalog rules. Each finding: {level: error|warn|info, text, page}.
    panel_thickness: {catalog id: thickness in inches} for panel lines."""
    out: list[dict] = []
    add = lambda level, text, page: out.append({"level": level, "text": text, "page": page})
    profs = [l for l in lines if l.get("kind") == "profile" and int(l.get("qty") or 0) > 0]
    hw = Counter()
    fams = set()
    for l in lines:
        if l.get("kind") == "hardware":
            base, fam = _base_family(l.get("catalog_id"))
            hw[base] += int(l.get("qty") or 0)
            if fam:
                fams.add(fam)
    pfams = set()
    for l in profs:
        p = profile(l.get("catalog_id"))
        if not p:
            continue
        pfams.add({"10": "10", "15": "15", "40": "ML", "45": "ML"}.get(p["series"], "MS"))
        L = float(l.get("length_in") or 0)
        lim = STOCK_MAX_IN["metric" if metric(p["part_no"]) else "fractional"]
        if L > lim:
            add("error", f"{p['part_no']} at {L:g} in is longer than an 80/20 stick ({lim:g} in). Split it with a butt joint or ask 80/20 for a special length.", "2-34")
        elif L > UPS_MAX_IN:
            add("info", f"{p['part_no']} at {L:g} in is over {UPS_MAX_IN:g} in, so the order ships by freight, not UPS.", "1-28")
    if fams and pfams and not fams <= pfams:
        add("error", "Some hardware is for a different series than the profiles; T-nuts and fasteners only fit their own series.", "3-4")

    def ops(op):
        return sum(int(o.get("count") or 0) * int(l.get("qty") or 0) for l in profs for o in l.get("machining") or [] if o.get("op") == op)

    cb, taps, access = ops("counterbore"), ops("end_tap"), ops("access_hole")
    if hw["ANCHOR"] and cb != hw["ANCHOR"]:
        add("warn", f"{hw['ANCHOR']} anchor fasteners but {cb} anchor counterbores. Each anchor needs one counterbore (service 7040 on 15 Series, "
                    "7042 on 10 Series) in the end of the member that butts in.", "3-12, 10-7")
    if cb and not hw["ANCHOR"] and not hw["BUTT"]:
        add("warn", f"{cb} counterbores but no anchor fasteners listed. Add the anchors (3360 on 15 Series) or remove the counterbores.", "3-12")
    flange = sum(int(l.get("qty") or 0) for l in lines if l.get("kind") == "hardware" and str(l.get("part_number") or "") in FLANGE_CASTERS)
    face_plates = sum(int(l.get("qty") or 0) for l in lines if str(l.get("part_number") or "") == "3458") // 4
    stems = hw["CASTER"] + hw["CASTER-LOCK"] - flange + hw["FOOT"] + hw["CASTER-PLATE"] - face_plates  # each takes one tapped end
    need_taps = stems + hw["ENDFAST"]
    if stems and "10" in fams and (hw["CASTER"] + hw["CASTER-LOCK"]):
        add("info", "10 Series ends only tap to 1/4-20, so stem casters go on a center tap base plate (2129 for a 3/8-16 stem).", "10-3, 5-40")
    elif need_taps and taps < need_taps:
        add("warn", f"{stems} casters or feet and {hw['ENDFAST']} end fasteners need {need_taps} tapped profile ends, but {taps} end taps are listed. "
                    "Stem casters and leveling feet thread into an end tap (7054 for a 7/16-14 stem on 1515, 7033 on 1530) or a base plate.",
            "5-4, 5-24, 10-3")
    if flange and hw["CASTER-PLATE"] < flange:
        add("warn", f"{flange} flange mount casters need a caster base plate each (2420 on 15 Series) to mount to the frame; "
                    f"{hw['CASTER-PLATE']} listed.", "5-6, 5-36")
    if hw["ENDFAST"] and access < hw["ENDFAST"]:
        add("warn", f"{hw['ENDFAST']} end fasteners need an access hole (7050 on 15 Series) in the mating profile for each one; {access} listed.", "3-16, 10-5")
    if hw["HINGE"] and hw["HINGE"] % 2:
        add("info", "80/20 lift-off hinges come as assemblies of two; an odd hinge count leaves one spare.", "4-76")
    # panels: thickness against the slot of the series
    ser = next(iter(pfams), None)
    sseries = {"ML": "40"}.get(ser, ser)
    slot = (data()["slots"].get(sseries or "", {}) or {})
    opening = slot.get("slot_opening_in") or ((slot.get("slot_opening_mm") or 0) / 25.4 or None)
    for l in lines:
        if l.get("kind") != "panel":
            continue
        t = (panel_thickness or {}).get(l.get("catalog_id"))
        if not t or not opening:
            continue
        lo, hi = PANEL_GASKET_THICKNESS_IN.get(sseries, (None, None))
        if t > opening + 1e-3:
            add("error", f"{panel_label(l.get('catalog_id'))} ({t:g} in) is thicker than the {sseries} Series slot opening ({opening:g} in). "
                         "Use a thinner panel or mount it on the face with panel mount blocks.", "4-6, 2-32")
        elif lo and t < lo - 0.03:
            add("info", f"{panel_label(l.get('catalog_id'))} ({t:g} in) is thin for the {sseries} Series slot; it will rattle without panel gasket "
                        f"(80/20 recommends {lo:g} to {hi:g} in with gasket).", "4-6")
    if any(o.get("op") in ("miter_cut", "miter_cbore") for l in profs for o in l.get("machining") or []):
        add("info", "Mitered pieces need a drawing with the 80/20 order.", "10-10")
    return out


def beam_note(pn: str, span_in: float, load_lb: float = 100.0) -> dict | None:
    """A finding with the sag of a horizontal member under a center load (catalog formula A, 2-10)."""
    d = deflection(pn, span_in, load_lb, "A")
    if d is None:
        return None
    return {"level": "warn" if d > span_in / 360 else "info",
            "text": f"Longest rail, {pn} over {span_in:.2f} in: about {d:.3f} in of sag with {load_lb:g} lb at the center "
                    f"(80/20 formula A{', more than span/360, so add a support or a stiffer profile' if d > span_in / 360 else ''}).", "page": "2-10"}


# 80/20 part numbers a customer's BOM may list, to our hardware catalog base and series (catalog pages in HARDWARE)
PART_TO_BASE: dict[str, tuple[str, str]] = {}
for (_b, _f), _rows in HARDWARE.items():
    if _rows:
        PART_TO_BASE.setdefault(_rows[0][0], (_b, _f))
PART_TO_BASE.update({
    "3359": ("ANCHOR", "15"), "3362": ("ANCHOR", "15"), "3373": ("ANCHOR", "15"), "3897": ("ANCHOR", "15"), "3392": ("ANCHOR", "10"), "3363": ("ANCHOR", "10"),
    "3370-Black": ("BUTT", "15"), "3369-Black": ("BUTT", "10"), "3680": ("ENDFAST", "15"), "3389": ("ENDFAST", "15"), "3682": ("ENDFAST", "10"), "3383": ("ENDFAST", "10"),
    "4301": ("BRKT-4H", "15"), "4115": ("BRKT-4H", "10"), "4336": ("BRKT-GUSSET", "15"), "4136": ("BRKT-GUSSET", "10"),
    "3321": ("TNUT-ECON", "10"), "3203": ("TNUT-SLIDE", "15"), "3703": ("TNUT-SLIDE", "15"),
    "2105": ("HINGE", "15"), "2065": ("HINGE", "10"), "2842": ("HINGE", "15"), "2836": ("HINGE", "15"), "2841": ("HINGE", "10"), "2835": ("HINGE", "10"),
    "2060": ("HANDLE", "15"), "2884": ("HANDLE", "15"), "2886": ("HANDLE", "15"),
    "2300": ("CASTER", "15"), "2310": ("CASTER", "15"), "2305": ("CASTER", "15"), "2307": ("CASTER", "15"), "2317": ("CASTER", "15"), "2318": ("CASTER", "15"),
    "2295": ("CASTER", "15"), "2296": ("CASTER-LOCK", "15"),
    "2321": ("CASTER-LOCK", "15"), "2323": ("CASTER-LOCK", "15"), "2333": ("CASTER-LOCK", "15"),
    "2420": ("CASTER-PLATE", "15"), "2426": ("CASTER-PLATE", "15"), "2418": ("CASTER-PLATE", "10"), "2419": ("CASTER-PLATE", "10"),
    "4303": ("BRKT-4H", "15"), "4113": ("BRKT-4H", "10"), "2190": ("FOOT", "15"), "2194": ("FOOT", "15"), "2195": ("FOOT", "15"), "2192": ("FOOT", "10"),
    **{cap: ("ENDCAP", "15" if cap in ("2030", "2045", "2046", "2050") else "10") for cap in END_CAPS.values()},
})


@lru_cache(maxsize=1)
def op_numbers() -> dict[str, tuple[str, str | None]]:
    """80/20 machining service number -> (our op, end tap thread or None)."""
    out: dict[str, tuple[str, str | None]] = {}
    for p in data()["profiles"].values():
        for t in p.get("end_taps") or []:
            out[t["op"]] = ("end_tap", t["tap"])
        if p.get("miter_op"):
            out[p["miter_op"]] = ("miter_cut", None)
        if p.get("miter_cbore_op"):
            out[p["miter_cbore_op"]] = ("miter_cbore", None)
    rev = {"anchor_counterbore": "counterbore", "butt_counterbore": "butt_counterbore", "access_hole": "access_hole",
           "access_hole_predetermined": "access_hole", "drill_thru_counterbore": "drill_thru_cbore",
           "central_connector_counterbore": "central_connector_cbore"}
    for k, o in data()["ops"].items():
        op = rev.get(k.split(":", 1)[1])
        if op:
            out[o["op"]] = (op, None)
    return out


def parse_ops(text: str) -> list[dict]:
    """80/20 machining service numbers in a BOM or drawing callout: "(2) #7040", "7060 BOTH ENDS", "7050 X2"."""
    nums = op_numbers()
    out: dict = {}
    for m in re.finditer(r"(?:\(\s*(\d{1,2})\s*\)\s*|\b(\d{1,2})\s*[xX]\s*)?#?\b((?:\d{2}-)?7\d{3})\b(?:\s*[xX]\s*(\d{1,2})\b)?", text or ""):
        num = m.group(3)
        if num not in nums:
            continue
        n = int(m.group(1) or m.group(2) or m.group(4) or 0) or (2 if re.search(r"BOTH\s*ENDS", text[m.end():m.end() + 20], re.I) else 1)
        op, thread = nums[num]
        key = (op, thread)
        out[key] = out.get(key, 0) + n
    return [{"op": op, "count": n, **({"thread": th} if th else {})} for (op, th), n in out.items()]


def match_part(text: str) -> tuple[str, str, str] | None:
    """An 80/20 hardware part number in text -> (catalog id, part number, note)."""
    for m in re.finditer(r"(?<![\w.-])(\d{4})(-Black)?(?![\w.]|-\d)", text or "", re.I):
        pn = m.group(1) + (m.group(2) or "")
        hit = PART_TO_BASE.get(pn) or PART_TO_BASE.get(m.group(1))
        if hit:
            base, fam = hit
            note = "80/20 hinge assemblies hold two hinges; set the quantity to hinges." if base == "HINGE" else ""
            return f"{base}-{fam}", m.group(1), note
    return None


# descriptions for parts a model or BOM names exactly (beyond the defaults in HARDWARE)
PART_DESC = {
    "2321": "Flanged mount swivel caster, 4 in soft rubber, front brake, 255 lb (5-7)",
    "2323": "Flanged mount swivel caster, 5 in soft rubber, front brake, 280 lb (5-7)",
    "2333": "Deluxe flange mount swivel caster, 4 in polyurethane, brake included, 250 lb (5-10)",
    "2317": "Flanged mount swivel caster, soft rubber, 150 lb (5-6)",
    "2318": "Flanged mount swivel caster, hard rubber, 200 lb (5-6)",
    "2426": "Flange mount caster base plate, 15 Series (5-36)",
    "4303": "15 Series 4 hole wide inside corner bracket (3-87)",
    "4301": "15 Series 4 hole tall inside corner bracket (3-88)",
    "4332": "15 Series 2 hole gusseted inside corner bracket (3-116)",
    "2045": "End cap for 1530 with push-in fastener (8-11)", "2046": "End cap for 1545 with push-in fastener (8-11)",
    "2050": "End cap for 3030 with push-in fastener (8-11)", "2030": "End cap for 1515 with push-in fastener (8-11)",
    "2015": "End cap for 1010 with push-in fastener (8-11)", "2025": "End cap for 1020 with push-in fastener (8-11)",
}
for (_b, _f), _rows in HARDWARE.items():
    for _pn, _d, _q, _pg in _rows[:1]:
        PART_DESC.setdefault(_pn, f"{_d} ({_pg})")
PART_DESC.update({"3458": "5/16-18 x 7/8 SHCS and economy T-nut (caster base plate to the T-slot) (5-36)",
                  "3123": "5/16-18 x 1.25 SHCS (caster base plate to a tapped profile end) (5-36)"})
FLANGE_CASTERS = {"2317", "2318", "2321", "2323", "2333"}
