"""Contacts and relationship tracker: organizations (primes, agencies, vendors, teaming partners),
their contacts, an interaction log with follow-ups, a starter list, and a SAM.gov teaming partner finder."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import crm_seed
from .connectors import sam_entity
from .db import get_db
from .models_crm import INTERACTION_KINDS, ORG_KINDS, ORG_STAGES, Contact, Interaction, Organization

router = APIRouter(prefix="/api/crm", tags=["crm"])


# ------------------------------------------------------------------ schemas
class OrgIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    kind: str | None = None
    stage: str | None = None
    website: str | None = None
    supplier_portal: str | None = None
    uei: str | None = None
    cage: str | None = None
    city: str | None = None
    state: str | None = None
    naics_codes: list[str] | None = None
    capabilities: str | None = None
    business_types: dict[str, Any] | None = None
    is_manufacturer: bool | None = None
    tags: list[str] | None = None
    notes: str | None = None


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


class InteractionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    organization_id: int | None = None
    contact_id: int | None = None
    opportunity_id: int | None = None
    date: str | None = None
    kind: str | None = None
    summary: str | None = None
    next_step: str | None = None
    follow_up_date: str | None = None
    done: bool | None = None


class SaveEntityIn(BaseModel):
    entity: dict[str, Any]
    kind: str = "teaming_partner"


# ------------------------------------------------------------------ helpers
def _check(value: str | None, allowed: list[str], field: str) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(422, f"{field} must be one of: {', '.join(allowed)}")


def _check_date(value: str | None, field: str) -> None:
    if value:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise HTTPException(422, f"{field} must be YYYY-MM-DD")


def _get_org(db: Session, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


def contact_dict(c: Contact) -> dict:
    return {"id": c.id, "organization_id": c.organization_id, "name": c.name, "title": c.title,
            "email": c.email, "phone": c.phone, "notes": c.notes}


def interaction_dict(i: Interaction) -> dict:
    return {"id": i.id, "organization_id": i.organization_id, "contact_id": i.contact_id,
            "opportunity_id": i.opportunity_id, "date": i.date, "kind": i.kind, "summary": i.summary,
            "next_step": i.next_step, "follow_up_date": i.follow_up_date, "done": i.done}


def _next_follow_up(org: Organization) -> str:
    dates = [i.follow_up_date for i in org.interactions if i.follow_up_date and not i.done]
    return min(dates) if dates else ""


def org_dict(o: Organization, full: bool = False) -> dict:
    d = {
        "id": o.id, "name": o.name, "kind": o.kind, "stage": o.stage, "website": o.website,
        "supplier_portal": o.supplier_portal, "uei": o.uei, "cage": o.cage, "city": o.city, "state": o.state,
        "naics_codes": o.naics_codes or [], "capabilities": o.capabilities, "business_types": o.business_types or {},
        "is_manufacturer": o.is_manufacturer, "tags": o.tags or [], "notes": o.notes, "source": o.source,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
        "next_follow_up": _next_follow_up(o),
        "contact_count": len(o.contacts),
    }
    if full:
        d["contacts"] = [contact_dict(c) for c in o.contacts]
        d["interactions"] = [interaction_dict(i) for i in sorted(o.interactions, key=lambda i: (i.date or "", i.id), reverse=True)]
    return d


def open_follow_ups(db: Session, within_days: int | None = None) -> list[dict]:
    """Open (not done) interactions that have a follow-up date, overdue first then soonest.

    within_days limits to follow-ups due on or before today + within_days (overdue ones are always included).
    Each item: id, organization_id, organization, summary, next_step, follow_up_date, overdue.
    """
    today = date.today().isoformat()
    stmt = (
        select(Interaction, Organization.name)
        .join(Organization, Organization.id == Interaction.organization_id)
        .where(Interaction.done.is_(False), Interaction.follow_up_date != "", Interaction.follow_up_date.is_not(None))
    )
    if within_days is not None:
        stmt = stmt.where(Interaction.follow_up_date <= (date.today() + timedelta(days=within_days)).isoformat())
    rows = db.execute(stmt.order_by(Interaction.follow_up_date, Interaction.id)).all()
    return [
        {
            "id": i.id, "organization_id": i.organization_id, "organization": name, "summary": i.summary,
            "next_step": i.next_step, "follow_up_date": i.follow_up_date, "overdue": i.follow_up_date < today,
        }
        for i, name in rows
    ]


# ------------------------------------------------------------------ meta
@router.get("/meta")
def meta():
    return {"kinds": ORG_KINDS, "stages": ORG_STAGES, "interaction_kinds": INTERACTION_KINDS,
            "business_types": sam_entity.BUSINESS_TYPES}


# ------------------------------------------------------------------ organizations
@router.get("/organizations")
def list_orgs(kind: str = "", stage: str = "", q: str = "", tag: str = "", db: Session = Depends(get_db)):
    stmt = select(Organization)
    if kind:
        stmt = stmt.where(Organization.kind == kind)
    if stage:
        stmt = stmt.where(Organization.stage == stage)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(
            func.lower(Organization.name).like(like), func.lower(Organization.notes).like(like),
            func.lower(Organization.capabilities).like(like), func.lower(Organization.uei).like(like),
            func.lower(Organization.cage).like(like), func.lower(Organization.city).like(like),
        ))
    orgs = db.scalars(stmt.order_by(func.lower(Organization.name))).all()
    if tag:
        t = tag.lower()
        orgs = [o for o in orgs if any(t == str(x).lower() for x in (o.tags or []))]
    return [org_dict(o) for o in orgs]


@router.post("/organizations")
def create_org(body: OrgIn, db: Session = Depends(get_db)):
    if not (body.name or "").strip():
        raise HTTPException(422, "name is required")
    _check(body.kind, ORG_KINDS, "kind")
    _check(body.stage, ORG_STAGES, "stage")
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["name"] = data["name"].strip()
    if "state" in data:
        data["state"] = data["state"].upper()[:2]
    org = Organization(**data)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org_dict(org, full=True)


@router.get("/organizations/{org_id}")
def get_org(org_id: int, db: Session = Depends(get_db)):
    return org_dict(_get_org(db, org_id), full=True)


@router.put("/organizations/{org_id}")
def update_org(org_id: int, body: OrgIn, db: Session = Depends(get_db)):
    org = _get_org(db, org_id)
    _check(body.kind, ORG_KINDS, "kind")
    _check(body.stage, ORG_STAGES, "stage")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(422, "name cannot be blank")
    for k, v in data.items():
        if v is None:
            continue
        if k == "state":
            v = v.upper()[:2]
        setattr(org, k, v)
    db.commit()
    db.refresh(org)
    return org_dict(org, full=True)


@router.delete("/organizations/{org_id}")
def delete_org(org_id: int, db: Session = Depends(get_db)):
    org = _get_org(db, org_id)
    db.delete(org)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ contacts
@router.get("/organizations/{org_id}/contacts")
def list_contacts(org_id: int, db: Session = Depends(get_db)):
    return [contact_dict(c) for c in _get_org(db, org_id).contacts]


@router.post("/organizations/{org_id}/contacts")
def create_contact(org_id: int, body: ContactIn, db: Session = Depends(get_db)):
    _get_org(db, org_id)
    if not (body.name or "").strip():
        raise HTTPException(422, "name is required")
    c = Contact(organization_id=org_id, **{k: v for k, v in body.model_dump().items() if v is not None})
    db.add(c)
    db.commit()
    db.refresh(c)
    return contact_dict(c)


def _get_contact(db: Session, org_id: int, contact_id: int) -> Contact:
    c = db.get(Contact, contact_id)
    if not c or c.organization_id != org_id:
        raise HTTPException(404, "Contact not found")
    return c


@router.put("/organizations/{org_id}/contacts/{contact_id}")
def update_contact(org_id: int, contact_id: int, body: ContactIn, db: Session = Depends(get_db)):
    c = _get_contact(db, org_id, contact_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(c, k, v)
    db.commit()
    return contact_dict(c)


@router.delete("/organizations/{org_id}/contacts/{contact_id}")
def delete_contact(org_id: int, contact_id: int, db: Session = Depends(get_db)):
    c = _get_contact(db, org_id, contact_id)
    for i in db.scalars(select(Interaction).where(Interaction.contact_id == contact_id)):
        i.contact_id = None
    db.delete(c)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ interactions
def _validate_interaction(db: Session, i: InteractionIn, org_id: int) -> None:
    _check(i.kind, INTERACTION_KINDS, "kind")
    _check_date(i.date, "date")
    _check_date(i.follow_up_date, "follow_up_date")
    if i.contact_id:
        c = db.get(Contact, i.contact_id)
        if not c or c.organization_id != org_id:
            raise HTTPException(422, "contact_id does not belong to this organization")


@router.get("/interactions")
def list_interactions(organization_id: int | None = None, opportunity_id: int | None = None, open_only: bool = False,
                      db: Session = Depends(get_db)):
    stmt = select(Interaction)
    if organization_id:
        stmt = stmt.where(Interaction.organization_id == organization_id)
    if opportunity_id:
        stmt = stmt.where(Interaction.opportunity_id == opportunity_id)
    if open_only:
        stmt = stmt.where(Interaction.done.is_(False))
    return [interaction_dict(i) for i in db.scalars(stmt.order_by(Interaction.date.desc(), Interaction.id.desc()))]


@router.post("/organizations/{org_id}/interactions")
def create_interaction(org_id: int, body: InteractionIn, db: Session = Depends(get_db)):
    _get_org(db, org_id)
    _validate_interaction(db, body, org_id)
    data = {k: v for k, v in body.model_dump().items() if v is not None and k != "organization_id"}
    data.setdefault("date", date.today().isoformat())
    i = Interaction(organization_id=org_id, **data)
    db.add(i)
    db.commit()
    db.refresh(i)
    return interaction_dict(i)


@router.post("/interactions")
def create_interaction_flat(body: InteractionIn, db: Session = Depends(get_db)):
    if not body.organization_id:
        raise HTTPException(422, "organization_id is required")
    return create_interaction(body.organization_id, body, db)


@router.put("/interactions/{interaction_id}")
def update_interaction(interaction_id: int, body: InteractionIn, db: Session = Depends(get_db)):
    i = db.get(Interaction, interaction_id)
    if not i:
        raise HTTPException(404, "Interaction not found")
    _validate_interaction(db, body, i.organization_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k == "organization_id":
            continue
        if v is None and k not in ("contact_id", "opportunity_id"):
            continue
        setattr(i, k, v)
    db.commit()
    return interaction_dict(i)


@router.delete("/interactions/{interaction_id}")
def delete_interaction(interaction_id: int, db: Session = Depends(get_db)):
    i = db.get(Interaction, interaction_id)
    if not i:
        raise HTTPException(404, "Interaction not found")
    db.delete(i)
    db.commit()
    return {"ok": True}


@router.get("/follow-ups")
def follow_ups(within_days: int | None = Query(14, ge=0, le=3650), db: Session = Depends(get_db)):
    return open_follow_ups(db, within_days)


# ------------------------------------------------------------------ seed
@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    return crm_seed.seed(db)


# ------------------------------------------------------------------ teaming finder
@router.get("/teaming/search")
def teaming_search(naics: str = "", state: str = "", business_type: str = "", q: str = "", page: int = Query(0, ge=0, le=999),
                   db: Session = Depends(get_db)):
    try:
        res = sam_entity.search(naics=naics, state=state, business_type=business_type, q=q, page=page)
    except sam_entity.EntityApiError as e:
        raise HTTPException(400, str(e))
    ueis = [r["uei"] for r in res["results"] if r["uei"]]
    saved = {}
    if ueis:
        saved = {u: (oid, k) for u, oid, k in db.execute(
            select(Organization.uei, Organization.id, Organization.kind).where(Organization.uei.in_(ueis)))}
    for r in res["results"]:
        if r["uei"] in saved:
            r["saved_id"], r["saved_kind"] = saved[r["uei"]]
    return res


@router.post("/teaming/save")
def teaming_save(body: SaveEntityIn, db: Session = Depends(get_db)):
    e = body.entity
    _check(body.kind, ORG_KINDS, "kind")
    uei = (e.get("uei") or "").strip().upper()
    name = (e.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "entity.name is required")
    org = db.scalar(select(Organization).where(Organization.uei == uei)) if uei else None
    created = org is None
    if created:
        org = Organization(name=name, kind=body.kind, stage="identified", source="sam_entity")
        db.add(org)
    else:
        org.kind = body.kind or org.kind
    org.name = name
    org.uei = uei
    org.cage = e.get("cage") or org.cage or ""
    org.city = e.get("city") or org.city or ""
    org.state = (e.get("state") or org.state or "")[:2].upper()
    org.naics_codes = list(e.get("naics_codes") or org.naics_codes or [])
    org.business_types = dict(e.get("business_types") or org.business_types or {})
    org.website = e.get("website") or org.website or ""
    if e.get("is_manufacturer"):
        org.is_manufacturer = True
    if created and e.get("primary_naics"):
        org.notes = f"Found in SAM.gov entity search. Primary NAICS {e['primary_naics']}."
    db.flush()
    poc = e.get("poc") or {}
    if poc.get("name") and not any(c.name.lower() == poc["name"].lower() for c in org.contacts):
        db.add(Contact(organization_id=org.id, name=poc["name"], title=poc.get("title") or poc.get("role") or "",
                       email=poc.get("email") or "", phone=poc.get("phone") or "", notes="From SAM.gov registration"))
    db.commit()
    db.refresh(org)
    return {"created": created, "organization": org_dict(org, full=True)}
