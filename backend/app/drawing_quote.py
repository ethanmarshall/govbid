"""Quote a part from its PDF drawing alone, when there is no STEP model.

The drawing reader (drawing.py) already pulls material, finish, tolerance, threads and title
block fields. This module reads the rest of what a price needs from the drawing text:

  - hole callouts with counts ("4X Ø.201 THRU", "Ø.250 THRU 4 PLCS", "2X 1/4-20 UNC-2B")
  - bend notes ("BEND UP 90° R.06", "4 BENDS") and sheet thickness or gauge
  - turned features (diameter callouts on shafts, pins, bushings; external threads; runout)
  - the overall envelope: explicit ("OVERALL SIZE 8.00 X 3.00 X 1.50", "OVERALL LENGTH 6.00")
    or, with low confidence, the largest dimension values on the sheet

Vector PDFs exported from CAD keep dimension text as real text, so this works on them; a
scanned drawing has no text and needs the optional Claude pass (only for drawings that may be
shared with an outside service, never ITAR/EAR or limited-distribution drawings).

Every guess becomes an assumption line on the quote. The envelope drives the material and
machining estimate, so check it against the drawing before you bid.
"""
from __future__ import annotations

import base64
import json
import re

from . import drawing, pricing
from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

PROCESSES = ("cnc_mill", "cnc_lathe", "sheet_metal", "3d_print")
STOCK_ALLOWANCE_IN = 0.125

NUM = r"(\d*\.\d+|\d+(?:\.\d+)?)"
DIA = r"(?:Ø|⌀|∅|\bDIA\.?\s*|\bDIAM(?:ETER)?\.?\s*)"
COUNT_PRE = re.compile(r"(?:\(\s*(\d{1,3})\s*\)|\b(\d{1,3})\s*[Xx×])\s*$")
COUNT_POST = re.compile(r"\b(\d{1,3})\s*(?:PL(?:ACE)?S?\b|PLCS\b|HOLES\b)", re.I)
HOLE_WORDS = re.compile(r"\b(THRU|THROUGH|DEEP|DP|DRILL|HOLES?|C'?BORE|CBORE|CSK|CSINK|REAM|PLCS?|PLACES?)\b", re.I)
DIA_VALUE = re.compile(DIA + r"\s*" + NUM, re.I)
DRILL_ONLY = re.compile(r"(?:#\d{1,2}|[A-Z]|\d*\.\d+)\s*DRILL\b|\bDRILL\s*(?:#\d{1,2}|\d*\.\d+)", re.I)
BEND_LINE = re.compile(r"\bBEND\s*(?:UP|DOWN|DN)\b|\b(?:UP|DOWN|DN)\s*\d{1,3}\s*(?:°|DEG)", re.I)
BEND_COUNT = re.compile(r"\b(\d{1,2})\s*BENDS\b|\bBENDS?\s*[:=]\s*(\d{1,2})\b", re.I)
# '0.125" THK', '.125 IN THICK', 'THK: .125', 'THICKNESS = 3 MM'. A number AFTER the keyword needs ':' or '=' or a
# decimal point, so 'THK. 5052 ALUMINUM' does not read the alloy number as the thickness.
THICK = re.compile(NUM + r"\s*(?:\"|''|IN\.?|INCH(?:ES)?|MM)?\s*(?:THK|THICK)\b"
                   r"|(?:\bTHK\.?|\bTHICK(?:NESS)?\.?)\s*(?:[:=]\s*" + NUM + r"|(\d*\.\d+))", re.I)
ALLOY_NUMBER = re.compile(r"^(?:1008|1010|1011|1018|1020|1045|2024|3003|4130|4140|5052|5083|6061|6063|7075|8620|303|304|316|410|416|17-4)$")
GAUGE = re.compile(r"\b(\d{1,2})\s*(?:GA\b\.?|GAUGE\b|GA\.)", re.I)
SHEET_WORDS = re.compile(r"\bSHEET\s*(?:METAL|STOCK)?\b(?!\s*\d+\s*OF)|FLAT\s*PATTERN|K-?\s*FACTOR|PRESS\s*BRAKE|BEND\s*RADIUS|\bFORMED\b|\bBRAKE\b", re.I)
LATHE_WORDS = re.compile(r"\bT\.?I\.?R\.?\b|RUNOUT|CONCENTRIC|\bKNURL|UNDERCUT|\bGROOVE|CENTER\s*DRILL|\bTURN(?:ED)?\b|\bCHAMFER\b", re.I)
LATHE_TITLES = re.compile(r"\b(SHAFT|PIN|BUSHING|SPACER|STANDOFF|SLEEVE|ROLLER|AXLE|SPINDLE|STUD|BOLT|NUT|PLUG|COLLAR|HUB|WASHER|NOZZLE|FITTING)\b", re.I)
PRINT_WORDS = re.compile(r"3\s*-?D\s*PRINT|ADDITIVE(?:LY)?\s*MANUFACTUR|\bFDM\b|\bFFF\b|\bSLA\b|\bSLS\b|\bMJF\b|STEREOLITHOGRAPHY|\bPRINTED\b", re.I)
PRINT_MATERIALS = [(r"\bPLA\b", "PLA"), (r"\bPETG\b", "PETG"), (r"\bASA\b", "ASA (UV stable)"), (r"\bABS\b", "ABS"),
                   (r"\bTPU\b", "TPU 95A (flexible)"), (r"NYLON\s*12.*MJF|MJF.*NYLON\s*12|\bPA\s*12\b.*MJF", "Nylon 12 (MJF)"),
                   (r"NYLON\s*12|\bPA\s*12\b", "Nylon 12 (SLS)"), (r"NYLON\s*11|\bPA\s*11\b", "Nylon 11 (SLS)"),
                   (r"TOUGH\s*RESIN", "Tough resin"), (r"\bRESIN\b", "Standard resin")]
EXPLICIT_XYZ = re.compile(r"(?:OVERALL(?:\s*(?:SIZE|DIMENSIONS?|DIMS?|ENVELOPE))?|ENVELOPE|PART\s*SIZE|BLANK\s*SIZE|FINISHED\s*SIZE|STOCK\s*SIZE)\s*[:=]?\s*"
                          + NUM + r"\s*[X×]\s*" + NUM + r"(?:\s*[X×]\s*" + NUM + r")?", re.I)
EXPLICIT_ONE = re.compile(r"(?:OVERALL\s*(LENGTH|WIDTH|HEIGHT|THICKNESS|DIA(?:METER)?)|\b(OAL)\b)\s*[:=]?\s*" + NUM
                          + r"|" + NUM + r"\s*(?:OVERALL|OAL)\b(?:\s*(LENGTH|WIDTH|HEIGHT))?", re.I)
DIM_VALUE = re.compile(r"(?<![\d.±/#\-+×xX])(\d{0,4}\.\d{1,4}|\d{1,4})(?![\d/]|\s*-\s*\d|\s*(?:°|DEG|UN|X\s*\d))")
TOL_AFTER = re.compile(r"^\s*(?:±|\+/-|\+-)")
ALLOWED_DIM_WORDS = {"REF", "TYP", "MAX", "MIN", "BSC", "BASIC", "X", "IN", "MM", "R", "SQ"}

# Sheet gauges, inches. Manufacturers' Standard Gauge for carbon steel and the usual stainless
# gauges; Brown & Sharpe (AWG) for aluminum and copper alloys.
GAUGE_STEEL = {7: .1793, 8: .1644, 9: .1495, 10: .1345, 11: .1196, 12: .1046, 13: .0897, 14: .0747, 16: .0598, 18: .0478,
               20: .0359, 22: .0299, 24: .0239, 26: .0179}
GAUGE_STAINLESS = {7: .1875, 8: .1719, 10: .1406, 11: .125, 12: .1094, 14: .0781, 16: .0625, 18: .05, 20: .0375, 22: .0312, 24: .025, 26: .0188}
GAUGE_ALUMINUM = {8: .1285, 10: .1019, 11: .0907, 12: .0808, 14: .0641, 16: .0508, 18: .0403, 20: .0320, 22: .0253, 24: .0201}


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _count_on_line(line: str, start: int) -> int:
    m = COUNT_PRE.search(line[max(0, start - 12): start])
    if m:
        return int(m.group(1) or m.group(2))
    m = COUNT_POST.search(line)
    if m:
        return int(m.group(1))
    return 1


def _is_note(line: str) -> bool:
    return bool(re.match(r"^\s*\d{1,2}[.)]\s+[A-Z]", line))


def _thread_spans(line: str) -> list[tuple[int, int]]:
    return [m.span() for m in drawing.THREAD_INCH.finditer(line)] + [m.span() for m in drawing.THREAD_METRIC.finditer(line)]


def _dimension_values(line: str, metric: bool) -> list[float]:
    """Numbers on a line that looks like dimension text (mostly numbers and symbols)."""
    if _is_note(line) or DIA_VALUE.search(line) or HOLE_WORDS.search(line) or _thread_spans(line):
        return []
    if re.search(r"TOLERANC|\.X{2,}|SCALE|SHEET\s*\d|REV\b|DATE|CAGE|DWG|SIZE|ANGLES|\bTYP|UNLESS|\d{4}-\d{2}-\d{2}", line, re.I):
        return []
    words = [w for w in re.findall(r"[A-Za-z]+", line) if w.upper() not in ALLOWED_DIM_WORDS]
    if sum(len(w) for w in words) > 4:
        return []
    out = []
    for m in DIM_VALUE.finditer(line):
        before = line[max(0, m.start() - 3): m.start()]
        if re.search(r"(?:±|\+/-|\+-|R)\s*$", before):  # a tolerance or a radius
            continue
        raw = m.group(1)
        if "." not in raw and not metric:
            continue  # inch drawings write dimensions as decimals
        v = float(raw)
        if metric:
            v /= 25.4
        if 0.01 <= v <= 240:
            out.append(round(v, 4))
    return out


def extract_geometry(read: dict, text: str) -> dict:
    """Pull envelope, holes, bends, sheet thickness and turned features from drawing text.

    read: the dict from drawing.read_drawing (or parse_text). Returns process_guess,
    envelope_in {length, width, height} (None where unknown), envelope_source
    ("explicit" | "dimension text" | "none"), confidence ("high" | "medium" | "low"),
    holes (plain, untapped), tapped_holes, thru_holes (plain or tapped holes marked THRU),
    bends (None when the drawing says nothing), turned {max_diameter, length} or None,
    sheet_thickness, cut_length_estimate, hole_diameters, features (notes), evidence (lines).
    """
    t = text or ""
    lines = _lines(t)
    metric = bool((read.get("tolerance") or {}).get("metric_drawing")) or bool(drawing.METRIC_UNITS.search(t))
    k = 1 / 25.4 if metric else 1.0
    evidence: list[str] = []
    features: list[str] = []

    # ------------------------------------------------ holes
    plain = thru = 0
    hole_diams: list[float] = []
    other_diams: list[float] = []
    for ln in lines:
        if _is_note(ln) and not DIA_VALUE.search(ln):
            continue
        spans = _thread_spans(ln)
        hole_word = HOLE_WORDS.search(ln)
        if spans:
            if re.search(r"\bTHRU\b|\bTHROUGH\b", ln, re.I):
                n = _count_on_line(ln, spans[0][0])
                thru += n
            continue  # tapped holes are counted from the reader's thread callouts
        dm = DIA_VALUE.search(ln)
        if dm and hole_word:
            n = _count_on_line(ln, dm.start())
            plain += n
            hole_diams += [round(float(dm.group(1)) * k, 4)] * n
            if re.search(r"\bTHRU\b|\bTHROUGH\b", ln, re.I):
                thru += n
            evidence.append(f"{ln}: {n} hole{'s' if n != 1 else ''}")
        elif DRILL_ONLY.search(ln) and not _is_note(ln):
            m = DRILL_ONLY.search(ln)
            n = _count_on_line(ln, m.start())
            plain += n
            if re.search(r"\bTHRU\b", ln, re.I):
                thru += n
            evidence.append(f"{ln}: {n} drilled hole{'s' if n != 1 else ''}")
        elif dm:
            for m in DIA_VALUE.finditer(ln):
                other_diams.append(round(float(m.group(1)) * k, 4))
            evidence.append(f"{ln}: diameter {other_diams[-1]} in (no THRU/DEEP: a turned diameter or a fitted bore)")
    threads = read.get("threads") or {}
    tapped = int(read.get("holes_tapped_guess") or threads.get("internal") or 0)
    if threads.get("callouts"):
        evidence.append(f"Threads: {', '.join(threads['callouts'])}")
    if threads.get("helicoils"):
        features.append(f"{threads['helicoils']} thread insert(s) (Helicoil or similar)")

    # ------------------------------------------------ bends and sheet
    bends = None
    m = BEND_COUNT.search(t)
    if m:
        bends = int(m.group(1) or m.group(2))
        evidence.append(f"{_clean_line(t, m)}: {bends} bends")
    else:
        n = 0
        for ln in lines:
            bm = BEND_LINE.search(ln)
            if bm:
                c = _count_on_line(ln, bm.start())
                n += c
                evidence.append(f"{ln}: {c} bend{'s' if c != 1 else ''}")
        bends = n or None
    thickness = None
    for ln in lines:
        for tm in THICK.finditer(ln):
            raw = next(g for g in tm.groups() if g)
            unit_k = 1 / 25.4 if re.search(r"\bMM\b", tm.group(0) + ln[tm.end(): tm.end() + 4], re.I) else k
            val = round(float(raw) * unit_k, 4)
            if ALLOY_NUMBER.match(raw) or not 0.005 <= val <= 6.0:  # an alloy number or not a believable thickness
                evidence.append(f"{ln}: ignored {raw} as a thickness")
                continue
            thickness = val
            evidence.append(f"{ln}: thickness {thickness} in")
            break
        if thickness is not None:
            break
    if thickness is None:
        gm = GAUGE.search(t)
        if gm:
            gauge_line = _clean_line(t, gm).lower()  # the gauge's own note says which material it is
            mat = gauge_line if re.search(r"alum|copper|brass|stainless|cres|steel|\bcrs\b|a1008|a1011", gauge_line) else \
                ((read.get("material") or {}).get("mapped") or (read.get("material") or {}).get("raw") or "").lower()
            table = GAUGE_ALUMINUM if ("alum" in mat or "copper" in mat or "brass" in mat) else GAUGE_STAINLESS if ("stainless" in mat or "cres" in mat) else GAUGE_STEEL
            g = int(gm.group(1))
            if g in table:
                thickness = table[g]
                which = "Brown & Sharpe (aluminum)" if table is GAUGE_ALUMINUM else "stainless" if table is GAUGE_STAINLESS else "manufacturers' standard (steel)"
                evidence.append(f"{_clean_line(t, gm)}: {g} gauge = {thickness} in by the {which} gauge table")
    sheet_words = bool(SHEET_WORDS.search(t))

    # ------------------------------------------------ envelope
    env = {"length": None, "width": None, "height": None}
    source = "none"
    m = EXPLICIT_XYZ.search(t)
    if m:
        vals = sorted((float(v) * k for v in m.groups() if v), reverse=True)
        for key, v in zip(("length", "width", "height"), vals):
            env[key] = round(v, 4)
        source = "explicit"
        evidence.append(f"{_clean_line(t, m)}: overall size")
    explicit_diameter = None
    for m in EXPLICIT_ONE.finditer(t):
        word = (m.group(1) or m.group(2) or m.group(5) or "LENGTH").upper()
        v = round(float(m.group(3) or m.group(4)) * k, 4)
        if word.startswith("DIA"):
            explicit_diameter = v
        else:
            key = {"OAL": "length", "THICKNESS": "height"}.get(word, word.lower())
            env[key] = env.get(key) or v
        source = "explicit"
        evidence.append(f"{_clean_line(t, m)}: overall {word.lower()} {v} in")
    dims: list[float] = []
    for ln in lines:
        vals = _dimension_values(ln, metric)
        if vals:
            dims += vals
            evidence.append(f"{ln}: dimension {', '.join(str(v) for v in vals)} in")
    dims = sorted(set(dims), reverse=True)

    # ------------------------------------------------ process
    raw_mat = ((read.get("material") or {}).get("raw") or "")
    title = read.get("title") or ""
    print_mat = next((name for pat, name in PRINT_MATERIALS if re.search(pat, raw_mat, re.I)), None)
    is_print = bool(PRINT_WORDS.search(t)) or bool(print_mat)
    is_sheet = bool(bends) or (thickness is not None and (sheet_words or thickness <= 0.25)) or bool(re.search(r"FLAT\s*PATTERN|PRESS\s*BRAKE", t, re.I))
    lathe_hits = len(LATHE_WORDS.findall(t)) + (2 if LATHE_TITLES.search(title) else 0) + (1 if threads.get("external") else 0)
    is_lathe = bool(other_diams or explicit_diameter) and lathe_hits >= 2
    if is_print:
        process = "3d_print"
        evidence.append("3D printing named on the drawing" + (f" (material {print_mat})" if print_mat else ""))
    elif is_sheet:
        process = "sheet_metal"
    elif is_lathe:
        process = "cnc_lathe"
    else:
        process = "cnc_mill"

    # Fill the envelope from dimension text where the drawing did not state it
    turned = None
    if process == "cnc_lathe":
        maxd = explicit_diameter or max(other_diams)
        length = env["length"] or next((d for d in dims if d > maxd * 0.5), None)
        turned = {"max_diameter": round(maxd, 4), "length": round(length, 4) if length else None,
                  "diameters": sorted(set(other_diams + ([explicit_diameter] if explicit_diameter else [])), reverse=True)}
        env = {"length": turned["length"], "width": turned["max_diameter"], "height": turned["max_diameter"]}
        if source != "explicit":
            source = "dimension text" if length else "none"
    elif source != "explicit" or not all(env.values()):
        pool = [d for d in dims if d not in env.values()]
        for key in ("length", "width", "height"):
            if env[key] is None and pool:
                if process == "sheet_metal" and key == "height" and thickness and pool and max(pool) <= thickness * 1.01:
                    break
                env[key] = pool.pop(0)
                if source == "none":
                    source = "dimension text"
        if source == "explicit" and not all(env.values()):
            features.append("Part of the envelope came from dimension text")
        vals = sorted((v for v in env.values() if v), reverse=True)
        env = dict(zip(("length", "width", "height"), vals + [None] * (3 - len(vals))))
    if process == "sheet_metal" and thickness and env["height"] is None:
        env["height"] = thickness

    cut = None
    if process == "sheet_metal" and env["length"] and env["width"]:
        t_in = thickness or 0.06
        flange = max((env["height"] or t_in) - t_in, 0) if bends else 0
        flat_w = env["width"] + flange * min(bends or 0, 2)
        d_holes = hole_diams + [0.25] * (plain - len(hole_diams)) + [0.2] * tapped
        cut = round(2 * (env["length"] + flat_w) + sum(3.1416 * d for d in d_holes), 2)

    # ------------------------------------------------ notes
    if read.get("heat_treat"):
        features.append("Heat treat or stress relief noted")
    if (read.get("welding") or {}).get("required"):
        features.append("Welding: " + (", ".join(read["welding"]["specs"]) or "weld notes found"))
    if read.get("surface_finish", {}).get("ra_microin"):
        features.append(f"Surface finish {read['surface_finish']['ra_microin']} Ra")
    if metric:
        features.append("Metric drawing: millimeters converted to inches")

    found = sum(1 for v in env.values() if v)
    if source == "explicit" and found == 3:
        confidence = "high" if (process != "cnc_mill" or plain or tapped) else "medium"
    elif source == "explicit" or found >= 2:
        confidence = "medium" if source == "explicit" else "low"
    else:
        confidence = "low"
    if not t.strip():
        confidence = "none"

    return {
        "process_guess": process,
        "envelope_in": env,
        "envelope_source": source,
        "confidence": confidence,
        "holes": plain,
        "tapped_holes": tapped,
        "thru_holes": thru,
        "hole_diameters": hole_diams,
        "bends": bends,
        "turned": turned,
        "sheet_thickness": thickness,
        "cut_length_estimate": cut,
        "print_material": print_mat,
        "dimension_values": dims[:12],
        "metric_drawing": metric,
        "features": features,
        "evidence": evidence[:40],
        "ai_used": False,
    }


def _clean_line(text: str, m: re.Match) -> str:
    s = text.rfind("\n", 0, m.start()) + 1
    e = text.find("\n", m.end())
    return re.sub(r"\s+", " ", text[s: e if e != -1 else len(text)]).strip()[:160]


# ---------------------------------------------------------------- optional Claude pass
AI_PROMPT = """This PDF is an engineering drawing of one part. Read it for a machine shop quote and return only JSON:
{"process_guess": "cnc_mill | cnc_lathe | sheet_metal | 3d_print",
 "envelope_in": {"length": number or null, "width": number or null, "height": number or null},
 "holes": plain untapped hole count, "tapped_holes": tapped hole count, "thru_holes": holes marked THRU,
 "bends": number or null, "sheet_thickness": inches or null,
 "turned": {"max_diameter": inches, "length": inches} or null,
 "evidence": ["the callouts or dimensions you used, as written"]}
Envelope is the overall finished size in inches (convert millimeters), largest first.
Count holes from callouts such as 4X. Use null for anything not on the drawing. Do not guess."""


def _claude_extract(data: bytes) -> dict:
    """Send the PDF to Claude for the geometry fields. Tests replace this function."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}},
            {"type": "text", "text": AI_PROMPT},
        ]}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise drawing.DrawingError("Claude did not return JSON for the drawing.")
    return json.loads(m.group(0))


def _num_or_none(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def merge_ai(geom: dict, ai: dict) -> dict:
    """Claude's values replace the text guesses where it gave one."""
    g = json.loads(json.dumps(geom))
    if ai.get("process_guess") in PROCESSES:
        g["process_guess"] = ai["process_guess"]
    env = ai.get("envelope_in") or {}
    for key in ("length", "width", "height"):
        v = _num_or_none(env.get(key))
        if v:
            g["envelope_in"][key] = round(v, 4)
    if any(_num_or_none(env.get(x)) for x in ("length", "width", "height")):
        g["envelope_source"] = "claude"
    for key in ("holes", "tapped_holes", "thru_holes", "bends"):
        if isinstance(ai.get(key), (int, float)) and not isinstance(ai.get(key), bool) and ai[key] >= 0:
            g[key] = int(ai[key])
    if _num_or_none(ai.get("sheet_thickness")):
        g["sheet_thickness"] = round(float(ai["sheet_thickness"]), 4)
    tr = ai.get("turned")
    if isinstance(tr, dict) and _num_or_none(tr.get("max_diameter")):
        g["turned"] = {"max_diameter": round(float(tr["max_diameter"]), 4), "length": _num_or_none(tr.get("length"))}
    g["evidence"] = [f"Claude: {e}" for e in (ai.get("evidence") or [])][:20] + g["evidence"]
    g["ai_used"] = True
    if g["confidence"] in ("none", "low"):
        g["confidence"] = "medium" if all(g["envelope_in"].values()) else "low"
    return g


def ai_allowed(read: dict) -> str | None:
    """Reason the drawing must not go to an outside service, or None."""
    if read.get("export_controlled"):
        return "The drawing is marked export-controlled (ITAR/EAR). It cannot be sent to Claude."
    letter = (read.get("distribution") or {}).get("letter") or ""
    if letter and letter != "A":
        return f"The drawing carries distribution statement {letter} (limited distribution). It cannot be sent to Claude."
    return None


# ---------------------------------------------------------------- spec
OVERRIDE_KEYS = ("process", "length", "width", "height", "holes", "tapped_holes", "thru_holes", "bends", "thickness", "max_diameter",
                 "material", "finishes", "tolerance", "quantities", "name", "part_number", "nsn", "first_article", "material_certs",
                 "packaging", "cut_length", "setups", "weld_length_in", "inserts", "infill", "technology", "support",
                 "reference_unit_price", "freight_per_lot", "approved_source_required", "cut_process", "fill_ratio",
                 "confirmed")  # confirmed: the user checked every value against the drawing (see review())


def _f(v, default=None):
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        raise pricing.SpecError(f"{v!r} is not a number")


def effective_inputs(read: dict, geom: dict, overrides: dict | None = None, config: dict | None = None) -> tuple[dict, list[str]]:
    """The values the quote uses: the drawing's, replaced by any override. Missing sizes get a
    stated assumption so a price can still be shown."""
    o = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
    if isinstance(o.get("envelope_in"), dict):
        for key, v in o.pop("envelope_in").items():
            if v not in (None, ""):
                o.setdefault(key, v)
    cfg = pricing.merged_config(config)
    notes: list[str] = []
    qo = drawing.quote_options(read, list(cfg["materials"]) + list(cfg["additive"]["materials"]),
                               list(cfg["finishes"]) + list(cfg["additive"]["finishes"]))
    process = o.get("process") or geom.get("process_guess") or "cnc_mill"
    if process == "auto":
        process = geom.get("process_guess") or "cnc_mill"
    if process not in PROCESSES:
        raise pricing.SpecError(f"process must be one of {list(PROCESSES)}")
    env = dict(geom.get("envelope_in") or {})
    src = geom.get("envelope_source") or "none"
    for key in ("length", "width", "height"):
        if key in o:
            env[key] = _f(o[key])
    turned = geom.get("turned") or {}
    max_d = _f(o.get("max_diameter")) or turned.get("max_diameter")
    thickness = _f(o.get("thickness")) or geom.get("sheet_thickness")

    edited = any(k in o for k in ("length", "width", "height"))
    if not edited and src == "dimension text":
        notes.append("Envelope taken from the largest dimension values on the drawing (low confidence). Check length, width and height.")
    elif not edited and src == "claude":
        notes.append("Envelope read by Claude from the drawing. Check it.")
    if process == "cnc_lathe":
        if not max_d:
            max_d = env.get("width") or 1.0
            notes.append(f"No turned diameter found: assumed Ø{max_d} in.")
        if not env.get("length"):
            env["length"] = round(max_d * 3, 3)
            notes.append(f"No overall length found: assumed {env['length']} in (3 x diameter). Enter the real length.")
        env["width"] = env["height"] = max_d
    else:
        if not env.get("length"):
            env["length"] = 2.0
            notes.append("No overall size found on the drawing: assumed 2.0 in long. Enter the real envelope.")
        if not env.get("width"):
            env["width"] = round(env["length"] * 0.6, 3)
            notes.append(f"Width not found: assumed {env['width']} in. Enter the real width.")
        if not env.get("height"):
            if process == "sheet_metal":
                env["height"] = thickness or 0.06
            else:
                env["height"] = round(min(env["width"], max(0.25, env["width"] * 0.25)), 3)
                notes.append(f"Height not found: assumed {env['height']} in. Enter the real thickness of the part.")
    if process == "sheet_metal" and not thickness:
        thickness = 0.06
        notes.append("Sheet thickness not found: assumed 0.060 in.")

    material = o.get("material") or qo.get("material") or ""
    if process == "3d_print":
        if material not in cfg["additive"]["materials"]:
            guess = geom.get("print_material")
            new = guess if guess in cfg["additive"]["materials"] else "PETG"
            if material:
                notes.append(f"'{material}' is not a 3D print material: priced in {new}.")
            else:
                notes.append(f"No print material on the drawing: priced in {new}.")
            material = new
    elif not material:
        material = "6061-T6 aluminum"
        raw = (read.get("material") or {}).get("raw")
        notes.append(f"Material {'callout ' + repr(raw) + ' not in your rates' if raw else 'not found'}: priced as 6061-T6 aluminum.")
    elif material not in cfg["materials"]:
        raise pricing.SpecError(f"Unknown material '{material}'. Known: {sorted(cfg['materials'])}")

    finishes = o.get("finishes") if "finishes" in o else qo.get("finishes", [])
    finishes = list(finishes or [])
    if process == "3d_print":
        dropped = [f for f in finishes if f not in cfg["additive"]["finishes"]]
        if dropped:
            notes.append(f"Metal finish(es) {', '.join(dropped)} dropped for a printed part.")
        finishes = [f for f in finishes if f in cfg["additive"]["finishes"]]
    else:
        finishes = [f for f in finishes if f in cfg["finishes"] or f in cfg["additive"]["finishes"]]

    def count(key, default):
        v = o.get(key, default)
        try:
            return max(0, int(float(v or 0)))
        except (TypeError, ValueError):
            raise pricing.SpecError(f"{key} must be a whole number")

    bends = count("bends", geom.get("bends") or 0)
    inp = {
        "process": process,
        "length": round(float(env["length"]), 4), "width": round(float(env["width"]), 4), "height": round(float(env["height"]), 4),
        "holes": count("holes", geom.get("holes")), "tapped_holes": count("tapped_holes", geom.get("tapped_holes")),
        "thru_holes": count("thru_holes", geom.get("thru_holes")), "bends": bends,
        "thickness": thickness, "max_diameter": max_d if process == "cnc_lathe" else None,
        "material": material, "finishes": finishes,
        "tolerance": o.get("tolerance") or qo.get("tolerance") or "standard",
        "quantities": o.get("quantities") or [1],
        "name": o.get("name") or qo.get("name") or "", "part_number": o.get("part_number") or qo.get("part_number") or "",
        "nsn": o.get("nsn") or "", "first_article": bool(o.get("first_article", qo.get("first_article", False))),
        "material_certs": bool(o.get("material_certs", qo.get("material_certs", False))),
        "packaging": o.get("packaging") or "commercial",
        "inserts": count("inserts", qo.get("inserts", 0)),
        "weld_length_in": _f(o.get("weld_length_in"), 0.0),
        "cut_length": _f(o.get("cut_length")),
        "setups": count("setups", 0) or None,
        "fill_ratio": min(max(_f(o.get("fill_ratio"), 0.6), 0.05), 1.0),
    }
    for key in ("infill", "technology", "support", "reference_unit_price", "freight_per_lot", "approved_source_required", "cut_process"):
        if key in o:
            inp[key] = o[key]
    if "tolerance" not in o and not qo.get("tolerance"):
        notes.append("No tolerance block found: priced at standard tolerance.")
    return inp, notes


def build_spec(read: dict, geom: dict, overrides: dict | None = None, config: dict | None = None) -> tuple[dict, list[str]]:
    """Pricing spec (the shape pricing.estimate takes) from the drawing read, the extracted
    geometry and the user's corrections. Returns (spec, assumptions)."""
    inp, notes = effective_inputs(read, geom, overrides, config)
    p = inp["process"]
    L, W, H = inp["length"], inp["width"], inp["height"]
    holes, tapped = inp["holes"], inp["tapped_holes"]
    spec: dict = {
        "name": inp["name"] or read.get("title") or read.get("part_number") or "Part from drawing",
        "part_number": inp["part_number"], "nsn": inp["nsn"], "quantities": inp["quantities"], "material": inp["material"],
        "tolerance": inp["tolerance"], "finishes": [{"type": f} for f in inp["finishes"]],
        "inspection": {"first_article": inp["first_article"]}, "packaging": {"level": inp["packaging"]},
        "material_certs_required": inp["material_certs"],
        "approved_source_required": bool(inp.get("approved_source_required", False)),
        "operations": [], "process": p,
        "drawing": {"drawing_id": read.get("drawing_id") or "", "filename": read.get("filename") or "",
                    "revision": read.get("revision") or "", "source": "drawing only, no model"},
    }
    if read.get("revision"):
        spec["revision"] = read["revision"]
    for key in ("reference_unit_price", "freight_per_lot"):
        if inp.get(key) not in (None, ""):
            spec[key] = float(inp[key])

    if p == "3d_print":
        vol = round(L * W * H * inp["fill_ratio"], 4)
        op = {"type": "additive", "part_volume_in3": vol, "bbox_in": [L, W, H], "support": inp.get("support", True) is not False}
        for key in ("technology", "infill"):
            if inp.get(key) not in (None, ""):
                op[key] = inp[key] if key == "technology" else float(inp[key])
        spec["operations"].append(op)
        notes.append(f"Part volume assumed at {inp['fill_ratio']:.0%} of the {L} x {W} x {H} in envelope ({vol} in³).")
        if tapped:
            spec["operations"].append({"type": "hardware_insert", "count": tapped, "unit_cost": 0.25, "minutes_each": 0.75})
            notes.append(f"{tapped} tapped hole(s) priced as heat-set inserts.")
    elif p == "sheet_metal":
        t = float(inp["thickness"])
        flange = max(H - t, 0) if inp["bends"] else 0
        flat_l, flat_w = L, W + flange * min(inp["bends"], 2)
        spec["stock"] = {"shape": "sheet", "dims": {"length": round(flat_l + 0.25, 3), "width": round(flat_w + 0.25, 3), "thickness": t}}
        cut = inp["cut_length"]
        if not cut:
            d_holes = (geom.get("hole_diameters") or [])[:holes]
            d_holes += [0.25] * (holes - len(d_holes)) + [0.2] * tapped
            cut = round(2 * (flat_l + flat_w) + sum(3.1416 * d for d in d_holes), 2)
        cutter = inp.get("cut_process") or ("waterjet" if t > 0.5 else "laser_cut")
        spec["operations"].append({"type": cutter, "cut_length_in": cut, "pierces": holes + tapped + 1})
        if inp["bends"]:
            spec["operations"].append({"type": "press_brake", "bends": inp["bends"]})
        if tapped:
            spec["operations"].append({"type": "fabrication", "minutes_per_part": round(tapped * 0.75, 2)})
            notes.append(f"{tapped} tapped hole(s) at 0.75 min each.")
        notes.append(f"Flat blank estimated at {flat_l} x {round(flat_w, 3)} in from the envelope"
                     + (f" plus {min(inp['bends'], 2)} flange(s)" if flange else "") + f"; cut length about {cut} in.")
        if inp["bends"] == 0 and not geom.get("bends"):
            notes.append("No bends found on the drawing: priced as a flat cut part.")
    elif p == "cnc_lathe":
        D = float(inp["max_diameter"])
        spec["stock"] = {"shape": "bar_round", "dims": {"diameter": round(D + STOCK_ALLOWANCE_IN, 3), "length": round(L + 2 * STOCK_ALLOWANCE_IN, 3)}}
        th = read.get("threads") or {}
        diam_count = max(1, len({round(float(x), 3) for x in (geom.get("turned") or {}).get("diameters", [])}) or 2)
        spec["operations"].append({"type": "cnc_lathe", "setups": int(inp["setups"] or 2),
                                   "features": {"diameters": diam_count, "threads": int(th.get("count") or tapped),
                                                "grooves": 0, "cross_holes": holes}})
        notes.append(f"Turned from Ø{D} in bar, {diam_count} diameters assumed; {holes} plain hole(s) priced as cross holes.")
    else:
        sl, sw, st = (round(x + STOCK_ALLOWANCE_IN, 3) for x in sorted((L, W, H), reverse=True))
        removed = max(sl * sw * st - L * W * H * inp["fill_ratio"], 0)
        spec["stock"] = {"shape": "plate", "dims": {"length": sl, "width": sw, "thickness": st}}
        spec["operations"].append({"type": "cnc_mill", "setups": int(inp["setups"] or 2),
                                   "features": {"holes": holes, "tapped_holes": tapped, "volume_removed_in3": round(removed, 3),
                                                "faces": 6 + holes + tapped}})
        notes.append(f"Milled from {sl} x {sw} x {st} in plate; part assumed to fill {inp['fill_ratio']:.0%} of its envelope "
                     f"({round(removed, 2)} in³ removed). 2 setups unless set.")
    if inp["inserts"] and p != "3d_print":
        spec["operations"].append({"type": "hardware_insert", "count": inp["inserts"], "unit_cost": 0.40, "minutes_each": 0.5})
        notes.append(f"{inp['inserts']} thread insert(s) from the drawing priced at $0.40 each.")
    if inp["weld_length_in"] > 0:
        spec["operations"].append({"type": "weld", "process": "mig", "weld_length_in": inp["weld_length_in"], "joints": 1, "fixture": True})
    elif (read.get("welding") or {}).get("required"):
        notes.append("The drawing calls for welding but no weld length was entered: welding is not in this price.")
    if read.get("heat_treat") and p != "3d_print":
        notes.append("Heat treat or stress relief is noted on the drawing and is not in this price.")
    if holes or tapped:
        notes.append(f"Holes from the callouts: {holes} plain, {tapped} tapped ({inp['thru_holes']} marked THRU).")
    notes.insert(0, "Priced from the drawing only (no 3D model). Check the envelope and feature counts against the drawing.")
    spec["drawing"]["notes"] = notes
    return spec, notes


def quote(read: dict, geom: dict, overrides: dict | None = None, config: dict | None = None, assembly: bool = False) -> dict:
    """Build the spec and price it. Returns {geometry, inputs, spec, estimate, assumptions, confidence}."""
    spec, notes = build_spec(read, geom, overrides, config)
    est = pricing.estimate(spec, config)
    est["assumptions"] = notes + est["assumptions"]
    inp, _ = effective_inputs(read, geom, overrides, config)
    sanity = sanity_warnings(inp, est)
    est["warnings"] = sanity + est["warnings"]
    rv = review(read, geom, overrides, sanity, assembly)
    spec["review"] = rv  # saved with the quote: a customer quote is refused while the read is unconfirmed
    return {"geometry": geom, "inputs": inp, "spec": spec, "estimate": est, "assumptions": est["assumptions"],
            "confidence": geom.get("confidence", "low"), "review": rv}


def review(read: dict, geom: dict, overrides: dict | None, sanity: list[str], assembly: bool = False) -> dict:
    """Is the drawing understood well enough to price without a person checking it?

    Not confident when: the drawing is an assembly; it has no text; the size is a low-confidence guess
    and was not entered by hand; no material was found and none was chosen; or the size or material cost
    is not believable. Any of those means a manual quote for this part (or the user checking every value
    and saying so with confirmed=true). Returns {confident, confirmed, reasons, manual_required}."""
    o = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
    reasons: list[str] = []
    if assembly:
        reasons.append("It is an assembly drawing, not one part.")
    if geom.get("confidence") == "none":
        reasons.append("The drawing has no readable text (scanned), so nothing was measured.")
    size_given = all(k in o for k in ("length", "width")) and any(k in o for k in ("height", "thickness", "max_diameter"))
    if geom.get("confidence") == "low" and not size_given:
        reasons.append("The overall size is a guess from the largest dimensions on the sheet.")
    mat = (read.get("material") or {}).get("mapped")
    if not mat and not o.get("material"):
        reasons.append("No material was found on the drawing.")
    if sanity:
        reasons.append("The size or material cost is not believable for one part.")
    confirmed = bool(o.get("confirmed")) and not assembly
    confident = not reasons or confirmed
    return {"confident": confident, "confirmed": confirmed, "reasons": reasons, "manual_required": not confident}


def sanity_warnings(inp: dict, est: dict) -> list[str]:
    """Catch a misread before it becomes a quote: sizes or material costs no drawing-only part should have."""
    out = []
    dims = {k: inp.get(k) for k in ("length", "width", "height", "thickness", "max_diameter") if isinstance(inp.get(k), (int, float))}
    big = {k: v for k, v in dims.items() if v > (6 if k == "thickness" else 120)}
    if big:
        out.append("CHECK THE SIZE: " + ", ".join(f"{k} {v:g} in" for k, v in big.items()) + " is not believable for one part. "
                   "Correct it below before using this price.")
    mat = sum(l["cost"] for l in est.get("per_part_lines") or [] if l.get("category") == "material")
    if mat > 2000:
        out.append(f"CHECK THE SIZE AND MATERIAL: raw material alone is ${mat:,.0f} per part. That usually means a dimension or thickness was misread.")
    return out
