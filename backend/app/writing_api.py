"""Writing API: evaluator review of proposal packages, sources sought / RFI drafts, capability statement."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, writing
from .db import get_db
from .models import Opportunity, Package, PipelineEntry
from .models_pp import PastPerformance
from .models_writing import ProposalReviewRun
from .package_export import safe_name
from .packages_api import package_full
from .services import get_profile

router = APIRouter(prefix="/api/writing")

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _opp(db: Session, opp_id: int) -> Opportunity:
    o = db.get(Opportunity, opp_id)
    if not o:
        raise HTTPException(404, "Opportunity not found")
    return o


# ------------------------------------------------------------------ 1. evaluator review
def run_dict(r: ProposalReviewRun, full: bool = True) -> dict:
    d = {"id": r.id, "package_id": r.package_id, "method": r.method, "created_at": r.created_at.isoformat() if r.created_at else None,
         "rating": ((r.result or {}).get("overall") or {}).get("rating")}
    if full:
        d["result"] = r.result or {}
    return d


@router.post("/review/{package_id}")
def run_review(package_id: int, db: Session = Depends(get_db)):
    p = db.get(Package, package_id)
    if not p:
        raise HTTPException(404, "Package not found")
    pkg = package_full(p)
    a = p.opportunity.analysis if p.opportunity and p.opportunity.analysis else None
    analysis = {"breakdown": a.breakdown or {}, "compliance_matrix": a.compliance_matrix or []} if a else None
    method, result = writing.review_package(pkg, analysis)
    run = ProposalReviewRun(package_id=p.id, method=method, result=result)
    db.add(run)
    db.commit()
    return run_dict(run)


@router.get("/review/{package_id}")
def list_reviews(package_id: int, db: Session = Depends(get_db)):
    runs = db.scalars(select(ProposalReviewRun).where(ProposalReviewRun.package_id == package_id)
                      .order_by(ProposalReviewRun.created_at.desc(), ProposalReviewRun.id.desc())).all()
    return {"ai_configured": writing.ai_enabled(), "runs": [run_dict(r, full=False) for r in runs],
            "latest": run_dict(runs[0]) if runs else None}


@router.get("/review-run/{run_id}")
def get_review(run_id: int, db: Session = Depends(get_db)):
    r = db.get(ProposalReviewRun, run_id)
    if not r:
        raise HTTPException(404, "Review not found")
    return run_dict(r)


@router.delete("/review-run/{run_id}")
def delete_review(run_id: int, db: Session = Depends(get_db)):
    r = db.get(ProposalReviewRun, run_id)
    if r:
        db.delete(r)
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ 2. sources sought / RFI
class MarkdownIn(BaseModel):
    markdown: str = ""


@router.get("/sources-sought/{opp_id}")
def sources_sought_info(opp_id: int, db: Session = Depends(get_db)):
    o = _opp(db, opp_id)
    applies = writing.is_sources_sought(o.notice_type, o.title, o.description)
    text = writing.plain(o.description)
    if o.analysis:
        text += "\n" + ((o.analysis.breakdown or {}).get("submission_instructions") or "")
    return {"applies": applies, "requests": writing.extract_requests(text) if applies else [], "ai_configured": writing.ai_enabled()}


@router.post("/sources-sought/{opp_id}")
def sources_sought_draft(opp_id: int, db: Session = Depends(get_db)):
    o = _opp(db, opp_id)
    return writing.draft_sources_sought(db, o)


@router.post("/sources-sought/{opp_id}/checklist")
def sources_sought_checklist(opp_id: int, body: MarkdownIn, db: Session = Depends(get_db)):
    o = _opp(db, opp_id)
    ctx = writing.sources_sought_context(db, o)
    return {"checklist": writing.ss_checklist(ctx["requests"], body.markdown, ctx)}


@router.post("/sources-sought/{opp_id}/docx")
def sources_sought_docx(opp_id: int, body: MarkdownIn, db: Session = Depends(get_db)):
    o = _opp(db, opp_id)
    data = writing.markdown_docx_bytes(body.markdown, f"Response to {o.title}")
    name = safe_name(f"{o.solicitation_number or 'notice'} sources sought response") + ".docx"
    return Response(data, media_type=DOCX_TYPE, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/sources-sought/{opp_id}/save")
def sources_sought_save(opp_id: int, body: MarkdownIn, db: Session = Depends(get_db)):
    o = _opp(db, opp_id)
    if not body.markdown.strip():
        raise HTTPException(400, "Draft is empty")
    pkg = writing.save_sources_sought_package(db, o, body.markdown)
    return {"package_id": pkg.id, "name": pkg.name}


# ------------------------------------------------------------------ 3. capability statement
SETTINGS_FIELDS = ["tagline", "overview", "competencies", "differentiators", "past_performance_ids", "contact_name",
                   "contact_title", "contact_phone", "contact_email", "website"]


class CapabilityIn(BaseModel):
    tagline: str = ""
    overview: str = ""
    competencies: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    past_performance_ids: list[int] = Field(default_factory=list)
    contact_name: str = ""
    contact_title: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    website: str = ""


class RenderIn(BaseModel):
    settings: CapabilityIn | None = None  # unsaved editor values; saved settings when omitted
    opp_id: int | None = None


def settings_dict(s) -> dict:
    d = {k: getattr(s, k) for k in SETTINGS_FIELDS}
    d["logo_file"] = s.logo_file
    return d


@router.get("/capability")
def capability_get(db: Session = Depends(get_db)):
    s = writing.get_capability_settings(db)
    prof = get_profile(db)
    data = writing.capability_data(db)
    pps = db.scalars(select(PastPerformance).order_by(PastPerformance.end_date.desc(), PastPerformance.id.desc())).all()
    return {
        "settings": settings_dict(s),
        "company": {"name": prof.name, "uei": prof.uei, "cage": prof.cage, "certifications": data["certs"],
                    "naics": data["naics"], "psc": data["psc"], "keywords": prof.keywords or []},
        "past_performance": [{"id": p.id, "title": p.title, "customer": p.customer, "agency": p.agency, "role": p.role,
                              "end_date": p.end_date} for p in pps],
        "ai_configured": writing.ai_enabled(),
    }


@router.put("/capability")
def capability_put(body: CapabilityIn, db: Session = Depends(get_db)):
    s = writing.get_capability_settings(db)
    for k, v in body.model_dump().items():
        if isinstance(v, list):
            v = [x.strip() if isinstance(x, str) else x for x in v if (x.strip() if isinstance(x, str) else x)]
        setattr(s, k, v)
    db.commit()
    return settings_dict(s)


@router.get("/capability/opportunities")
def capability_opportunities(db: Session = Depends(get_db)):
    """Opportunities to tailor to: pipeline entries first, then recent active notices."""
    seen, out = set(), []
    for o in db.scalars(select(Opportunity).join(PipelineEntry).order_by(PipelineEntry.updated_at.desc()).limit(60)):
        seen.add(o.id)
        out.append({"id": o.id, "label": f"{o.solicitation_number or ''} {o.title}".strip()[:140], "pipeline": True})
    for o in db.scalars(select(Opportunity).where(Opportunity.active.is_(True)).order_by(Opportunity.fetched_at.desc()).limit(80)):
        if o.id not in seen:
            out.append({"id": o.id, "label": f"{o.solicitation_number or ''} {o.title}".strip()[:140], "pipeline": False})
    return out


def _render_inputs(db: Session, body: RenderIn):
    opp = _opp(db, body.opp_id) if body.opp_id else None
    return writing.capability_data(db, opp, body.settings.model_dump() if body.settings else None)


def _fit_headers(fit: dict) -> dict:
    return {"X-Fit-Scale": str(fit["scale"]), "X-Fit-Shrunk": "1" if fit["shrunk"] else "0",
            "X-Fit-Overflow": "1" if fit["overflow"] else "0",
            "Access-Control-Expose-Headers": "X-Fit-Scale, X-Fit-Shrunk, X-Fit-Overflow"}


def _cap_name(db: Session) -> str:
    return safe_name(f"{get_profile(db).name or 'Company'} Capability Statement")


@router.post("/capability/pdf")
def capability_pdf_post(body: RenderIn, db: Session = Depends(get_db)):
    pdf, fit = writing.capability_pdf(_render_inputs(db, body))
    return Response(pdf, media_type="application/pdf",
                    headers={**_fit_headers(fit), "Content-Disposition": f'inline; filename="{_cap_name(db)}.pdf"'})


@router.get("/capability.pdf")
def capability_pdf_get(opp_id: int | None = None, db: Session = Depends(get_db)):
    pdf, fit = writing.capability_pdf(_render_inputs(db, RenderIn(opp_id=opp_id)))
    return Response(pdf, media_type="application/pdf",
                    headers={**_fit_headers(fit), "Content-Disposition": f'attachment; filename="{_cap_name(db)}.pdf"'})


@router.get("/capability.docx")
def capability_docx_get(opp_id: int | None = None, db: Session = Depends(get_db)):
    data = writing.capability_docx(_render_inputs(db, RenderIn(opp_id=opp_id)))
    return Response(data, media_type=DOCX_TYPE, headers={"Content-Disposition": f'attachment; filename="{_cap_name(db)}.docx"'})


@router.post("/capability/docx")
def capability_docx_post(body: RenderIn, db: Session = Depends(get_db)):
    data = writing.capability_docx(_render_inputs(db, body))
    return Response(data, media_type=DOCX_TYPE, headers={"Content-Disposition": f'attachment; filename="{_cap_name(db)}.docx"'})


class TailorIn(BaseModel):
    opp_id: int
    settings: CapabilityIn | None = None


@router.post("/capability/tailor")
def capability_tailor(body: TailorIn, db: Session = Depends(get_db)):
    """Suggested tagline, competency order and past performance for one opportunity. Nothing is saved."""
    opp = _opp(db, body.opp_id)
    s = writing.get_capability_settings(db)
    view = type("View", (), {})()
    for k, v in settings_dict(s).items():
        setattr(view, k, v)
    if body.settings:
        for k, v in body.settings.model_dump().items():
            setattr(view, k, v)
    out = writing.tailor_keywords(db, view, opp)
    out["method"] = "keywords"
    if writing.ai_enabled() and view.competencies:
        try:
            ai = writing.claude_tailor(view, opp)
            out.update(tagline=ai["tagline"], competencies=ai["competencies"], method="claude")
        except Exception as exc:  # noqa: BLE001
            out["warning"] = f"AI rewrite failed ({exc.__class__.__name__}); showing keyword ordering."
    return out


LOGO_TYPES = {".png", ".jpg", ".jpeg"}


@router.post("/capability/logo")
async def capability_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in LOGO_TYPES:
        raise HTTPException(400, "Logo must be a PNG or JPG image.")
    d = config.UPLOAD_DIR / "capability"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("logo.*"):
        old.unlink()
    dest = d / f"logo{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        from PIL import Image

        with Image.open(dest) as im:
            im.verify()
    except Exception:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "That file is not a readable image.")
    s = writing.get_capability_settings(db)
    s.logo_file = dest.name
    db.commit()
    return settings_dict(s)


@router.delete("/capability/logo")
def capability_logo_delete(db: Session = Depends(get_db)):
    s = writing.get_capability_settings(db)
    if s.logo_file:
        (config.UPLOAD_DIR / "capability" / Path(s.logo_file).name).unlink(missing_ok=True)
    s.logo_file = ""
    db.commit()
    return settings_dict(s)

