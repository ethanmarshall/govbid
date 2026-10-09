"""What we read from a customer's files, in plain words, so they can spot a misread before they order.

Each function returns a list of {"label", "value", "flag"} rows. flag is "" normally, "assumed" when we filled
something in that the files did not say (they should check it), or "check" when we are unsure of what we read.
Nothing here includes costs, rates or margins.
"""
from __future__ import annotations

import functools
import logging
from collections import Counter

log = logging.getLogger(__name__)


def _safe(fn):
    """Reading out facts must never stop a quote: on any surprise, show nothing rather than fail."""
    @functools.wraps(fn)
    def wrap(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # noqa: BLE001
            log.warning("portal facts %s failed: %s", fn.__name__, exc)
            return []
    return wrap

DENSITY = None  # filled lazily from the shop materials


def _in(v) -> str:
    if v is None:
        return ""
    if v < 0.01:
        return f"{v:.4f}"
    return f"{v:.3f}" if v < 10 else f"{v:.2f}"


def _size(l, w, h=None) -> str:
    vals = [x for x in (l, w, h) if x is not None]
    return " x ".join(_in(x) for x in vals) + " in"


def row(label: str, value, flag: str = "") -> dict:
    return {"label": label, "value": str(value), "flag": flag}


def _holes(diams: list[float]) -> str:
    c = Counter(round(d, 3) for d in diams if d)
    parts = [f"{n} x Ø{_in(d)}" for d, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
    if len(parts) > 4:
        parts = parts[:4] + [f"{sum(c.values()) - sum(n for _, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:4])} more"]
    return ", ".join(parts)


def material_row(mat: str, source: str) -> dict:
    """source: chosen | drawing | default"""
    if source == "chosen":
        return row("Material", f"{mat} (you chose)")
    if source == "drawing":
        return row("Material", f"{mat} (from your drawing)")
    return row("Material", f"{mat} (not in your files, so we assumed it; choose yours above)", "assumed")


def finish_row(finishes: list, source: str) -> dict:
    finishes = [str(f.get("name") or f.get("finish") or f.get("type") or "") if isinstance(f, dict) else str(f) for f in finishes or []]
    finishes = [f for f in finishes if f]
    if finishes:
        return row("Finish", ", ".join(finishes) + (" (from your drawing)" if source == "drawing" else ""))
    return row("Finish", "None")


@_safe
def step_part(geom: dict, mat: str, mat_source: str, finishes: list[str], fin_source: str, process: str, density: float | None) -> list[dict]:
    bb = geom.get("bounding_box") or {}
    out = [row("Overall size", _size(bb.get("length"), bb.get("width"), bb.get("height"))), row("Made by", process),
           material_row(mat, mat_source)]
    if geom.get("turned"):
        t = geom["turned"]
        out.append(row("Turned", f"Ø{_in(t.get('max_diameter'))} max, {_in(t.get('length'))} in long"))
    if geom.get("sheet_metal"):
        sm = geom["sheet_metal"]
        out.append(row("Sheet", f"{_in(sm.get('thickness'))} in thick, {sm.get('bends', 0)} bend{'s' if sm.get('bends') != 1 else ''}"))
    holes = geom.get("holes") or []
    out.append(row("Holes", _holes([h.get("diameter") for h in holes]) if holes else "None found"))
    if geom.get("volume") and density:
        out.append(row("Weight, about", f"{geom['volume'] * density:.2f} lb"))
    out.append(finish_row(finishes, fin_source))
    return out


@_safe
def step_assembly(geom: dict, groups: list[dict], mat: str, mat_source: str) -> list[dict]:
    bb = geom.get("bounding_box") or {}
    total = sum(int(g.get("qty", 1)) for g in groups) or geom.get("solids")
    names = ", ".join(f"{g.get('qty', 1)} x {g.get('name') or 'part'}" for g in groups[:6]) + (" and more" if len(groups) > 6 else "")
    return [row("Overall size", _size(bb.get("length"), bb.get("width"), bb.get("height"))),
            row("Parts in the model", f"{total} ({len(groups)} different)"), row("Parts", names), material_row(mat, mat_source),
            row("Joining", "Welded or fastened, to be confirmed by an engineer", "check")]


@_safe
def drawing_part(read: dict, geom: dict, mat: str, mat_source: str, finishes: list[str], fin_source: str, process: str,
                 reasons: list[str] | None = None) -> list[dict]:
    out = []
    title = " ".join(x for x in (read.get("part_number"), read.get("title")) if x)
    if title:
        out.append(row("Part", title + (f", rev {read['revision']}" if read.get("revision") else "")))
    env = geom.get("envelope_in") or {}
    if env.get("length"):
        src = geom.get("envelope_source")
        out.append(row("Overall size", _size(env.get("length"), env.get("width"), env.get("height")),
                       "" if src == "explicit" else "check"))
    else:
        out.append(row("Overall size", "Not found on the drawing", "check"))
    raw = (read.get("material") or {}).get("raw")
    out.append(row("Material on the drawing", raw) if raw else row("Material on the drawing", "Not found", "check"))
    out.append(material_row(mat, mat_source))
    out.append(row("Made by", process))
    tg = geom.get("turned") or {}
    if tg.get("max_diameter"):
        out.append(row("Turned", f"\u00d8{_in(tg['max_diameter'])} max" + (f", {_in(tg['length'])} in long" if tg.get("length") else "")))
    if geom.get("sheet_thickness"):
        out.append(row("Sheet thickness", f"{_in(geom['sheet_thickness'])} in"))
    if geom.get("bends"):
        out.append(row("Bends", geom["bends"]))
    if geom.get("holes"):
        d = geom.get("hole_diameters") or []
        out.append(row("Holes", f"{geom['holes']}" + (f" ({_holes(d)})" if d else "")))
    th = read.get("threads") or {}
    if th.get("count"):
        out.append(row("Threads", f"{th['count']}" + (f": {', '.join(th.get('callouts', [])[:3])}" if th.get("callouts") else "")))
    tol = read.get("tolerance") or {}
    if tol.get("tightest_in"):
        out.append(row("Tightest tolerance", f"±{_in(tol['tightest_in'])} in" + (f" ({tol['raw']})" if tol.get("raw") and tol["raw"] not in (f"±{tol['tightest_in']}",) else "")))
    sf = read.get("surface_finish") or {}
    if sf.get("ra_microin"):
        out.append(row("Surface finish", f"{sf['ra_microin']} µin Ra"))
    out.append(finish_row(finishes, fin_source))
    if read.get("heat_treat"):
        out.append(row("Heat treat", ", ".join(str(h.get("raw", h)) if isinstance(h, dict) else str(h) for h in read["heat_treat"][:2])))
    insp = read.get("inspection") or {}
    if insp.get("first_article") or insp.get("material_certs"):
        out.append(row("Paperwork", ", ".join(x for x, on in (("First article inspection", insp.get("first_article")),
                                                                ("Material certs", insp.get("material_certs"))) if on)))
    for r in (reasons or [])[:3]:
        out.append(row("Needs a look", r, "check"))
    return out


@_safe
def box_build(bb: dict) -> list[dict]:
    out = []
    title = " ".join(x for x in (bb.get("part_number"), bb.get("name")) if x)
    if title:
        out.append(row("Assembly", title))
    enc = bb.get("enclosure") or {}
    if enc.get("length_in"):
        out.append(row("Enclosure", enc.get("description") or _size(enc.get("length_in"), enc.get("width_in"), enc.get("height_in")),
                       "check" if enc.get("check") else ""))
    for p in (bb.get("pcbs") or [])[:2]:
        size = f", {_in(p['width_in'])} x {_in(p['height_in'])} in" if p.get("width_in") else ""
        out.append(row("Circuit board", f"{p.get('layers', '?')} layer{size}, {p.get('tht_parts', 0) + p.get('smt_unique', 0)} part types", "check" if p.get("check") else ""))
        for b in (p.get("bom_lines") or [])[:6]:
            out.append(row("On the board", f"{b.get('qty', 1)} x {b.get('description') or b.get('mpn')}"))
    custom = [ln for ln in bb.get("lines") or [] if ln.get("needs_quote")]
    bought = [ln for ln in bb.get("lines") or [] if not ln.get("needs_quote")]
    for ln in custom[:6]:
        out.append(row("Custom part", ln.get("description", ""), "check"))
    for ln in bought[:8]:
        out.append(row("Part", f"{ln.get('qty', 1)} x {ln.get('description') or ln.get('part_number')}"))
    if len(custom) + len(bought) > 14:
        out.append(row("More", f"{len(custom) + len(bought) - 14} more line items"))
    return out


@_safe
def flat_parts(parts: list[dict], thickness: float, mat: str, mat_source: str, process: str) -> list[dict]:
    out = [row("Parts", f"{len(parts)} different, {sum(int(p.get('qty', 1)) for p in parts)} in the files"),
           row("Sheet", f"{_in(thickness)} in thick"), material_row(mat, mat_source), row("Cut by", process)]
    for p in parts[:5]:
        holes = p.get("hole_diameters") or []
        h = ", ".join(f"{x['count']} x Ø{_in(x['diameter'])}" for x in holes[:3])
        extra = f", {p['cutouts']} cutouts" + (f" ({h})" if h else "") if p.get("cutouts") else ""
        bends = f", {p['bends']} bend line{'s' if p['bends'] != 1 else ''}" if p.get("bends") else ""
        out.append(row(p.get("name") or "Part", f"{_in(p.get('width'))} x {_in(p.get('height'))} in flat{extra}{bends}"))
    if len(parts) > 5:
        out.append(row("More", f"{len(parts) - 5} more parts"))
    return out


@_safe
def pcb(board: dict, found: dict, bom_lines: int) -> list[dict]:
    out = [row("Board", f"{board.get('layers', '?')} layers" + (f", {_in(board['width_in'])} x {_in(board['height_in'])} in" if board.get("width_in") else ""))]
    out.append(row("Parts", f"{board.get('smt_placements', 0)} surface mount placements on {board.get('sides', 1)} side{'s' if board.get('sides', 1) != 1 else ''}, "
                            f"{board.get('tht_parts', 0)} through-hole"))
    if board.get("bga") or board.get("fine_pitch"):
        out.append(row("Fine pitch and BGA", f"{board.get('fine_pitch', 0)} fine pitch, {board.get('bga', 0)} BGA"))
    got = [n for n, on in (("Gerbers", found.get("gerbers")), ("drill file", found.get("drill")), ("pick-and-place", found.get("cpl")), ("BOM", found.get("bom"))) if on]
    missing = [n for n, on in (("Gerbers", found.get("gerbers")), ("drill file", found.get("drill")), ("pick-and-place", found.get("cpl")), ("BOM", found.get("bom"))) if not on]
    out.append(row("Files found", ", ".join(got) or "None"))
    if missing:
        out.append(row("Missing", ", ".join(missing), "check"))
    if bom_lines:
        out.append(row("BOM lines", bom_lines))
    return out
