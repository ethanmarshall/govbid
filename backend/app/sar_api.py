"""Source Approval Request (SAR) tracker API.

Process facts (categories, checklist, review time, format, submission addresses) come from the DLA "Source Approval
Request (SAR) and Alternate Offer (AO) Guide", November 2022:
https://www.dla.mil/Portals/104/Documents/SmallBusiness/DLA%20SAR%20Guide.pdf
(content read from the Internet Archive copy captured 2026-08-09). See app/models_sar.py for the details and page
references. Supporting source for the categories: DLA small business SAR training slides (5/11/2023),
https://www.dla.mil/Portals/104/Documents/SmallBusiness/SAR%20TKO%20Slides%205-11-2023.pdf
No separate "eSAR" web portal is described in the guide: packages go by email (DoD SAFE link over 8 MB).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import Opportunity, PartQuote
from .models_sar import (
    CATEGORY_KEYS, DLA_ACTIVITIES, DLA_SAR_CONTACTS, EXTRA_DOC_SECTIONS, ITEM_STATES, REVIEW_LONG_DAYS,
    REVIEW_MIN_DAYS, SAR_CATEGORIES, SAR_CHECKLIST, SAR_GUIDE_TITLE, SAR_GUIDE_URL, SAR_STATUSES, SourceApproval,
)
from .nsn_history import history, normalize_nsn, reference_price, try_nsn

router = APIRouter(prefix="/api/sar", tags=["sar"])

MAX_UPLOAD = 50 * 1024 * 1024


# ------------------------------------------------------------------ helpers
def sar_dir(sar_id: int) -> Path:
    d = Path(config.UPLOAD_DIR) / "sar" / str(sar_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "file"
    return name[:150]


def _parse_date(s: str) -> date | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _niin_digits(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    return d[-9:] if len(d) in (9, 13) else ""


def checklist_for(s: SourceApproval) -> list[dict]:
    """Checklist rows with required flag for the SAR's category, stored state and uploaded files."""
    state = s.checklist or {}
    files = s.files or []
    rows = []
    for c in SAR_CHECKLIST:
        required = (s.category in c["categories"]) if s.category else True
        st = state.get(c["key"]) or {}
        rows.append({**c, "required": required, "status": st.get("status", "todo"), "note": st.get("note", ""),
                     "files": [f for f in files if f.get("section") == c["key"]]})
    for key, title in EXTRA_DOC_SECTIONS.items():
        rows.append({"key": key, "section": "", "title": title, "categories": [], "hint": "", "required": False,
                     "status": (state.get(key) or {}).get("status", "todo"), "note": (state.get(key) or {}).get("note", ""),
                     "files": [f for f in files if f.get("section") == key]})
    return rows


def linked_opportunities(db: Session, niin: str) -> list[dict]:
    if not niin:
        return []
    out = []
    for o in db.scalars(select(Opportunity).where(Opportunity.nsn != "")).all():
        if _niin_digits(o.nsn) == niin:
            out.append({"id": o.id, "title": o.title, "solicitation_number": o.solicitation_number, "source": o.source,
                        "response_deadline": o.response_deadline, "quantity": o.quantity, "active": o.active})
    out.sort(key=lambda r: r["response_deadline"] or "", reverse=True)
    return out


def days_in_review(s: SourceApproval, today: date | None = None) -> int | None:
    d = _parse_date(s.submitted_date)
    if not d or s.status not in ("submitted", "under_review"):
        return None
    return ((today or date.today()) - d).days


def sar_dict(db: Session, s: SourceApproval, full: bool = False) -> dict:
    price = reference_price(db, s.nsn) if s.nsn else None
    value = round(price * s.annual_demand, 2) if price is not None and s.annual_demand else None
    rows = checklist_for(s)
    req = [r for r in rows if r["required"]]
    done = [r for r in req if r["status"] in ("done", "na")]
    d = {
        "id": s.id, "nsn": s.nsn, "niin": s.niin, "part_number": s.part_number, "nomenclature": s.nomenclature,
        "approved_sources": s.approved_sources or [], "dla_activity": s.dla_activity, "category": s.category, "amsc": s.amsc,
        "solicitation_number": s.solicitation_number, "status": s.status, "submitted_date": s.submitted_date,
        "decision_date": s.decision_date, "decision_notes": s.decision_notes, "approved_part_number": s.approved_part_number,
        "approved_cage": s.approved_cage, "annual_demand": s.annual_demand, "last_award_price": price,
        "estimated_annual_value": value, "checklist_done": len(done), "checklist_required": len(req),
        "days_in_review": days_in_review(s), "file_count": len(s.files or []),
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
    if full:
        d.update({
            "checklist": rows, "files": s.files or [], "re_measurements": s.re_measurements, "re_materials": s.re_materials,
            "re_notes": s.re_notes, "notes": s.notes, "linked_opportunities": linked_opportunities(db, s.niin),
            "contact": DLA_SAR_CONTACTS.get(s.dla_activity),
            "file_name_hint": f"NSN {s.nsn} CAGE <your CAGE>.pdf" if s.nsn else "",
        })
    return d


def _get(db: Session, sar_id: int) -> SourceApproval:
    s = db.get(SourceApproval, sar_id)
    if not s:
        raise HTTPException(404, "Source approval request not found")
    return s


# ------------------------------------------------------------------ schemas
class SarIn(BaseModel):
    nsn: str | None = None
    part_number: str | None = None
    nomenclature: str | None = None
    approved_sources: list | None = None
    dla_activity: str | None = None
    category: str | None = None
    amsc: str | None = None
    solicitation_number: str | None = None
    status: str | None = None
    submitted_date: str | None = None
    decision_date: str | None = None
    decision_notes: str | None = None
    approved_part_number: str | None = None
    approved_cage: str | None = None
    annual_demand: int | None = None
    checklist: dict | None = None
    re_measurements: str | None = None
    re_materials: str | None = None
    re_notes: str | None = None
    notes: str | None = None


def _apply(s: SourceApproval, data: dict) -> None:
    if "nsn" in data:
        raw = (data.pop("nsn") or "").strip()
        if raw:
            try:
                n = normalize_nsn(raw)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            s.nsn, s.niin = n["nsn"], n["niin"]
        else:
            s.nsn, s.niin = "", ""
    if data.get("status") is not None and data["status"] not in SAR_STATUSES:
        raise HTTPException(400, f"status must be one of {SAR_STATUSES}")
    if data.get("category") and data["category"] not in CATEGORY_KEYS:
        raise HTTPException(400, f"category must be one of {CATEGORY_KEYS}")
    if data.get("dla_activity") and data["dla_activity"] not in DLA_ACTIVITIES:
        raise HTTPException(400, f"dla_activity must be one of {DLA_ACTIVITIES}")
    for f in ("submitted_date", "decision_date"):
        if data.get(f) and not _parse_date(data[f]):
            raise HTTPException(400, f"{f} must be YYYY-MM-DD")
    if data.get("annual_demand") is not None and data["annual_demand"] < 0:
        raise HTTPException(400, "annual_demand cannot be negative")
    if "approved_sources" in data and data["approved_sources"] is not None:
        clean = []
        for a in data["approved_sources"]:
            if isinstance(a, str):
                a = {"cage": a}
            if not isinstance(a, dict):
                continue
            row = {"cage": str(a.get("cage", "")).strip().upper()[:10], "part_number": str(a.get("part_number", "")).strip()[:80],
                   "name": str(a.get("name", "")).strip()[:200]}
            if row["cage"] or row["part_number"] or row["name"]:
                clean.append(row)
        data["approved_sources"] = clean
    if "checklist" in data and data["checklist"] is not None:
        merged = dict(s.checklist or {})
        for k, v in data["checklist"].items():
            if k not in CHECKLIST_ALL or not isinstance(v, dict):
                continue
            st = v.get("status", (merged.get(k) or {}).get("status", "todo"))
            if st not in ITEM_STATES:
                raise HTTPException(400, f"checklist status must be one of {ITEM_STATES}")
            merged[k] = {"status": st, "note": str(v.get("note", (merged.get(k) or {}).get("note", "")))[:2000]}
        data["checklist"] = merged
    if data.get("status") in ("submitted", "under_review") and not (data.get("submitted_date") or s.submitted_date):
        data["submitted_date"] = date.today().isoformat()
    if data.get("status") in ("approved", "disapproved") and not (data.get("decision_date") or s.decision_date):
        data["decision_date"] = date.today().isoformat()
    for k, v in data.items():
        if v is None and k not in ("annual_demand",):
            continue
        setattr(s, k, v)


CHECKLIST_ALL = {c["key"] for c in SAR_CHECKLIST} | set(EXTRA_DOC_SECTIONS)


# ------------------------------------------------------------------ meta and candidates (before /{sar_id})
@router.get("/meta")
def meta():
    return {
        "statuses": SAR_STATUSES, "activities": DLA_ACTIVITIES, "categories": SAR_CATEGORIES, "checklist": SAR_CHECKLIST,
        "extra_sections": EXTRA_DOC_SECTIONS, "item_states": ITEM_STATES, "contacts": DLA_SAR_CONTACTS,
        "review_min_days": REVIEW_MIN_DAYS, "review_long_days": REVIEW_LONG_DAYS,
        "guide": {"title": SAR_GUIDE_TITLE, "url": SAR_GUIDE_URL},
    }


def _quote_needs_approval(q: PartQuote) -> bool:
    if (q.spec or {}).get("approved_source_required") is False:
        return False
    warns = (q.result or {}).get("warnings") or []
    if any("approved source" in str(w).lower() for w in warns):
        return True
    return (q.spec or {}).get("approved_source_required") is True


def sar_candidates(db: Session, limit: int = 50) -> list[dict]:
    """NSNs worth a SAR: seen in opportunities (DIBBS imports, SAM notices) or in part quotes flagged as approved-source only.

    Ranked by number of distinct solicitations, then by the last award value (unit price x quantity when known).
    """
    groups: dict[str, dict] = {}

    def grp(nsn: str) -> dict | None:
        n = try_nsn(nsn)
        if not n:
            return None
        g = groups.get(n["niin"])
        if not g:
            g = groups[n["niin"]] = {"nsn": n["nsn"], "niin": n["niin"], "nomenclature": "", "solicitations": set(),
                                     "opportunity_ids": [], "quote_ids": [], "last_seen": "", "quantities": []}
        elif len(n["nsn"]) > len(g["nsn"]):
            g["nsn"] = n["nsn"]
        return g

    for o in db.scalars(select(Opportunity).where(Opportunity.nsn != "")).all():
        g = grp(o.nsn)
        if not g:
            continue
        g["solicitations"].add((o.solicitation_number or f"opp-{o.id}").strip().upper())
        g["opportunity_ids"].append(o.id)
        g["nomenclature"] = g["nomenclature"] or (o.title or "")[:120]
        g["last_seen"] = max(g["last_seen"], o.posted_date or "")
        if o.quantity:
            g["quantities"].append(o.quantity)
    for q in db.scalars(select(PartQuote).where(PartQuote.nsn != "")).all():
        if not _quote_needs_approval(q):
            continue
        g = grp(q.nsn)
        if not g:
            continue
        g["quote_ids"].append(q.id)
        g["nomenclature"] = g["nomenclature"] or (q.name or "")[:120]

    existing = {s.niin: s for s in db.scalars(select(SourceApproval)).all() if s.niin}
    out = []
    for niin, g in groups.items():
        try:
            h = history(db, g["nsn"])
        except ValueError:
            h = {"records": [], "stats": {}}
        st = h.get("stats") or {}
        awards = [r for r in h.get("records", []) if r.get("source") != "quote_lost"]
        last_val = None
        last_cage = ""
        if awards:
            a = awards[0]
            last_cage = a.get("cage") or ""
            if a.get("total"):
                last_val = a["total"]
            elif a.get("unit_price") is not None and a.get("quantity"):
                last_val = round(a["unit_price"] * a["quantity"], 2)
        s = existing.get(niin)
        out.append({
            "nsn": g["nsn"], "niin": niin, "nomenclature": g["nomenclature"], "solicitation_count": len(g["solicitations"]),
            "opportunity_ids": g["opportunity_ids"], "quote_ids": g["quote_ids"], "last_seen": g["last_seen"],
            "quantities": g["quantities"][:5], "last_unit_price": st.get("last_unit_price"), "last_award_value": last_val,
            "last_award_date": st.get("last_award_date"), "last_awardee": st.get("last_awardee"), "last_awardee_cage": last_cage,
            "award_count": st.get("award_count", 0), "existing_sar_id": s.id if s else None, "existing_sar_status": s.status if s else None,
        })
    out.sort(key=lambda r: (r["existing_sar_id"] is None, r["solicitation_count"], r["last_award_value"] or 0,
                            r["last_unit_price"] or 0), reverse=True)
    return out[:limit]


@router.get("/candidates")
def candidates(limit: int = 50, db: Session = Depends(get_db)):
    return sar_candidates(db, limit=max(1, min(limit, 500)))


# ------------------------------------------------------------------ CRUD
@router.get("")
def list_sars(status: str = "", q: str = "", db: Session = Depends(get_db)):
    rows = db.scalars(select(SourceApproval).order_by(SourceApproval.updated_at.desc())).all()
    if status:
        rows = [r for r in rows if r.status == status]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in f"{r.nsn} {r.niin} {r.part_number} {r.nomenclature} {r.notes}".lower()]
    return [sar_dict(db, r) for r in rows]


@router.post("")
def create_sar(body: SarIn, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if not (data.get("nsn") or "").strip():
        raise HTTPException(400, "NSN is required")
    s = SourceApproval()
    _apply(s, data)
    if not s.nomenclature:
        # fill nomenclature from award history or an opportunity when known
        try:
            recs = history(db, s.nsn)["records"]
            s.nomenclature = next((r["nomenclature"] for r in recs if r.get("nomenclature")), "")
        except ValueError:
            pass
    db.add(s)
    db.commit()
    return sar_dict(db, s, full=True)


@router.get("/{sar_id}")
def read_sar(sar_id: int, db: Session = Depends(get_db)):
    return sar_dict(db, _get(db, sar_id), full=True)


@router.put("/{sar_id}")
def update_sar(sar_id: int, body: SarIn, db: Session = Depends(get_db)):
    s = _get(db, sar_id)
    _apply(s, body.model_dump(exclude_unset=True))
    s.updated_at = datetime.utcnow()
    db.commit()
    return sar_dict(db, s, full=True)


@router.delete("/{sar_id}")
def delete_sar(sar_id: int, db: Session = Depends(get_db)):
    s = _get(db, sar_id)
    d = Path(config.UPLOAD_DIR) / "sar" / str(s.id)
    db.delete(s)
    db.commit()
    if d.exists():
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}


# ------------------------------------------------------------------ documents
@router.post("/{sar_id}/documents")
async def upload_documents(sar_id: int, section: str = Form(...), files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    s = _get(db, sar_id)
    if section not in CHECKLIST_ALL:
        raise HTTPException(400, f"section must be one of {sorted(CHECKLIST_ALL)}")
    d = sar_dir(s.id)
    have = list(s.files or [])
    names = {f["name"] for f in have}
    added = []
    for up in files:
        data = await up.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(400, f"{up.filename} is over 50 MB")
        base = f"{section}-{_safe(up.filename)}"
        name, n = base, 1
        stem, suffix = Path(base).stem, Path(base).suffix
        while name in names:
            n += 1
            name = f"{stem} ({n}){suffix}"
        (d / name).write_bytes(data)
        names.add(name)
        rec = {"section": section, "name": name, "original": up.filename or name, "size": len(data),
               "uploaded_at": datetime.utcnow().isoformat(timespec="seconds")}
        have.append(rec)
        added.append(rec)
    s.files = have
    st = dict(s.checklist or {})
    if section in st and st[section].get("status") == "todo" or section not in st:
        st[section] = {"status": "in_progress", "note": (st.get(section) or {}).get("note", "")}
    s.checklist = st
    s.updated_at = datetime.utcnow()
    db.commit()
    return {"added": added, "sar": sar_dict(db, s, full=True)}


def _file_rec(s: SourceApproval, name: str) -> dict:
    rec = next((f for f in s.files or [] if f["name"] == name), None)
    if not rec:
        raise HTTPException(404, "File not found")
    return rec


@router.get("/{sar_id}/documents/{name}")
def download_document(sar_id: int, name: str, db: Session = Depends(get_db)):
    s = _get(db, sar_id)
    rec = _file_rec(s, name)
    p = sar_dir(s.id) / rec["name"]
    if not p.exists():
        raise HTTPException(404, "File is missing on disk")
    return FileResponse(p, filename=rec.get("original") or rec["name"])


@router.delete("/{sar_id}/documents/{name}")
def delete_document(sar_id: int, name: str, db: Session = Depends(get_db)):
    s = _get(db, sar_id)
    rec = _file_rec(s, name)
    p = sar_dir(s.id) / rec["name"]
    if p.exists():
        p.unlink()
    s.files = [f for f in s.files or [] if f["name"] != name]
    s.updated_at = datetime.utcnow()
    db.commit()
    return sar_dict(db, s, full=True)


# ------------------------------------------------------------------ calendar and dashboard hooks
def calendar_items(db: Session) -> list[dict]:
    """Expected decision windows for submitted SARs (DLA guide: at least 90 days, possibly 180 or longer)."""
    out = []
    for s in db.scalars(select(SourceApproval).where(SourceApproval.status.in_(["submitted", "under_review"]))).all():
        d = _parse_date(s.submitted_date)
        if not d:
            continue
        label = f"NSN {s.nsn}" + (f" ({s.nomenclature[:40]})" if s.nomenclature else "")
        out.append({"uid": f"sar-{s.id}-90", "date": d + timedelta(days=REVIEW_MIN_DAYS),
                    "summary": f"SAR: earliest typical decision, {label}",
                    "description": f"Submitted {s.submitted_date} to DLA {s.dla_activity or ''}. DLA says reviews take at least {REVIEW_MIN_DAYS} days.".strip(),
                    "url": f"/source-approvals?id={s.id}"})
        out.append({"uid": f"sar-{s.id}-180", "date": d + timedelta(days=REVIEW_LONG_DAYS),
                    "summary": f"SAR: ask for status, {label}",
                    "description": f"{REVIEW_LONG_DAYS} days since submission. Contact the SAR monitor if there is no decision.",
                    "url": f"/source-approvals?id={s.id}"})
    return out


def dashboard_items(db: Session) -> list[str]:
    """SARs in review longer than DLA's stated typical range (180 days)."""
    out = []
    for s in db.scalars(select(SourceApproval).where(SourceApproval.status.in_(["submitted", "under_review"]))).all():
        n = days_in_review(s)
        if n is not None and n > REVIEW_LONG_DAYS:
            who = DLA_SAR_CONTACTS.get(s.dla_activity, {}).get("sar_email", "")
            out.append(f"SAR for NSN {s.nsn} has been in review {n} days (DLA typical: {REVIEW_MIN_DAYS} to {REVIEW_LONG_DAYS}). "
                       f"Ask the SAR monitor for status{(' at ' + who) if who else ''}.")
    return out
