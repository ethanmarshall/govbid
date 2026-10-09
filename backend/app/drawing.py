"""Read an engineering drawing (PDF) and pull out what a part quote needs.

Most DLA technical data packages ship drawings as PDFs. When the PDF has a text layer
(exported from CAD), pypdf extracts the text and regexes find the title block fields,
material and finish callouts, tolerances, threads, specs, distribution statement and
export-control markings. Scanned drawings have no text layer: the reader says so, and
with ANTHROPIC_API_KEY set and use_ai=True it can send the PDF to Claude to transcribe.

Everything here is a best-effort read. Check the drawing before you quote.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from .analysis import cited_standards
from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

# ---------------------------------------------------------------- material callouts
# (pattern, app material name). Checked in order; first match wins. "Strong" patterns are
# safe to search anywhere in the drawing text; "weak" ones (bare alloy numbers) only on the
# MATERIAL line of the title block or notes.
MATERIAL_STRONG: list[tuple[str, str]] = [
    (r"QQ-A-250/12|AMS\s*-?\s*4078|\b7075\s*-?\s*T\d+|\bAL(?:UM(?:INUM)?)?\.?\s*7075|ASTM\s*B\s*-?\s*209\D{0,30}7075|ASTM\s*B\s*-?\s*211\D{0,30}7075|ASTM\s*B\s*-?\s*221\D{0,30}7075", "7075-T6 aluminum"),
    (r"QQ-A-250/11|AMS\s*-?\s*4027|\b6061\s*-?\s*T\d+|\bAL(?:UM(?:INUM)?)?\.?\s*6061|ASTM\s*B\s*-?\s*(?:209|211|221|308)\D{0,30}6061", "6061-T6 aluminum"),
    (r"QQ-A-250/8|\b5052\s*-?\s*H\d+|\bAL(?:UM(?:INUM)?)?\.?\s*5052|ASTM\s*B\s*-?\s*209\D{0,30}5052", "5052-H32 aluminum"),
    (r"\b7075\s*(?:-?\s*T\d+)?\s*AL(?:UM(?:INUM)?)?\b", "7075-T6 aluminum"),
    (r"\b6061\s*(?:-?\s*T\d+)?\s*AL(?:UM(?:INUM)?)?\b", "6061-T6 aluminum"),
    (r"\b5052\s*(?:-?\s*H\d+)?\s*AL(?:UM(?:INUM)?)?\b", "5052-H32 aluminum"),
    (r"\b316L?\s*(?:CRES|SS|STAINLESS)|CRES\s*316|AISI\s*316|UNS\s*S3160\d|ASTM\s*A\s*-?\s*(?:240|276|479)\D{0,30}316", "316 stainless"),
    (r"\b304L?\s*(?:CRES|SS|STAINLESS)|CRES\s*304|AISI\s*304|UNS\s*S3040\d|ASTM\s*A\s*-?\s*(?:240|276|479)\D{0,30}304", "304 stainless"),
    (r"\b4140\s*(?:STEEL|ALLOY|HT|Q&T|ANNEALED)|AISI\s*4140|SAE\s*4140|UNS\s*G41400", "4140 steel"),
    # Mild / low-carbon sheet and plate (A1008 cold rolled, A1011 hot rolled, 1008-1020, CRS, HRS): priced as the app's mild steel
    (r"\bA\s*-?\s*10(?:08|11|18)\b|\b10(?:08|10|20)\s*(?:STEEL|CRS|HRS|CR\b|HR\b)|MILD\s*(?:CARBON\s*)?STEEL|LOW\s*CARBON\s*STEEL|COLD\s*ROLLED\s*STEEL|HOT\s*ROLLED\s*STEEL|\bCRS\b|\bHRS\b|\bHRPO\b", "A36 / 1018 steel"),
    (r"ASTM\s*A\s*-?\s*36\b|\b1018\s*(?:STEEL|CRS|HRS|CF)|AISI\s*1018|SAE\s*1018|UNS\s*G10180|ASTM\s*A\s*-?\s*108\D{0,30}1018", "A36 / 1018 steel"),
    (r"\bC\s*36000\b|\b360\s*BRASS|BRASS\s*,?\s*(?:ALLOY\s*)?360|FREE[- ]CUTTING\s*BRASS|ASTM\s*B\s*-?\s*16\b", "brass 360"),
    (r"\bC\s*11000\b|COPPER\s*,?\s*(?:ALLOY\s*)?110\b|\bCU\s*110\b|\bETP\s*COPPER", "copper 110"),
    (r"DELRIN|\bACETAL\b|POLYOXYMETHYLENE|\bPOM\b", "delrin (acetal)"),
    (r"\bG\s*-?\s*10\b|\bFR\s*-?\s*4\b|NEMA\s*(?:GRADE\s*)?(?:G-?10|FR-?4)", "G10 / FR4"),
]
MATERIAL_WEAK: list[tuple[str, str]] = [
    (r"\b7075\b", "7075-T6 aluminum"),
    (r"\b6061\b", "6061-T6 aluminum"),
    (r"\b5052\b", "5052-H32 aluminum"),
    (r"\b316L?\b", "316 stainless"),
    (r"\b304L?\b", "304 stainless"),
    (r"\b4140\b", "4140 steel"),
    (r"\b1018\b|\bA36\b", "A36 / 1018 steel"),
    (r"\bBRASS\b", "brass 360"),
    (r"\bCOPPER\b", "copper 110"),
]

# ---------------------------------------------------------------- finish callouts
FINISH_RULES: list[tuple[str, str | None]] = [  # the first four are one family: a line matched by one skips the rest
    # Anodize: the type decides the finish. Type I (chromic) has no matching app finish.
    (r"(?:MIL-PRF-8625|MIL-A-8625)\W{0,6}(?:\w+\W+){0,4}?TYPE\s*(?:III|3)\b|HARD\s*(?:COAT\s*)?ANODI[SZ]E|HARDCOAT", "hard anodize (Type III)"),
    (r"(?:MIL-PRF-8625|MIL-A-8625)\W{0,6}(?:\w+\W+){0,4}?TYPE\s*(?:II|2)\b", "anodize (Type II)"),
    (r"(?:MIL-PRF-8625|MIL-A-8625)\W{0,6}(?:\w+\W+){0,4}?TYPE\s*(?:I|1)(?:B|C)?\b", None),
    (r"MIL-PRF-8625|MIL-A-8625|\bANODI[SZ]E", "anodize (Type II)"),
    (r"MIL-DTL-5541|MIL-C-5541|CHEM(?:ICAL)?\s*FILM|ALODINE|IRIDITE|CHROMATE\s*CONVERSION", "chem film (MIL-DTL-5541)"),
    (r"AMS\s*-?\s*2700|AMS-QQ-P-35|QQ-P-35|ASTM\s*A\s*-?\s*967|PASSIVAT", "passivate (stainless)"),
    (r"ASTM\s*B\s*-?\s*633|QQ-Z-325|ZINC\s*PLAT|ZINC\s*ELECTROPLAT|\bZN\s*PLATE", "zinc plate"),
    (r"MIL-DTL-13924|MIL-C-13924|BLACK\s*OXIDE", "black oxide"),
    (r"POWDER\s*COAT", "powder coat"),
    (r"MIL-PRF-85285|MIL-DTL-53039|MIL-DTL-64159|MIL-PRF-23377|\bCARC\b|\bPAINT(?:ED)?\b|\bPRIME(?:R|D)?\s*(?:AND|&)\s*PAINT", "paint (wet)"),
]
NEGATED_FINISH = re.compile(r"\b(?:DO\s*NOT|NO|DON'T|WITHOUT)\s+(?:\w+\s+){0,2}$", re.I)

# ---------------------------------------------------------------- other patterns
THREAD_INCH = re.compile(
    r"(?<![\w.])(#\s?\d{1,2}|\d{1,2}/\d{1,2}|\d(?:\s\d{1,2}/\d{1,2})?|\d?\.\d{2,4})\s*-\s*(\d{1,3})\s*(UNC|UNF|UNEF|UNJC|UNJF|UNJ|UNS|UN|NPT|NPTF)(?:\s*-?\s*(\d[AB]))?",
    re.I,
)
THREAD_METRIC = re.compile(r"(?<![\w.])M\s?(\d{1,2}(?:\.\d)?)\s*[xX×]\s*(\d(?:\.\d{1,2})?)(?:\s*-\s*(\d[gGhH](?:\s?\d[gGhH])?))?")
HELICOIL = re.compile(r"HELI-?COIL|MS\s*-?\s*21209|NAS\s*-?\s*1130|NA\s*-?\s*0276|SCREW\s*THREAD\s*INSERT|THREAD\s*INSERT|KEENSERT|MS\s*-?\s*51830", re.I)
COUNT_BEFORE = re.compile(r"(?:\(\s*(\d{1,3})\s*\)|\b(\d{1,3})\s*[Xx×])\s*$")
COUNT_AFTER = re.compile(r"^[^\n]{0,60}?\b(\d{1,3})\s*(?:PL(?:ACE)?S?|PLCS|HOLES)\b", re.I)

PART_NUMBER = re.compile(r"\b(?:PART\s*(?:NO|NUMBER|NUM)\.?|P\s*/\s*N|PN)\s*[:#.]?\s*([A-Z0-9][A-Z0-9\-./]{2,30})", re.I)
DRAWING_NUMBER = re.compile(r"\b(?:DWG|DRAWING)\s*(?:NO|NUMBER|NUM)?\.?\s*[:#.]?\s*([A-Z0-9][A-Z0-9\-./]{2,30})", re.I)
CAGE = re.compile(r"\bCAGE\s*(?:CODE|NO\.?)?\s*[:#]?\s*([0-9A-HJ-NP-Z]{5})\b", re.I)
REVISION = re.compile(r"\bREV(?:ISION)?\.?\s*(?:LEVEL)?\s*[:#]?\s*([A-HJ-NPR-Y]{1,2}|\d{1,3})\b(?!\s*(?:DESCRIPTION|DATE|APPROVED|ZONE))")
TITLE = re.compile(r"^[ \t]*(?:TITLE|NOMENCLATURE|DESCRIPTION)[ \t]*[:.]?[ \t]*(\S.{2,79})$", re.I | re.M)
TITLE_BLOCK_WORDS = {"SCALE", "SHEET", "SHEETCAGE", "CAGE", "CODE", "SIZE", "DWG", "NO", "NO.", "REV", "DATE", "DRAWN", "APPROVED", "CHECKED",
                     "TITLE", "OF", "WEIGHT", "FSCM", "CONTRACT", "ENG", "QA", "MFG", "APPROVALS", "DO", "NOT", "SCALE.", "DRAWING", "BY"}
MATERIAL_LINE = re.compile(r"\bMAT(?:ERIA)?L\.?\s*[:\-,]\s*(.{3,160})|\bMATERIAL\s+(?!CERT|TRACE|SHALL|TO\b|IS\b|AND\b)(.{3,160})", re.I)
DISTRIBUTION = re.compile(r"DISTRIBUTION\s+STATEMENT\s+([A-F])\b[\s.:\-]*([^\n]{0,300})", re.I)
EXPORT_PATTERNS = [
    r"WARNING\s*[-:]?\s*THIS\s+DOCUMENT\s+CONTAINS\s+TECHNICAL\s+DATA\s+WHOSE\s+EXPORT\s+IS\s+RESTRICTED",
    r"\bITAR\b",
    r"INTERNATIONAL\s+TRAFFIC\s+IN\s+ARMS",
    r"EXPORT\s+ADMINISTRATION\s+(?:ACT|REGULATIONS)",
    r"ARMS\s+EXPORT\s+CONTROL\s+ACT",
    r"EXPORT[- ]CONTROLLED",
]
TOL_VALUE = re.compile(r"(?:±|\+/-|\+\s*/\s*-|\+-|±)\s*(0?\.\d{1,5}|\d\.\d{1,5})(?![ \t]*(?:°|DEG)|\d)", re.I)
SURFACE = re.compile(r"\b(\d{1,3})\s*(?:µ\s*IN\.?|MICRO\s*-?\s*INCH(?:ES)?)?\s*(?:Ra|RA|AA|RMS)\b|(?:\bRa\b|\bRA\b|SURFACE\s+(?:FINISH|ROUGHNESS)|SURFACE\s+TEXTURE)\s*[:=]?\s*(?:[A-Za-z]+\s+){0,2}?(\d{1,3})\b")
HEAT_TREAT = re.compile(r"HEAT\s*TREAT|\bHARDEN|\bHRC\s*\d|\bRC\s*\d{2}|ROCKWELL|AMS\s*-?\s*27(?:59|70|71)|STRESS\s*RELIEV|CASE\s*HARDEN|CARBURIZ|NORMALIZ|AGE\s*HARDEN|SOLUTION\s*HEAT", re.I)
FIRST_ARTICLE = re.compile(r"FIRST\s*ARTICLE|\bFAT\b|\bFAI\b|\bAS\s*9102", re.I)
CERTS = re.compile(r"MATERIAL\s*CERT|MILL\s*CERT|CERTIFIED\s*(?:MILL\s*)?TEST\s*REPORT|\bCMTR\b|TRACEAB|CHEMICAL\s*AND\s*PHYSICAL\s*(?:TEST|PROPERT|CERT|REPORT)|CERTS?\s*(?:OF|FOR)\s*MATERIAL", re.I)
WELD_SPECS = re.compile(r"AWS\s*-?\s*D\s*1\.\d|AWS\s*-?\s*D\s*17\.\d|AWS\s*-?\s*D\s*14\.\d|AWS\s*-?\s*A\s*2\.4|MIL-STD-1595|MIL-STD-2219|MIL-STD-248|MIL-STD-1689|MIL-W-\d{4,5}|NAVSEA\s*(?:TECH\s*PUB\s*)?(?:S9074-AR-GIB-010/)?278|AMS\s*-?\s*STD\s*-?\s*2219", re.I)
EXTRA_SPECS = re.compile(r"\bASTM\s*[A-G]\s*-?\s*\d{1,4}\b|\bAMS\s*-?\s*\d{4}[A-Z]?\b|\bAMS-(?:QQ|STD|H)-[A-Z]?-?\d+(?:/\d+)?|\bQQ-[A-Z]-\d{2,4}(?:/\d+)?|\bAWS\s*[A-D]\d+\.\d+|\bNAS\s*-?\s*\d{3,5}\b|\bMS\s*-?\s*\d{5}(?!\d)|\bSAE\s*(?:AS|AMS|J)\s*-?\s*\d{3,5}\b|\bMIL-[A-Z]-\d{3,6}(?:/\d+)?", re.I)
NOTE_LINE = re.compile(r"^\s*(\d{1,2})[.)]\s+(.{4,})$", re.M)
METRIC_UNITS = re.compile(r"DIMENSIONS\s+(?:ARE\s+)?IN\s+(?:MILLIMETERS|MM)|ALL\s+DIMENSIONS\s+IN\s+MM|UNLESS\s+OTHERWISE\s+SPECIFIED\s+DIMENSIONS\s+ARE\s+IN\s+MILLIMETERS", re.I)

DISTRIBUTION_MEANING = {
    "A": "Approved for public release.",
    "B": "U.S. Government agencies only.",
    "C": "U.S. Government agencies and their contractors only.",
    "D": "DoD and U.S. DoD contractors only.",
    "E": "DoD components only.",
    "F": "Further dissemination only as directed by the controlling office.",
}


# Bump when the reading rules change, so drawings uploaded earlier are read again instead of reusing a stale cached read.
PARSER_VERSION = 2


class DrawingError(ValueError):
    pass


# ---------------------------------------------------------------- text
def extract_pdf_text(path: Path) -> tuple[str, int]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        parts = []
        for p in reader.pages:
            try:
                parts.append(p.extract_text() or "")
            except Exception:  # one bad page should not sink the read
                parts.append("")
        return "\n".join(parts), pages
    except Exception as exc:
        raise DrawingError(f"Could not read the PDF: {exc}") from exc


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip(" .:;,-")


def map_material(raw: str, strict: bool = False) -> str | None:
    """Map a material callout to the app's material name, or None."""
    if not raw:
        return None
    for pat, name in MATERIAL_STRONG:
        if re.search(pat, raw, re.I):
            return name
    if not strict:
        for pat, name in MATERIAL_WEAK:
            if re.search(pat, raw, re.I):
                return name
    return None


def _find_material(text: str) -> dict:
    for m in MATERIAL_LINE.finditer(text):
        raw = _clean(m.group(1) or m.group(2))
        mapped = map_material(raw)
        if mapped or re.search(r"\d|STEEL|ALUM|BRASS|COPPER|PLASTIC|NYLON|CRES", raw, re.I):
            return {"raw": raw, "mapped": mapped}
    # No MATERIAL line: look for an unambiguous callout anywhere
    for pat, name in MATERIAL_STRONG:
        m = re.search(pat, text, re.I)
        if m:
            line = next((ln for ln in text.splitlines() if m.group(0) in ln), m.group(0))
            return {"raw": _clean(line)[:160], "mapped": name}
    return {"raw": "", "mapped": None}


def _find_finishes(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set = set()
    claimed: list[tuple[int, int]] = []  # anodize lines already matched by a more specific rule
    for i, (pat, name) in enumerate(FINISH_RULES):
        anodize = i < 4
        for m in re.finditer(pat, text, re.I):
            if anodize and any(a <= m.start() < b for a, b in claimed):
                continue
            before = text[max(0, m.start() - 25): m.start()]
            if NEGATED_FINISH.search(before):
                continue
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            raw = _clean(text[line_start: line_end if line_end != -1 else len(text)])[:160]
            if anodize:
                claimed.append((line_start, line_end if line_end != -1 else len(text)))
            key = name or raw
            if key in seen:
                continue
            seen.add(key)
            out.append({"raw": raw, "mapped": name})
    return out


def tolerance_class(tightest: float | None) -> str | None:
    """Tightest decimal tolerance in inches -> standard / tight / precision."""
    if tightest is None:
        return None
    if tightest >= 0.005:
        return "standard"
    if tightest >= 0.002:
        return "tight"
    return "precision"


def _find_tolerance(text: str) -> dict:
    metric = bool(METRIC_UNITS.search(text))
    found: dict[str, float] = {}  # as written -> inches
    # Title-block style ".XX ±.01  .XXX ±.005" sometimes extracts without the sign
    for m in re.finditer(r"\.X{2,4}\s*[=:]?\s*(?:±|\+/-|\+-)?\s*(\.\d{1,5})", text):
        found.setdefault(m.group(1), float(m.group(1)))
    for m in TOL_VALUE.finditer(text):
        found.setdefault(m.group(1), float(m.group(1)))
    vals: list[float] = []
    raws: list[str] = []
    for raw, v in found.items():
        if metric:
            v = v / 25.4
        if 0 < v < 0.1:
            vals.append(v)
            raws.append(f"±{raw}" + (" mm" if metric else ""))
    tightest = min(vals) if vals else None
    return {"raw": ", ".join(raws)[:200], "tightest_in": round(tightest, 5) if tightest is not None else None,
            "class": tolerance_class(tightest), "metric_drawing": metric}


def _multiplier(text: str, start: int, end: int) -> int:
    m = COUNT_BEFORE.search(text[max(0, start - 12): start])
    if m:
        return int(m.group(1) or m.group(2))
    m = COUNT_AFTER.search(text[end: end + 60])
    if m:
        return int(m.group(1))
    return 1


def _find_threads(text: str) -> dict:
    callouts: list[dict] = []
    for m in THREAD_INCH.finditer(text):
        cls = (m.group(4) or "").upper()
        kind = (m.group(3) or "").upper()
        callouts.append({"callout": _clean(m.group(0)), "count": _multiplier(text, m.start(), m.end()),
                         "internal": None if not cls else cls.endswith("B"), "pipe": kind.startswith("NPT")})
    for m in THREAD_METRIC.finditer(text):
        cls = m.group(3) or ""
        callouts.append({"callout": _clean(m.group(0)), "count": _multiplier(text, m.start(), m.end()),
                         "internal": None if not cls else cls[-1] in "Hh", "pipe": False})
    helicoils = 0
    for ln in text.splitlines():  # one insert callout often names the spec twice (HELICOIL ... MS21209)
        m = HELICOIL.search(ln)
        if m:
            k = re.search(r"\b(\d{1,3})\s*[Xx×]\s|\((\d{1,3})\)|\b(\d{1,3})\s*(?:PL(?:ACE)?S?|PLCS)\b", ln)
            helicoils += int(next(g for g in k.groups() if g)) if k else 1
    count = sum(c["count"] for c in callouts)
    internal = sum(c["count"] for c in callouts if c["internal"] is not False)
    return {"count": count, "internal": internal, "external": count - internal, "helicoils": helicoils,
            "callouts": [c["callout"] + (f" ({c['count']}X)" if c["count"] > 1 else "") for c in callouts]}


def _find_specs(text: str) -> list[dict]:
    specs = {s["standard"]: s for s in cited_standards(text)}
    for m in EXTRA_SPECS.finditer(text):
        key = re.sub(r"\s+", " ", m.group(0)).upper().strip()
        key = re.sub(r"^(ASTM|AMS|NAS|MS)\s*-?\s*", r"\1 ", key) if not key.startswith(("AMS-", "MIL-")) else key
        if any(key in k or k in key for k in specs):
            continue
        specs[key] = {"standard": key, "type": "Specification", "count": 1, "free": False}
    return sorted(specs.values(), key=lambda s: s["standard"])


def _first(pattern: re.Pattern, text: str, need_digit: bool = False) -> str:
    for m in pattern.finditer(text):
        v = _clean(m.group(1))
        if v and (not need_digit or re.search(r"\d", v)):
            return v
    return ""


TITLE_GRID = re.compile(r"\bSIZE\b.{0,20}\b(?:CAGE|FSCM)\b.{0,20}\bDWG\b.{0,20}\bREV\b", re.I)


def _title_grid(text: str) -> dict:
    """ASME Y14 style title block row: 'SIZE  CAGE CODE  DWG NO  REV' with the values on the next line."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not TITLE_GRID.search(ln):
            continue
        for nxt in lines[i + 1: i + 3]:
            tok = nxt.split()
            if len(tok) >= 4 and re.fullmatch(r"[A-F]", tok[0], re.I) and re.fullmatch(r"[0-9A-HJ-NP-Z]{5}", tok[1].upper()):
                return {"cage": tok[1].upper(), "drawing_number": " ".join(tok[2:-1]), "revision": tok[-1].upper()}
    return {}


def nice_title(title: str) -> str:
    """'RESISTANCE CHECK TRAINER ASSEMBLY, FMP' -> 'Resistance Check Trainer Assembly, FMP' (short all-caps words stay acronyms)."""
    if not title or not title.isupper():
        return title or ""
    return re.sub(r"[A-Z][A-Z0-9'-]*", lambda m: m.group(0) if (len(m.group(0)) <= 3 and m.group(0) not in ("THE", "AND", "FOR", "BOX", "KIT", "CAP", "NUT", "PIN", "ROD", "TOP", "LID")) else m.group(0).capitalize(), title)


def _title(text: str, drawing_number: str = "") -> str:
    v = _first(TITLE, text)
    if v and not set(w.upper().strip(".") for w in re.findall(r"[A-Za-z.]+", v)) <= TITLE_BLOCK_WORDS:
        return v
    return _title_near_label(text, drawing_number)


def _title_near_label(text: str, drawing_number: str = "") -> str:
    """CAD exports often put the title text a few lines before or after a bare TITLE label.
    Take the longest run of plain words next to the label that is not another title-block label."""
    lines = [ln.strip() for ln in text.splitlines()]
    best = ""
    for i, ln in enumerate(lines):
        if ln.upper() != "TITLE":
            continue
        run: list[str] = []
        runs: list[list[str]] = []
        for cand in lines[max(0, i - 8): i + 5]:
            words = re.findall(r"[A-Za-z][A-Za-z.&/'-]*", cand)
            ok = (cand and cand.upper() != "TITLE" and len(words) >= 1 and sum(len(w) for w in words) >= max(4, 0.6 * len(cand.replace(" ", "")))
                  and not set(w.upper().strip(".") for w in words) <= TITLE_BLOCK_WORDS and (not drawing_number or drawing_number not in cand)
                  and len(cand) <= 60 and not re.match(r"^\s*\d+\.\s", cand)  # numbered notes are not titles
                  and not re.search(r"UNLESS|TOLERANC|INTERPRET|DIMENSIONS|PROJECTION|NOTES?:|\d+\s*OF\s*\d+", cand, re.I))
            if ok:
                run.append(cand)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        for r in runs:
            joined = _clean(" ".join(r))
            if len(joined) > len(best) and len(joined) <= 100:
                best = joined
    return best


def _revision(text: str) -> str:
    vals = [m.group(1).upper() for m in REVISION.finditer(text)]
    if not vals:
        return ""
    # Highest revision wins (revision blocks list older ones too): numbers are drafts before letters
    return max(vals, key=lambda v: (v.isalpha(), len(v), v))


def _line_hits(pattern: re.Pattern, text: str, limit: int = 8) -> list[str]:
    out: list[str] = []
    for ln in text.splitlines():
        if pattern.search(ln):
            c = _clean(ln)[:200]
            if c and c not in out:
                out.append(c)
        if len(out) >= limit:
            break
    return out


def parse_text(text: str) -> dict:
    """Parse drawing text into quote fields. Pure function; read_drawing wraps it."""
    t = text or ""
    grid = _title_grid(t)
    part_number = _first(PART_NUMBER, t, need_digit=True)
    drawing_number = grid.get("drawing_number") or _first(DRAWING_NUMBER, t, need_digit=True)
    material = _find_material(t)
    finishes = _find_finishes(t)
    tolerance = _find_tolerance(t)
    threads = _find_threads(t)
    tap_notes = len(re.findall(r"\bTAP\b", t, re.I))
    thru_notes = len(re.findall(r"\bTHRU\b", t, re.I))
    dist = DISTRIBUTION.search(t)
    distribution = {"letter": dist.group(1).upper(), "raw": _clean(dist.group(0))[:300],
                    "meaning": DISTRIBUTION_MEANING[dist.group(1).upper()]} if dist else {"letter": "", "raw": "", "meaning": ""}
    export_hits = [p for p in EXPORT_PATTERNS if re.search(p, t, re.I)]
    if re.search(r"\bEAR\b", t) and re.search(r"EXPORT", t, re.I):
        export_hits.append("EAR")
    surface = [int(a or b) for a, b in SURFACE.findall(t) if (a or b)]  # microinches
    surface = [v for v in surface if 4 <= v <= 500]
    welding = sorted({re.sub(r"\s+", " ", m.group(0)).upper() for m in WELD_SPECS.finditer(t)})
    notes = [f"{n}. {_clean(body)}" for n, body in NOTE_LINE.findall(t)][:40]
    fa_lines = _line_hits(FIRST_ARTICLE, t)
    cert_lines = _line_hits(CERTS, t)

    warnings: list[str] = []
    if distribution["letter"] and distribution["letter"] != "A":
        warnings.append(f"Distribution statement {distribution['letter']}: {distribution['meaning']} Do not share this drawing outside authorized recipients.")
    if export_hits:
        warnings.append("Export-controlled technical data (ITAR/EAR marking). Share it only with U.S. persons or others authorized, and keep it off services not approved for controlled data.")
    if tolerance["metric_drawing"]:
        warnings.append("Dimensions are in millimeters; tolerances were converted to inches for the tolerance class.")
    for f in finishes:
        if f["mapped"] is None:
            warnings.append(f"Finish '{f['raw']}' has no matching finish in your rates. Price it by hand.")
    if material["raw"] and not material["mapped"]:
        warnings.append(f"Material '{material['raw']}' does not match a material in your rates. Pick the closest one or add it.")
    if threads["helicoils"]:
        warnings.append(f"{threads['helicoils']} thread insert callout(s) (Helicoil or similar): count them as hardware inserts.")
    if threads["external"]:
        warnings.append(f"{threads['external']} external thread(s) found; on a milled part these are not tapped holes.")

    return {
        "part_number": part_number or drawing_number,
        "drawing_number": drawing_number,
        "cage": grid.get("cage") or _first(CAGE, t).upper(),
        "revision": grid.get("revision") or _revision(t),
        "title": _title(t, drawing_number),
        "material": material,
        "finishes": finishes,
        "tolerance": tolerance,
        "threads": threads,
        "holes_tapped_guess": threads["internal"] or tap_notes,
        "tap_notes": tap_notes,
        "thru_notes": thru_notes,
        "specs": _find_specs(t),
        "distribution": distribution,
        "export_controlled": bool(export_hits),
        "surface_finish": {"raw": ", ".join(f"{v} Ra" for v in surface), "ra_microin": min(surface) if surface else None},
        "heat_treat": _line_hits(HEAT_TREAT, t),
        "inspection": {"first_article": bool(fa_lines), "material_certs": bool(cert_lines), "lines": fa_lines + [c for c in cert_lines if c not in fa_lines]},
        "welding": {"specs": welding, "required": bool(welding) or bool(re.search(r"\bWELD", t, re.I))},
        "notes": notes,
        "warnings": warnings,
    }


# ---------------------------------------------------------------- AI read for scanned drawings
AI_PROMPT = """This PDF is an engineering drawing, probably scanned. Transcribe it for a machine shop quote.
Return only JSON with these keys:
{"text": "every readable word on the drawing: title block, revision block, general notes (keep their numbers, one note per line), tolerance block, and every dimension callout that has a tolerance, thread, finish or material",
 "part_number": "", "drawing_number": "", "cage": "", "revision": "", "title": "",
 "material": "material callout as written", "finishes": ["finish callouts as written"],
 "general_tolerance": "as written", "thread_callouts": ["as written, with the NX count"],
 "distribution_statement": "letter A-F or empty", "export_warning": true}
Use empty strings or lists when something is not on the drawing. Do not guess."""


def _claude_read_pdf(data: bytes) -> dict:
    """Send the PDF to Claude and return its JSON transcription. Tests replace this function."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}},
            {"type": "text", "text": AI_PROMPT},
        ]}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise DrawingError("Claude did not return JSON for the drawing.")
    return json.loads(m.group(0))


def _merge_ai(ai: dict) -> dict:
    lines = [ai.get("text") or ""]
    # Feed the structured answers back through the same parser so mapping rules stay in one place
    if ai.get("material"):
        lines.append(f"MATERIAL: {ai['material']}")
    lines += [str(f) for f in ai.get("finishes") or []]
    if ai.get("general_tolerance"):
        lines.append(str(ai["general_tolerance"]))
    lines += [str(c) for c in ai.get("thread_callouts") or []]
    if ai.get("distribution_statement") and "DISTRIBUTION STATEMENT" not in lines[0].upper():
        lines.append(f"DISTRIBUTION STATEMENT {ai['distribution_statement']}.")
    if ai.get("export_warning") and not re.search(r"ITAR|EXPORT", lines[0], re.I):
        lines.append("EXPORT-CONTROLLED")
    parsed = parse_text("\n".join(lines))
    for key in ("part_number", "drawing_number", "cage", "revision", "title"):
        if ai.get(key):
            parsed[key] = _clean(str(ai[key]))
    if not parsed["part_number"]:
        parsed["part_number"] = parsed["drawing_number"]
    return parsed


def _empty() -> dict:
    return parse_text("")


def read_drawing(path: Path | str, use_ai: bool = False) -> dict:
    """Read a PDF drawing and return the parsed fields (see parse_text) plus text_found, pages, ai_used."""
    path = Path(path)
    text, pages = extract_pdf_text(path)
    found = len(re.findall(r"[A-Za-z0-9]", text)) >= 20
    if found:
        out = parse_text(text)
        out.update({"text_found": True, "pages": pages, "ai_used": False, "text_chars": len(text)})
        if not (out["part_number"] or out["material"]["raw"] or out["notes"]):
            out["warnings"].append("Text was found but no title block fields matched. Check the drawing and enter the fields by hand.")
        return out

    out = _empty()
    out.update({"text_found": False, "pages": pages, "ai_used": False, "text_chars": len(text)})
    if use_ai and ANTHROPIC_API_KEY:
        try:
            out = _merge_ai(_claude_read_pdf(path.read_bytes()))
            out.update({"text_found": False, "pages": pages, "ai_used": True, "text_chars": len(text)})
            out["warnings"].insert(0, "Scanned drawing read by Claude. Check every field against the drawing.")
        except Exception as exc:  # network, quota, bad JSON
            out["warnings"].insert(0, f"The drawing is scanned and the AI read failed ({exc}). Enter the fields by hand.")
    elif use_ai:
        out["warnings"].insert(0, "The drawing is scanned (no text layer). Set ANTHROPIC_API_KEY to read scanned drawings with Claude, or enter the fields by hand.")
    else:
        out["warnings"].insert(0, "The drawing is scanned (no text layer), so nothing could be read. Enter the fields by hand"
                               + (", or read it with Claude (only for drawings you may share with an outside service)." if ANTHROPIC_API_KEY else "."))
    return out


def quote_options(read: dict, materials: list[str] | None = None, finishes: list[str] | None = None) -> dict:
    """InstantQuote option values the drawing supports with confidence. Unknown or unmapped fields are left out."""
    o: dict = {}
    mat = (read.get("material") or {}).get("mapped")
    if mat and (materials is None or mat in materials):
        o["material"] = mat
    fins = [f["mapped"] for f in read.get("finishes") or [] if f.get("mapped") and (finishes is None or f["mapped"] in finishes)]
    if fins:
        # Type III replaces Type II when both matched (a generic ANODIZE line plus the spec callout)
        if "hard anodize (Type III)" in fins and "anodize (Type II)" in fins:
            fins.remove("anodize (Type II)")
        o["finishes"] = list(dict.fromkeys(fins))
    tol = (read.get("tolerance") or {}).get("class")
    if tol:
        o["tolerance"] = tol
    th = read.get("threads") or {}
    holes = read.get("holes_tapped_guess") or 0
    if holes:
        o["threaded_holes"] = int(holes)
    elif th.get("count"):
        o["threaded_holes"] = int(th["count"])
    if th.get("helicoils"):
        o["inserts"] = int(th["helicoils"])
    if read.get("part_number"):
        o["part_number"] = read["part_number"]
    if read.get("title"):
        o["name"] = nice_title(read["title"])
    insp = read.get("inspection") or {}
    if insp.get("material_certs"):
        o["material_certs"] = True
    if insp.get("first_article"):
        o["first_article"] = True
    return o
