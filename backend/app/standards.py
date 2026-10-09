"""Standards library logic: parse document IDs, merge the built-in catalog with saved rows,
record standards cited in solicitations and flag revision mismatches.

Other code should call:
  parse_doc_id(text) -> (base_id, revision)
  record_cited_standards(db, opportunity, cited) -> list[dict]   (after analysis.cited_standards)
  revision_check(db, cited) -> list[dict]                         (read-only version)
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote, quote_plus

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models_standards import StandardEntry
from .standards_catalog import CATALOG, CATEGORIES, DOD, NAVSEA_TP, PUBLISHER_FREE

ASSIST_URL = "https://quicksearch.dla.mil/qsSearch.aspx"

# Publisher home or store pages (each checked to load). ASTM's store search takes the designation.
PUBLISHER_URLS = {
    "SAE": "https://www.sae.org/standards",
    "ASME": "https://www.asme.org/codes-standards/find-codes-standards",
    "AWS": "https://pubs.aws.org/",
    "IPC": "https://www.ipc.org/ipc-standards",
    "IPC/JEDEC": "https://www.ipc.org/ipc-standards",
    "NFPA": "https://www.nfpa.org/codes-and-standards",
    "UL": "https://www.shopulstandards.com/",
    "ISO": "https://www.iso.org/",
    "IEC": "https://webstore.iec.ch/",
    "ANSI/ESD (ESD Association)": "https://www.esda.org/standards/",
    "IEEE": "https://standards.ieee.org/",
    "ECIA": "https://www.ecianow.org/",
    "RTCA": "https://www.rtca.org/",
    "NEMA": "https://www.nema.org/standards",
    "ASQ": "https://asq.org/quality-press",
    "NCSL International": "https://ncsli.org/",
    "ASNT": "https://www.asnt.org/",
    "AIA (NAS)": "https://www.aia-aerospace.org/",
    "Battelle (MMPDS)": "https://www.mmpds.org/",
    "AMPP (SSPC)": "https://www.ampp.org/",
    "S1000D (free download)": "https://s1000d.org/",
    "ADL Initiative (free)": "https://adlnet.gov/",
    "IPPC (free)": "https://www.ippc.int/",
    "IDEA": "https://www.idofea.org/",
    "LIA": "https://www.lia.org/",
    "ISA": "https://www.isa.org/standards-and-publications/isa-standards",
    "TIA": "https://www.tiaonline.org/standards/",
    "NIST (free)": "https://csrc.nist.gov/publications/sp800",
    "eCFR (free)": "https://www.ecfr.gov/",
    "acquisition.gov (free)": "https://www.acquisition.gov/dfars",
}
SPECIFIC_URLS = {
    "NIST SP 800-171": "https://csrc.nist.gov/pubs/sp/800/171/r3/final",
    "29 CFR 1910": "https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1910",
    "32 CFR 170": "https://www.ecfr.gov/current/title-32/subtitle-A/chapter-I/subchapter-G/part-170",
    "DFARS 252.204-7012": "https://www.acquisition.gov/dfars/252.204-7012-safeguarding-covered-defense-information-and-cyber-incident-reporting.",
}

SCOPES = ("all", "library", "cited", "catalog")


# ------------------------------------------------------------------ ID keys and catalog index
def _key(doc_id: str) -> str:
    """Comparison key: case, spaces, hyphens and most punctuation ignored."""
    k = re.sub(r"[^A-Z0-9./]", "", (doc_id or "").upper())
    k = k.replace("CFRPART", "CFR")
    return k


_CATALOG_BY_KEY: dict[str, dict] = {}
for _e in CATALOG:
    _CATALOG_BY_KEY[_key(_e["id"])] = _e
_CAT_ORDER = {c: i for i, c in enumerate(CATEGORIES)}


def catalog_entry(base_id: str) -> dict | None:
    """Catalog entry for an exact base ID (case, spaces and hyphens ignored)."""
    if not base_id:
        return None
    k = _key(base_id)
    if k in _CATALOG_BY_KEY:
        return _CATALOG_BY_KEY[k]
    return None


def parent_catalog_entry(base_id: str) -> dict | None:
    """Parent document for slash sheets and parts: MIL-DTL-38999/20 -> MIL-DTL-38999, IEC 60068-2-6 -> IEC 60068."""
    cur = base_id or ""
    for _ in range(4):
        m = re.match(r"^(.*\d)(?:/\d+|-\d+)$", cur)
        if not m:
            break
        cur = m.group(1)
        e = catalog_entry(cur)
        if e:
            return e
    return None


def canonical_id(base_id: str) -> str:
    e = catalog_entry(base_id)
    return e["id"] if e else base_id


# ------------------------------------------------------------------ parsing
_CHANGE_RE = re.compile(
    r"[\s,]*\(?\s*(?:W/\s*|WITH\s+)?(CHANGE|CHG|NOTICE|NOT|AMENDMENT|AMEND|AMD|VALIDATION NOTICE)\.?\s*-?\s*(\d+)\s*\)?\s*$"
)
_PAREN_NUM_RE = re.compile(r"\((\d{1,2})\)\s*$")
_REV_WORD_RE = re.compile(r"[\s,]*\(?(?:REV(?:ISION)?|ISSUE|EDITION|ED)\.?\s*([A-Z0-9.]{1,6})\)?\s*$")
_CHANGE_LABEL = {"CHANGE": "Change", "CHG": "Change", "NOTICE": "Notice", "NOT": "Notice", "VALIDATION NOTICE": "Notice",
                 "AMENDMENT": "Amendment", "AMEND": "Amendment", "AMD": "Amendment"}
_YEAR = r"(?:19|20)\d{2}"


def _r(m: re.Match | None, i: int) -> str:
    return (m.group(i) or "") if m else ""


def _parse_core(s: str) -> tuple[str, str] | None:
    """Return (base, revision) for a cleaned, upper-case ID string, or None if no rule matched."""
    # Military and DoD documents: MIL-STD-130N, MIL-DTL-5541F, MIL-STD-2073-1E, MIL-DTL-38999/20D
    s = re.sub(r"^(MIL|DOD)[\s-]+(STD|HDBK|PRF|DTL|SPEC|[A-Z])[\s-]+(?=\d)", r"\1-\2-", s)
    m = re.match(r"^((?:MIL|DOD)-(?:STD|HDBK|PRF|DTL|SPEC|[A-Z])-)0*(\d+)((?:-\d+)*)(?:/(\d+))?\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        base = m.group(1) + m.group(2) + m.group(3) + (f"/{m.group(4)}" if m.group(4) else "")
        return base, _r(m, 5)
    m = re.match(r"^(DI-[A-Z]{4}-\d{5})\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return m.group(1), _r(m, 2)
    m = re.match(r"^(FED-STD-[A-Z]?\d+)\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return m.group(1), _r(m, 2)
    m = re.match(r"^(A-A-\d+)\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return m.group(1), _r(m, 2)
    # SAE AMS-QQ-N-290A, AMS-STD-595A, AMS-DTL-23053/5
    m = re.match(r"^(?:SAE[\s-]*)?(AMS-(?:QQ-[A-Z]|STD|DTL|PRF|[A-Z])-\d+(?:/\d+)?)\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return m.group(1), _r(m, 2)
    # Federal specs: QQ-A-250/5, TT-C-490F, PPP-B-601
    m = re.match(r"^([A-Z]{1,3}-[A-Z]-\d+(?:/\d+)?)\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return m.group(1), _r(m, 2)
    m = re.match(r"^(MS\d{4,5}|NASM\d{3,5})\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return m.group(1), _r(m, 2)
    m = re.match(r"^NAS\s*(\d{3,4})\s*(?:[-:(]\s*(" + _YEAR + r")\)?)?", s)
    if m:
        return f"NAS {m.group(1)}", _r(m, 2)
    # NAVSEA technical publications: S9074-AQ-GIB-010/248
    m = re.match(r"^(?:NAVSEA\s*)?([ST]\d{4}-[A-Z]{2}-[A-Z]{3}-\d{3}/\d+)", s)
    if m:
        return m.group(1), ""
    # Regulations and clauses
    m = re.match(r"^(DFARS|FAR)\s*(\d{1,3}\.\d{3}-\d{1,4})", s)
    if m:
        return f"{m.group(1)} {m.group(2)}", ""
    m = re.match(r"^(\d{1,2})\s*CFR\s*(?:PART\s*)?(\d+(?:\.\d+)?)(\s*SUBPART\s*[A-Z]{1,2})?", s)
    if m:
        sub = re.sub(r"\s+", " ", m.group(3) or "").strip()
        sub = f" Subpart {sub.split()[-1]}" if sub else ""
        return f"{m.group(1)} CFR {m.group(2)}{sub}", ""
    m = re.match(r"^FCC\s*(?:PART\s*)?15\b", s)
    if m:
        return "47 CFR Part 15", ""
    # NIST
    m = re.match(r"^(?:NIST\s*)?FIPS\s*(?:PUB\s*)?(\d+(?:-\d+)?)", s)
    if m:
        return f"FIPS {m.group(1)}", ""
    m = re.match(r"^NIST\s*(?:CSF|CYBERSECURITY FRAMEWORK)\s*(\d(?:\.\d)?)?", s)
    if m:
        return "NIST CSF", _r(m, 1)
    m = re.match(r"^(?:NIST\s*)?(?:SP|SPECIAL PUBLICATION)?\s*(800-\d+[A-Z]?(?!\d))(?:\s*,?\s*R(?:EV(?:ISION)?)?\.?\s*(\d+))?", s)
    if m and (s.startswith("NIST") or s.startswith("SP")):
        return f"NIST SP {m.group(1)}", (f"Rev {m.group(2)}" if m.group(2) else "")
    # ISO / IEC / CISPR, with :year
    m = re.match(r"^(?:ANSI/|BS\s+EN\s+|EN\s+)?(ISO/IEC|ISO/ASTM|ASTM/ISO|ISO/TS|IEC/TS|ISO|IEC|CISPR)\s*(\d+(?:[-.]\d+)*)(?:\s*[:]\s*(\d{4}))?", s)
    if m:
        prefix = "ISO/ASTM" if m.group(1) == "ASTM/ISO" else m.group(1)
        num, year = m.group(2), _r(m, 3)
        if not year:
            ym = re.match(r"^(.*)-(" + _YEAR + r")$", num)
            if ym and "-" in num:
                num, year = ym.group(1), ym.group(2)
        return f"{prefix} {num}", year
    # ASME
    m = re.match(r"^ASME\s*(?:BPVC|B&PV|BOILER AND PRESSURE VESSEL CODE)?[\s,]*SEC(?:TION|\.)?\s*([IVX]+)\b(?:.*?(" + _YEAR + r"))?", s)
    if m:
        return f"ASME BPVC Section {m.group(1)}", _r(m, 2)
    m = re.match(r"^(?:ANSI\s*/\s*)?(?:ASME\s*(?:/\s*ANSI)?\s*)?(Y|B)\s?(\d+(?:\.\d+)+)(M)?(?:\s*[-:]?\s*\(?(" + _YEAR + r")\)?)?(?![\d.])", s)
    if m and (s.startswith("ASME") or s.startswith("ANSI") or m.group(1) == "Y"):
        letter, num, metric, year = m.group(1), m.group(2), m.group(3) or "", _r(m, 4)
        if letter == "Y":
            metric = ""  # Y14.5M-1994 is the older edition of Y14.5
        return f"ASME {letter}{num}{metric}", year
    # IPC and J-STD
    m = re.match(r"^(?:IPC[/\s-]*)?(?:JEDEC[/\s-]*)?J-?STD-?(\d{3})\s*([A-Z]{1,2})?(?![A-Z0-9])", s)
    if m:
        return f"J-STD-{m.group(1)}", _r(m, 2)
    m = re.match(r"^IPC(/WHMA|/JEDEC|/EIA)?[\s-]?((?:[A-Z]{1,4}-)?)(\d{3,4})(/\d{4})?\s*([A-Z]{1,2})?(?![A-Z0-9])", s)
    if m:
        return f"IPC{m.group(1) or ''}-{m.group(2)}{m.group(3)}{m.group(4) or ''}", _r(m, 5)
    # SAE EIA / GEIA
    m = re.match(r"^(?:SAE[\s-]*|ANSI/)?(GEIA-(?:STD|HB)-\d{4}(?:-\d+)?|EIA-\d{3,4}(?:-\d+)?)\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return m.group(1), _r(m, 2)
    # SAE AS / AMS / ARP / AIR: AS9100D, AMS 2700F, AS22759/16
    m = re.match(r"^(?:SAE[\s-]*)?(AS|AMS|ARP|AIR)\s?-?(\d{3,5})(/\d+)?\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3) or ''}", _r(m, 4)
    m = re.match(r"^SAE\s*J\s?(\d{3,4})(?:\s*[_-]\s*(\d{6}))?", s)
    if m:
        return f"SAE J{m.group(1)}", _r(m, 2)
    # ASTM A276/A276M-24
    m = re.match(r"^(?:ANSI/)?ASTM\s*([A-G])\s?(\d{1,5})(?:M)?(?:\s*/\s*[A-G]\s?\d{1,5}M?)?(?:\s*-\s*(\d{2,4}(?:[A-Z]\d?)?(?:E\d)?))?", s)
    if m:
        return f"ASTM {m.group(1)}{m.group(2)}", _r(m, 3)
    # AWS D1.1/D1.1M:2020
    m = re.match(r"^(?:ANSI/)?AWS\s*(QC\s?\d+)(?:\s*[:-]\s*(" + _YEAR + r"))?", s)
    if m:
        return f"AWS {m.group(1).replace(' ', '')}", _r(m, 2)
    m = re.match(r"^(?:ANSI/)?AWS\s*([A-Z])\s?(\d+(?:\.\d+)+)M?(?:\s*/\s*[A-Z]\d+(?:\.\d+)+M?)?(?:\s*[:-]\s*(" + _YEAR + r"))?", s)
    if m:
        return f"AWS {m.group(1)}{m.group(2)}", _r(m, 3)
    m = re.match(r"^(?:ANSI/)?NFPA\s*(\d+[A-Z]?)(?:\s*[,:\-]?\s*\(?(?:EDITION\s*)?(" + _YEAR + r")\)?)?", s)
    if m:
        return f"NFPA {m.group(1)}", _r(m, 2)
    m = re.match(r"^(?:ANSI/)?UL\s*(\d+[A-Z]?(?:-\d+[A-Z]?)?)(?:.*?(\d+)(?:ST|ND|RD|TH)\s*ED)?", s)
    if m:
        return f"UL {m.group(1)}", (f"Ed {m.group(2)}" if m.group(2) else "")
    m = re.match(r"^(?:ANSI\s*/\s*)?ESDA?\s*(STM|SP|TR|ADV|S)\s?(\d+(?:\.\d+)*)(?:\s*-\s*(" + _YEAR + r"))?", s)
    if m:
        kind = m.group(1)
        base = f"ESD {kind}{m.group(2)}" if kind in ("TR", "ADV") else f"ANSI/ESD {kind}{m.group(2)}"
        return base, _r(m, 3)
    m = re.match(r"^(?:ANSI\s*/?\s*)?(?:ASQC?|NCSL|NEMA|LIA)?\s*/?\s*Z\s?(\d+(?:\.\d+)+)(?:\s*[-:]\s*(" + _YEAR + r"))?", s)
    if m:
        num = m.group(1)
        head = num.split(".")[0]
        prefix = {"1": "ANSI/ASQ", "540": "ANSI/NCSL"}.get(head, "ANSI")
        return f"{prefix} Z{num}", _r(m, 2)
    m = re.match(r"^(?:ANSI\s*)?C63\.(\d+)(?:\s*-\s*(" + _YEAR + r"))?", s)
    if m:
        return f"ANSI C63.{m.group(1)}", _r(m, 2)
    m = re.match(r"^(?:ANSI/)?IEEE\s*(?:STD\.?\s*)?(C?\d+(?:\.\d+)*)(?:\s*-\s*(" + _YEAR + r"))?", s)
    if m:
        return f"IEEE {m.group(1)}", _r(m, 2)
    m = re.match(r"^(?:RTCA\s*/?\s*)?DO-?(\d{3})\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return f"RTCA DO-{m.group(1)}", _r(m, 2)
    m = re.match(r"^(?:ANSI/)?ISA-?\s?(\d+(?:\.\d+)+)(?:\s*-\s*(" + _YEAR + r"))?", s)
    if m:
        return f"ANSI/ISA-{m.group(1)}", _r(m, 2)
    m = re.match(r"^(?:ANSI/)?TIA(?:/EIA)?-(\d+)", s)
    if m:
        return f"TIA-{m.group(1)}", ""
    m = re.match(r"^NEMA\s*(\d+)", s)
    if m:
        return f"NEMA {m.group(1)}", ""
    m = re.match(r"^SSPC[-\s]*SP\s*(\d+)", s)
    if m:
        return f"SSPC-SP {m.group(1)}", ""
    m = re.match(r"^(?:ASNT\s*)?SNT-TC-1A(?:\s*[-(]\s*(" + _YEAR + r")\)?)?", s)
    if m:
        return "ASNT SNT-TC-1A", _r(m, 1)
    m = re.match(r"^IDEA-STD-(\d+)\s*([A-Z])?(?![A-Z0-9])", s)
    if m:
        return f"IDEA-STD-{m.group(1)}", _r(m, 2)
    m = re.match(r"^MMPDS(?:\s*-\s*(\d+))?", s)
    if m:
        return "MMPDS", _r(m, 1)
    m = re.match(r"^S1000D(?:\s*(?:ISSUE)?\s*(\d+(?:\.\d+)*))?", s)
    if m:
        return "S1000D", _r(m, 1)
    m = re.match(r"^ISPM\s*-?\s*(\d+)", s)
    if m:
        return f"ISPM {m.group(1)}", ""
    m = re.match(r"^SCORM(?:\s*(\d{4}|\d\.\d))?", s)
    if m:
        return "SCORM", _r(m, 1)
    return None


def parse_doc_id_full(text: str) -> dict:
    """Parse any document reference into {base_id, revision, change, cited_as}.

    'MIL-STD-130N(1)' and 'MIL-STD-130N w/CHANGE 1' -> base MIL-STD-130, revision N, change 'Change 1'.
    """
    raw = re.sub(r"\s+", " ", (text or "").strip())
    s = raw.upper().strip(" .,;")
    s = s.replace("–", "-").replace("—", "-")
    change = ""
    m = _CHANGE_RE.search(s)
    if m:
        change = f"{_CHANGE_LABEL.get(m.group(1), 'Change')} {m.group(2)}"
        s = s[: m.start()].strip(" ,(")
    else:
        m = _PAREN_NUM_RE.search(s)
        if m and re.search(r"[A-Z]\s*\(\d{1,2}\)$", s):
            change = f"Change {m.group(1)}"
            s = s[: m.start()].strip()
    rev_hint = ""
    m = _REV_WORD_RE.search(s)
    if m and re.search(r"\d", s[: m.start()]):
        rev_hint = m.group(1).strip(".")
        s = s[: m.start()].strip(" ,")
    parsed = _parse_core(s)
    if parsed is None:
        base, rev = s, ""
        ym = re.match(r"^(.*?\S)\s*[-:]\s*(" + _YEAR + r")$", s)
        lm = re.match(r"^([A-Z][A-Z0-9/.\- ]*\d)([A-Z])$", s)
        if ym:
            base, rev = ym.group(1), ym.group(2)
        elif lm and "-" in s:
            base, rev = lm.group(1), lm.group(2)
    else:
        base, rev = parsed
    if rev_hint and not rev:
        rev = f"Rev {rev_hint}" if base.startswith("NIST SP") else rev_hint
    base = canonical_id(base.strip())
    return {"base_id": base, "revision": rev, "change": change, "cited_as": raw}


def parse_doc_id(text: str) -> tuple[str, str]:
    """('MIL-STD-130N') -> ('MIL-STD-130', 'N'); ('ASME Y14.5-2018') -> ('ASME Y14.5', '2018')."""
    p = parse_doc_id_full(text)
    return p["base_id"], p["revision"]


def norm_rev(rev: str) -> str:
    r = (rev or "").upper()
    r = re.sub(r"\b(REVISION|REV|EDITION|ED|ISSUE)\b\.?", "", r)
    return re.sub(r"[^A-Z0-9.]", "", r)


def revisions_differ(a: str, b: str) -> bool:
    na, nb = norm_rev(a), norm_rev(b)
    return bool(na and nb and na != nb)


def looks_like_id(q: str) -> bool:
    q = (q or "").strip()
    if not q or len(q) > 60:
        return False
    return bool(re.search(r"\d", q) and re.search(r"[A-Za-z]", q) and re.match(r"^[A-Za-z]{1,6}[\s/&-]*[A-Za-z0-9]", q))


# ------------------------------------------------------------------ links and publisher guesses
def guess_publisher(base_id: str) -> str:
    b = (base_id or "").upper()
    rules = [
        (r"^(MIL|DOD)-|^DI-|^FED-STD|^A-A-|^[A-Z]{1,3}-[A-Z]-\d|^MS\d", DOD),
        (r"^[ST]\d{4}-", NAVSEA_TP),
        (r"^ASTM|^ISO/ASTM", "ASTM"),
        (r"^ASME", "ASME"),
        (r"^AWS", "AWS"),
        (r"^J-STD", "IPC/JEDEC"),
        (r"^IPC", "IPC"),
        (r"^(AS|AMS|ARP|AIR)\d|^AMS-|^SAE|^EIA-|^GEIA|^NASM", "SAE"),
        (r"^NFPA", "NFPA"),
        (r"^UL ", "UL"),
        (r"^IEC|^CISPR", "IEC"),
        (r"^ISO", "ISO"),
        (r"^NIST|^FIPS", "NIST (free)"),
        (r"\bCFR\b", "eCFR (free)"),
        (r"^DFARS|^FAR ", "acquisition.gov (free)"),
        (r"ESD", "ANSI/ESD (ESD Association)"),
        (r"^IEEE|^ANSI C63", "IEEE"),
        (r"^RTCA", "RTCA"),
        (r"^NEMA", "NEMA"),
    ]
    for pat, pub in rules:
        if re.search(pat, b):
            return pub
    return ""


def links_for(base_id: str, publisher: str) -> dict:
    out = {
        "assist_url": ASSIST_URL,
        "everyspec_url": "https://www.google.com/search?q=" + quote_plus(f'site:everyspec.com "{base_id}"'),
        "publisher_url": "",
    }
    if base_id in SPECIFIC_URLS:
        out["publisher_url"] = SPECIFIC_URLS[base_id]
    elif publisher in ("ASTM", "ISO/ASTM"):
        code = re.sub(r"^(ASTM|ISO/ASTM)\s*", "", base_id)
        out["publisher_url"] = "https://store.astm.org/catalogsearch/result/?q=" + quote(code)
    elif publisher in PUBLISHER_URLS:
        out["publisher_url"] = PUBLISHER_URLS[publisher]
    return out


# ------------------------------------------------------------------ merged views
def _citation_summary(citations: list, revision_on_file: str) -> tuple[int, str, bool]:
    cits = citations or []
    opps = {c.get("opportunity_id") for c in cits}
    latest = ""
    for c in sorted(cits, key=lambda c: c.get("seen_at") or ""):
        if c.get("revision"):
            latest = c["revision"]
    mismatch = any(revisions_differ(c.get("revision", ""), revision_on_file) for c in cits)
    return len(opps), latest, mismatch


def entry_view(row: StandardEntry | None, cat: dict | None = None, base_id: str = "") -> dict:
    """One merged record from the catalog entry and/or the database row."""
    if cat is None and row is not None:
        cat = catalog_entry(row.base_id)
    base = (row.base_id if row is not None else None) or (cat["id"] if cat else base_id)
    parent = None if cat else parent_catalog_entry(base)
    publisher = (row.publisher if row is not None and row.publisher else "") or (cat or {}).get("publisher") or guess_publisher(base)
    free = (cat or {}).get("free")
    if free is None:
        free = row.free if row is not None and row.publisher else PUBLISHER_FREE.get(publisher, False)
    citations = list(row.citations or []) if row is not None else []
    rev_file = row.revision_on_file if row is not None else ""
    cited_count, latest_rev, mismatch = _citation_summary(citations, rev_file)
    title = (row.title if row is not None and row.title else "") or (cat or {}).get("title", "")
    summary = (cat or {}).get("summary", "") or (row.summary if row is not None else "")
    category = (row.category if row is not None and row.category else "") or (cat or {}).get("category") or (parent or {}).get("category", "")
    if not cat and parent and not summary:
        summary = f"Part of {parent['id']} ({parent['title']}). {parent['summary']}"
    if not category and base.startswith("DI-"):
        category = "Data item descriptions (DIDs)"
    return {
        "base_id": base,
        "title": title or ((f"{parent['title']} (slash sheet or part)") if parent else ""),
        "category": category,
        "summary": summary,
        "publisher": publisher,
        "free": bool(free),
        "in_catalog": cat is not None,
        "parent_id": parent["id"] if parent else "",
        "in_library": bool(row.in_library) if row is not None else False,
        "revision_on_file": rev_file,
        "file_name": row.file_name if row is not None else "",
        "has_file": bool(row is not None and row.file_name),
        "notes": row.notes if row is not None else "",
        "source": row.source if row is not None else "catalog",
        "status": row.status if row is not None else "",
        "doc_date": row.doc_date if row is not None else "",
        "listed_revision": row.listed_revision if row is not None else "",
        "citations": sorted(citations, key=lambda c: c.get("seen_at") or "", reverse=True),
        "cited_count": cited_count,
        "latest_cited_revision": latest_rev,
        "mismatch": mismatch,
        "updated_at": row.updated_at.isoformat() if row is not None and row.updated_at else None,
        **links_for(base, publisher),
    }


def merged_entries(db: Session) -> list[dict]:
    rows = {r.base_id: r for r in db.scalars(select(StandardEntry)).all()}
    out = []
    seen = set()
    for cat in CATALOG:
        out.append(entry_view(rows.get(cat["id"]), cat))
        seen.add(cat["id"])
    for base, row in rows.items():
        if base not in seen:
            out.append(entry_view(row, None))
    return out


def _nat(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", (s or "").upper())]


def filter_entries(items: list[dict], q: str = "", category: str = "", scope: str = "all", free: bool | None = None) -> list[dict]:
    if scope == "library":
        items = [i for i in items if i["in_library"] or i["has_file"]]
    elif scope == "cited":
        items = [i for i in items if i["cited_count"] > 0]
    elif scope == "catalog":
        items = [i for i in items if i["in_catalog"]]
    if category:
        items = [i for i in items if i["category"] == category]
    if free is not None:
        items = [i for i in items if i["free"] == free]
    q = (q or "").strip()
    if not q:
        if scope == "cited":
            return sorted(items, key=lambda i: (-i["cited_count"], _nat(i["base_id"])))
        return sorted(items, key=lambda i: (_CAT_ORDER.get(i["category"], 99), _nat(i["base_id"])))
    qkey = _key(q)
    parsed_key = _key(parse_doc_id(q)[0]) if looks_like_id(q) else ""
    words = [w for w in re.split(r"\s+", q.lower()) if w]
    ranked = []
    for i in items:
        ik = _key(i["base_id"])
        hay = f"{i['base_id']} {i['title']} {i['summary']} {i['category']} {i['notes']} {i['publisher']}".lower()
        if parsed_key and ik == parsed_key or ik == qkey:
            rank = 0
        elif qkey and ik.startswith(qkey):
            rank = 1
        elif qkey and len(qkey) >= 3 and qkey in ik:
            rank = 2
        elif all(w in hay for w in words):
            rank = 3 if all(w in f"{i['base_id']} {i['title']}".lower() for w in words) else 4
        else:
            continue
        ranked.append((rank, _nat(i["base_id"]), i))
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in ranked]


def category_counts(items: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for i in items:
        counts[i["category"] or "Other"] = counts.get(i["category"] or "Other", 0) + 1
    order = list(CATEGORIES) + sorted(c for c in counts if c not in CATEGORIES)
    return [{"category": c, "count": counts[c]} for c in order if counts.get(c)]


def lookup(db: Session, text: str) -> dict:
    p = parse_doc_id_full(text)
    row = db.scalar(select(StandardEntry).where(StandardEntry.base_id == p["base_id"]))
    cat = catalog_entry(p["base_id"])
    entry = entry_view(row, cat, base_id=p["base_id"])
    return {"parsed": p, "known": bool(cat or row), "entry": entry}


# ------------------------------------------------------------------ rows
def get_row(db: Session, base_id: str) -> StandardEntry | None:
    return db.scalar(select(StandardEntry).where(StandardEntry.base_id == base_id))


def get_or_create_row(db: Session, base_id: str, source: str = "manual") -> StandardEntry:
    row = get_row(db, base_id)
    if row is not None:
        return row
    cat = catalog_entry(base_id)
    publisher = (cat or {}).get("publisher") or guess_publisher(base_id)
    row = StandardEntry(
        base_id=base_id,
        title=(cat or {}).get("title", ""),
        category=(cat or {}).get("category", "") or ((parent_catalog_entry(base_id) or {}).get("category", "")),
        summary=(cat or {}).get("summary", ""),
        publisher=publisher,
        free=(cat or {}).get("free", PUBLISHER_FREE.get(publisher, False)),
        source="catalog" if cat and source == "manual" else source,
        citations=[],
    )
    db.add(row)
    db.flush()
    return row


def _opp_attr(opportunity, name: str):
    if isinstance(opportunity, dict):
        return opportunity.get(name)
    return getattr(opportunity, name, None)


def _cited_items(cited: list) -> list[dict]:
    """Parse analysis.cited_standards output (or plain strings) into per-reference records."""
    out = []
    for item in cited or []:
        text = item.get("standard", "") if isinstance(item, dict) else str(item)
        if not text.strip():
            continue
        p = parse_doc_id_full(text)
        out.append({**p, "count": item.get("count", 1) if isinstance(item, dict) else 1,
                    "type": item.get("type", "") if isinstance(item, dict) else ""})
    return out


def _check_result(p: dict, row: StandardEntry | None) -> dict:
    cat = catalog_entry(p["base_id"])
    rev_file = row.revision_on_file if row is not None else ""
    title = (row.title if row is not None and row.title else "") or (cat or {}).get("title", "")
    return {
        "base_id": p["base_id"],
        "cited_as": p["cited_as"],
        "cited_revision": p["revision"],
        "cited_change": p["change"],
        "revision_on_file": rev_file,
        "mismatch": revisions_differ(p["revision"], rev_file),
        "title": title,
        "in_catalog": cat is not None,
        "in_library": bool(row is not None and row.in_library),
        "has_file": bool(row is not None and row.file_name),
    }


def record_cited_standards(db: Session, opportunity, cited: list[dict]) -> list[dict]:
    """Save the standards a solicitation cites and return a revision check for each.

    `cited` is the list from app.analysis.cited_standards(text). Each document gets (or keeps) a
    library row; the citation for this opportunity is replaced with the current one.
    """
    opp_id = _opp_attr(opportunity, "id")
    sol = _opp_attr(opportunity, "solicitation_number") or ""
    title = _opp_attr(opportunity, "title") or ""
    now = datetime.utcnow().isoformat(timespec="seconds")
    items = _cited_items(cited)
    by_base: dict[str, list[dict]] = {}
    for p in items:
        by_base.setdefault(p["base_id"], []).append(p)
    results = []
    for base, refs in by_base.items():
        row = get_or_create_row(db, base, source="solicitation")
        kept = [c for c in (row.citations or []) if c.get("opportunity_id") != opp_id]
        seen_as = set()
        for p in refs:
            if p["cited_as"].upper() in seen_as:
                continue
            seen_as.add(p["cited_as"].upper())
            kept.append({
                "opportunity_id": opp_id,
                "solicitation_number": sol,
                "title": title,
                "cited_as": p["cited_as"],
                "revision": p["revision"],
                "change": p["change"],
                "count": p["count"],
                "seen_at": now,
            })
        row.citations = kept  # new list so the JSON column is marked dirty
        row.updated_at = datetime.utcnow()
        for p in refs:
            results.append(_check_result(p, row))
    db.commit()
    return results


def revision_check(db: Session, cited: list[dict]) -> list[dict]:
    """Same output as record_cited_standards, without writing anything."""
    items = _cited_items(cited)
    if not items:
        return []
    bases = {p["base_id"] for p in items}
    rows = {r.base_id: r for r in db.scalars(select(StandardEntry).where(StandardEntry.base_id.in_(bases))).all()}
    return [_check_result(p, rows.get(p["base_id"])) for p in items]


# ------------------------------------------------------------------ import of exported lists
IMPORT_ALIASES = {
    "id": ["document id", "document number", "doc id", "document identifier", "document", "doc number", "doc no",
           "identifier", "doc", "id", "number", "specification", "standard", "spec", "document no"],
    "title": ["title", "document title", "doc title", "name", "description"],
    "status": ["status", "document status", "doc status"],
    "date": ["doc date", "document date", "date", "revision date", "publication date", "pub date", "issue date"],
    "revision": ["revision", "rev", "revision letter", "current revision"],
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (h or "").lower()).strip()


def _map_import_headers(row: list[str]) -> dict[str, int]:
    normed = [re.sub(r"\s+", " ", _norm_header(h)) for h in row]
    mapping: dict[str, int] = {}
    for field, aliases in IMPORT_ALIASES.items():
        for alias in aliases:
            idx = next((i for i, h in enumerate(normed) if h == alias and i not in mapping.values()), None)
            if idx is not None:
                mapping[field] = idx
                break
    return mapping


def import_rows(db: Session, rows: list[list[str]], save_to_library: bool = False) -> dict:
    """Upsert documents from a tabular export (ASSIST, EverySpec or your own list)."""
    header_idx, mapping = None, {}
    for i, r in enumerate(rows[:15]):
        m = _map_import_headers(r)
        if "id" in m:
            header_idx, mapping = i, m
            break
    if header_idx is None:
        mapping = {"id": 0, "title": 1}
        data = rows
    else:
        data = rows[header_idx + 1:]
    existing = {r.base_id: r for r in db.scalars(select(StandardEntry)).all()}
    created = updated = skipped = 0

    def cell(r: list[str], field: str) -> str:
        i = mapping.get(field)
        return (r[i] if i is not None and i < len(r) and r[i] is not None else "").strip()

    for r in data:
        raw_id = cell(r, "id")
        if not raw_id or not re.search(r"\d", raw_id):
            skipped += 1
            continue
        p = parse_doc_id_full(raw_id)
        base = p["base_id"]
        listed_rev = cell(r, "revision") or p["revision"]
        title, status, date = cell(r, "title")[:500], cell(r, "status")[:120], cell(r, "date")[:40]
        row = existing.get(base)
        if row is None:
            row = get_or_create_row(db, base, source="import")
            existing[base] = row
            created += 1
        else:
            updated += 1
        if title and not row.title:
            row.title = title
        if status:
            row.status = status
        if date:
            row.doc_date = date
        if listed_rev:
            row.listed_revision = listed_rev[:40]
        if save_to_library:
            row.in_library = True
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "total": created + updated}
