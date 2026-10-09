"""Search everything: one query over packages, library, past performance, opportunities, analyses, part quotes,
standards, contacts, interactions and source approval requests.

Uses an SQLite FTS5 index (table search_fts) when available. The index is rebuilt on demand when a cheap
signature of the source tables (row count, max id, total text length) changes, so it never drifts far from the data.
Without FTS5 it falls back to Python substring matching with simple scoring. Both support "quoted phrases" and
multiple words (all must match).

Also serves GET /api/search/digest-preview, the HTML daily digest (see app/digest.py).
"""
from __future__ import annotations

import html
import re
from typing import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .db import get_db
from .models import Analysis, LibraryEntry, Opportunity, Package, PackageSection, PartQuote

router = APIRouter(prefix="/api/search", tags=["search"])

HL_START, HL_END = "", ""  # highlight markers in snippets (private-use characters)
TYPE_LABELS = {
    "section": "Package section", "library": "Content library", "past_performance": "Past performance",
    "opportunity": "Opportunity", "analysis": "Analysis", "part_quote": "Part quote", "standard": "Standard",
    "organization": "Organization", "contact": "Contact", "interaction": "Interaction", "sar": "Source approval",
}
TITLE_WEIGHT, BODY_WEIGHT = 5.0, 1.0


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _j(*parts) -> str:
    return "\n".join(str(p) for p in parts if p)


# ------------------------------------------------------------------ documents
def iter_documents(db: Session) -> Iterator[dict]:
    """Every searchable record as {type, ref, title, body, url, copy}."""
    for s, pname, pid in db.execute(select(PackageSection, Package.name, Package.id).join(Package, Package.id == PackageSection.package_id)).all():
        t = " ".join(x for x in (s.number, s.title) if x)
        yield {"type": "section", "ref": str(s.id), "title": f"{pname}: {t}", "body": _j(s.content, s.guidance, s.volume),
               "url": f"/packages/{pid}?section={s.id}", "copy": s.content or ""}
    for e in db.scalars(select(LibraryEntry)).all():
        yield {"type": "library", "ref": str(e.id), "title": e.title, "body": _j(e.content, e.category, " ".join(e.tags or [])),
               "url": f"/packages?tab=library&id={e.id}", "copy": e.content or ""}
    try:
        from .models_pp import PastPerformance
        for p in db.scalars(select(PastPerformance)).all():
            yield {"type": "past_performance", "ref": str(p.id), "title": p.title or p.contract_number or "Past performance",
                   "body": _j(p.customer, p.agency, p.contract_number, p.naics, p.description, p.results, p.notes,
                              " ".join(p.relevance_keywords or [])),
                   "url": f"/past-performance?id={p.id}", "copy": _j(p.description, p.results)}
    except Exception:  # noqa: BLE001
        pass
    for o in db.scalars(select(Opportunity)).all():
        yield {"type": "opportunity", "ref": str(o.id), "title": o.title or o.solicitation_number,
               "body": _j(o.solicitation_number, o.agency, o.nsn, o.naics, _strip_html(o.description)),
               "url": f"/opportunities/{o.id}", "copy": ""}
    for a, title in db.execute(select(Analysis, Opportunity.title).join(Opportunity, Opportunity.id == Analysis.opportunity_id)).all():
        reqs = [str(r.get("requirement", "")) for r in (a.compliance_matrix or []) if isinstance(r, dict)]
        yield {"type": "analysis", "ref": str(a.id), "title": f"Analysis: {title}", "body": _j(a.summary, *reqs),
               "url": f"/opportunities/{a.opportunity_id}", "copy": ""}
    for q in db.scalars(select(PartQuote)).all():
        yield {"type": "part_quote", "ref": str(q.id), "title": q.name or q.part_number or q.nsn or f"Quote {q.id}",
               "body": _j(q.nsn, q.part_number, q.notes, (q.spec or {}).get("material", "")),
               "url": f"/part-quotes?id={q.id}", "copy": ""}
    try:
        from .models_standards import StandardEntry
        for s in db.scalars(select(StandardEntry).where((StandardEntry.in_library.is_(True)) | (StandardEntry.notes != ""))).all():
            yield {"type": "standard", "ref": str(s.id), "title": f"{s.base_id}: {s.title}" if s.title else s.base_id,
                   "body": _j(s.notes, s.summary, s.category, s.publisher),
                   "url": f"/standards?open={s.base_id}", "copy": ""}
    except Exception:  # noqa: BLE001
        pass
    try:
        from .models_crm import Contact, Interaction, Organization
        for o in db.scalars(select(Organization)).all():
            yield {"type": "organization", "ref": str(o.id), "title": o.name,
                   "body": _j(o.kind, o.cage, o.uei, o.city, o.capabilities, o.notes, " ".join(o.tags or [])),
                   "url": f"/contacts?id={o.id}", "copy": ""}
        for c, oname in db.execute(select(Contact, Organization.name).join(Organization, Organization.id == Contact.organization_id)).all():
            yield {"type": "contact", "ref": str(c.id), "title": f"{c.name} ({oname})",
                   "body": _j(c.title, c.email, c.phone, c.notes), "url": f"/contacts?id={c.organization_id}", "copy": ""}
        for i, oname in db.execute(select(Interaction, Organization.name).join(Organization, Organization.id == Interaction.organization_id)).all():
            yield {"type": "interaction", "ref": str(i.id), "title": f"{oname}: {i.kind} {i.date}".strip(),
                   "body": _j(i.summary, i.next_step), "url": f"/contacts?id={i.organization_id}", "copy": ""}
    except Exception:  # noqa: BLE001
        pass
    try:
        from .models_sar import SourceApproval
        for s in db.scalars(select(SourceApproval)).all():
            yield {"type": "sar", "ref": str(s.id), "title": f"SAR NSN {s.nsn} {s.nomenclature}".strip(),
                   "body": _j(s.part_number, " ".join(a.get("cage", "") for a in s.approved_sources or []), s.status, s.dla_activity,
                              s.decision_notes, s.notes, s.re_measurements, s.re_materials, s.re_notes),
                   "url": f"/source-approvals?id={s.id}", "copy": ""}
    except Exception:  # noqa: BLE001
        pass


# Tables and text columns that feed the signature (cheap aggregate queries).
_SIGNATURE_SOURCES = [
    ("package_sections", ["content", "title", "guidance"]),
    ("library", ["content", "title"]),
    ("past_performance", ["title", "description", "results", "notes"]),
    ("opportunities", ["title", "description"]),
    ("analyses", ["summary", "compliance_matrix"]),
    ("part_quotes", ["name", "nsn", "part_number", "notes"]),
    ("standard_entries", ["notes", "title", "in_library"]),
    ("organizations", ["name", "capabilities", "notes"]),
    ("contacts", ["name", "notes", "email"]),
    ("interactions", ["summary", "next_step"]),
    ("source_approvals", ["nsn", "notes", "decision_notes", "re_notes", "re_measurements", "re_materials", "part_number", "nomenclature"]),
    ("packages", ["name"]),
]


def signature(db: Session) -> str:
    parts = []
    for table, cols in _SIGNATURE_SOURCES:
        try:
            length = " + ".join(f"coalesce(length({c}),0)" for c in cols)
            row = db.execute(text(f'SELECT count(*), coalesce(max(id),0), coalesce(total({length}),0) FROM "{table}"')).one()
            parts.append(f"{table}:{row[0]}:{row[1]}:{int(row[2])}")
        except Exception:  # noqa: BLE001  (table missing in an older database)
            db.rollback()
            parts.append(f"{table}:-")
    return "|".join(parts)


# ------------------------------------------------------------------ query parsing
def parse_query(q: str) -> list[str]:
    """Split into terms: "quoted phrases" stay whole, other words split on whitespace. Lowercased, deduped."""
    terms: list[str] = []
    for m in re.finditer(r'"([^"]+)"|(\S+)', q or ""):
        t = (m.group(1) or m.group(2) or "").strip().strip('"').lower()
        t = re.sub(r"\s+", " ", t)
        if t and t not in terms:
            terms.append(t)
    return terms


def _fts_term(t: str) -> str | None:
    words = re.findall(r"\w+", t, re.UNICODE)
    if not words:
        return None
    phrase = '"' + " ".join(words) + '"'
    if len(words) == 1 and " " not in t and len(words[0]) >= 3:
        return phrase + "*"  # prefix match for single words
    return phrase


# ------------------------------------------------------------------ FTS5 engine
_FTS_OK: bool | None = None


def fts_available(db: Session) -> bool:
    global _FTS_OK
    if _FTS_OK is None:
        try:
            db.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5("
                            "type UNINDEXED, ref UNINDEXED, url UNINDEXED, copy UNINDEXED, title, body, tokenize='porter unicode61')"))
            db.execute(text("CREATE TABLE IF NOT EXISTS search_meta (key TEXT PRIMARY KEY, value TEXT)"))
            db.commit()
            _FTS_OK = True
        except Exception:  # noqa: BLE001
            db.rollback()
            _FTS_OK = False
    return _FTS_OK


def rebuild_index(db: Session, sig: str | None = None) -> int:
    sig = sig or signature(db)
    docs = list(iter_documents(db))
    db.execute(text("DELETE FROM search_fts"))
    if docs:
        db.execute(text("INSERT INTO search_fts(type, ref, url, copy, title, body) VALUES (:type, :ref, :url, :copy, :title, :body)"),
                   [{k: d[k] or "" for k in ("type", "ref", "url", "copy", "title", "body")} for d in docs])
    db.execute(text("INSERT OR REPLACE INTO search_meta(key, value) VALUES ('signature', :s)"), {"s": sig})
    db.commit()
    return len(docs)


def ensure_index(db: Session, force: bool = False) -> bool:
    """Rebuild the FTS index if the data changed. Returns True if it rebuilt."""
    sig = signature(db)
    row = db.execute(text("SELECT value FROM search_meta WHERE key = 'signature'")).first()
    if force or not row or row[0] != sig:
        rebuild_index(db, sig)
        return True
    return False


def _fts_search(db: Session, terms: list[str], types: set[str] | None, limit: int) -> list[dict]:
    ensure_index(db)
    parts = [p for p in (_fts_term(t) for t in terms) if p]
    if not parts:
        return []
    match = " AND ".join(parts)
    sql = (f"SELECT type, ref, url, copy, title, "
           f"snippet(search_fts, -1, '{HL_START}', '{HL_END}', '...', 28) AS snip, "
           f"bm25(search_fts, 0, 0, 0, 0, {TITLE_WEIGHT}, {BODY_WEIGHT}) AS rank "
           f"FROM search_fts WHERE search_fts MATCH :m ORDER BY rank LIMIT :lim")
    try:
        rows = db.execute(text(sql), {"m": match, "lim": limit * 3 if types else limit}).all()
    except Exception:  # noqa: BLE001  (malformed MATCH expression)
        db.rollback()
        return []
    out = []
    for row in rows:
        r = row._mapping
        if types and r["type"] not in types:
            continue
        out.append({"type": r["type"], "ref": r["ref"], "url": r["url"], "copy": r["copy"], "title": r["title"],
                    "snippet": r["snip"], "score": round(-float(r["rank"]), 3)})
    return out[:limit]


# ------------------------------------------------------------------ fallback engine
def _count(hay: str, term: str) -> int:
    return len(re.findall(r"(?<!\w)" + re.escape(term), hay))


def _snippet(body: str, terms: list[str], width: int = 180) -> str:
    low = body.lower()
    pos = [low.find(t) for t in terms if low.find(t) >= 0]
    start = max(min(pos) - 60, 0) if pos else 0
    piece = body[start:start + width]
    pre = "..." if start > 0 else ""
    post = "..." if start + width < len(body) else ""
    for t in sorted(terms, key=len, reverse=True):
        piece = re.sub(re.escape(t), lambda m: f"{HL_START}{m.group(0)}{HL_END}", piece, flags=re.I)
    return re.sub(r"\s+", " ", pre + piece + post).strip()


def _like_search(db: Session, terms: list[str], types: set[str] | None, limit: int) -> list[dict]:
    if not terms:
        return []
    out = []
    for d in iter_documents(db):
        if types and d["type"] not in types:
            continue
        tl, bl = (d["title"] or "").lower(), (d["body"] or "").lower()
        score = 0.0
        ok = True
        for t in terms:
            ct, cb = _count(tl, t), _count(bl, t)
            if not ct and not cb:
                ok = False
                break
            score += TITLE_WEIGHT * ct + BODY_WEIGHT * min(cb, 10)
        if not ok:
            continue
        snip_src = d["body"] if any(t in bl for t in terms) else d["title"]
        out.append({"type": d["type"], "ref": d["ref"], "url": d["url"], "copy": d["copy"], "title": d["title"],
                    "snippet": _snippet(snip_src or "", terms), "score": round(score, 3)})
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


def search(db: Session, q: str, types: list[str] | None = None, limit: int = 30, engine: str = "auto") -> dict:
    """Ranked results for `q` across every source. engine: auto | fts | like."""
    terms = parse_query(q)
    tset = {t for t in (types or []) if t} or None
    use_fts = engine != "like" and fts_available(db)
    results = _fts_search(db, terms, tset, limit) if use_fts else _like_search(db, terms, tset, limit)
    if use_fts and not results and terms:
        # FTS tokenization can miss partial tokens such as part number fragments; try substring matching.
        results = _like_search(db, terms, tset, limit)
    for r in results:
        r["type_label"] = TYPE_LABELS.get(r["type"], r["type"])
        r["reusable"] = r["type"] in ("section", "library")
        if not r["reusable"]:
            r.pop("copy", None)
    return {"query": q, "terms": terms, "engine": "fts5" if use_fts else "like", "count": len(results), "results": results,
            "markers": [HL_START, HL_END]}


# ------------------------------------------------------------------ routes
@router.get("")
def search_route(q: str = "", types: str = "", limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)):
    return search(db, q, [t.strip() for t in types.split(",")] if types else None, limit)


@router.get("/types")
def search_types():
    return TYPE_LABELS


@router.post("/reindex")
def reindex(db: Session = Depends(get_db)):
    if not fts_available(db):
        return {"engine": "like", "indexed": 0}
    return {"engine": "fts5", "indexed": rebuild_index(db)}


@router.get("/digest-preview", response_class=HTMLResponse)
def digest_preview(days: int = Query(1, ge=1, le=60), db: Session = Depends(get_db)):
    from .digest import build_digest, render_html

    return HTMLResponse(render_html(build_digest(db, days=days)))
