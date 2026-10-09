"""Writing tools: evaluator-style proposal review, sources sought / RFI response drafts, capability statements.

Notes on terms used here
- Adjectival ratings (Outstanding, Good, Acceptable, Marginal, Unacceptable) follow the technical rating scale
  commonly used in DoD source selections (DoD Source Selection Procedures). Agencies define their own scales in
  Section M, so every rating this module produces is labeled an estimate. Example of the scale in use:
  GAO decision B-410736, https://www.gao.gov/products/b-410736
- Strength / weakness / deficiency wording follows FAR 15.001 definitions ("deficiency" is a material failure to
  meet a Government requirement, or a combination of significant weaknesses that raises the risk of unsuccessful
  performance to an unacceptable level; a "weakness" is a flaw that increases that risk).
- SDVOSB and VOSB status: SBA VetCert certification is what counts for federal SDVOSB set-asides. A pending
  application is never described as a certification.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .analysis import _parse_json, html_to_text
from .models import CompanyProfile, Opportunity, Package, PackageSection
from .models_pp import PastPerformance
from .package_export import words
from .presets import FSC_TITLES, NAICS_TITLES

RATINGS = ["Outstanding", "Good", "Acceptable", "Marginal", "Unacceptable"]
ESTIMATE_NOTE = ("Ratings are an estimate using the adjectival scale common in DoD source selections. "
                 "The agency's own Section M definitions control.")
MIN_SECTION_WORDS = 75
DEFAULT_WORDS_PER_PAGE = 500


# ------------------------------------------------------------------ Claude
def ai_enabled() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def call_claude(system: str, user: str, max_tokens: int = 8000) -> str:
    """The one place this module talks to the Anthropic SDK (tests monkeypatch it)."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(model=config.ANTHROPIC_MODEL, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def no_dashes(s: str) -> str:
    return (s or "").replace(" — ", ", ").replace("—", ", ").replace(" ,", ",")


# ------------------------------------------------------------------ shared text helpers
_STOP = set("""a an and are as at be by for from has have in into is it its of on or that the this to was were will with
within without shall should may must any all each per other such than then these those their there which who whom
contractor government offeror offerors provide provided provides including include includes item items services service
work required requirement requirements support new use used using under over not only also can our your you we they
factor factors approach proposal proposals evaluation evaluated subfactor volume section please describe""".split())


def tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9][a-z0-9\-/]*[a-z0-9]|[a-z0-9]", (text or "").lower()):
        if len(w) < 3 or w in _STOP or (w.isdigit() and len(w) < 4):
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def plain(text: str) -> str:
    text = text or ""
    if re.search(r"<(p|br|div|li|span|table)\b", text, re.I):
        text = html_to_text(text)
    return text


PLACEHOLDER_RE = re.compile(
    r"\[(?:[^\]\n]{0,60}?\b(?:insert|tbd|tbc|todo|add|fill|enter|confirm|placeholder|name|number|date|amount|phone|email)\b"
    r"[^\]\n]{0,60}|[A-Z][A-Z0-9 /&#.,'-]{2,60}|x{2,}|\?+|\.\.\.)\](?!\()|\bTBD\b|\bTBC\b|\bTODO\b|\bXXX+\b|lorem ipsum",
    re.I,
)


def find_placeholders(text: str) -> list[str]:
    hits = []
    for m in PLACEHOLDER_RE.finditer(text or ""):
        s = m.group(0)
        # Paragraph references such as [L.3.2] or [C.4] are citations, not blanks.
        if re.fullmatch(r"\[(?:[A-Z]\.)?[\d.]+\]|\[(?:Sec\.?|Section|PWS|SOW|FAR|DFARS)[^\]]*\]", s, re.I):
            continue
        if s not in hits:
            hits.append(s)
    return hits


# ------------------------------------------------------------------ 1. evaluator review
def section_label(s: dict) -> str:
    vol = re.sub(r"^(Volume\s+[IVX0-9]+).*", r"\1", s.get("volume") or "")
    if vol and (s.get("title") or "").lower().startswith(vol.lower()):
        vol = ""
    return " ".join(x for x in (vol, s.get("number"), s.get("title")) if x) or f"Section {s.get('id')}"


def _factor_category(factor: str) -> str:
    f = factor.lower()
    if "past perf" in f or "experience" in f or "reference" in f:
        return "Past performance"
    if re.search(r"price|cost", f):
        return "Pricing"
    if re.search(r"small business|subcontract", f):
        return "Small business"
    return "Technical / performance"


FACTOR_CATEGORY_KEYS = {
    "Past performance": ["past performance", "experience", "reference", "contract"],
    "Pricing": ["price", "pricing", "cost", "clin"],
    "Small business": ["small business", "subcontracting"],
    "Technical / performance": [],
}
REQ_CATEGORY_TO_FACTOR = {
    "Technical / performance": "Technical / performance", "Delivery": "Technical / performance",
    "Reporting": "Technical / performance", "Past performance": "Past performance", "Pricing": "Pricing",
}


def review_inputs(pkg: dict, analysis: dict | None) -> dict:
    """Collect what an evaluator would look at. pkg is packages_api.package_full(); analysis has breakdown + matrix."""
    breakdown = (analysis or {}).get("breakdown") or {}
    matrix = (analysis or {}).get("compliance_matrix") or pkg.get("matrix") or []
    factors = [str(f) for f in breakdown.get("evaluation_factors") or [] if str(f).strip()]
    method = breakdown.get("evaluation_method") or ""
    if not factors:
        factors = ["Technical capability"]
        if re.search(r"past performance", json.dumps(breakdown).lower()) or any(r.get("category") == "Past performance" for r in matrix):
            factors.append("Past performance")
        factors.append("Price")
    return {
        "sections": pkg.get("sections") or [], "matrix": matrix, "factors": factors, "method": method,
        "instructions": breakdown.get("submission_instructions") or "",
        "page_limits": [str(x) for x in breakdown.get("page_limits") or []],
        "words_per_page": int((pkg.get("cover") or {}).get("words_per_page") or DEFAULT_WORDS_PER_PAGE),
    }


def _limit_targets(limit_text: str, sections: list[dict]) -> tuple[float | None, list[dict], str]:
    m = re.search(r"(\d+(?:\.\d+)?)\s+pages?", limit_text, re.I)
    if not m:
        return None, [], ""
    n = float(m.group(1))
    low = limit_text.lower()
    for key in ("executive summary", "past performance", "technical", "management", "price", "pricing", "cost", "staffing",
                "quality", "transition", "small business"):
        if key in low:
            hit = [s for s in sections if key in f"{s.get('volume')} {s.get('title')}".lower()]
            if key in ("price", "pricing", "cost"):
                hit = [s for s in sections if re.search(r"price|pricing|cost", f"{s.get('volume')} {s.get('title')}".lower())]
            if hit:
                return n, hit, key
    if re.search(r"\b(entire|total|whole|overall)\b|proposal|quote|response|capabilit", low):
        return n, sections, "whole package"
    return n, [], ""


def page_limit_issues(inp: dict) -> list[dict]:
    wpp = inp["words_per_page"] or DEFAULT_WORDS_PER_PAGE
    issues = []
    for s in inp["sections"]:
        if s.get("page_limit"):
            est = round(words(s.get("content")) / wpp, 1)
            if est > float(s["page_limit"]):
                issues.append({"section_id": s["id"], "limit": s["page_limit"], "estimated_pages": est,
                               "issue": f"{section_label(s)} is about {est} pages against a {s['page_limit']:g} page limit."})
    for text in inp["page_limits"]:
        n, secs, key = _limit_targets(text, inp["sections"])
        if not n or not secs:
            continue
        est = round(sum(words(s.get("content")) for s in secs) / wpp, 1)
        if est > n:
            issues.append({"section_id": secs[0]["id"] if len(secs) == 1 else None, "limit": n, "estimated_pages": est,
                           "issue": f"Solicitation limit \"{text.strip()}\": the {key} sections run about {est} pages."})
    return issues


def _rating_from(deficiencies: int, weaknesses: int, strengths: int) -> str:
    if deficiencies:
        return "Unacceptable"
    if weaknesses >= 2:
        return "Marginal"
    if weaknesses == 1 or strengths < 2:
        return "Acceptable"
    return "Good"  # rules cannot judge quality well enough to call anything Outstanding


def rule_review(pkg: dict, analysis: dict | None) -> dict:
    inp = review_inputs(pkg, analysis)
    sections = inp["sections"]
    wpp = inp["words_per_page"]
    covered_in = {rid: s for s in sections for rid in (s.get("covered_ids") or [])}
    assigned_in = {rid: s for s in sections for rid in (s.get("requirement_ids") or [])}
    fixes: list[dict] = []
    sec_notes: dict[int, dict] = {s["id"]: {"weak": [], "def": [], "strong": [], "risk": []} for s in sections}

    # Compliance against the matrix
    compliance = []
    for r in inp["matrix"]:
        rid = r.get("id")
        req = r.get("requirement") or ""
        if rid in covered_in:
            s = covered_in[rid]
            compliance.append({"requirement_id": rid, "status": "met", "where": section_label(s), "note": "Marked covered by the writer."})
            continue
        s = assigned_in.get(rid)
        if s is None:
            compliance.append({"requirement_id": rid, "status": "missing", "where": "", "note": "Not assigned to any section."})
            fixes.append({"priority": 1, "section_id": None, "action": f"Assign and answer requirement {r.get('reference') or rid}: {req[:140]}"})
            continue
        req_t = tokens(req)
        overlap = len(req_t & tokens(s.get("content"))) / max(len(req_t), 1)
        if words(s.get("content")) and overlap >= 0.5:
            compliance.append({"requirement_id": rid, "status": "partial", "where": section_label(s),
                               "note": "The text appears to touch this requirement but it is not marked covered. Check it answers every part, then mark it."})
            fixes.append({"priority": 2, "section_id": s["id"], "action": f"Confirm requirement {r.get('reference') or rid} is fully answered and mark it covered."})
        else:
            compliance.append({"requirement_id": rid, "status": "missing", "where": section_label(s),
                               "note": "Assigned here but not answered or not marked covered."})
            fixes.append({"priority": 1, "section_id": s["id"], "action": f"Answer requirement {r.get('reference') or rid} explicitly: {req[:140]}"})

    # Section-level checks
    for s in sections:
        n = words(s.get("content"))
        notes = sec_notes[s["id"]]
        if n == 0:
            notes["def"].append(f"{section_label(s)} is empty.")
            fixes.append({"priority": 1, "section_id": s["id"], "action": f"Write {section_label(s)}; it is empty."})
        elif n < MIN_SECTION_WORDS:
            notes["weak"].append(f"{section_label(s)} is only {n} words, too thin to earn credit.")
            fixes.append({"priority": 2, "section_id": s["id"], "action": f"Expand {section_label(s)} ({n} words) with specifics: how, who, when, and proof."})
        else:
            notes["strong"].append(f"{section_label(s)} is drafted ({n} words).")
        ph = find_placeholders(s.get("content"))
        if ph:
            notes["weak"].append(f"{section_label(s)} still has placeholders: {', '.join(ph[:5])}.")
            fixes.append({"priority": 1, "section_id": s["id"], "action": f"Replace placeholders in {section_label(s)}: {', '.join(ph[:5])}."})

    limits = page_limit_issues(inp)
    for li in limits:
        fixes.append({"priority": 1, "section_id": li.get("section_id"), "action": f"Cut to the page limit. {li['issue']} Pages over the limit are often not read."})
        if li.get("section_id") in sec_notes:
            sec_notes[li["section_id"]]["risk"].append(li["issue"])

    # Missing standard volumes
    titles = " ".join(f"{s.get('volume')} {s.get('title')}".lower() for s in sections)
    has_pp_sec = "past performance" in titles or "experience" in titles
    has_price_sec = bool(re.search(r"price|pricing|cost", titles))
    if not has_pp_sec:
        fixes.append({"priority": 1 if any("past perf" in f.lower() for f in inp["factors"]) else 2, "section_id": None,
                      "action": "Add a past performance section (relevant contracts, customer, value, period, and reference contacts)."})
    if not has_price_sec:
        fixes.append({"priority": 1 if any(re.search(r"price|cost", f.lower()) for f in inp["factors"]) else 2, "section_id": None,
                      "action": "Add a price section or confirm where pricing is submitted (price volume, schedule, or SF 1449)."})

    # Factor cards
    factor_cards = []
    for f in inp["factors"]:
        cat = _factor_category(f)
        keys = [k for k in tokens(re.sub(r"^factor\s*\d+\s*[:\-]?", "", f, flags=re.I)) if len(k) >= 4] or [cat.lower()]
        keys += FACTOR_CATEGORY_KEYS.get(cat, [])
        linked = [s for s in sections if any(k in f"{s.get('volume')} {s.get('title')} {s.get('content')}".lower() for k in keys)]
        if cat == "Technical / performance" and not linked:
            linked = [s for s in sections if not re.search(r"price|pricing|cost|past performance", f"{s.get('volume')} {s.get('title')}".lower())
                      and words(s.get("content"))]
        card = {"factor": f, "rating": "Acceptable", "strengths": [], "weaknesses": [], "deficiencies": [], "risks": [],
                "section_ids": [s["id"] for s in linked]}
        if not linked:
            card["deficiencies"].append(f"No section addresses this factor (looked for: {', '.join(keys[:6])}).")
            fixes.append({"priority": 1, "section_id": None, "action": f"Add content that answers the evaluation factor \"{f}\" using its own wording."})
        for s in linked:
            n = sec_notes[s["id"]]
            card["strengths"] += n["strong"]
            card["weaknesses"] += n["weak"]
            card["deficiencies"] += n["def"]
            card["risks"] += n["risk"]
        missing = [c for c in compliance if c["status"] == "missing"
                   and REQ_CATEGORY_TO_FACTOR.get(next((r.get("category") for r in inp["matrix"] if r.get("id") == c["requirement_id"]), ""), "") == cat]
        if missing:
            card["deficiencies"].append(f"{len(missing)} requirement(s) tied to this factor are unanswered: " + ", ".join(str(c["requirement_id"]) for c in missing[:10]) + ".")
        met = [c for c in compliance if c["status"] == "met"
               and REQ_CATEGORY_TO_FACTOR.get(next((r.get("category") for r in inp["matrix"] if r.get("id") == c["requirement_id"]), ""), "") == cat]
        if met:
            card["strengths"].append(f"{len(met)} related requirement(s) marked covered.")
        card["rating"] = _rating_from(len(card["deficiencies"]), len(card["weaknesses"]) + len(card["risks"]), len(card["strengths"]))
        if cat == "Pricing":
            card["rating"] = "Acceptable" if linked and not card["deficiencies"] else card["rating"]
            card["risks"].append("Price is usually evaluated for reasonableness, not rated adjectivally. Check Section M.")
        factor_cards.append(card)

    # Overall
    missing_n = sum(1 for c in compliance if c["status"] == "missing")
    partial_n = sum(1 for c in compliance if c["status"] == "partial")
    worst = max((RATINGS.index(c["rating"]) for c in factor_cards), default=2)
    if missing_n and worst < RATINGS.index("Marginal"):
        worst = RATINGS.index("Marginal")
    rating = RATINGS[worst]
    total_words = sum(words(s.get("content")) for s in sections)
    summary = (f"Rule-based check of {len(sections)} sections (about {round(total_words / wpp, 1)} pages). "
               f"{len(inp['matrix']) - missing_n - partial_n} of {len(inp['matrix'])} matrix requirements marked covered, "
               f"{partial_n} possibly covered, {missing_n} unanswered. {len(limits)} page limit issue(s). "
               "Rules check completeness and compliance only; they cannot judge persuasiveness. " + ESTIMATE_NOTE)
    if not inp["matrix"]:
        summary = "No compliance matrix is linked (analyze the opportunity first), so requirement coverage was not checked. " + summary

    fixes = _dedupe_fixes(fixes)
    return {"overall": {"rating": rating, "summary": summary, "estimate": True}, "factors": factor_cards,
            "compliance": compliance, "page_limit_issues": [li["issue"] for li in limits], "fixes": fixes,
            "stats": {"sections": len(sections), "words": total_words, "est_pages": round(total_words / wpp, 1),
                      "requirements": len(inp["matrix"]), "missing": missing_n, "partial": partial_n}}


def _dedupe_fixes(fixes: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in sorted(fixes, key=lambda x: int(x.get("priority") or 3)):
        key = (f.get("section_id"), f.get("action"))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


REVIEW_SYSTEM = """You are a U.S. government source selection evaluator reviewing a small business proposal draft.
Evaluate strictly against the solicitation's instructions (Section L), evaluation factors and method (Section M),
page limits and the compliance matrix. Use FAR 15.001 meanings: a strength exceeds a requirement in a way that benefits
the Government; a weakness is a flaw that increases the risk of unsuccessful performance; a deficiency is a material
failure to meet a requirement. Rate with the adjectival scale common in DoD source selections:
Outstanding | Good | Acceptable | Marginal | Unacceptable. These ratings are estimates.
Cite section ids. Be specific and terse. No em dashes.
Return ONLY a JSON object, no prose, with exactly this shape:
{"overall": {"rating": "Outstanding|Good|Acceptable|Marginal|Unacceptable", "summary": "3-5 sentences"},
 "factors": [{"factor": "", "rating": "", "strengths": [""], "weaknesses": [""], "deficiencies": [""], "risks": [""], "section_ids": [0]}],
 "compliance": [{"requirement_id": 0, "status": "met|partial|missing", "where": "section label", "note": ""}],
 "page_limit_issues": [""],
 "fixes": [{"priority": 1, "section_id": 0, "action": ""}]}
Include one compliance row per matrix requirement. priority: 1 = must fix before submission, 2 = should fix, 3 = polish.
Use null for section_id when a fix is not tied to one section."""


def review_prompt(pkg: dict, analysis: dict | None) -> str:
    inp = review_inputs(pkg, analysis)
    covered = {rid for s in inp["sections"] for rid in (s.get("covered_ids") or [])}
    parts = [f"Package: {pkg.get('name')}"]
    if pkg.get("opportunity"):
        o = pkg["opportunity"]
        parts.append(f"Solicitation: {o.get('solicitation_number')} {o.get('title')} ({o.get('agency')})")
    parts += [f"Evaluation method: {inp['method'] or 'not stated'}",
              "Evaluation factors:\n" + "\n".join(f"- {f}" for f in inp["factors"]),
              f"Submission instructions: {inp['instructions'] or 'not captured'}",
              "Page limits: " + ("; ".join(inp["page_limits"]) or "none captured") + f" (assume {inp['words_per_page']} words per page)"]
    if inp["matrix"]:
        parts.append("Compliance matrix (id | reference | category | writer marked covered | requirement):\n" + "\n".join(
            f"{r.get('id')} | {r.get('reference') or ''} | {r.get('category') or ''} | {'yes' if r.get('id') in covered else 'no'} | {(r.get('requirement') or '')[:400]}"
            for r in inp["matrix"][:250]))
    budget = 140_000
    for s in inp["sections"]:
        body = (s.get("content") or "")[: max(0, budget)]
        budget -= len(body)
        parts.append(f'<section id="{s["id"]}" label="{section_label(s)}" page_limit="{s.get("page_limit") or ""}" '
                     f'words="{words(s.get("content"))}" assigned="{s.get("requirement_ids") or []}">\n{body or "(empty)"}\n</section>')
    return "\n\n".join(parts)


def _normalize_review(data: dict, pkg: dict) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("overall"), dict):
        raise ValueError("Review JSON is missing 'overall'")
    sec_ids = {s["id"] for s in pkg.get("sections") or []}

    def rating(x):
        x = str(x or "").strip().title()
        return x if x in RATINGS else "Acceptable"

    def lst(x):
        return [no_dashes(str(i)) for i in x] if isinstance(x, list) else ([no_dashes(str(x))] if x else [])

    def sid(x):
        try:
            x = int(x)
        except (TypeError, ValueError):
            return None
        return x if x in sec_ids else None

    out = {"overall": {"rating": rating(data["overall"].get("rating")), "summary": no_dashes(str(data["overall"].get("summary") or "")) + " " + ESTIMATE_NOTE,
                       "estimate": True}, "factors": [], "compliance": [], "page_limit_issues": lst(data.get("page_limit_issues")), "fixes": []}
    for f in data.get("factors") or []:
        if isinstance(f, dict):
            out["factors"].append({"factor": str(f.get("factor") or ""), "rating": rating(f.get("rating")),
                                   **{k: lst(f.get(k)) for k in ("strengths", "weaknesses", "deficiencies", "risks")},
                                   "section_ids": [i for i in (sid(x) for x in (f.get("section_ids") or [])) if i]})
    for c in data.get("compliance") or []:
        if isinstance(c, dict):
            st = str(c.get("status") or "").lower()
            out["compliance"].append({"requirement_id": c.get("requirement_id"), "status": st if st in ("met", "partial", "missing") else "partial",
                                      "where": str(c.get("where") or ""), "note": no_dashes(str(c.get("note") or ""))})
    for x in data.get("fixes") or []:
        if isinstance(x, dict) and x.get("action"):
            try:
                pr = min(3, max(1, int(x.get("priority") or 2)))
            except (TypeError, ValueError):
                pr = 2
            out["fixes"].append({"priority": pr, "section_id": sid(x.get("section_id")), "action": no_dashes(str(x["action"]))})
    return out


def claude_review(pkg: dict, analysis: dict | None) -> dict:
    data = _parse_json(call_claude(REVIEW_SYSTEM, review_prompt(pkg, analysis), max_tokens=12000))
    result = _normalize_review(data, pkg)
    # Deterministic checks the model can miss: measured page counts and leftover placeholders.
    rules = rule_review(pkg, analysis)
    for issue in rules["page_limit_issues"]:
        if issue not in result["page_limit_issues"]:
            result["page_limit_issues"].append(issue)
    have = {(f["section_id"], f["action"]) for f in result["fixes"]}
    for f in rules["fixes"]:
        if f["action"].startswith(("Replace placeholders", "Cut to the page limit")) and (f["section_id"], f["action"]) not in have:
            result["fixes"].append(f)
    result["fixes"] = _dedupe_fixes(result["fixes"])
    result["stats"] = rules["stats"]
    return result


def review_package(pkg: dict, analysis: dict | None) -> tuple[str, dict]:
    """Returns (method, result). method is 'claude' or 'rules'. Falls back to rules if the AI call or its JSON fails."""
    if ai_enabled():
        try:
            return "claude", claude_review(pkg, analysis)
        except Exception as exc:  # noqa: BLE001
            r = rule_review(pkg, analysis)
            r["overall"]["summary"] = f"AI review failed ({exc.__class__.__name__}); showing the rule-based review. " + r["overall"]["summary"]
            r["ai_error"] = str(exc)[:300]
            return "rules", r
    return "rules", rule_review(pkg, analysis)


# ------------------------------------------------------------------ 2. sources sought / RFI
SS_TITLE_RE = re.compile(r"sources?[\s-]+sought|\bRFI\b|request\s+for\s+information|market\s+(research|survey)", re.I)
SS_BODY_RE = re.compile(
    r"sources?[\s-]+sought|request\s+for\s+information|\bRFI\b|for\s+market\s+research\s+purposes|market\s+research\s+(only|purposes)"
    r"|capabilit(?:y|ies)\s+statements?\s+(?:is\s+|are\s+)?(?:requested|request|due|shall|should|must|will)"
    r"|(?:submit|provide)\s+(?:a\s+|your\s+)?capabilit(?:y|ies)\s+statements?", re.I)


def is_sources_sought(notice_type: str = "", title: str = "", description: str = "") -> bool:
    nt = (notice_type or "").lower()
    if "award" in nt:
        return False
    if "sources sought" in nt or "special notice" in nt and SS_TITLE_RE.search(title or ""):
        return True
    if SS_TITLE_RE.search(title or "") or SS_TITLE_RE.search(notice_type or ""):
        return True
    return bool(SS_BODY_RE.search(plain(description)[:20000]))


REQUEST_VERBS = r"(provide|describe|identify|include|list|state|indicate|submit|explain|confirm|discuss|demonstrate|detail|specify|what|how|does|do|is|are|can|will|has|have|please)"
REQUEST_KEYS = r"(name|uei|cage|size|socioeconomic|naics|past performance|capabilit|experience|point of contact|poc|address|business type|set-aside|teaming|lead time|schedule|price|cost|recommend)"


def extract_requests(text: str) -> list[str]:
    """Pull numbered or bulleted questions and requested items from notice text, in order."""
    text = plain(text)
    out: list[str] = []

    def add(s: str):
        s = re.sub(r"\s+", " ", s).strip(" -:;")
        if 12 <= len(s) <= 500 and s.lower() not in {x.lower() for x in out}:
            out.append(s)

    for line in text.replace("\r", "\n").split("\n"):
        m = re.match(r"^\s*(?:\(?\d{1,2}[.)]|\(?[a-hA-H][.)]|[ivx]{1,4}[.)]|[•\-\*▪●o])\s+(.+)", line)
        if not m:
            continue
        body = m.group(1).strip()
        if "?" in body or re.match(REQUEST_VERBS + r"\b", body, re.I) or re.search(REQUEST_KEYS, body, re.I):
            add(body)
    for m in re.finditer(r"[^.?!\n]{10,300}\?", text):
        add(m.group(0))
    return out[:30]


def status_statements(profile: CompanyProfile, naics: str = "") -> dict:
    """Honest size and socioeconomic wording from the profile. Pending applications are never called certifications."""
    certs = profile.certifications or {}
    small = (profile.small_under_naics or {}).get(naics) if naics else None
    socio = []
    sd, vo = certs.get("SDVOSB", "none"), certs.get("VOSB", "none")
    if sd == "certified":
        socio.append("SBA-certified Service-Disabled Veteran-Owned Small Business (SDVOSB, VetCert)")
    elif sd == "pending":
        socio.append("Service-disabled veteran-owned small business; SBA VetCert application pending (not yet certified as an SDVOSB)")
    if vo == "certified" and sd != "certified":
        socio.append("SBA-certified Veteran-Owned Small Business (VOSB, VetCert)")
    elif vo == "pending" and sd not in ("certified", "pending"):
        socio.append("Veteran-owned small business; SBA VetCert VOSB application pending (not yet certified)")
    labels = {"8A": "SBA 8(a) Business Development participant", "HUBZONE": "SBA-certified HUBZone small business",
              "WOSB": "Women-Owned Small Business (WOSB)", "EDWOSB": "Economically Disadvantaged Women-Owned Small Business (EDWOSB)"}
    for k, label in labels.items():
        st = certs.get(k, "none")
        if st == "certified":
            socio.append(label)
        elif st == "pending":
            socio.append(f"{k if k != 'HUBZONE' else 'HUBZone'} application pending (not yet certified)")
    if naics:
        if small is True:
            size = f"Small business under NAICS {naics} (self-represented in SAM)"
        elif small is False:
            size = f"Other than small under NAICS {naics}"
        else:
            size = f"[Confirm business size under the SBA size standard for NAICS {naics}]"
    else:
        size = "Small business (self-represented in SAM)" if certs.get("SB") in ("certified", "pending") or any(v == "certified" for v in certs.values()) else "[Confirm business size]"
    return {"size": size, "socioeconomic": socio, "small_under_notice_naics": small}


def naics_comment(profile: CompanyProfile, naics: str) -> str:
    codes = list(profile.naics_codes or [])
    if not naics:
        return "The notice does not list a NAICS code. Our registered NAICS codes: " + (", ".join(f"{c} ({NAICS_TITLES.get(c, '')})".replace(" ()", "") for c in codes) or "[list NAICS codes]") + "."
    title = NAICS_TITLES.get(naics, "")
    small = (profile.small_under_naics or {}).get(naics)
    size_bit = (" We are small under its size standard." if small is True else
                " We are not small under its size standard." if small is False else
                " [Confirm we are small under its SBA size standard.]")
    if naics in codes:
        return f"The notice's NAICS {naics}{f' ({title})' if title else ''} is registered in our SAM profile.{size_bit}"
    others = ", ".join(f"{c}{f' ({NAICS_TITLES[c]})' if c in NAICS_TITLES else ''}" for c in codes[:4])
    return (f"NAICS {naics}{f' ({title})' if title else ''} is not currently in our SAM registration"
            f"{'; related codes we hold: ' + others if others else ''}. [Add it to SAM if we intend to compete.]{size_bit}")


def _pp_records(db: Session, text: str, limit: int = 3) -> list[PastPerformance]:
    from .past_performance_api import match_past_performance

    ids = [m["id"] for m in match_past_performance(db, text, limit=limit)]
    recs = [db.get(PastPerformance, i) for i in ids]
    return [r for r in recs if r]


ROLE_SHORT = {"prime": "Prime", "sub": "Subcontract", "commercial": "Commercial", "personal_project": "Company project",
              "employment": "Principal's prior employment"}
ROLE_WORDS = {"prime": "Prime contractor", "sub": "Subcontractor", "commercial": "Commercial customer work",
              "personal_project": "Company-funded or personal project (not a government contract)", "employment": "Experience of our principal while employed elsewhere (not a company contract)"}


def pp_line(p: PastPerformance) -> str:
    bits = [f"**{p.title or 'Project'}**"]
    who = " / ".join(x for x in (p.customer, p.agency) if x)
    if who:
        bits.append(who)
    bits.append(ROLE_WORDS.get(p.role, p.role))
    if p.contract_number:
        bits.append(f"Contract {p.contract_number}")
    if p.value is not None:
        bits.append(f"${p.value:,.0f}")
    period = " to ".join(x for x in (p.start_date, p.end_date or ("present" if p.start_date else "")) if x)
    if period:
        bits.append(period)
    line = ", ".join(bits) + "."
    desc = (p.description or "").strip().replace("\n", " ")
    if desc:
        line += " " + (desc[:350] + ("..." if len(desc) > 350 else ""))
    if p.results:
        line += " Results: " + p.results.strip().replace("\n", " ")[:200]
    return line


def get_capability_settings(db: Session):
    from .models_writing import CapabilitySettings

    s = db.get(CapabilitySettings, 1)
    if s is None:
        s = CapabilitySettings(id=1, competencies=[], differentiators=[], past_performance_ids=[])
        db.add(s)
        db.commit()
    return s


def poc_lines(settings) -> list[str]:
    name = settings.contact_name or "[Contact name]"
    title = settings.contact_title or "[Title]"
    return [f"{name}, {title}", f"Phone: {settings.contact_phone or '[Phone]'}", f"Email: {settings.contact_email or '[Email]'}"] + \
           ([f"Website: {settings.website}"] if settings.website else [])


def _answer_for(q: str, ctx: dict) -> str:
    ql = q.lower()
    if re.search(r"socio|business size|size status|small business|set-aside|type of business|business type|sdvosb|veteran", ql):
        return "; ".join([ctx["status"]["size"]] + ctx["status"]["socioeconomic"]) + "."
    if re.search(r"\buei\b|\bcage\b|duns|sam registration|unique entity", ql):
        return f"UEI {ctx['uei']}; CAGE {ctx['cage']}; SAM registration {ctx['sam']}."
    if re.search(r"naics", ql):
        return ctx["naics_comment"]
    if re.search(r"past performance|experience|similar|previous|prior contract|reference", ql):
        return ("\n".join(f"- {line}" for line in ctx["pp"]) if ctx["pp"]
                else "[Describe relevant contracts or projects: customer, scope, value, period, and a reference.]")
    if re.search(r"point of contact|\bpoc\b|contact information", ql):
        return "; ".join(ctx["poc"]) + "."
    if re.search(r"capabilit|able to|ability|can you|manufactur|perform|provide the|approach", ql):
        caps = ctx["capabilities"]
        lead = "[State directly whether we can meet this requirement and how.]"
        return lead + ("\n" + "\n".join(f"- {c}" for c in caps[:6]) if caps else "")
    return "[Answer this question directly.]"


def sources_sought_context(db: Session, opp: Opportunity) -> dict:
    from .services import get_profile

    profile = get_profile(db)
    settings = get_capability_settings(db)
    a = opp.analysis
    corpus = "\n".join(x for x in (plain(opp.description), (a.breakdown or {}).get("submission_instructions", "") if a else "",
                                   (a.breakdown or {}).get("scope", "") if a else "") if x)
    sam = {"active": "active" + (f" (expires {profile.sam_expiration})" if profile.sam_expiration else ""),
           "pending": "pending", "expired": "expired [renew before responding]"}.get(profile.sam_status, "[confirm SAM registration status]")
    pp = _pp_records(db, f"{opp.title}\n{opp.naics}\n{corpus}", limit=3)
    caps = list(settings.competencies or []) or list(profile.keywords or [])
    return {
        "profile": profile, "settings": settings, "requests": extract_requests(corpus), "corpus": corpus,
        "name": profile.name or "[Company name]", "uei": profile.uei or "[UEI]", "cage": profile.cage or "[CAGE code]", "sam": sam,
        "status": status_statements(profile, opp.naics), "naics_comment": naics_comment(profile, opp.naics),
        "pp_records": pp, "pp": [pp_line(p) for p in pp], "capabilities": caps, "poc": poc_lines(settings),
    }


def _gov_contact(opp: Opportunity) -> str:
    for c in opp.contacts or []:
        if isinstance(c, dict) and (c.get("fullName") or c.get("name") or c.get("email")):
            return ", ".join(x for x in (c.get("fullName") or c.get("name"), c.get("email")) if x)
    return ""


def template_sources_sought(opp: Opportunity, ctx: dict) -> str:
    st = ctx["status"]
    kind = opp.notice_type if SS_TITLE_RE.search(opp.notice_type or "") or "sources sought" in (opp.notice_type or "").lower() else (
        "Request for Information" if re.search(r"\bRFI\b|request\s+for\s+information", f"{opp.title} {opp.description}", re.I) else "Sources Sought")
    gc = _gov_contact(opp)
    L = [f"# Response to {kind}: {opp.title}", "",
         f"- **Notice number:** {opp.solicitation_number or '[notice number]'}",
         f"- **Agency:** {opp.agency or '[agency]'}",
         f"- **Submitted to:** {gc or '[contracting officer name and email]'}",
         f"- **Submitted by:** {ctx['name']}", "- **Date:** [date]", "",
          "## 1. Company information", "", "| Item | Detail |", "|---|---|",
          f"| Company name | {ctx['name']} |", f"| UEI | {ctx['uei']} |", f"| CAGE code | {ctx['cage']} |",
          f"| SAM registration | {ctx['sam']} |", f"| Business size | {st['size']} |",
          f"| Socioeconomic status | {'; '.join(st['socioeconomic']) or 'None claimed'} |",
          f"| Point of contact | {'; '.join(ctx['poc'])} |", "",
          "## 2. NAICS code and size standard", "", ctx["naics_comment"], ""]
    n = 3
    if ctx["requests"]:
        L += [f"## {n}. Responses to the notice's questions", ""]
        for i, q in enumerate(ctx["requests"], 1):
            L += [f"### {n}.{i} {q[:160]}", "", _answer_for(q, ctx), ""]
        n += 1
    L += [f"## {n}. Relevant capabilities", ""]
    L += ([f"- {c}" for c in ctx["capabilities"]] or ["[List the capabilities that match this requirement: processes, equipment, certifications, capacity.]"])
    n += 1
    L += ["", f"## {n}. Relevant past performance", ""]
    L += ([f"- {line}" for line in ctx["pp"]] or ["[Add relevant contracts or projects: customer, scope, value, period, reference.]"])
    if any(p.role in ("personal_project", "employment") for p in ctx["pp_records"]):
        L += ["", "_Some entries above describe principal or company-funded work rather than government contracts, as labeled._"]
    n += 1
    L += ["", f"## {n}. Point of contact", ""] + [f"- {x}" for x in ctx["poc"]]
    L += ["", "_This response is for market research and planning purposes and is not a proposal._", ""]
    return "\n".join(L)


SS_SYSTEM = """You draft responses to U.S. federal Sources Sought notices and Requests for Information for a small business.
Rules:
- Answer the notice's specific questions in order, numbered to match the notice, then give company data, capabilities,
  relevant past performance and point of contact. Aim for 2 to 5 pages. Plain, direct, specific. No marketing fluff. No em dashes.
- Use the size and socioeconomic status statements exactly as provided. Never call a pending certification a certification.
- Use only the facts provided. Where a needed fact is missing, insert a bracketed placeholder like [insert lead time].
- Describe each past performance entry with its stated role (prime, sub, commercial, personal project, employment); do not upgrade it.
- Output Markdown only (# title, ## sections, ### question headings, bullets, pipe tables)."""


def claude_sources_sought(opp: Opportunity, ctx: dict) -> str:
    st = ctx["status"]
    user = "\n\n".join([
        f"Notice: {opp.notice_type} {opp.solicitation_number} {opp.title}\nAgency: {opp.agency}\nNAICS: {opp.naics} PSC: {opp.psc}\nGovernment contact: {_gov_contact(opp)}",
        f"Notice text:\n{ctx['corpus'][:60000]}",
        "Questions and requested items found in the notice:\n" + ("\n".join(f"{i}. {q}" for i, q in enumerate(ctx["requests"], 1)) or "(none extracted; find them in the text)"),
        f"Company: {ctx['name']}; UEI {ctx['uei']}; CAGE {ctx['cage']}; SAM {ctx['sam']}",
        f"Size statement (use verbatim): {st['size']}",
        "Socioeconomic statements (use verbatim): " + ("; ".join(st["socioeconomic"]) or "none"),
        f"NAICS comment: {ctx['naics_comment']}",
        "Capabilities:\n" + "\n".join(f"- {c}" for c in ctx["capabilities"]),
        f"Company notes: {ctx['profile'].notes}" if ctx["profile"].notes else "",
        "Relevant past performance:\n" + ("\n".join(f"- {x}" for x in ctx["pp"]) or "(none on file)"),
        "Point of contact:\n" + "\n".join(ctx["poc"]),
    ])
    return no_dashes(call_claude(SS_SYSTEM, user, max_tokens=8000))


def ss_checklist(requests: list[str], md: str, ctx: dict) -> list[dict]:
    """What the notice asked for vs what the draft covers."""
    parts = re.split(r"\n(?=#{2,3}\s)", md or "")
    items = []
    for q in requests:
        qt = tokens(q)
        best, best_score = "", 0.0
        for p in parts:
            score = len(qt & tokens(p)) / max(len(qt), 1)
            if score > best_score:
                best, best_score = p, score
        if best_score >= 0.5:
            status = "needs input" if find_placeholders(best) else "covered"
        elif best_score >= 0.25:
            status = "partial"
        else:
            status = "missing"
        items.append({"item": q, "status": status, "source": "notice"})
    std = [("UEI stated", ctx["uei"] if not ctx["uei"].startswith("[") else None, r"\bUEI\b"),
           ("CAGE code stated", ctx["cage"] if not ctx["cage"].startswith("[") else None, r"\bCAGE\b"),
           ("Business size stated", None, r"business size|small business|other than small"),
           ("Socioeconomic status stated accurately", None, r"socioeconomic|veteran|8\(a\)|hubzone|women-owned|none claimed"),
           ("NAICS fit addressed", None, r"\bNAICS\b"),
           ("Relevant past performance", None, r"past performance"),
           ("Point of contact", None, r"point of contact|\bPOC\b")]
    for label, value, pat in std:
        if value and value in md:
            status = "covered"
        elif re.search(pat, md or "", re.I):
            status = "needs input" if value is None and label.startswith(("UEI", "CAGE")) else "covered"
        else:
            status = "missing"
        items.append({"item": label, "status": status, "source": "standard"})
    pend = [s for s in ctx["status"]["socioeconomic"] if "pending" in s]
    if pend and re.search(r"(SBA[- ])?certified\s+(SDVOSB|service[- ]disabled|VOSB|veteran)", md or "", re.I) and not any("SBA-certified" in s for s in ctx["status"]["socioeconomic"]):
        items.append({"item": "Draft appears to claim a certification that is only pending. Fix before sending.", "status": "missing", "source": "accuracy"})
    return items


def draft_sources_sought(db: Session, opp: Opportunity) -> dict:
    ctx = sources_sought_context(db, opp)
    method, warn = "template", ""
    md = ""
    if ai_enabled():
        try:
            md = claude_sources_sought(opp, ctx)
            method = "claude"
        except Exception as exc:  # noqa: BLE001
            warn = f"AI drafting failed ({exc.__class__.__name__}); showing the template."
    if not md:
        md = template_sources_sought(opp, ctx)
    return {"method": method, "markdown": md, "requests": ctx["requests"], "checklist": ss_checklist(ctx["requests"], md, ctx),
            "warning": warn, "past_performance": [{"id": p.id, "title": p.title} for p in ctx["pp_records"]]}


def markdown_docx_bytes(md: str, title: str = "") -> bytes:
    from docx import Document
    from docx.shared import Inches

    from .package_export import _setup, markdown_to_docx

    doc = Document()
    _setup(doc, "Calibri", 11)
    for s in doc.sections:
        s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Inches(1)
    body = md or ""
    m = re.match(r"^\s*#\s+(.+)\n", body)
    if m:
        doc.add_heading(m.group(1).strip(), level=1)
        body = body[m.end():]
    elif title:
        doc.add_heading(title, level=1)
    markdown_to_docx(doc, body, base_level=1)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def save_sources_sought_package(db: Session, opp: Opportunity, md: str) -> Package:
    from .services import get_profile

    profile = get_profile(db)
    label = opp.solicitation_number or (opp.title or "Notice")[:80]
    pkg = Package(name=f"{label} sources sought response"[:300], kind="proposal", opportunity_id=opp.id, status="draft",
                  due_date=opp.response_deadline or "",
                  cover={"solicitation_number": opp.solicitation_number, "agency": opp.agency, "volume_title": "Sources Sought Response",
                         "business_status": "", "font": "Calibri", "font_size": 11, "validity_days": None},
                  notes=f"Drafted {datetime.utcnow():%Y-%m-%d} from the sources sought tool for {profile.name or 'the company'}.")
    db.add(pkg)
    db.flush()
    db.add(PackageSection(package_id=pkg.id, position=0, title="Sources sought response", content=md or "", status="drafting",
                          guidance="Answer every question in the notice in order. Keep it to the page count the notice asks for (usually 2 to 5 pages)."))
    db.commit()
    db.refresh(pkg)
    return pkg


# ------------------------------------------------------------------ 3. capability statement
def cert_lines(profile: CompanyProfile) -> list[str]:
    certs = profile.certifications or {}
    out = []
    names = {"SDVOSB": "SDVOSB", "VOSB": "VOSB", "8A": "8(a)", "HUBZONE": "HUBZone", "WOSB": "WOSB", "EDWOSB": "EDWOSB"}
    for k, label in names.items():
        st = certs.get(k, "none")
        if st == "certified":
            out.append(f"SBA-certified {label}" + (" (VetCert)" if k in ("SDVOSB", "VOSB") else ""))
        elif st == "pending":
            out.append(f"{label}: " + ("VetCert application pending" if k in ("SDVOSB", "VOSB") else "application pending"))
    if certs.get("SDVOSB") == "certified" and "SBA-certified VOSB (VetCert)" in out:
        out.remove("SBA-certified VOSB (VetCert)")
    if certs.get("SB") in ("certified", "pending") or any(certs.get(k) == "certified" for k in names):
        out.insert(0, "Small business")
    if certs.get("SDVOSB") == "pending" and not any(o.startswith("SBA-certified SDVOSB") for o in out):
        out.append("Service-disabled veteran-owned")
    return out


def code_lines(codes: list[str], titles: dict) -> list[str]:
    return [f"{c} {titles[c]}" if c in titles else c for c in codes or []]


def tailor_keywords(db: Session, settings, opp: Opportunity | None) -> dict:
    """Reorder competencies by overlap with the opportunity and pick the best-matching past performance."""
    comps = list(settings.competencies or [])
    pp_ids = list(settings.past_performance_ids or [])
    if not opp:
        return {"competencies": comps, "past_performance_ids": pp_ids, "tagline": settings.tagline}
    a = opp.analysis
    text = "\n".join(x for x in (opp.title, opp.naics, opp.psc, plain(opp.description), (a.breakdown or {}).get("scope", "") if a else "", a.summary if a else "") if x)
    ot = tokens(text)
    ranked = sorted(enumerate(comps), key=lambda ic: (-len(tokens(ic[1]) & ot), ic[0]))
    want = max(len(pp_ids), 3)
    matched = [m.id for m in _pp_records(db, text, limit=want)]
    picked = matched + [i for i in pp_ids if i not in matched]
    return {"competencies": [c for _, c in ranked], "past_performance_ids": picked[:want], "tagline": settings.tagline}


CAP_SYSTEM = """You tailor a small business capability statement to one federal opportunity.
Return ONLY JSON: {"tagline": "one line, under 90 characters", "competencies": ["short phrase", ...]}
Reorder and lightly reword the company's existing competencies so the most relevant come first, using the
opportunity's terms where they truthfully apply. Do not add capabilities the company did not list. No em dashes."""


def claude_tailor(settings, opp: Opportunity) -> dict:
    user = json.dumps({"opportunity": {"title": opp.title, "agency": opp.agency, "naics": opp.naics, "psc": opp.psc,
                                       "description": plain(opp.description)[:20000]},
                       "tagline": settings.tagline, "competencies": settings.competencies or [],
                       "differentiators": settings.differentiators or []})
    data = _parse_json(call_claude(CAP_SYSTEM, user, max_tokens=2000))
    comps = [no_dashes(str(c)) for c in data.get("competencies") or [] if str(c).strip()]
    return {"tagline": no_dashes(str(data.get("tagline") or settings.tagline)), "competencies": comps or list(settings.competencies or [])}


def capability_data(db: Session, opp: Opportunity | None = None, override: dict | None = None) -> dict:
    """Everything the PDF/DOCX needs. override: unsaved editor values (same keys as the settings)."""
    from .services import get_profile

    profile = get_profile(db)
    s = get_capability_settings(db)
    vals = {k: getattr(s, k) for k in ("tagline", "overview", "competencies", "differentiators", "past_performance_ids", "contact_name",
                                       "contact_title", "contact_phone", "contact_email", "website", "logo_file")}
    if override:
        vals.update({k: v for k, v in override.items() if k in vals and k != "logo_file"})
    if opp:
        class _S:  # lightweight view so tailor_keywords sees the override values
            pass
        view = _S()
        for k, v in vals.items():
            setattr(view, k, v)
        t = tailor_keywords(db, view, opp)
        vals["competencies"], vals["past_performance_ids"] = t["competencies"], t["past_performance_ids"]
    pps = [db.get(PastPerformance, i) for i in vals["past_performance_ids"] or []]
    logo = None
    if vals.get("logo_file"):
        p = config.UPLOAD_DIR / "capability" / Path(vals["logo_file"]).name
        logo = p if p.exists() else None
    return {
        "name": profile.name or "Company name", "uei": profile.uei, "cage": profile.cage,
        "sam_status": profile.sam_status, "certs": cert_lines(profile),
        "naics": code_lines(profile.naics_codes or [], NAICS_TITLES), "psc": code_lines(profile.psc_codes or [], FSC_TITLES),
        **{k: vals[k] for k in ("tagline", "overview", "contact_name", "contact_title", "contact_phone", "contact_email", "website")},
        "competencies": [c for c in vals["competencies"] or [] if str(c).strip()],
        "differentiators": [c for c in vals["differentiators"] or [] if str(c).strip()],
        "past_performance": [p for p in pps if p], "logo": logo,
        "tailored_for": f"{opp.solicitation_number} {opp.title}".strip() if opp else "",
    }


def _esc(s) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


NAVY = "#1F3A5F"
ACCENT = "#B8860B"


def _pp_flow_text(p: PastPerformance) -> tuple[str, str]:
    head = _esc(p.title or "Project")
    sub = ", ".join(_esc(x) for x in (" / ".join(y for y in (p.customer, p.agency) if y), ROLE_SHORT.get(p.role, p.role),
                                     p.contract_number, f"${p.value:,.0f}" if p.value is not None else "",
                                     " to ".join(x for x in (p.start_date, p.end_date) if x)) if x)
    desc = (p.description or "").strip().replace("\n", " ")
    if len(desc) > 260:
        desc = desc[:257].rsplit(" ", 1)[0] + "..."
    return f"<b>{head}</b><br/><font color='#555555'>{sub}</font>", _esc(desc)


def capability_pdf(data: dict) -> tuple[bytes, dict]:
    """Render the one-page statement. Returns (pdf_bytes, fit) where fit = {scale, shrunk, overflow}."""
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Frame, Paragraph, Spacer, Table, TableStyle

    W, H = letter
    M = 0.5 * inch
    gutter = 0.3 * inch
    col_w = (W - 2 * M - gutter) / 2

    def styles(k: float):
        return {
            "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11 * k, leading=13 * k, textColor=HexColor(NAVY), spaceBefore=6 * k, spaceAfter=3 * k),
            "b": ParagraphStyle("b", fontName="Helvetica", fontSize=9.5 * k, leading=12 * k, leftIndent=9 * k, bulletIndent=0, spaceAfter=2 * k),
            "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5 * k, leading=12.2 * k, spaceAfter=4 * k),
            "pp": ParagraphStyle("pp", fontName="Helvetica", fontSize=9 * k, leading=11.2 * k, spaceAfter=1 * k),
            "ppd": ParagraphStyle("ppd", fontName="Helvetica", fontSize=8.6 * k, leading=10.6 * k, spaceAfter=6 * k),
            "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.4 * k, leading=10.2 * k),
            "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.4 * k, leading=10.2 * k, textColor=HexColor(NAVY)),
        }

    def left_flows(st):
        f = [Paragraph("CORE COMPETENCIES", st["h"])]
        f += [Paragraph(_esc(c), st["b"], bulletText="•") for c in data["competencies"]] or [Paragraph("[Add core competencies]", st["p"])]
        if data["differentiators"]:
            f.append(Paragraph("DIFFERENTIATORS", st["h"]))
            f += [Paragraph(_esc(c), st["b"], bulletText="•") for c in data["differentiators"]]
        return f

    def right_flows(st):
        f = [Paragraph("PAST PERFORMANCE", st["h"])]
        if not data["past_performance"]:
            f.append(Paragraph("[Pick past performance records to show here]", st["p"]))
        for p in data["past_performance"]:
            head, desc = _pp_flow_text(p)
            f.append(Paragraph(head, st["pp"]))
            if desc:
                f.append(Paragraph(desc, st["ppd"]))
            else:
                f.append(Spacer(1, 5))
        return f

    def band(st):
        def cell(label, lines):
            return [Paragraph(label, st["cellb"]), Paragraph("<br/>".join(_esc(x) for x in lines) or "&nbsp;", st["cell"])]
        contact = [x for x in (", ".join(y for y in (data["contact_name"], data["contact_title"]) if y), data["contact_phone"],
                               data["contact_email"], data["website"]) if x]
        ids = [f"UEI: {data['uei'] or 'not on file'}", f"CAGE: {data['cage'] or 'not on file'}"]
        if data.get("sam_status") == "active":
            ids.append("SAM: active")
        rows = [cell("COMPANY DATA", ids) + cell("CERTIFICATIONS", data["certs"] or ["None claimed"]),
                cell("NAICS", data["naics"] or ["not on file"]) + cell("PSC / FSC", data["psc"] or ["not on file"]),
                cell("CONTACT", contact or ["Add contact details"]) + [Paragraph("", st["cell"]), Paragraph("", st["cell"])]]
        lw = 1.15 * inch
        cw = (W - 2 * M) / 2 - lw
        t = Table(rows, colWidths=[lw, cw, lw, cw])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, -1), HexColor("#EEF2F7")),
                               ("LINEABOVE", (0, 0), (-1, 0), 2, HexColor(NAVY)), ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
        return t

    def height(flows, w):
        return sum(f.wrap(w, H)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in flows)

    header_h = 1.05 * inch
    chosen = None
    for k in (1.0, 0.95, 0.9, 0.85, 0.8):
        st = styles(k)
        ov = [Paragraph(_esc(data["overview"]), st["p"])] if data.get("overview") else []
        ov_h = height(ov, W - 2 * M) if ov else 0
        b = band(st)
        _, band_h = b.wrap(W - 2 * M, H)
        avail = H - 2 * M - header_h - 0.12 * inch - ov_h - band_h - 0.15 * inch
        lh, rh = height(left_flows(st), col_w), height(right_flows(st), col_w)
        chosen = (k, st, ov, ov_h, b, band_h, avail)
        if max(lh, rh) <= avail - 12:  # small allowance for frame padding
            break
    k, st, ov, ov_h, b, band_h, avail = chosen

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(f"{data['name']} Capability Statement")
    c.setAuthor(data["name"])
    # Header band
    c.setFillColor(HexColor(NAVY))
    c.rect(0, H - M - header_h + 0.1 * inch, W, header_h + M - 0.1 * inch, stroke=0, fill=1)
    c.setFillColor(HexColor(ACCENT))
    c.rect(0, H - M - header_h + 0.1 * inch - 4, W, 4, stroke=0, fill=1)
    text_right = W - M
    if data.get("logo"):
        try:
            from reportlab.lib.utils import ImageReader

            img = ImageReader(str(data["logo"]))
            iw, ih = img.getSize()
            lh_ = 0.75 * inch
            lw_ = min(1.6 * inch, iw * lh_ / max(ih, 1))
            c.drawImage(img, W - M - lw_, H - M - 0.8 * inch, width=lw_, height=lh_, mask="auto", preserveAspectRatio=True)
            text_right = W - M - lw_ - 0.2 * inch
        except Exception:  # noqa: BLE001  (a bad logo file should not break the statement)
            pass
    c.setFillColor(white)
    name_size = 22
    while name_size > 12 and c.stringWidth(data["name"], "Helvetica-Bold", name_size) > text_right - M:
        name_size -= 1
    c.setFont("Helvetica-Bold", name_size)
    c.drawString(M, H - M - 0.3 * inch, data["name"])
    if data.get("tagline"):
        tag = Paragraph(f"<font color='white'>{_esc(data['tagline'])}</font>", ParagraphStyle("t", fontName="Helvetica", fontSize=11, leading=13))
        tag.wrapOn(c, text_right - M, 0.5 * inch)
        tag.drawOn(c, M, H - M - 0.62 * inch)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#C9D6E8"))
    c.drawString(M, H - M - 0.86 * inch, "CAPABILITY STATEMENT" + (f"  |  Prepared for {data['tailored_for'][:90]}" if data.get("tailored_for") else ""))

    y_top = H - M - header_h - 0.12 * inch
    if ov:
        Frame(M, y_top - ov_h - 6, W - 2 * M, ov_h + 6, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0).addFromList(list(ov), c)
        y_top -= ov_h + 6
    band_y = M
    col_h = y_top - (band_y + band_h + 0.15 * inch)
    lf, rf = left_flows(st), right_flows(st)
    Frame(M, band_y + band_h + 0.15 * inch, col_w, col_h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0).addFromList(lf, c)
    Frame(M + col_w + gutter, band_y + band_h + 0.15 * inch, col_w, col_h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0).addFromList(rf, c)
    c.setStrokeColor(HexColor("#C9D6E8"))
    c.line(M + col_w + gutter / 2, band_y + band_h + 0.2 * inch, M + col_w + gutter / 2, y_top - 4)
    b.drawOn(c, M, band_y)
    c.showPage()
    c.save()
    overflow = bool(lf or rf)
    return buf.getvalue(), {"scale": k, "shrunk": k < 1.0, "overflow": overflow}


def capability_docx(data: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    from .package_export import _setup, _shade

    doc = Document()
    _setup(doc, "Calibri", 10)
    for s in doc.sections:
        s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Inches(0.5)
        s.page_width, s.page_height = Inches(8.5), Inches(11)
    head = doc.add_table(rows=1, cols=2)
    _shade(head.cell(0, 0), "1F3A5F")
    _shade(head.cell(0, 1), "1F3A5F")
    p = head.cell(0, 0).paragraphs[0]
    r = p.add_run(data["name"])
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), RGBColor(0xFF, 0xFF, 0xFF)
    if data.get("tagline"):
        r2 = head.cell(0, 0).add_paragraph().add_run(data["tagline"])
        r2.font.size, r2.font.color.rgb = Pt(11), RGBColor(0xFF, 0xFF, 0xFF)
    r3 = head.cell(0, 0).add_paragraph().add_run("CAPABILITY STATEMENT")
    r3.bold, r3.font.size, r3.font.color.rgb = True, Pt(8), RGBColor(0xC9, 0xD6, 0xE8)
    if data.get("logo"):
        try:
            lp = head.cell(0, 1).paragraphs[0]
            lp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            lp.add_run().add_picture(str(data["logo"]), height=Inches(0.7))
        except Exception:  # noqa: BLE001
            pass
    if data.get("overview"):
        doc.add_paragraph(data["overview"])
    body = doc.add_table(rows=1, cols=2)
    left, right = body.cell(0, 0), body.cell(0, 1)

    def heading(cell, text, first=False):
        para = cell.paragraphs[0] if first else cell.add_paragraph()
        run = para.add_run(text)
        run.bold, run.font.size, run.font.color.rgb = True, Pt(11), RGBColor(0x1F, 0x3A, 0x5F)

    heading(left, "CORE COMPETENCIES", True)
    for comp in data["competencies"]:
        left.add_paragraph(comp, style="List Bullet")
    if data["differentiators"]:
        heading(left, "DIFFERENTIATORS")
        for d in data["differentiators"]:
            left.add_paragraph(d, style="List Bullet")
    heading(right, "PAST PERFORMANCE", True)
    for pp in data["past_performance"]:
        para = right.add_paragraph()
        para.add_run(pp.title or "Project").bold = True
        sub = ", ".join(x for x in (" / ".join(y for y in (pp.customer, pp.agency) if y), ROLE_SHORT.get(pp.role, pp.role),
                                    pp.contract_number, f"${pp.value:,.0f}" if pp.value is not None else "") if x)
        if sub:
            para.add_run("\n" + sub).font.size = Pt(9)
        if pp.description:
            d = pp.description.strip().replace("\n", " ")
            right.add_paragraph(d[:257] + ("..." if len(d) > 260 else "")).runs[0].font.size = Pt(9)
    band = doc.add_table(rows=3, cols=4)
    contact = [x for x in (", ".join(y for y in (data["contact_name"], data["contact_title"]) if y), data["contact_phone"], data["contact_email"], data["website"]) if x]
    cells = [("COMPANY DATA", [f"UEI: {data['uei'] or 'not on file'}", f"CAGE: {data['cage'] or 'not on file'}"]),
             ("CERTIFICATIONS", data["certs"] or ["None claimed"]), ("NAICS", data["naics"]), ("PSC / FSC", data["psc"]),
             ("CONTACT", contact), ("", [])]
    for i, (label, lines) in enumerate(cells):
        row, col = divmod(i, 2)
        lc, vc = band.cell(row, col * 2), band.cell(row, col * 2 + 1)
        _shade(lc, "EEF2F7")
        _shade(vc, "EEF2F7")
        rr = lc.paragraphs[0].add_run(label)
        rr.bold, rr.font.size = True, Pt(8.5)
        vc.paragraphs[0].add_run("\n".join(lines)).font.size = Pt(8.5)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
