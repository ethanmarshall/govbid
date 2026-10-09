"""Spot assembly drawings and turn their notes into a box build to start from.

The drawing quoter prices ONE part (an envelope, a material, holes and bends). Fed an assembly drawing
(an enclosure with a cover plate, a PCB, switches and jacks, several material notes), it measures the
wrong thing and the price is meaningless. detect() scores the signs of an assembly; prefill() reads the
numbered notes, item callouts and per-sheet dimensions into the box build spec (app/box_build.py) so the
user starts from the drawing instead of a blank form. Everything it fills is a reading of the notes:
the UI shows the evidence and the user checks it.
"""
from __future__ import annotations

import re
from pathlib import Path

from .box_build import blank_line, blank_pcb, classify_component
from .drawing import map_material, nice_title

TITLE_WORDS = re.compile(r"\b(ASSEMBLY|ASSY|ASM|KIT|TRAINER|CONSOLE|CHASSIS|CABINET|SIMULATOR|TEST\s*SET|PANEL\s*ASSY)\b", re.I)
PART_MATERIAL = re.compile(r"^\s*\d+\.\s*([A-Z][A-Z /&-]{2,40}?)\s+MATERIAL\b[,:]?\s*(.+)$", re.I | re.M)
ELECTRICAL = [("PCB", r"\bPCBA?\b|PRINTED\s*(?:CIRCUIT|WIRING)\s*(?:BOARD|ASSEMBLY)|CIRCUIT\s*CARD"),
              ("switches", r"\bTOGGLE|\bSWITCH(?:ES)?\b|PUSH\s*BUTTON|ROCKER"),
              ("jacks or connectors", r"TEST\s*JACK|BANANA|BINDING\s*POST|CONNECTOR|RECEPTACLE|D-?SUB|D38999|MS3\d{3}"),
              ("terminal blocks", r"TERMINAL\s*BLOCK|TERMINAL\s*STRIP"),
              ("wiring", r"\bHARNESS|\bWIRE\b|\bWIRING\b|\bAWG\b|CABLE\s*ASS"),
              ("indicators or displays", r"\bLED\b|INDICATOR|DISPLAY|\bLCD\b|\bLAMP\b"),
              ("power parts", r"POWER\s*SUPPLY|\bFUSE|BREAKER|TRANSFORMER|RELAY"),
              ("silkscreen or legends", r"SILK\s*-?\s*SCREEN|LEGEND")]
BOM_HEAD = re.compile(r"\b(?:PARTS?\s*LIST|BILL\s*OF\s*MATERIALS?|FIND\s*NO|ITEM\s*NO\.?\s+(?:QTY|PART))\b", re.I)
QTY = re.compile(r"\(\s*QTY\s*[:=]?\s*(\d{1,4})\s*\)|\bQTY\s*[:=]?\s*(\d{1,4})\b|\((\d{1,4})\s*X\s*\)|\b(\d{1,4})\s*X\b(?!\s*\d)|\((\d{1,4})\s*(?:PL|PLCS|PLACES)\)", re.I)
MFR = re.compile(r"\b(?:MFR|MFG|MANUFACTURER)\.?\s*(?:P/?N|PART\s*(?:NO|#)|#|NO\.?)?\s*[:#]?\s*:?\s*([A-Z0-9][A-Z0-9\-./]{2,30})", re.I)
GENERIC_NOTE = re.compile(r"DIMENSIONS?\s+SHOWN|FOR\s+REF(?:E?RENCE)?\s+ONLY|SUBJECT\s+TO\s+(?:CUSTOMER\s+)?(?:REVIEW|APPROVAL)|SHOWN\s+FOR\s+REF|"
                          r"HAS\s+BEEN\s+REMOVED|SHOWN\s+WITH|INTERPRET\s+PER|UNLESS\s+OTHERWISE|LAYOUT,|COLOR,|HEX\s*CODE|MATERIAL\b|FINISH\s+FOR|"
                          r"BREAK\s+(?:ALL\s+)?(?:SHARP\s+)?EDGES|DEBURR", re.I)
# Reference dimensions in parentheses '(14)' '(18.75)', or bare decimals '12.25 MAX'. Bare whole numbers are left out:
# on a drawing sheet those are the zone markers along the border (1 2 3 4).
DIM_LINE = re.compile(r"^\(\s*(\d{0,3}\.\d{1,4}|\d{1,3})\s*\)\s*(?:MAX|MIN|REF|TYP\.?)?$|^(\d{0,3}\.\d{1,4})\s*(?:MAX|MIN|REF|TYP\.?)?$", re.I)
PINS_BY_POLE = [(r"\b3PDT\b", 9), (r"\b4PDT\b", 12), (r"\bDPDT\b|\bSP3T\b", 6), (r"\bDPST\b", 4), (r"\bSPDT\b", 3), (r"\bSPST\b", 2)]
FINISH_MAP = [(r"POWDER\s*COAT", "powder_coat"), (r"ANODI[SZ]", "anodize"), (r"CHEM(?:ICAL)?\s*FILM|MIL-DTL-5541|ALODINE", "chem_film"), (r"\bPAINT", "paint")]


def page_texts(path: Path | str) -> list[str]:
    from pypdf import PdfReader

    out = []
    for p in PdfReader(str(path)).pages:
        try:
            out.append(p.extract_text() or "")
        except Exception:  # noqa: BLE001  (one bad page should not stop the read)
            out.append("")
    return out


def detect(read: dict, pages: list[str]) -> dict | None:
    """{score, reasons} when the drawing looks like an assembly, else None."""
    text = "\n".join(pages)
    score, reasons = 0, []
    title = read.get("title") or ""
    if TITLE_WORDS.search(title):
        score += 2
        reasons.append(f"the title says {TITLE_WORDS.search(title).group(1).lower()}")
    parts = {m.group(1).strip().upper() for m in PART_MATERIAL.finditer(text)}
    if len(parts) >= 2:
        score += 2
        reasons.append(f"separate materials for {len(parts)} parts ({', '.join(sorted(p.lower() for p in parts))})")
    found = [name for name, pat in ELECTRICAL if re.search(pat, text, re.I)]
    if found:
        score += min(len(found), 3) + (1 if "PCB" in found else 0)
        reasons.append("electrical parts: " + ", ".join(found))
    qty_notes = sum(1 for ln in text.splitlines() if QTY.search(ln) and re.search(r"[A-Z]{3,}", ln))
    if qty_notes >= 2:
        score += 1
        reasons.append(f"{qty_notes} notes with item quantities")
    if BOM_HEAD.search(text):
        score += 2
        reasons.append("a parts list")
    return {"score": score, "reasons": reasons} if score >= 4 else None


def _notes(page: str) -> list[str]:
    """Numbered notes, joined when a note wraps onto the next line."""
    out: list[str] = []
    for ln in page.splitlines():
        s = ln.strip()
        m = re.match(r"^(?:[A-Z]\s*)?(\d{1,2})\.\s+(.+)$", s)
        if m:
            out.append(m.group(2).strip())
        elif out and s and not re.match(r"^[\d(.]", s) and s.upper() == s and len(s) > 12 and not s.endswith(")") and len(out[-1]) < 200 and not out[-1].endswith("."):
            out[-1] += " " + s
    return out


def _dims(page: str) -> list[float]:
    vals = []
    for ln in page.splitlines():
        m = DIM_LINE.match(ln.strip())
        if m:
            v = float(m.group(1) or m.group(2))
            if 0.05 <= v <= 120:
                vals.append(v)
    for m in re.finditer(r"\(\s*(\d{0,3}\.\d{1,4}|\d{1,3})\s*\)\s*(?:\n\s*)?MAX", page, re.I):
        vals.append(float(m.group(1)))
    return vals


def _qty(text: str) -> int | None:
    m = QTY.search(text)
    return int(next(g for g in m.groups() if g)) if m else None


def _pins(desc: str) -> int:
    for pat, n in PINS_BY_POLE:
        if re.search(pat, desc, re.I):
            return n
    m = re.search(r"\b(\d{1,2})\s*(?:POS(?:ITION)?S?|PIN|P)\b", desc, re.I)
    return int(m.group(1)) if m else 2


def prefill(read: dict, pages: list[str]) -> dict:
    """A box build spec to start from, with the evidence for each value and what still needs checking."""
    text = "\n".join(pages)
    evidence: list[str] = []
    assumptions: list[str] = []
    fabricated: list[dict] = []
    lines: list[dict] = []
    pcb_lines: list[dict] = []
    pcb_page = next((p for p in pages if re.search(r"\bPCBA?\b|CIRCUIT\s*CARD", p, re.I)), "")
    enc_page = next((p for p in pages if re.search(r"ENCLOSURE\s+MATERIAL", p, re.I)), "") or (pages[1] if len(pages) > 1 else pages[0] if pages else "")

    # ---- custom fabricated parts (one MATERIAL note each)
    for m in PART_MATERIAL.finditer(text):
        name, callout = m.group(1).strip().title(), m.group(2).strip().rstrip(".")
        fabricated.append({"name": name, "callout": callout, "material": map_material(callout) or ""})
        evidence.append(f"Custom part: {name}, {callout}.")

    # ---- enclosure
    enc_mat = next((f for f in fabricated if re.search(r"ENCLOSURE|CHASSIS|HOUSING|BOX|CASE", f["name"], re.I)), None)
    etype = "sheet_steel"
    if enc_mat:
        c = enc_mat["callout"].upper()
        etype = ("stainless_nema4x" if re.search(r"STAINLESS|CRES|\b30[34]\b|\b316\b", c) else "diecast_aluminum" if re.search(r"DIE\s*-?CAST", c)
                 else "extruded_aluminum" if re.search(r"ALUM", c) else "polycarbonate" if re.search(r"POLYCARB", c) else "abs_plastic" if re.search(r"\bABS\b|PLASTIC", c)
                 else "sheet_steel")
    d = sorted(set(_dims(enc_page)), reverse=True)
    enclosure = {"source": "catalog", "type": etype, "length_in": None, "width_in": None, "height_in": None, "finish": "none",
                 "silkscreen_colors": 0, "silkscreen_sides": 1, "mods": {"auto_cutouts": True}, "description": (enc_mat or {}).get("callout", "")}
    if len(d) >= 2:
        enclosure["length_in"], enclosure["width_in"] = d[0], d[1]
        rest = [v for v in d[2:] if v >= 1.5]
        if rest:
            enclosure["height_in"] = min(rest)
        depth = f" x {enclosure['height_in']:g}" if enclosure["height_in"] else ""
        evidence.append(f"Enclosure about {d[0]:g} x {d[1]:g}{depth} in "
                        "from the dimensions on the enclosure sheet (largest two, and the smallest depth over 1.5 in).")
        assumptions.append("Enclosure size comes from the reference dimensions on its sheet. Check the depth: covers and lids can add to it.")
    for pat, key in FINISH_MAP:
        if re.search(pat, text, re.I):
            enclosure["finish"] = key
            evidence.append(f"Finish: {key.replace('_', ' ')}.")
            break
    if re.search(r"SILK\s*-?\s*SCREEN", text, re.I):
        colors = 1 + (1 if re.search(r"TWO\s*COLOR|2\s*COLOR", text, re.I) else 0)
        enclosure["silkscreen_colors"] = colors
        evidence.append(f"Silkscreen: {colors} color, one side.")
    if fabricated:
        names = ", ".join(f["name"].lower() for f in fabricated)
        assumptions.append(f"Custom parts on this drawing ({names}) are not catalog items. The enclosure is priced from the catalog placeholder for a "
                           "box of this type and size. For a real price, quote each part (DXF flat parts, or Instant quote from its STEP file), "
                           "save it, and link it here, then set the enclosure to Custom.")

    # ---- items from the notes
    on_panel_holes = 0
    for pi, page in enumerate(pages):
        is_pcb_page = page is pcb_page and bool(pcb_page)
        for note in _notes(page):
            if GENERIC_NOTE.search(note) and not re.search(r"TEST\s*JACK|TOGGLE|TERMINAL|CONNECTOR|SWITCH|LOCK", note, re.I):
                continue
            qty = _qty(note)
            mfr = (MFR.search(note).group(1) if MFR.search(note) else "")
            desc = re.sub(r"\s*\((?:QTY|MFR|MFG)[^)]*\)\.?", "", note).strip().rstrip(".")
            ctype = classify_component(mfr, desc)
            if re.search(r"MOUNTING\s*HOLES?.*HARDWARE|#\d+\s*SIZE\s*HARDWARE", note, re.I):
                n = qty or 4
                size = re.search(r"#\d+", note)
                lines.append(blank_line(type="hardware", description=f"{size.group(0) + ' ' if size else ''}PCB mounting hardware (screw, standoff, washer)", qty=n,
                                        mount="internal", terminations=0))
                evidence.append(f"{n} sets of mounting hardware: {note}")
                continue
            if re.search(r"INERT\s*COMPONENT", note, re.I):
                lines.append(blank_line(type="other", description="Inert components next to circuit symbols (count not on the drawing: set the quantity)",
                                        qty=qty or 1, mount="panel", terminations=0))
                assumptions.append("The drawing calls for inert components next to the circuit symbols but does not count them. Set that quantity.")
                continue
            if re.search(r"CAM\s*LOCK|\bLATCH\b|\bLOCK\b", note, re.I):
                lm = re.search(r"((?:CAM\s*)?LOCK|LATCH)\s*(\([^)]*\))?", note, re.I)
                what = f"{lm.group(1).capitalize()} {lm.group(2).lower() if lm.group(2) else ''}".strip()
                lines.append(blank_line(type="hardware", description=what, qty=qty or 1, mount="panel", terminations=0))
                on_panel_holes += qty or 1
                evidence.append(f"Lock: {note}")
                continue
            if ctype in ("other",) and not qty:
                continue  # not an item callout
            n = qty or 1
            if is_pcb_page and (re.search(r"PC\s*PINS?|PCB|THT|THROUGH\s*HOLE", note, re.I) or ctype in ("terminal_block",)):
                pins = _pins(desc)
                pcb_lines.append({"ref": "", "mpn": mfr, "manufacturer": "", "description": desc, "qty": n, "tht": True, "unit_price": None,
                                  "price_source": "", "distributor": "", "_pins": pins})
                if ctype in ("toggle_switch", "rocker_switch", "pushbutton", "rotary_switch", "keyswitch", "led_indicator", "potentiometer"):
                    on_panel_holes += n  # PCB-mounted, but it still pokes through the panel
                evidence.append(f"On the PCB: {n} x {desc[:70]} ({pins} pins each{'' if re.search(r'SP|DP|3P|4P|POS|PIN', desc, re.I) else ', assumed'}).")
                continue
            ln = blank_line(type=ctype, part_number=mfr, description=desc, qty=n,
                            mount="internal" if ctype in ("power_supply", "relay", "terminal_block", "hardware", "heatsink", "computer_module", "cable_assembly") else "panel")
            lines.append(ln)
            evidence.append(f"Part: {n} x {desc[:80]} ({ctype.replace('_', ' ')}).")
        # loose callouts such as "RUBBER FOOT (4X)"
        for ln_text in page.splitlines():
            s = ln_text.strip()
            m = re.match(r"^([A-Z][A-Z ,/-]{3,40}?)\s*\((\d{1,3})\s*X\s*\)$", s)
            if m and not re.match(r"^\d", s):
                what = m.group(1).strip().title()
                lines.append(blank_line(type="hardware", description=what, qty=int(m.group(2)), mount="internal", terminations=0))
                evidence.append(f"{int(m.group(2))} x {what.lower()} (from a callout).")

    # ---- PCB
    pcbs = []
    if pcb_page:
        pd = sorted(set(_dims(pcb_page)), reverse=True)
        b = blank_pcb(name="PCB assembly", layers=2)
        if len(pd) >= 2:
            b["width_in"], b["height_in"] = pd[0], pd[1]
            evidence.append(f"PCB about {pd[0]:g} x {pd[1]:g} in (largest dimensions on the PCB sheet).")
        b["tht_parts"] = sum(x["qty"] for x in pcb_lines)
        b["tht_joints"] = sum(x["qty"] * x.pop("_pins") for x in pcb_lines)
        b["bom_lines"] = pcb_lines
        pcbs.append(b)
        assumptions.append("PCB: 2 layers and through-hole parts only, since the drawing shows no SMT parts or layer count. "
                           "Drop the Gerbers and BOM on the board for an exact count.")
    if on_panel_holes:
        enclosure["mods"]["round_holes"] = on_panel_holes + sum(ln["qty"] for ln in lines if ln["type"] == "test_jack")
        evidence.append(f"{enclosure['mods']['round_holes']:g} round panel holes (jacks, PCB switches and the lock).")
    if not lines and not pcbs:
        assumptions.append("No item notes were found. Add the parts by hand or drop the assembly BOM.")
    title = read.get("title") or ""
    return {"name": nice_title(title), "part_number": read.get("part_number") or read.get("drawing_number") or "",
            "enclosure": enclosure, "pcbs": pcbs, "lines": lines, "peripherals": [], "children": [],
            "wiring": {"mark_wires": True}, "labor": {"ipc_class": 2, "serialize": True, "nre_in_price": True, "lab_tests": []},
            "options": {"packaging_level": "commercial"}, "fabricated": fabricated, "evidence": evidence, "assumptions": assumptions}


def analyze(path: Path | str, read: dict) -> dict | None:
    """detect + prefill for an uploaded drawing; None for a single-part drawing."""
    pages = page_texts(path)
    hit = detect(read, pages)
    if not hit:
        return None
    return {**hit, "box_build": prefill(read, pages),
            "message": "This is an assembly drawing (" + "; ".join(hit["reasons"]) + "). A single-part price from it is not meaningful. "
                       "Open it as a box build: the enclosure, parts and PCB below were read from the notes."}
