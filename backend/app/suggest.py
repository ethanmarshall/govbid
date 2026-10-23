"""A suggested way to make a part when the customer didn't say what it is made of.

Without a material we assume aluminum and machine it. For a part that is costly to machine (5-axis work, many
setups) and could just as well be printed (a handwheel, a knob, a cover, a fixture), that assumption can make a
quote many times too high. So we also price it 3D printed in a tough plastic, with the hardware a printed part
gets: heat-set inserts in holes sized for them, and drill bushings pressed into a set of index holes so they wear
like metal. When the print is far cheaper, it becomes the suggested method, shown as an assumption the customer
or you can change under Made by.
"""
from __future__ import annotations

from collections import defaultdict

SUGGEST_MATERIAL = "PETG"  # tough, cheap, prints accurately; the customer can pick another
MAX_SHARE = 0.5  # suggest printing when it costs at most half of machining
BUSHING_UNIT_COST = 5.00  # press-fit drill bushing, McMaster-class
BUSHING_MINUTES = 1.5


def print_extras(geo: dict, config: dict | None = None) -> dict:
    """Hardware for a printed part from its holes: {"inserts": n, "bushings": n, "notes": [...]}.
    Index holes: four or more holes of one size on different axes (a radial pattern, like a handwheel's), or at
    least eight on one axis. Insert holes: sized for a heat-set insert's mounting hole or a tap drill."""
    from . import inserts as ins

    holes = [h for h in geo.get("holes") or [] if h.get("diameter")]
    by_d: dict[float, list] = defaultdict(list)
    for h in holes:
        by_d[round(float(h["diameter"]), 2)].append(h)
    bush, rest = [], []
    for d, hs in by_d.items():
        axes = {tuple(round(abs(a), 2) for a in h.get("axis") or []) for h in hs}
        if d >= 0.2 and ((len(hs) >= 4 and len(axes) >= 3) or len(hs) >= 8):
            bush += hs
        else:
            rest += hs
    table = ins.table(config)
    n_ins = 0
    for h in rest:
        if float(h["diameter"]) > 0.42:  # a bore or clearance hole, not an insert (5/16 and M8 inserts need about 0.41)
            continue
        mm = float(h["diameter"]) * 25.4
        for t in table.values():
            if t["bottom_d"] - 0.2 <= mm <= t["entry_d"] + 0.2 or abs(mm - float(t.get("tap_drill") or 0)) <= 0.15:
                n_ins += 1
                break
    notes = []
    if n_ins:
        notes.append(f"{n_ins} heat-set insert{'s' if n_ins > 1 else ''} in the hole{'s' if n_ins > 1 else ''} sized for one")
    if bush:
        notes.append(f"{len(bush)} drill bushings pressed into the {len(bush)} index holes")
    return {"inserts": n_ins, "bushings": len(bush), "notes": notes}


def print_opts(geo: dict, opts: dict, config: dict | None = None) -> tuple[dict, dict]:
    ex = print_extras(geo, config)
    o = {**opts, "process": "3d_print", "material": opts.get("material") or SUGGEST_MATERIAL}
    if ex["inserts"] and not o.get("threaded_holes"):
        o["threaded_holes"] = ex["inserts"]
    if ex["bushings"]:
        o["bushings"] = ex["bushings"]
    return o, ex


def suggestion(file_id: str, geo: dict, opts: dict, machined: dict | None, config: dict | None = None) -> dict | None:
    """A printed option for a part costly to machine, or None. machined: the option we would otherwise use."""
    from . import cad, cad_quote, pricing

    if not machined or machined.get("process") == "3d_print":
        return None
    cx = cad_quote.complexity_of(geo)
    hard = bool(machined.get("five_axis") or cx.get("five_axis")) or int(geo.get("estimated_setups") or 0) >= 4
    if not hard:
        return None
    o, ex = print_opts(geo, {**opts, "material": SUGGEST_MATERIAL}, config)
    try:
        r = cad_quote.quote(file_id, o, config)
    except (pricing.SpecError, cad.CadError, KeyError, ValueError):
        return None  # too big for the printer, say
    price = r["estimate"]["price_breaks"][0]["unit_price"]
    if not price or price > MAX_SHARE * float(machined["unit_price"]):
        return None
    what = f"3D printed in {SUGGEST_MATERIAL}" + (f", with {' and '.join(ex['notes'])}" if ex["notes"] else "")
    why = ("machining it needs a 5-axis machine" if hard and (machined.get("five_axis") or cx.get("five_axis"))
           else f"machining it takes {geo.get('estimated_setups')} setups")
    return {"process": "3d_print", "material": SUGGEST_MATERIAL, "label": "3D printed, suggested", "unit_price": price, "note": "",
            "five_axis": False, "breaks": r["estimate"]["price_breaks"], "suggested": True, "opts": o, "extras": ex,
            "summary": what, "why": why, "machined_price": float(machined["unit_price"])}
