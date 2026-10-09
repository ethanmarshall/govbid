"""Shared logic used by the API and the command-line sync."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .connectors import sam_gov
from .models import CompanyProfile, Opportunity, SyncLog

UPDATABLE = [
    "solicitation_number", "title", "agency", "notice_type", "set_aside_code", "set_aside_desc", "naics", "psc",
    "nsn", "quantity", "posted_date", "response_deadline", "place_of_performance", "pop_state", "url",
    "description_url", "contacts", "attachments", "estimated_value", "active", "raw",
]


def get_profile(db: Session) -> CompanyProfile:
    p = db.get(CompanyProfile, 1)
    if p is None:
        p = CompanyProfile(id=1, certifications={"SB": "none", "SDVOSB": "none", "VOSB": "none"})
        db.add(p)
        db.commit()
    return p


def upsert_opportunities(db: Session, records: list[dict]) -> tuple[int, int]:
    added = updated = 0
    for rec in records:
        if not rec.get("external_id"):
            continue
        existing = db.scalar(
            select(Opportunity).where(Opportunity.source == rec["source"], Opportunity.external_id == rec["external_id"])
        )
        if existing:
            for k in UPDATABLE:
                if k in rec and rec[k] not in (None, ""):
                    setattr(existing, k, rec[k])
            if rec.get("description") and not existing.description:
                existing.description = rec["description"]
            existing.fetched_at = datetime.utcnow()
            updated += 1
        else:
            db.add(Opportunity(**{k: v for k, v in rec.items() if hasattr(Opportunity, k)}))
            added += 1
    db.commit()
    return added, updated


def sync_sam(
    db: Session,
    *,
    days_back: int = 14,
    naics: list[str] | None = None,
    titles: list[str] | None = None,
    set_aside: str | None = None,
    max_pages: int = 3,
) -> dict:
    """Pull SAM.gov notices. One query per NAICS code (or per title keyword) keeps request counts predictable."""
    profile = get_profile(db)
    if titles:
        queries = [("title", t) for t in titles]
    else:
        codes = naics if naics is not None else list(profile.naics_codes or [])
        queries = [("naics", c) for c in codes] or [("naics", None)]  # no NAICS on file: one broad query
    log = SyncLog(source="sam")
    db.add(log)
    total_added = total_updated = used = 0
    errors = []
    for kind, value in queries:
        try:
            raw, n = sam_gov.search(
                days_back=days_back, set_aside=set_aside, max_pages=max_pages,
                naics=value if kind == "naics" else None,
                keyword_title=value if kind == "title" else None,
            )
            used += n
            a, u = upsert_opportunities(db, [sam_gov.normalize(x) for x in raw])
            total_added += a
            total_updated += u
        except sam_gov.SamApiError as exc:
            errors.append(str(exc))
            if "limit" in str(exc).lower() or "SAM_API_KEY" in str(exc):
                break
    log.added, log.updated, log.requests_used, log.error = total_added, total_updated, used, "\n".join(errors)
    db.commit()
    return {"added": total_added, "updated": total_updated, "requests_used": used, "queries": len(queries), "errors": errors}
