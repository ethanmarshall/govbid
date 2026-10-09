"""Package builder API: proposal packages and technical data packages."""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import analysis as analysis_mod
from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, UPLOAD_DIR
from .db import get_db
from .models import (
    ITEM_STATUSES, LIBRARY_CATEGORIES, PACKAGE_KINDS, PACKAGE_STATUSES, SECTION_STATUSES,
    LibraryEntry, Opportunity, Package, PackageItem, PackageSection,
)
from .package_export import build_docx, build_zip, safe_name, words
from .package_templates import TEMPLATES
from .services import get_profile

router = APIRouter(prefix="/api")

WORDS_PER_PAGE = 500  # single-spaced 12 pt with 1-inch margins, roughly


# ------------------------------------------------------------------ paths and serializers
def pkg_dir(pkg_id: int) -> Path:
    d = UPLOAD_DIR / "packages" / f"pkg_{pkg_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def item_dir_for(pkg_id: int):
    def _f(item_id: int) -> Path:
        d = pkg_dir(pkg_id) / f"item_{item_id}"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return _f


def section_dict(s: PackageSection) -> dict:
    w = words(s.content)
    return {
        "id": s.id, "position": s.position, "volume": s.volume, "number": s.number, "title": s.title,
        "guidance": s.guidance, "content": s.content, "page_limit": s.page_limit, "status": s.status,
        "requirement_ids": s.requirement_ids or [], "covered_ids": s.covered_ids or [],
        "page_break_before": s.page_break_before, "words": w, "est_pages": round(w / WORDS_PER_PAGE, 1),
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def item_dict(i: PackageItem) -> dict:
    return {"id": i.id, "position": i.position, "cdrl": i.cdrl, "title": i.title, "did": i.did, "category": i.category,
            "status": i.status, "due": i.due, "notes": i.notes, "files": i.files or []}


def matrix_for(pkg: Package) -> list[dict]:
    o = pkg.opportunity
    return list(o.analysis.compliance_matrix) if o and o.analysis else []


def package_summary(p: Package) -> dict:
    secs = p.sections
    items = p.items
    matrix = matrix_for(p)
    assigned = {rid for s in secs for rid in (s.requirement_ids or [])}
    covered = {rid for s in secs for rid in (s.covered_ids or [])}
    return {
        "id": p.id, "name": p.name, "kind": p.kind, "status": p.status, "due_date": p.due_date,
        "contract_number": p.contract_number, "opportunity_id": p.opportunity_id,
        "opportunity_title": p.opportunity.title if p.opportunity else None,
        "sections_total": len(secs), "sections_done": sum(1 for s in secs if s.status == "done"),
        "items_total": len(items), "items_ready": sum(1 for i in items if i.status in ("ready", "delivered", "accepted")),
        "requirements_total": len(matrix), "requirements_assigned": len(assigned), "requirements_covered": len(covered),
        "words": sum(words(s.content) for s in secs),
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def package_full(p: Package) -> dict:
    d = package_summary(p)
    d.update({
        "cover": p.cover or {}, "notes": p.notes,
        "sections": [section_dict(s) for s in p.sections],
        "items": [item_dict(i) for i in p.items],
        "matrix": matrix_for(p),
        "opportunity": None,
    })
    if p.opportunity:
        o = p.opportunity
        d["opportunity"] = {"id": o.id, "title": o.title, "solicitation_number": o.solicitation_number, "agency": o.agency,
                            "response_deadline": o.response_deadline, "has_analysis": o.analysis is not None,
                            "page_limits": (o.analysis.breakdown or {}).get("page_limits", []) if o.analysis else []}
    return d


def get_pkg(db: Session, pkg_id: int) -> Package:
    p = db.get(Package, pkg_id)
    if not p:
        raise HTTPException(404, "Package not found")
    return p


def touch(p: Package) -> None:
    p.updated_at = datetime.utcnow()


# ------------------------------------------------------------------ requirement assignment and coverage sync
def assign_requirements(sections: list[PackageSection], matrix: list[dict], template: list) -> None:
    """Put each compliance row in the template section whose categories include the row's category."""
    if not sections or not matrix:
        return
    by_cat: dict[str, PackageSection] = {}
    for sec, tpl in zip(sections, template):
        for cat in tpl[4]:
            by_cat.setdefault(cat, sec)
    fallback = by_cat.get("Technical / performance") or sections[min(1, len(sections) - 1)]
    buckets: dict[int, list] = {}
    for row in matrix:
        target = by_cat.get(row.get("category") or "", fallback)
        buckets.setdefault(id(target), []).append(row.get("id"))
    for sec in sections:
        sec.requirement_ids = buckets.get(id(sec), [])


def location_label(s: PackageSection) -> str:
    vol = re.sub(r"^(Volume\s+[IVX0-9]+).*", r"\1", s.volume or "")
    return " ".join(x for x in (vol, s.number, s.title) if x)


def sync_coverage(db: Session, pkg: Package) -> None:
    """Write 'where addressed' back to the opportunity's compliance matrix."""
    o = pkg.opportunity
    if not o or not o.analysis:
        return
    loc_for: dict = {}
    assigned_to: dict = {}
    for s in pkg.sections:
        for rid in s.requirement_ids or []:
            assigned_to[rid] = location_label(s)
        for rid in s.covered_ids or []:
            loc_for[rid] = location_label(s)
    changed = False
    rows = []
    for r in o.analysis.compliance_matrix:
        r = dict(r)
        rid = r.get("id")
        if rid in loc_for:
            if r.get("response_location") != loc_for[rid] or r.get("status") != "done":
                r["response_location"], r["status"] = loc_for[rid], "done"
                changed = True
        elif rid in assigned_to and r.get("status") == "done" and r.get("response_location") in set(assigned_to.values()):
            r["response_location"], r["status"] = "", "open"
            changed = True
        rows.append(r)
    if changed:
        o.analysis.compliance_matrix = rows  # reassign so SQLAlchemy sees the JSON change


# ------------------------------------------------------------------ packages
class PackageCreate(BaseModel):
    name: str = ""
    kind: str = "proposal"
    template: str = "auto"  # auto = kind's template, or "blank"
    opportunity_id: int | None = None
    contract_number: str = ""


@router.get("/package-meta")
def package_meta():
    return {"kinds": PACKAGE_KINDS, "statuses": PACKAGE_STATUSES, "section_statuses": SECTION_STATUSES,
            "item_statuses": ITEM_STATUSES, "library_categories": LIBRARY_CATEGORIES, "ai_configured": bool(ANTHROPIC_API_KEY),
            "words_per_page": WORDS_PER_PAGE}


@router.get("/packages")
def list_packages(opportunity_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Package).order_by(Package.updated_at.desc())
    if opportunity_id:
        stmt = stmt.where(Package.opportunity_id == opportunity_id)
    return [package_summary(p) for p in db.scalars(stmt).all()]


@router.post("/packages")
def create_package(body: PackageCreate, db: Session = Depends(get_db)):
    if body.kind not in PACKAGE_KINDS:
        raise HTTPException(400, f"kind must be one of {PACKAGE_KINDS}")
    opp = db.get(Opportunity, body.opportunity_id) if body.opportunity_id else None
    if body.opportunity_id and not opp:
        raise HTTPException(404, "Opportunity not found")
    profile = get_profile(db)
    certs = profile.certifications or {}
    status_bits = ["Service-Disabled Veteran-Owned Small Business" if certs.get("SDVOSB") == "certified" else "",
                   "Small Business" if certs.get("SB") == "certified" else ""]
    name = body.name.strip() or (f"{opp.title}" if opp else ("New technical data package" if body.kind == "tdp" else "New proposal"))
    pkg = Package(
        name=name[:300], kind=body.kind, opportunity_id=opp.id if opp else None,
        due_date=opp.response_deadline if opp and body.kind == "proposal" else "",
        contract_number=body.contract_number,
        cover={
            "solicitation_number": opp.solicitation_number if opp else "",
            "agency": opp.agency if opp else "",
            "business_status": next((b for b in status_bits if b), ""),
            "validity_days": 90 if body.kind == "proposal" else None,
            "font": "Times New Roman", "font_size": 12,
            "distribution_statement": "DISTRIBUTION STATEMENT C. Distribution authorized to U.S. Government agencies and their contractors." if body.kind == "tdp" else "",
        },
    )
    db.add(pkg)
    db.flush()
    tpl_key = body.kind if body.template == "auto" else body.template
    sections_tpl, items_tpl = TEMPLATES.get(tpl_key, ([], []))
    sections = []
    for pos, (vol, num, title, guidance, _cats, brk) in enumerate(sections_tpl):
        s = PackageSection(package_id=pkg.id, position=pos, volume=vol, number=num, title=title, guidance=guidance, page_break_before=brk)
        db.add(s)
        sections.append(s)
    for pos, (cdrl, title, did, cat) in enumerate(items_tpl):
        db.add(PackageItem(package_id=pkg.id, position=pos, cdrl=cdrl, title=title, did=did, category=cat))
    if opp and opp.analysis and sections:
        assign_requirements(sections, opp.analysis.compliance_matrix or [], sections_tpl)
    db.commit()
    db.refresh(pkg)
    return package_full(pkg)


@router.get("/packages/{pkg_id}")
def read_package(pkg_id: int, db: Session = Depends(get_db)):
    return package_full(get_pkg(db, pkg_id))


class PackageUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    due_date: str | None = None
    contract_number: str | None = None
    opportunity_id: int | None = None
    cover: dict | None = None
    notes: str | None = None


@router.put("/packages/{pkg_id}")
def update_package(pkg_id: int, body: PackageUpdate, db: Session = Depends(get_db)):
    p = get_pkg(db, pkg_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in PACKAGE_STATUSES:
        raise HTTPException(400, f"status must be one of {PACKAGE_STATUSES}")
    if "opportunity_id" in data and data["opportunity_id"] and not db.get(Opportunity, data["opportunity_id"]):
        raise HTTPException(404, "Opportunity not found")
    for k, v in data.items():
        setattr(p, k, v)
    touch(p)
    db.commit()
    db.refresh(p)
    return package_full(p)


@router.delete("/packages/{pkg_id}")
def delete_package(pkg_id: int, db: Session = Depends(get_db)):
    p = get_pkg(db, pkg_id)
    db.delete(p)
    db.commit()
    shutil.rmtree(UPLOAD_DIR / "packages" / f"pkg_{pkg_id}", ignore_errors=True)
    return {"ok": True}


# ------------------------------------------------------------------ sections
class SectionIn(BaseModel):
    volume: str | None = None
    number: str | None = None
    title: str | None = None
    guidance: str | None = None
    content: str | None = None
    page_limit: float | None = None
    status: str | None = None
    requirement_ids: list | None = None
    covered_ids: list | None = None
    page_break_before: bool | None = None
    after_id: int | None = None  # create only: insert after this section


@router.post("/packages/{pkg_id}/sections")
def add_section(pkg_id: int, body: SectionIn, db: Session = Depends(get_db)):
    p = get_pkg(db, pkg_id)
    secs = list(p.sections)
    idx = len(secs)
    if body.after_id:
        for n, s in enumerate(secs):
            if s.id == body.after_id:
                idx = n + 1
                break
    prev = secs[idx - 1] if idx > 0 and secs else None
    new = PackageSection(package_id=p.id, volume=body.volume if body.volume is not None else (prev.volume if prev else ""),
                         number=body.number or "", title=body.title or "New section", guidance=body.guidance or "", content=body.content or "")
    secs.insert(idx, new)
    p.sections = secs
    for n, s in enumerate(secs):
        s.position = n
    touch(p)
    db.commit()
    return package_full(p)


@router.put("/sections/{sid}")
def update_section(sid: int, body: SectionIn, db: Session = Depends(get_db)):
    s = db.get(PackageSection, sid)
    if not s:
        raise HTTPException(404, "Section not found")
    data = body.model_dump(exclude_unset=True)
    data.pop("after_id", None)
    if "status" in data and data["status"] not in SECTION_STATUSES:
        raise HTTPException(400, f"status must be one of {SECTION_STATUSES}")
    if "requirement_ids" in data:
        # A requirement lives in one section; take it away from any sibling that had it.
        moving = set(data["requirement_ids"] or [])
        for other in s.package.sections:
            if other.id != s.id and moving & set(other.requirement_ids or []):
                other.requirement_ids = [r for r in other.requirement_ids if r not in moving]
                other.covered_ids = [r for r in (other.covered_ids or []) if r not in moving]
        keep = set(data["requirement_ids"])
        s.covered_ids = [r for r in (s.covered_ids or []) if r in keep]
    for k, v in data.items():
        setattr(s, k, v)
    if "covered_ids" in data:
        s.covered_ids = [r for r in data["covered_ids"] if r in set(s.requirement_ids or [])]
    touch(s.package)
    sync_coverage(db, s.package)
    db.commit()
    return section_dict(s)


@router.delete("/sections/{sid}")
def delete_section(sid: int, db: Session = Depends(get_db)):
    s = db.get(PackageSection, sid)
    if not s:
        raise HTTPException(404, "Section not found")
    p = s.package
    orphaned = list(s.requirement_ids or [])
    db.delete(s)
    db.flush()
    remaining = [x for x in p.sections if x.id != sid]
    if orphaned and remaining:
        # Hand orphaned requirements to the previous section so nothing falls off the matrix.
        target = remaining[min(max(0, s.position - 1), len(remaining) - 1)]
        target.requirement_ids = list(target.requirement_ids or []) + orphaned
    for n, x in enumerate(remaining):
        x.position = n
    touch(p)
    sync_coverage(db, p)
    db.commit()
    db.refresh(p)
    return package_full(p)


class ReorderIn(BaseModel):
    section_ids: list[int]


@router.post("/packages/{pkg_id}/sections/reorder")
def reorder_sections(pkg_id: int, body: ReorderIn, db: Session = Depends(get_db)):
    p = get_pkg(db, pkg_id)
    order = {sid: n for n, sid in enumerate(body.section_ids)}
    for s in p.sections:
        s.position = order.get(s.id, len(order) + s.position)
    touch(p)
    db.commit()
    db.refresh(p)
    return package_full(p)


# ------------------------------------------------------------------ AI drafting
class DraftIn(BaseModel):
    instructions: str = ""
    library_ids: list[int] = Field(default_factory=list)
    mode: str = "draft"  # draft | improve


DRAFT_SYSTEM = """You write sections of U.S. federal government proposals and technical data packages for a small business.
Rules:
- Write in plain, direct, specific language. No marketing fluff, no superlatives, no em dashes.
- Answer every assigned requirement explicitly, using the solicitation's own terms and paragraph references.
- Use only facts from the company information and library material provided. Where a fact is needed but missing,
  insert a bracketed placeholder such as [insert number of technicians] instead of inventing it.
- Format as Markdown: ### subheadings, short paragraphs, bullet lists, and pipe tables where they help.
- Return only the section body. Do not repeat the section title."""


@router.post("/sections/{sid}/draft")
def draft_section(sid: int, body: DraftIn, db: Session = Depends(get_db)):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(400, "Set ANTHROPIC_API_KEY in backend/.env to use AI drafting.")
    s = db.get(PackageSection, sid)
    if not s:
        raise HTTPException(404, "Section not found")
    p = s.package
    profile = get_profile(db)
    matrix = {r.get("id"): r for r in matrix_for(p)}
    reqs = [matrix[r] for r in (s.requirement_ids or []) if r in matrix]
    lib = db.scalars(select(LibraryEntry).where(LibraryEntry.id.in_(body.library_ids))).all() if body.library_ids else []

    parts = [
        f"Package: {p.name} ({'technical data package' if p.kind == 'tdp' else 'proposal'})",
        f"Section: {' '.join(x for x in (s.volume, s.number, s.title) if x)}",
        f"Section guidance: {s.guidance}" if s.guidance else "",
        f"Page limit for this section: {s.page_limit} pages (about {int(s.page_limit * WORDS_PER_PAGE)} words)" if s.page_limit else "",
        "Company: " + ", ".join(x for x in (profile.name, f"UEI {profile.uei}" if profile.uei else "", f"NAICS {', '.join(profile.naics_codes or [])}" if profile.naics_codes else "") if x),
        f"Company notes: {profile.notes}" if profile.notes else "",
    ]
    if p.opportunity:
        o = p.opportunity
        parts.append(f"Solicitation: {o.solicitation_number} {o.title}, {o.agency}")
        if o.analysis:
            parts.append(f"Solicitation summary: {o.analysis.summary}")
            scope = (o.analysis.breakdown or {}).get("scope")
            if scope:
                parts.append(f"Scope: {scope}")
            ev = (o.analysis.breakdown or {}).get("evaluation_method")
            if ev:
                parts.append(f"Evaluation: {ev}")
    if reqs:
        parts.append("Requirements this section must address:\n" + "\n".join(f"- [{r.get('reference') or r.get('id')}] {r.get('requirement')}" for r in reqs))
    for e in lib:
        parts.append(f'<library title="{e.title}" category="{e.category}">\n{e.content}\n</library>')
    if body.mode == "improve" and s.content.strip():
        parts.append(f"Current draft to improve (keep its facts, tighten it, close gaps against the requirements):\n{s.content}")
    if body.instructions:
        parts.append(f"Writer's instructions: {body.instructions}")

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=8000, system=DRAFT_SYSTEM,
        messages=[{"role": "user", "content": "\n\n".join(x for x in parts if x)}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    text = text.replace("—", ", ").replace(" ,", ",")
    return {"draft": text}


# ------------------------------------------------------------------ items (deliverables and attachments)
class ItemIn(BaseModel):
    cdrl: str | None = None
    title: str | None = None
    did: str | None = None
    category: str | None = None
    status: str | None = None
    due: str | None = None
    notes: str | None = None


@router.post("/packages/{pkg_id}/items")
def add_item(pkg_id: int, body: ItemIn, db: Session = Depends(get_db)):
    p = get_pkg(db, pkg_id)
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data.setdefault("title", "New item")
    db.add(PackageItem(package_id=p.id, position=len(p.items), **data))
    touch(p)
    db.commit()
    db.refresh(p)
    return package_full(p)


@router.put("/items/{iid}")
def update_item(iid: int, body: ItemIn, db: Session = Depends(get_db)):
    it = db.get(PackageItem, iid)
    if not it:
        raise HTTPException(404, "Item not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in ITEM_STATUSES:
        raise HTTPException(400, f"status must be one of {ITEM_STATUSES}")
    for k, v in data.items():
        setattr(it, k, v)
    touch(it.package)
    db.commit()
    return item_dict(it)


@router.delete("/items/{iid}")
def delete_item(iid: int, db: Session = Depends(get_db)):
    it = db.get(PackageItem, iid)
    if not it:
        raise HTTPException(404, "Item not found")
    pkg_id = it.package_id
    db.delete(it)
    db.commit()
    shutil.rmtree(pkg_dir(pkg_id) / f"item_{iid}", ignore_errors=True)
    return package_full(get_pkg(db, pkg_id))


@router.post("/items/{iid}/files")
async def upload_item_files(iid: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    it = db.get(PackageItem, iid)
    if not it:
        raise HTTPException(404, "Item not found")
    d = item_dir_for(it.package_id)(it.id)
    current = {f["name"]: f for f in it.files or []}
    for f in files:
        name = re.sub(r"[^A-Za-z0-9._ ()-]", "_", Path(f.filename or "file").name)
        dest = d / name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        current[name] = {"name": name, "size": dest.stat().st_size, "uploaded_at": datetime.utcnow().isoformat()}
    it.files = list(current.values())
    if it.status == "not_started":
        it.status = "in_progress"
    touch(it.package)
    db.commit()
    return item_dict(it)


@router.get("/items/{iid}/files/{name}")
def download_item_file(iid: int, name: str, db: Session = Depends(get_db)):
    it = db.get(PackageItem, iid)
    if not it:
        raise HTTPException(404, "Item not found")
    path = item_dir_for(it.package_id)(it.id) / Path(name).name
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name)


@router.delete("/items/{iid}/files/{name}")
def delete_item_file(iid: int, name: str, db: Session = Depends(get_db)):
    it = db.get(PackageItem, iid)
    if not it:
        raise HTTPException(404, "Item not found")
    path = item_dir_for(it.package_id)(it.id) / Path(name).name
    if path.exists():
        path.unlink()
    it.files = [f for f in it.files or [] if f["name"] != Path(name).name]
    db.commit()
    return item_dict(it)


# ------------------------------------------------------------------ export
def _export_inputs(db: Session, p: Package):
    profile = get_profile(db)
    full = package_full(p)
    prof = {"name": profile.name, "uei": profile.uei, "cage": profile.cage}
    return full, prof


@router.get("/packages/{pkg_id}/export.docx")
def export_docx(pkg_id: int, db: Session = Depends(get_db)):
    p = get_pkg(db, pkg_id)
    full, prof = _export_inputs(db, p)
    out = pkg_dir(p.id) / f"{safe_name(p.name)}.docx"
    build_docx(full, prof, full["matrix"], out)
    return FileResponse(out, filename=out.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/packages/{pkg_id}/export.zip")
def export_zip(pkg_id: int, db: Session = Depends(get_db)):
    p = get_pkg(db, pkg_id)
    full, prof = _export_inputs(db, p)
    docx_path = build_docx(full, prof, full["matrix"], pkg_dir(p.id) / f"{safe_name(p.name)}.docx")
    matrix_xlsx = None
    o = p.opportunity
    if o and o.analysis and p.kind == "proposal":
        meta = {"title": o.title, "solicitation_number": o.solicitation_number, "agency": o.agency, "response_deadline": o.response_deadline}
        a = {"summary": o.analysis.summary, "breakdown": o.analysis.breakdown, "compliance_matrix": o.analysis.compliance_matrix}
        matrix_xlsx = analysis_mod.matrix_to_xlsx(meta, a, pkg_dir(p.id) / "Compliance_Matrix.xlsx")
    out = pkg_dir(p.id) / f"{safe_name(p.name)}_package.zip"
    build_zip(full, docx_path, item_dir_for(p.id), matrix_xlsx, out)
    return FileResponse(out, filename=out.name, media_type="application/zip")


# ------------------------------------------------------------------ content library
class LibraryIn(BaseModel):
    category: str = "Boilerplate"
    title: str
    content: str = ""
    tags: list[str] = Field(default_factory=list)


def lib_dict(e: LibraryEntry) -> dict:
    return {"id": e.id, "category": e.category, "title": e.title, "content": e.content, "tags": e.tags or [],
            "words": words(e.content), "updated_at": e.updated_at.isoformat() if e.updated_at else None}


@router.get("/library")
def list_library(q: str = "", category: str = "", db: Session = Depends(get_db)):
    stmt = select(LibraryEntry).order_by(LibraryEntry.category, LibraryEntry.title)
    if category:
        stmt = stmt.where(LibraryEntry.category == category)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(LibraryEntry.title.ilike(like) | LibraryEntry.content.ilike(like))
    return [lib_dict(e) for e in db.scalars(stmt).all()]


@router.post("/library")
def create_library(body: LibraryIn, db: Session = Depends(get_db)):
    e = LibraryEntry(**body.model_dump())
    db.add(e)
    db.commit()
    return lib_dict(e)


@router.put("/library/{eid}")
def update_library(eid: int, body: LibraryIn, db: Session = Depends(get_db)):
    e = db.get(LibraryEntry, eid)
    if not e:
        raise HTTPException(404, "Entry not found")
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    db.commit()
    return lib_dict(e)


@router.delete("/library/{eid}")
def delete_library(eid: int, db: Session = Depends(get_db)):
    e = db.get(LibraryEntry, eid)
    if e:
        db.delete(e)
        db.commit()
    return {"ok": True}


class SaveToLibraryIn(BaseModel):
    category: str = "Boilerplate"
    title: str | None = None


@router.post("/sections/{sid}/save-to-library")
def save_section_to_library(sid: int, body: SaveToLibraryIn, db: Session = Depends(get_db)):
    s = db.get(PackageSection, sid)
    if not s:
        raise HTTPException(404, "Section not found")
    if not s.content.strip():
        raise HTTPException(400, "Section is empty")
    e = LibraryEntry(category=body.category, title=body.title or f"{s.title} ({s.package.name})", content=s.content)
    db.add(e)
    db.commit()
    return lib_dict(e)
