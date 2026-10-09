"""Recompetes and buyers: incumbent contracts ending soon in the owner's NAICS/PSC codes, a watch list for them,
and buyer analytics (who buys, how much, how often it is set aside) from USAspending.gov.

Data source: https://api.usaspending.gov (no key). Endpoints and fields are documented in
app/connectors/usaspending_market.py. Responses are cached in the market_cache table for 24 hours,
keyed by method, path and request body.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .connectors import usaspending_market as usm
from .db import get_db
from .models import Opportunity
from .models_crm import Interaction, Organization
from .models_market import TRACK_STATUSES, MarketCache, TrackedRecompete
from .services import get_profile

router = APIRouter(prefix="/api/market", tags=["market"])

CACHE_TTL = timedelta(hours=24)
DASHBOARD_DAYS = 180
CLOSED_STATUSES = {"no_bid", "closed"}


def _today() -> date:
    return date.today()


# ------------------------------------------------------------------ cache
def cache_key(method: str, path: str, body: dict | None) -> str:
    raw = method.upper() + " " + path + " " + json.dumps(body or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class CachedFetcher:
    """Serves USAspending requests from the DB cache when younger than 24 hours, else fetches and stores them."""

    def __init__(self, db: Session, refresh: bool = False, http: usm.HttpFetcher | None = None):
        self.db = db
        self.refresh = refresh
        self._http = http
        self.oldest: datetime | None = None
        self.network_calls = 0

    @property
    def http(self) -> usm.HttpFetcher:
        if self._http is None:
            self._http = usm.HttpFetcher()
        return self._http

    def _seen(self, ts: datetime) -> None:
        if self.oldest is None or ts < self.oldest:
            self.oldest = ts

    def many(self, reqs: list[usm.Request]) -> list[dict]:
        keys = [cache_key(*r) for r in reqs]
        now = datetime.utcnow()
        rows = {r.key: r for r in self.db.scalars(select(MarketCache).where(MarketCache.key.in_(set(keys)))).all()} if keys else {}
        results: dict[str, dict] = {}
        missing: dict[str, usm.Request] = {}
        for k, req in zip(keys, reqs):
            row = rows.get(k)
            if row is not None and not self.refresh and now - row.fetched_at < CACHE_TTL:
                results[k] = row.response
                self._seen(row.fetched_at)
            elif k not in missing:
                missing[k] = req
        if missing:
            fetched = self.http.many(list(missing.values()))
            self.network_calls += len(missing)
            for (k, (method, path, body)), data in zip(missing.items(), fetched):
                row = rows.get(k)
                if row is None:
                    row = MarketCache(key=k, method=method, path=path, body=body or {})
                    self.db.add(row)
                    rows[k] = row
                row.response = data
                row.fetched_at = now
                results[k] = data
                self._seen(now)
            self.db.commit()
        return [results[k] for k in keys]

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    def as_of(self) -> str:
        return (self.oldest or datetime.utcnow()).isoformat(timespec="seconds") + "Z"


def _fetcher(db: Session, refresh: bool) -> CachedFetcher:
    return CachedFetcher(db, refresh)


# ------------------------------------------------------------------ schemas
class RecompeteIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    naics: list[str] | None = None
    psc: list[str] | None = None
    months_from: int = 6
    months_to: int = 18
    agency: str = ""
    min_value: float | None = None
    set_aside: str = ""  # a key of SET_ASIDE_GROUPS, or comma separated codes
    refresh: bool = False


class BuyersIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    naics: list[str] | None = None
    psc: list[str] | None = None
    basis: str = ""  # naics | psc | both (both = awards matching a NAICS AND a PSC)
    years: int = 3
    sample: int = 20
    refresh: bool = False


class TrackIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    generated_internal_id: str | None = None
    award_id: str | None = None
    recipient: str | None = None
    recipient_uei: str | None = None
    amount: float | None = None
    agency: str | None = None
    sub_agency: str | None = None
    office: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    naics: str | None = None
    psc: str | None = None
    set_aside: str | None = None
    extent_competed: str | None = None
    offers: str | None = None
    description: str | None = None
    url: str | None = None
    status: str | None = None
    notes: str | None = None
    reminder_date: str | None = None
    opportunity_id: int | None = None


class CrmIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    kind: str = "note"
    date: str | None = None
    summary: str | None = None
    next_step: str = ""
    follow_up_date: str = ""


# ------------------------------------------------------------------ helpers
def _clean(codes: list[str] | None) -> list[str]:
    out = []
    for c in codes or []:
        c = str(c).strip().upper()
        if c and c not in out:
            out.append(c)
    return out


def profile_codes(db: Session) -> dict:
    p = get_profile(db)
    fsc = usm.fsc_prefixes(p.nsn_watchlist or [])
    psc = _clean(list(p.psc_codes or []) + fsc)
    return {"naics": _clean(p.naics_codes), "psc": psc, "fsc_from_nsn": fsc}


def set_aside_codes(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    if value in usm.SET_ASIDE_GROUPS:
        return list(usm.SET_ASIDE_GROUPS[value])
    return [c.strip() for c in value.split(",") if c.strip()]


def _check_date(value: str | None, field: str) -> None:
    if value:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise HTTPException(400, f"{field} must be YYYY-MM-DD")


def tracked_dict(t: TrackedRecompete, today: date | None = None) -> dict:
    today = today or _today()
    days = None
    if t.end_date:
        try:
            days = (date.fromisoformat(t.end_date) - today).days
        except ValueError:
            days = None
    return {
        "id": t.id, "generated_internal_id": t.generated_internal_id, "award_id": t.award_id, "recipient": t.recipient,
        "recipient_uei": t.recipient_uei, "amount": t.amount, "agency": t.agency, "sub_agency": t.sub_agency, "office": t.office,
        "start_date": t.start_date, "end_date": t.end_date, "days_left": days, "naics": t.naics, "psc": t.psc,
        "set_aside": t.set_aside, "extent_competed": t.extent_competed, "offers": t.offers, "description": t.description,
        "url": t.url, "status": t.status, "notes": t.notes, "reminder_date": t.reminder_date,
        "opportunity_id": t.opportunity_id, "organization_id": t.organization_id,
        "created_at": t.created_at.isoformat() if t.created_at else "",
    }


def _get_tracked(db: Session, tid: int) -> TrackedRecompete:
    t = db.get(TrackedRecompete, tid)
    if not t:
        raise HTTPException(404, "Tracked contract not found")
    return t


# ------------------------------------------------------------------ endpoints
@router.get("/defaults")
def defaults(db: Session = Depends(get_db)):
    today = _today()
    w = usm.recompete_window(today)
    return {
        **profile_codes(db),
        "today": today.isoformat(), "window": {"start": w[0].isoformat(), "end": w[1].isoformat()},
        "months_from": 6, "months_to": 18,
        "set_aside_groups": {"sdvosb": "SDVOSB", "veteran": "Veteran (VOSB and SDVOSB)", "small_business": "Any small business set-aside",
                             "none": "No set-aside used"},
        "set_aside_labels": usm.SET_ASIDE_LABELS, "statuses": TRACK_STATUSES,
        "last_complete_fy": usm.last_complete_fys(today, 1)[0],
    }


@router.post("/recompetes")
def recompetes(body: RecompeteIn, db: Session = Depends(get_db)):
    prof = profile_codes(db)
    naics = _clean(body.naics) if body.naics is not None else prof["naics"]
    psc = _clean(body.psc) if body.psc is not None else prof["psc"]
    if not naics and not psc:
        raise HTTPException(400, "Enter at least one NAICS or PSC/FSC code (or add them to your profile).")
    today = _today()
    window = usm.recompete_window(today, max(0, body.months_from), max(0, body.months_to))
    fetch = _fetcher(db, body.refresh)
    try:
        out = usm.search_recompetes(fetch, naics=naics, psc=psc, window=window, today=today, agency=body.agency.strip(),
                                    min_value=body.min_value, set_asides=set_aside_codes(body.set_aside))
    except (RuntimeError, OSError) as e:
        raise HTTPException(502, str(e))
    finally:
        fetch.close()
    tracked = {gid: tid for gid, tid in db.execute(select(TrackedRecompete.generated_internal_id, TrackedRecompete.id)).all()}
    for r in out["results"]:
        r["tracked_id"] = tracked.get(r["generated_internal_id"])
    return {**out, "naics": naics, "psc": psc, "window": {"start": window[0].isoformat(), "end": window[1].isoformat()},
            "as_of": fetch.as_of()}


@router.get("/award/{generated_internal_id}")
def award(generated_internal_id: str, refresh: bool = False, db: Session = Depends(get_db)):
    fetch = _fetcher(db, refresh)
    try:
        d = usm.award_detail(fetch, generated_internal_id)
    except (RuntimeError, OSError) as e:
        raise HTTPException(502, str(e))
    finally:
        fetch.close()
    return {**d, "as_of": fetch.as_of()}


def _buyer_codes(db: Session, body: BuyersIn) -> tuple[list[str], list[str], str]:
    prof = profile_codes(db)
    naics = _clean(body.naics) if body.naics is not None else prof["naics"]
    psc = _clean(body.psc) if body.psc is not None else prof["psc"]
    basis = body.basis or ("naics" if naics else "psc")
    if basis == "naics":
        psc = []
    elif basis == "psc":
        naics = []
    elif basis != "both":
        raise HTTPException(400, "basis must be naics, psc or both")
    if not naics and not psc:
        raise HTTPException(400, "Enter at least one NAICS or PSC/FSC code (or add them to your profile).")
    return naics, psc, basis


@router.post("/buyers")
def buyers(body: BuyersIn, db: Session = Depends(get_db)):
    naics, psc, basis = _buyer_codes(db, body)
    fys = usm.last_complete_fys(_today(), min(max(body.years, 1), 10))
    fetch = _fetcher(db, body.refresh)
    try:
        out = usm.buyer_analytics(fetch, naics=naics, psc=psc, fys=fys)
    except (RuntimeError, OSError) as e:
        raise HTTPException(502, str(e))
    finally:
        fetch.close()
    return {**out, "naics": naics, "psc": psc, "basis": basis, "as_of": fetch.as_of()}


@router.post("/buyers/offices")
def buyer_offices(body: BuyersIn, db: Session = Depends(get_db)):
    naics, psc, basis = _buyer_codes(db, body)
    fys = usm.last_complete_fys(_today(), min(max(body.years, 1), 10))
    fetch = _fetcher(db, body.refresh)
    try:
        out = usm.office_sample(fetch, naics=naics, psc=psc, fys=fys, sample=min(max(body.sample, 1), 50))
    except (RuntimeError, OSError) as e:
        raise HTTPException(502, str(e))
    finally:
        fetch.close()
    return {**out, "naics": naics, "psc": psc, "basis": basis, "as_of": fetch.as_of()}


@router.get("/tracked")
def list_tracked(db: Session = Depends(get_db)):
    today = _today()
    rows = db.scalars(select(TrackedRecompete).order_by(TrackedRecompete.end_date)).all()
    return [tracked_dict(t, today) for t in rows]


_TRACK_FIELDS = ["award_id", "recipient", "recipient_uei", "amount", "agency", "sub_agency", "office", "start_date", "end_date",
                 "naics", "psc", "set_aside", "extent_competed", "offers", "description", "url", "status", "notes",
                 "reminder_date", "opportunity_id"]


def _apply(t: TrackedRecompete, body: TrackIn, db: Session) -> None:
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in TRACK_STATUSES:
        raise HTTPException(400, f"status must be one of {TRACK_STATUSES}")
    _check_date(data.get("reminder_date"), "reminder_date")
    if data.get("opportunity_id") is not None and not db.get(Opportunity, data["opportunity_id"]):
        raise HTTPException(400, "Opportunity not found")
    for k in _TRACK_FIELDS:
        if k in data:
            v = data[k]
            if v is None and k not in ("opportunity_id",):
                continue
            setattr(t, k, v)


@router.post("/tracked")
def track(body: TrackIn, db: Session = Depends(get_db)):
    gid = (body.generated_internal_id or "").strip()
    if not gid:
        raise HTTPException(400, "generated_internal_id is required")
    existing = db.scalar(select(TrackedRecompete).where(TrackedRecompete.generated_internal_id == gid))
    if existing:
        return {**tracked_dict(existing), "already": True}
    t = TrackedRecompete(generated_internal_id=gid, url=usm.AWARD_PAGE + gid)
    _apply(t, body, db)
    db.add(t)
    db.commit()
    return tracked_dict(t)


@router.put("/tracked/{tid}")
def update_tracked(tid: int, body: TrackIn, db: Session = Depends(get_db)):
    t = _get_tracked(db, tid)
    _apply(t, body, db)
    db.commit()
    return tracked_dict(t)


@router.delete("/tracked/{tid}")
def delete_tracked(tid: int, db: Session = Depends(get_db)):
    db.delete(_get_tracked(db, tid))
    db.commit()
    return {"ok": True}


@router.post("/tracked/{tid}/refresh-detail")
def refresh_tracked_detail(tid: int, db: Session = Depends(get_db)):
    """Fill office, set-aside, competition and current end date from the award detail."""
    t = _get_tracked(db, tid)
    fetch = _fetcher(db, False)
    try:
        d = usm.award_detail(fetch, t.generated_internal_id)
    except (RuntimeError, OSError) as e:
        raise HTTPException(502, str(e))
    finally:
        fetch.close()
    for k in ["office", "set_aside", "extent_competed", "offers", "agency", "sub_agency", "end_date", "start_date"]:
        if d.get(k):
            setattr(t, k, str(d[k]))
    db.commit()
    return tracked_dict(t)


@router.post("/tracked/{tid}/crm")
def tracked_to_crm(tid: int, body: CrmIn, db: Session = Depends(get_db)):
    """Find or create the awarding office as a CRM agency organization and log an interaction against it."""
    t = _get_tracked(db, tid)
    name = (body.name or t.office or t.sub_agency or t.agency or "").strip()
    if not name:
        raise HTTPException(400, "No awarding office name. Load the award detail or enter a name.")
    _check_date(body.date, "date")
    _check_date(body.follow_up_date, "follow_up_date")
    org = db.get(Organization, t.organization_id) if t.organization_id else None
    if org is None:
        org = db.scalar(select(Organization).where(Organization.kind == "agency", Organization.name.ilike(name)))
    created = False
    if org is None:
        parent = " / ".join(x for x in [t.agency, t.sub_agency] if x and x != name)
        org = Organization(name=name, kind="agency", stage="identified", tags=["recompete"],
                           naics_codes=[t.naics] if t.naics else [],
                           notes=f"Awarding office from USAspending{(' (' + parent + ')') if parent else ''}.", source="manual")
        db.add(org)
        db.flush()
        created = True
    t.organization_id = org.id
    summary = (body.summary or "").strip() or (
        f"Tracking possible recompete of {t.award_id or t.generated_internal_id} ({t.recipient or 'incumbent unknown'}), "
        f"ends {t.end_date or 'unknown'}. {t.url}".strip())
    kind = body.kind if body.kind in ("email", "call", "meeting", "event", "portal", "note") else "note"
    it = Interaction(organization_id=org.id, opportunity_id=t.opportunity_id, date=body.date or _today().isoformat(),
                     kind=kind, summary=summary, next_step=body.next_step or "", follow_up_date=body.follow_up_date or "")
    db.add(it)
    db.commit()
    return {"organization_id": org.id, "organization": org.name, "created": created, "interaction_id": it.id,
            "tracked": tracked_dict(t)}


@router.get("/opportunity-options")
def opportunity_options(q: str = "", db: Session = Depends(get_db)):
    stmt = select(Opportunity).order_by(Opportunity.id.desc()).limit(20)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Opportunity.title.ilike(like), Opportunity.solicitation_number.ilike(like), Opportunity.agency.ilike(like)))
    return [{"id": o.id, "title": o.title, "solicitation_number": o.solicitation_number, "agency": o.agency,
             "notice_type": o.notice_type} for o in db.scalars(stmt).all()]


@router.delete("/cache")
def clear_cache(db: Session = Depends(get_db)):
    n = db.query(MarketCache).delete()
    db.commit()
    return {"deleted": n}


# ------------------------------------------------------------------ calendar and dashboard hooks
def calendar_items(db: Session) -> list[dict]:
    """Reminder dates and contract end dates for tracked recompetes (closed and no-bid items skipped)."""
    out = []
    for t in db.scalars(select(TrackedRecompete).where(TrackedRecompete.status.notin_(CLOSED_STATUSES))).all():
        label = f"{t.award_id or t.generated_internal_id} ({t.recipient or 'incumbent'})"
        where = t.office or t.sub_agency or t.agency
        if t.reminder_date:
            try:
                out.append({"uid": f"recompete-rem-{t.id}@govbid", "date": date.fromisoformat(t.reminder_date),
                            "summary": f"Recompete reminder: {label}",
                            "description": (t.notes or f"Buyer: {where}")[:500], "url": "/market?tab=tracked"})
            except ValueError:
                pass
        if t.end_date:
            try:
                out.append({"uid": f"recompete-end-{t.id}@govbid", "date": date.fromisoformat(t.end_date),
                            "summary": f"Incumbent contract ends: {label}",
                            "description": f"Buyer: {where}. {t.url}".strip(), "url": "/market?tab=tracked"})
            except ValueError:
                pass
    return out


def dashboard_items(db: Session) -> list[str]:
    """Tracked contracts ending within 180 days that have no linked opportunity yet."""
    today = _today()
    limit = (today + timedelta(days=DASHBOARD_DAYS)).isoformat()
    rows = db.scalars(select(TrackedRecompete).where(
        TrackedRecompete.status.notin_(CLOSED_STATUSES), TrackedRecompete.opportunity_id.is_(None),
        TrackedRecompete.end_date != "", TrackedRecompete.end_date >= today.isoformat(), TrackedRecompete.end_date <= limit,
    ).order_by(TrackedRecompete.end_date)).all()
    return [f"Recompete watch: {t.award_id or t.generated_internal_id} ({t.recipient or 'incumbent'}) at "
            f"{t.office or t.sub_agency or t.agency or 'unknown buyer'} ends {t.end_date} with no solicitation linked. "
            f"Check SAM.gov for a presolicitation or sources sought." for t in rows]
