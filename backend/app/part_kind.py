"""Bought or made: what each body in a customer's model is.

A model shows bought parts next to the ones we make (latches, hinges, casters, screws, sensors), and a body we
don't recognize must not be priced as a machined part by default. Evidence, strongest first:

1. a choice on the quote line (yours in review, or the customer's)
2. the customer's BOM (make/buy column, vendor, catalog part number)
3. what you decided for a part of that name on earlier quotes (learned in review)
4. a catalog part number in the name (McMaster, 80/20) or a standard part name (ISO 4762, "Hardware")
5. words in the name: "hinge", "latch", "screw" are bought; "bracket", "housing", "spacer" are made
6. how it is modeled: several small bodies under one repeated sub-assembly name ("Door Latch <4>") are one bought
   unit, because a part we make is drawn as a part, not as a set of loose pieces
7. small fastener-shaped bodies

Anything still unknown is priced as made, and a made line whose price looks out of line for its size is flagged
so you can switch it to bought in one click.
"""
from __future__ import annotations

import re
from collections import Counter

INSTANCE = re.compile(r"\s*<\d+>\s*$")
PIECE = re.compile(r",\s*piece \d+$", re.I)

# bought whatever else the name says ("Mounting Plate Hardware", "Hinge plate")
ALWAYS_BUY = re.compile(
    r"\b(hardware|fasteners?|screws?|bolts?|nuts?|t-?nuts?|washers?|rivets?|latch(es)?|hinges?|casters?|deadbolts?|o-?rings?|"
    r"circlips?|retaining rings?|mcmaster|misumi|purchased|cots|reference|ref|standard content|shcs|bhcs|bhscs|fhcs|fbhscs|"
    r"(iso|din|ansi|asme|ms|nas|an) ?b?\d{2,5})\b", re.I)
# bought unless the name also says it is made ("bearing housing", "motor mount")
BUY = re.compile(
    r"\b(bearings?|bushings?|springs?|inserts?|standoffs?|knobs?|handles?|clamps?|toggle|motors?|servos?|steppers?|sensors?|"
    r"switch(es)?|connectors?|terminals?|relays?|breakers?|fuses?|fans?|displays?|transducers?|transmitters?|gauges?|valves?|"
    r"fittings?|couplings?|pulleys?|sprockets?|chains?|belts?|magnets?|feet|foot|leveler|bumpers?|grommets?|gaskets?|seals?|"
    r"dowels?|pins?|leds?|buttons?|batter(y|ies)|regulators?|cables?|hoses?|grips?|wheels?|rollers?|glides?|keys?|"
    r"608|6\d\dzz|2rs)\b", re.I)
MADE = re.compile(
    r"\b(spacer|housing|cover|retainer|boss|cap|holder|mount|seat|block|plate|bracket|tunnel|shaft|sleeve|frame|carrier|"
    r"weldment|chassis|enclosure|base|body|adapter|flange|bezel|panel|lid|tray|arm|rail|beam|gusset|custom|machined|"
    r"fabricated)s?\b", re.I)
# a body named after a CAD feature or a default name tells us nothing ("CirPattern2", "Fillet4", "Part 1")
NO_NAME = re.compile(r"^(fillet|chamfer|cirpattern|linpattern|pattern|cut-?extrude|boss-?extrude|extrude|revolve|cut-?revolve|"
                     r"sweep|cut-?sweep|loft|mirror|shell|body|solid|part|imported|component|surface)[\s_-]*\d*$", re.I)
# the customer's own sub-assembly ("Shaft Assembly <1>"): its name describes the assembly, not each body in it
OWN_ASSEMBLY = re.compile(r"\b(assembly|assy|asm|weldment|master)\b", re.I)
MCMASTER = re.compile(r"(?<![A-Z0-9])\d{4,5}[A-Z]\d{1,4}(?![A-Z0-9])", re.I)


def stem(name: str) -> str:
    """'Door Latch <4>' and 'Door Latch, piece 2' -> 'door latch'."""
    n = PIECE.sub("", str(name or ""))
    n = INSTANCE.sub("", n)
    return re.sub(r"[_\s]+", " ", n).strip().lower()[:80]


def group_stem(g: dict) -> str:
    names = [n for n in (g.get("body_names") or []) if n]
    if names:
        return stem(Counter(stem(n) for n in names).most_common(1)[0][0])
    return stem(g.get("name") or "")


def structure(groups: list[dict]) -> dict[str, dict]:
    """Per name stem: the groups under it, whether the bodies carry sub-assembly instance numbers, how many
    different shapes it has and the largest size, so a repeated multi-piece sub-assembly can be told apart."""
    out: dict[str, dict] = {}
    for g in groups:
        s = group_stem(g)
        e = out.setdefault(s, {"groups": [], "instanced": True, "shapes": 0, "max_dim": 0.0, "bodies": 0})
        e["groups"].append(g)
        names = g.get("body_names") or []
        e["instanced"] = e["instanced"] and bool(names) and all(INSTANCE.search(n or "") for n in names)
        e["shapes"] += 1
        e["bodies"] += int(g.get("qty", 1) or 1)
        bb = g.get("bounding_box") or {}
        e["max_dim"] = max(e["max_dim"], *(float(bb.get(k) or 0) for k in ("length", "width", "height")))
    return out


def _dims(g: dict) -> list[float]:
    bb = g.get("bounding_box") or {}
    return sorted(float(bb.get(k) or 0) for k in ("length", "width", "height"))


def detail(geo: dict | None, g: dict) -> str:
    """Why a small body looks like catalog CAD (modeled threads, knurling, a ball, a washer), or ""."""
    if not geo:
        return ""
    d = _dims(g)
    f = geo.get("faces") or {}
    faces = sum(f.values())
    vol = float(geo.get("volume") or g.get("volume") or 0)
    if not d[2]:
        return ""
    if d[2] <= 2.5 and faces >= 100:
        return "modeled in fine detail (threads or knurling), like a catalog part's CAD"
    if d[2] <= 4 and f.get("cone", 0) >= 20:
        return "has modeled threads, like a catalog screw or stud"
    if d[2] <= 1.0 and faces <= 2 and f.get("sphere", 0) >= 1:
        return "a ball, like a bearing or detent ball"
    if d[2] <= 2 and d[0] <= 0.12 and len(geo.get("holes") or []) == 1 and d[1] >= 0.8 * d[2]:
        return "a thin ring with one hole, like a washer"
    if d[2] <= 1.25 and vol < 0.3 and (geo.get("suggested_process") or g.get("suggested_process")) == "cnc_lathe":
        return "small and shaped like a fastener"
    return ""


def decide(g: dict, *, st: dict | None = None, rules: dict | None = None, choice: str | None = None,
           bom_buy: bool | None = None, geo: dict | None = None) -> tuple[bool, str, str]:
    """(bought, how we know, source). source: chosen | bom | learned | name | model | default.
    geo: the body's geometry (faces, holes), for the shape checks."""
    s = group_stem(g)
    names = " ".join([g.get("name") or ""] + list(g.get("raw_names") or [])).replace("_", " ")
    if choice in ("bought", "make"):
        return choice == "bought", "you chose", "chosen"
    if bom_buy is not None:
        return bom_buy, "your BOM", "bom"
    rules = rules or {}
    if s and s in (rules.get("bought") or {}):
        return True, "decided in an earlier review", "learned"
    if s and s in (rules.get("made") or {}):
        return False, "decided in an earlier review", "learned"
    from . import catalog_8020

    if MCMASTER.search(names) or catalog_8020.match_part(names):
        return True, "catalog part number in the name", "name"
    if ALWAYS_BUY.search(names):
        return True, "the name says it is bought hardware", "name"
    meaningful = bool(s) and not NO_NAME.match(s) and not OWN_ASSEMBLY.search(s)
    if meaningful and MADE.search(names):
        return False, "the name says it is made", "name"
    if meaningful and BUY.search(names):
        return True, "the name says it is a bought part", "name"
    e = (st or {}).get(s)
    if e and e["instanced"] and e["shapes"] >= 2 and e["max_dim"] <= 6 and not OWN_ASSEMBLY.search(s):
        return True, "drawn as a set of small pieces under one sub-assembly name, like a bought part", "model"
    why = detail(geo, g) if geo else ("small and shaped like a fastener" if _dims(g)[2] and _dims(g)[2] <= 1.25
                                      and (g.get("volume") or 0) < 0.3 and g.get("suggested_process") == "cnc_lathe" else "")
    if why:
        return True, why, "model"
    return False, "", "default"


def looks_bought(ln: dict, g: dict) -> bool:
    """A made line priced high for its size: probably a bought part nobody named."""
    d = _dims(g)
    price = ln.get("unit_cost") or ln.get("unit_price") or 0
    return bool(d[2]) and d[2] <= 3.5 and price >= 120


def learn(rules: dict | None, s: str, bought: bool) -> dict:
    """Your make or buy choice in review, remembered for the next quote with a part of that name."""
    rules = {"bought": dict((rules or {}).get("bought") or {}), "made": dict((rules or {}).get("made") or {})}
    if not s:
        return rules
    keep, drop = ("bought", "made") if bought else ("made", "bought")
    rules[drop].pop(s, None)
    rules[keep][s] = rules[keep].get(s, 0) + 1
    if len(rules[keep]) > 2000:  # oldest first out
        rules[keep] = dict(list(rules[keep].items())[-2000:])
    return rules
