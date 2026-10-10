from __future__ import annotations

import re
from contextlib import asynccontextmanager
import shutil
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import analysis as analysis_mod
from . import bidding, presets
from .config import ANTHROPIC_API_KEY, SAM_API_KEY, UPLOAD_DIR
from .connectors import sam_gov, tabular_import, usaspending
from .db import get_db, init_db
from .eligibility import CERT_LABELS, SET_ASIDES, evaluate
from .models import PIPELINE_STAGES, Analysis, Opportunity, Package, PipelineEntry, SavedSearch, SyncLog
from .services import get_profile, sync_sam, upsert_opportunities

@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="GovBid Pro", version="1.0.0", lifespan=lifespan)
from .packages_api import router as packages_router  # noqa: E402

app.include_router(packages_router)
from .pricing_api import router as pricing_router  # noqa: E402

app.include_router(pricing_router)
from .cad_api import router as cad_router  # noqa: E402

app.include_router(cad_router)
from .standards_api import router as standards_router  # noqa: E402
from .crm_api import router as crm_router  # noqa: E402
from .cmmc_api import router as cmmc_router  # noqa: E402
from .past_performance_api import router as past_performance_router  # noqa: E402
from .drawings_api import router as drawings_router  # noqa: E402
from .nsn_api import router as nsn_router  # noqa: E402
from .insights_api import router as insights_router  # noqa: E402
from .jobs_api import router as jobs_router  # noqa: E402
from .quality_api import router as quality_router  # noqa: E402
from .finance_api import router as finance_router  # noqa: E402
from .workbook_api import router as workbook_router  # noqa: E402
from .flowdown_api import router as flowdown_router  # noqa: E402
from .sar_api import router as sar_router  # noqa: E402
from .search_api import router as search_router  # noqa: E402
from .market_api import router as market_router  # noqa: E402
from .writing_api import router as writing_router  # noqa: E402
from .extrusion_api import router as extrusion_router  # noqa: E402
from .electrical_api import router as electrical_router  # noqa: E402
from .quote_tools_api import router as quote_tools_router  # noqa: E402
from .flat_api import router as flat_router  # noqa: E402
from .box_build_api import router as box_build_router  # noqa: E402
from .portal_api import internal as portal_internal_router, public as portal_public_router  # noqa: E402
from .hardware_api import router as hardware_router  # noqa: E402
from .calibration_api import router as calibration_router  # noqa: E402

for _r in (standards_router, crm_router, cmmc_router, past_performance_router, drawings_router, nsn_router, insights_router,
           jobs_router, quality_router, finance_router, workbook_router, flowdown_router, sar_router, search_router,
           market_router, writing_router, extrusion_router, electrical_router, quote_tools_router, flat_router, box_build_router, portal_public_router, portal_internal_router,
           hardware_router, calibration_router):
    app.include_router(_r)
from . import auth as auth_mod  # noqa: E402

app.include_router(auth_mod.router)
from .backup import router as backup_router  # noqa: E402

app.include_router(backup_router)
app.middleware("http")(auth_mod.middleware)


@app.get("/api/health", include_in_schema=False)
def health():
    return {"ok": True}


app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ helpers
def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if m:
        y = int(m[3])
        y = y + 2000 if y < 100 else y
        try:
            return date(y, int(m[1]), int(m[2]))
        except ValueError:
            return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def opp_summary(o: Opportunity, profile) -> dict:
    due = parse_date(o.response_deadline)
    elig = evaluate(o.set_aside_code, o.naics, profile).to_dict()
    return {
        "id": o.id,
        "source": o.source,
        "solicitation_number": o.solicitation_number,
        "title": o.title,
        "agency": o.agency,
        "notice_type": o.notice_type,
        "set_aside_code": o.set_aside_code,
        "set_aside_desc": o.set_aside_desc or elig["set_aside_label"],
        "naics": o.naics,
        "psc": o.psc,
        "nsn": o.nsn,
        "quantity": o.quantity,
        "posted_date": o.posted_date,
        "response_deadline": o.response_deadline,
        "days_left": (due - date.today()).days if due else None,
        "place_of_performance": o.place_of_performance,
        "url": o.url,
        "estimated_value": o.estimated_value,
        "eligibility": elig,
        "pipeline_stage": o.pipeline.stage if o.pipeline else None,
        "has_analysis": o.analysis is not None,
        "export_controlled": bidding.export_flags_for(o)["flagged"],
    }


def get_opp(db: Session, opp_id: int) -> Opportunity:
    o = db.get(Opportunity, opp_id)
    if not o:
        raise HTTPException(404, "Opportunity not found")
    return o


def opp_dir(opp_id: int) -> Path:
    d = UPLOAD_DIR / f"opp_{opp_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ meta and profile
@app.get("/api/meta")
def meta():
    return {
        "set_asides": {k: v["label"] for k, v in SET_ASIDES.items() if k not in ("", "NONE")},
        "certifications": CERT_LABELS,
        "pipeline_stages": PIPELINE_STAGES,
        "sam_key_configured": bool(SAM_API_KEY),
        "ai_configured": bool(ANTHROPIC_API_KEY),
        **presets.meta(),
    }


class ProfileIn(BaseModel):
    name: str = ""
    jcp_status: str = "none"
    jcp_cert_number: str = ""
    jcp_expiration: str = ""
    uei: str = ""
    cage: str = ""
    sam_status: str = "not_registered"
    sam_expiration: str = ""
    state: str = ""
    naics_codes: list[str] = Field(default_factory=list)
    psc_codes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    nsn_watchlist: list[str] = Field(default_factory=list)
    certifications: dict[str, str] = Field(default_factory=dict)
    small_under_naics: dict[str, bool] = Field(default_factory=dict)
    notes: str = ""


PROFILE_FIELDS = list(ProfileIn.model_fields)


@app.get("/api/profile")
def read_profile(db: Session = Depends(get_db)):
    p = get_profile(db)
    return {f: getattr(p, f) for f in PROFILE_FIELDS}


@app.put("/api/profile")
def update_profile(body: ProfileIn, db: Session = Depends(get_db)):
    p = get_profile(db)
    data = body.model_dump()
    data["naics_codes"] = [c.strip() for c in data["naics_codes"] if c.strip()]
    data["state"] = data["state"].upper()[:2]
    for f, v in data.items():
        setattr(p, f, v)
    db.commit()
    return {f: getattr(p, f) for f in PROFILE_FIELDS}


class ApplyRecommendedIn(BaseModel):
    naics: bool = True
    fsc: bool = True
    make_primary: bool = True


@app.post("/api/profile/apply-recommended")
def apply_recommended(body: ApplyRecommendedIn = ApplyRecommendedIn(), db: Session = Depends(get_db)):
    """Merge the recommended NAICS codes and FSC watchlist into the profile without dropping anything already there."""
    p = get_profile(db)
    if body.naics:
        current = [c for c in (p.naics_codes or []) if c]
        merged = current + [c for c in presets.RECOMMENDED_NAICS if c not in current]
        if body.make_primary and presets.PRIMARY_NAICS in merged:
            merged.remove(presets.PRIMARY_NAICS)
            merged.insert(0, presets.PRIMARY_NAICS)
        p.naics_codes = merged
        small = dict(p.small_under_naics or {})
        for c in merged:
            small.setdefault(c, True)
        p.small_under_naics = small
    if body.fsc:
        current = [w for w in (p.nsn_watchlist or []) if w]
        p.nsn_watchlist = current + [f for f in presets.RECOMMENDED_FSC if f not in current]
    db.commit()
    return {f: getattr(p, f) for f in PROFILE_FIELDS}


# ------------------------------------------------------------------ sync and import
class SamSyncIn(BaseModel):
    days_back: int = 14
    naics: list[str] | None = None
    set_aside: str | None = None
    max_pages: int = 3
    option: str | None = None  # a presets.SYNC_OPTIONS id; overrides naics/titles
    titles: list[str] | None = None  # SAM.gov title searches, one request each


@app.post("/api/sync/sam")
def sync_sam_endpoint(body: SamSyncIn, db: Session = Depends(get_db)):
    if not SAM_API_KEY:
        raise HTTPException(400, "SAM_API_KEY is not set in backend/.env")
    naics, titles = body.naics, body.titles
    if body.option:
        opt = next((o for o in presets.SYNC_OPTIONS if o["id"] == body.option), None)
        if not opt:
            raise HTTPException(400, f"Unknown sync option {body.option}")
        naics, titles = opt.get("naics"), opt.get("titles")
    return sync_sam(db, days_back=body.days_back, naics=naics, titles=titles, set_aside=body.set_aside or None, max_pages=body.max_pages)


@app.get("/api/sync/log")
def sync_log(db: Session = Depends(get_db)):
    rows = db.scalars(select(SyncLog).order_by(SyncLog.id.desc()).limit(20)).all()
    return [
        {"source": r.source, "started_at": r.started_at.isoformat(), "added": r.added, "updated": r.updated, "requests_used": r.requests_used, "error": r.error}
        for r in rows
    ]


@app.post("/api/import/{source}")
async def import_file(source: str, file: UploadFile = File(...), apply_watchlist: bool = True, db: Session = Depends(get_db)):
    if source not in ("dibbs", "forecast", "manual"):
        raise HTTPException(400, "source must be dibbs, forecast or manual")
    dest = UPLOAD_DIR / "imports" / f"{datetime.utcnow():%Y%m%d%H%M%S}_{Path(file.filename or 'upload').name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    if dest.suffix.lower() in (".csv", ".tsv", ".xlsx", ".xlsm"):
        records = tabular_import.parse_table(dest, source)
    elif source == "dibbs":
        records = tabular_import.parse_dibbs_index(dest)
    else:
        raise HTTPException(400, "Upload a CSV or XLSX file (or the DIBBS daily index .txt for DIBBS).")

    parsed = len(records)
    if source == "dibbs" and apply_watchlist:
        records = tabular_import.filter_watchlist(records, get_profile(db).nsn_watchlist or [])
    added, updated = upsert_opportunities(db, records)
    db.add(SyncLog(source=f"import:{source}", added=added, updated=updated))
    db.commit()
    return {"parsed": parsed, "kept": len(records), "added": added, "updated": updated}


# ------------------------------------------------------------------ opportunities
@app.get("/api/opportunities")
def list_opportunities(
    q: str = "",
    kw: str = "",  # comma list; matches any keyword in title, description, agency or solicitation number
    source: str = "",
    set_aside: str = "",
    naics: str = "",
    state: str = "",
    eligibility: str = "",  # comma list: eligible_now,eligible_once_certified,not_eligible
    my_naics_only: bool = False,
    hide_expired: bool = True,
    notice_type: str = "",
    sort: str = "deadline",
    page: int = 1,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    profile = get_profile(db)
    stmt = select(Opportunity)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Opportunity.title.ilike(like), Opportunity.solicitation_number.ilike(like), Opportunity.agency.ilike(like), Opportunity.nsn.ilike(like), Opportunity.description.ilike(like)))
    words = [w.strip() for w in kw.split(",") if w.strip()]
    if words:
        stmt = stmt.where(or_(*[
            col.ilike(f"%{w}%")
            for w in words
            for col in (Opportunity.title, Opportunity.description, Opportunity.agency, Opportunity.solicitation_number)
        ]))
    if source:
        stmt = stmt.where(Opportunity.source.in_(source.split(",")))
    if set_aside:
        codes = [c.strip().upper() for c in set_aside.split(",")]
        stmt = stmt.where(or_(Opportunity.set_aside_code.in_(codes), *([Opportunity.set_aside_code == ""] if "NONE" in codes else [])))
    if naics:
        stmt = stmt.where(Opportunity.naics.in_([c.strip() for c in naics.split(",")]))
    elif my_naics_only and profile.naics_codes:
        stmt = stmt.where(Opportunity.naics.in_(profile.naics_codes))
    if state:
        stmt = stmt.where(Opportunity.pop_state == state.upper())
    if notice_type:
        stmt = stmt.where(Opportunity.notice_type.ilike(f"%{notice_type}%"))

    rows = [opp_summary(o, profile) for o in db.scalars(stmt).all()]
    if hide_expired:
        rows = [r for r in rows if r["days_left"] is None or r["days_left"] >= 0]
    if eligibility:
        wanted = set(eligibility.split(","))
        rows = [r for r in rows if r["eligibility"]["status"] in wanted]

    if sort == "deadline":
        rows.sort(key=lambda r: (r["days_left"] is None, r["days_left"] if r["days_left"] is not None else 0))
    elif sort == "posted":
        rows.sort(key=lambda r: r["posted_date"] or "", reverse=True)
    elif sort == "value":
        rows.sort(key=lambda r: r["estimated_value"] or 0, reverse=True)

    counts = {"eligible_now": 0, "eligible_once_certified": 0, "not_eligible": 0}
    for r in rows:
        counts[r["eligibility"]["status"]] = counts.get(r["eligibility"]["status"], 0) + 1
    start = (page - 1) * limit
    return {"total": len(rows), "counts": counts, "page": page, "results": rows[start : start + limit]}


@app.get("/api/opportunities/{opp_id}")
def opportunity_detail(opp_id: int, db: Session = Depends(get_db)):
    o = get_opp(db, opp_id)
    profile = get_profile(db)
    if o.source == "sam" and not o.description and o.description_url and SAM_API_KEY:
        desc = sam_gov.fetch_description(o.description_url)
        if desc:
            o.description = desc
            db.commit()
    data = opp_summary(o, profile)
    files = sorted(p.name for p in opp_dir(o.id).iterdir() if p.is_file())
    data.update(
        {
            "description": o.description,
            "contacts": o.contacts,
            "attachments": o.attachments,
            "documents": files,
            "analysis": None,
            "pipeline": None,
        }
    )
    if o.analysis:
        a = o.analysis
        data["analysis"] = {"method": a.method, "summary": a.summary, "breakdown": a.breakdown, "compliance_matrix": a.compliance_matrix, "source_files": a.source_files, "created_at": a.created_at.isoformat()}
    flags = bidding.export_flags_for(o)
    data["export_control"] = flags
    data["jcp_note"] = bidding.jcp_status_note(profile, flags["flagged"])
    from .models import OpportunityChange
    data["changes"] = [bidding.change_dict(c) for c in db.scalars(
        select(OpportunityChange).where(OpportunityChange.opportunity_id == o.id).order_by(OpportunityChange.detected_at.desc()).limit(20)).all()]
    data["standards_check"] = []
    cited = ((o.analysis.breakdown or {}).get("cited_standards") if o.analysis else None) or []
    if cited:
        from .standards import revision_check
        try:
            data["standards_check"] = revision_check(db, cited)
        except Exception:  # noqa: BLE001  (never break the detail page over the library)
            data["standards_check"] = []
    if o.pipeline:
        p = o.pipeline
        data["pipeline"] = {"stage": p.stage, "priority": p.priority, "bid_amount": p.bid_amount, "notes": p.notes, "debrief": p.debrief, "updated_at": p.updated_at.isoformat() if p.updated_at else None}
    return data


class ManualOpp(BaseModel):
    title: str
    solicitation_number: str = ""
    agency: str = ""
    set_aside_code: str = ""
    naics: str = ""
    response_deadline: str = ""
    url: str = ""
    description: str = ""
    source: str = "manual"


@app.post("/api/opportunities")
def create_opportunity(body: ManualOpp, db: Session = Depends(get_db)):
    ext = body.solicitation_number or f"manual-{datetime.utcnow():%Y%m%d%H%M%S%f}"
    rec = body.model_dump() | {"external_id": ext, "notice_type": "Manual entry", "set_aside_code": body.set_aside_code.upper()}
    upsert_opportunities(db, [rec])
    o = db.scalar(select(Opportunity).where(Opportunity.source == body.source, Opportunity.external_id == ext))
    return {"id": o.id}


@app.delete("/api/opportunities/{opp_id}")
def delete_opportunity(opp_id: int, db: Session = Depends(get_db)):
    o = get_opp(db, opp_id)
    for pkg in db.scalars(select(Package).where(Package.opportunity_id == opp_id)).all():
        pkg.opportunity_id = None  # keep the package, drop the link
    from .models import PartQuote
    for pq in db.scalars(select(PartQuote).where(PartQuote.opportunity_id == opp_id)).all():
        pq.opportunity_id = None
    from .models import OpportunityChange
    from .models_crm import Interaction
    db.query(OpportunityChange).filter(OpportunityChange.opportunity_id == opp_id).delete()
    for it in db.scalars(select(Interaction).where(Interaction.opportunity_id == opp_id)).all():
        it.opportunity_id = None
    db.delete(o)
    db.commit()
    shutil.rmtree(UPLOAD_DIR / f"opp_{opp_id}", ignore_errors=True)
    return {"ok": True}


# ------------------------------------------------------------------ documents and analysis
@app.post("/api/opportunities/{opp_id}/documents")
async def upload_documents(opp_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    get_opp(db, opp_id)
    saved = []
    for f in files:
        name = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(f.filename or "file").name)
        with (opp_dir(opp_id) / name).open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(name)
    return {"saved": saved}


@app.delete("/api/opportunities/{opp_id}/documents/{name}")
def delete_document(opp_id: int, name: str, db: Session = Depends(get_db)):
    get_opp(db, opp_id)
    path = opp_dir(opp_id) / Path(name).name
    if path.exists():
        path.unlink()
    return {"ok": True}


@app.post("/api/opportunities/{opp_id}/fetch-attachments")
def fetch_attachments(opp_id: int, db: Session = Depends(get_db)):
    """Download SAM.gov attachment links into the opportunity folder."""
    o = get_opp(db, opp_id)
    if not o.attachments:
        return {"saved": [], "errors": ["This notice lists no attachments."]}
    saved, errors = [], []
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for i, link in enumerate(o.attachments):
            params = {"api_key": SAM_API_KEY} if "api.sam.gov" in link and SAM_API_KEY else None
            try:
                r = client.get(link, params=params)
                r.raise_for_status()
                cd = r.headers.get("content-disposition", "")
                m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
                name = re.sub(r"[^A-Za-z0-9._ -]", "_", m.group(1) if m else f"attachment_{i + 1}")
                (opp_dir(o.id) / name).write_bytes(r.content)
                saved.append(name)
            except Exception as exc:
                errors.append(f"{link}: {exc.__class__.__name__}")
    return {"saved": saved, "errors": errors}


@app.post("/api/opportunities/{opp_id}/analyze")
def analyze_opportunity(opp_id: int, db: Session = Depends(get_db)):
    o = get_opp(db, opp_id)
    profile = get_profile(db)
    docs: list[tuple[str, str]] = []
    if o.description:
        docs.append(("Notice description", analysis_mod.html_to_text(o.description) if "<" in o.description else o.description))
    for path in sorted(opp_dir(o.id).iterdir()):
        if path.is_file():
            docs.append((path.name, analysis_mod.extract_text(path)))
    meta = {k: getattr(o, k) for k in ("title", "solicitation_number", "agency", "notice_type", "set_aside_desc", "naics", "psc", "response_deadline", "place_of_performance")}
    elig = evaluate(o.set_aside_code, o.naics, profile).to_dict()
    method, result = analysis_mod.analyze(meta, docs, elig)
    corpus = "\n".join(t for _, t in docs)
    ec = bidding.export_control(corpus)
    result["breakdown"]["export_control"] = ec
    if ec["flagged"]:
        reds = result["breakdown"].setdefault("red_flags", [])
        note = "Technical data is export controlled: you need an approved JCP certification (DD Form 2345) to receive the drawings."
        if note not in reds:
            reds.append(note)
    a = o.analysis or Analysis(opportunity_id=o.id)
    o.analysis = a
    a.method, a.summary, a.breakdown, a.compliance_matrix = method, result["summary"], result["breakdown"], result["compliance_matrix"]
    a.source_files = [n for n, _ in docs]
    a.created_at = datetime.utcnow()
    db.add(a)
    db.commit()
    if result["breakdown"].get("cited_standards"):
        from .standards import record_cited_standards
        try:
            record_cited_standards(db, o, result["breakdown"]["cited_standards"])
        except Exception:  # noqa: BLE001  (the analysis is saved either way)
            db.rollback()
    return opportunity_detail(opp_id, db)


class MatrixIn(BaseModel):
    compliance_matrix: list[dict]


@app.put("/api/opportunities/{opp_id}/matrix")
def save_matrix(opp_id: int, body: MatrixIn, db: Session = Depends(get_db)):
    o = get_opp(db, opp_id)
    if not o.analysis:
        raise HTTPException(400, "Run the analysis first")
    o.analysis.compliance_matrix = body.compliance_matrix
    db.commit()
    return {"ok": True}


@app.get("/api/opportunities/{opp_id}/matrix.xlsx")
def export_matrix(opp_id: int, db: Session = Depends(get_db)):
    o = get_opp(db, opp_id)
    if not o.analysis:
        raise HTTPException(400, "Run the analysis first")
    a = {"summary": o.analysis.summary, "breakdown": o.analysis.breakdown, "compliance_matrix": o.analysis.compliance_matrix}
    meta = {"title": o.title, "solicitation_number": o.solicitation_number, "agency": o.agency, "response_deadline": o.response_deadline}
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", o.solicitation_number or f"opp_{o.id}")
    out = analysis_mod.matrix_to_xlsx(meta, a, opp_dir(o.id).parent / f"compliance_{safe}.xlsx")
    return FileResponse(out, filename=out.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ------------------------------------------------------------------ pipeline
class PipelineIn(BaseModel):
    stage: str = "tracking"
    priority: str = "medium"
    bid_amount: float | None = None
    notes: str = ""
    debrief: str = ""


@app.put("/api/opportunities/{opp_id}/pipeline")
def set_pipeline(opp_id: int, body: PipelineIn, db: Session = Depends(get_db)):
    o = get_opp(db, opp_id)
    if body.stage not in PIPELINE_STAGES:
        raise HTTPException(400, f"stage must be one of {PIPELINE_STAGES}")
    p = o.pipeline or PipelineEntry(opportunity_id=o.id)
    o.pipeline = p
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.add(p)
    db.commit()
    return {"ok": True}


@app.delete("/api/opportunities/{opp_id}/pipeline")
def remove_pipeline(opp_id: int, db: Session = Depends(get_db)):
    o = get_opp(db, opp_id)
    if o.pipeline:
        db.delete(o.pipeline)
        o.pipeline = None
        db.commit()
    return {"ok": True}


@app.get("/api/pipeline")
def list_pipeline(db: Session = Depends(get_db)):
    profile = get_profile(db)
    entries = db.scalars(select(PipelineEntry)).all()
    out = []
    for p in entries:
        row = opp_summary(p.opportunity, profile)
        row["pipeline"] = {"stage": p.stage, "priority": p.priority, "bid_amount": p.bid_amount, "notes": p.notes, "debrief": p.debrief}
        if p.stage in bidding.OPEN_STAGES:
            sc = bidding.bid_score(db, p.opportunity, profile)
            row["score"] = {"score": sc["score"], "recommendation": sc["recommendation"]}
        out.append(row)
    return out


# ------------------------------------------------------------------ competitor intel
@app.get("/api/competitors")
def competitors(naics: str = "", set_aside: str = "", keyword: str = "", agency: str = "", years: int = 3, db: Session = Depends(get_db)):
    profile = get_profile(db)
    codes = [c.strip() for c in naics.split(",") if c.strip()] or list(profile.naics_codes or [])
    if not codes and not keyword:
        raise HTTPException(400, "Give a NAICS code or keyword, or add NAICS codes to your profile.")
    try:
        awards = usaspending.search_awards(
            naics=codes or None,
            keywords=[keyword] if keyword else None,
            agency=agency or None,
            set_aside_codes=[s.strip() for s in set_aside.split(",") if s.strip()] or None,
            years_back=years,
        )
    except Exception as exc:
        raise HTTPException(502, f"USAspending request failed: {exc}")
    return {"awards": awards, "top_competitors": usaspending.top_competitors(awards), "total_value": sum(a["amount"] for a in awards)}


# ------------------------------------------------------------------ saved searches and dashboard
class SavedSearchIn(BaseModel):
    name: str
    params: dict


@app.get("/api/saved-searches")
def list_saved(db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name, "params": s.params} for s in db.scalars(select(SavedSearch)).all()]


@app.post("/api/saved-searches")
def create_saved(body: SavedSearchIn, db: Session = Depends(get_db)):
    s = SavedSearch(name=body.name, params=body.params)
    db.add(s)
    db.commit()
    return {"id": s.id}


@app.delete("/api/saved-searches/{sid}")
def delete_saved(sid: int, db: Session = Depends(get_db)):
    s = db.get(SavedSearch, sid)
    if s:
        db.delete(s)
        db.commit()
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    profile = get_profile(db)
    opps = db.scalars(select(Opportunity)).all()
    live = []
    for o in opps:
        s = opp_summary(o, profile)
        if s["days_left"] is None or s["days_left"] >= 0:
            live.append(s)
    by_status: dict[str, int] = {}
    for s in live:
        by_status[s["eligibility"]["status"]] = by_status.get(s["eligibility"]["status"], 0) + 1
    due_soon = sorted(
        [s for s in live if s["days_left"] is not None and s["days_left"] <= 10 and s["eligibility"]["status"] != "not_eligible"],
        key=lambda s: s["days_left"],
    )[:10]
    sdvosb_waiting = [s for s in live if s["set_aside_code"] in ("SDVOSBC", "SDVOSBS", "VSA", "VSS")]
    stages: dict[str, int] = {}
    for p in db.scalars(select(PipelineEntry)).all():
        stages[p.stage] = stages.get(p.stage, 0) + 1
    by_source = dict(db.execute(select(Opportunity.source, func.count()).group_by(Opportunity.source)).all())
    last = db.scalar(select(SyncLog).order_by(SyncLog.id.desc()))
    return {
        "open_total": len(live),
        "by_eligibility": by_status,
        "by_source": by_source,
        "due_soon": due_soon,
        "veteran_set_asides": len(sdvosb_waiting),
        "pipeline": stages,
        "last_sync": last.started_at.isoformat() if last else None,
        "profile_complete": bool(profile.naics_codes and profile.name),
        "sdvosb_status": (profile.certifications or {}).get("SDVOSB", "none"),
        "packages_open": db.scalar(select(func.count()).select_from(Package).where(Package.status != "submitted")) or 0,
        **_dashboard_extras(db, profile),
    }


def _dashboard_extras(db: Session, profile) -> dict:
    """Follow-ups, amendment changes, compliance and renewal warnings. Each part fails soft."""
    out: dict = {"follow_ups": [], "changes_unseen": 0, "recent_changes": [], "cmmc": None, "alerts": []}
    try:
        from .crm_api import open_follow_ups
        out["follow_ups"] = open_follow_ups(db, 14)[:8]
    except Exception:  # noqa: BLE001
        pass
    from .models import OpportunityChange
    out["changes_unseen"] = db.query(OpportunityChange).filter(OpportunityChange.seen.is_(False)).count()
    out["recent_changes"] = [bidding.change_dict(c, db.get(Opportunity, c.opportunity_id)) for c in db.scalars(
        select(OpportunityChange).where(OpportunityChange.seen.is_(False)).order_by(OpportunityChange.detected_at.desc()).limit(8)).all()]
    try:
        from .cmmc_api import compute_summary
        out["cmmc"] = compute_summary(db)
    except Exception:  # noqa: BLE001
        pass
    try:
        from .digest import module_alerts
        out["alerts"] += [a["text"] for a in module_alerts(db)]
    except Exception:  # noqa: BLE001
        pass
    today = date.today()
    for label, val in (("SAM.gov registration", profile.sam_expiration), ("JCP certification", profile.jcp_expiration)):
        d = parse_date(val)
        if d and (d - today).days <= 60:
            out["alerts"].append(f"{label} {'expired' if d < today else 'expires'} {d.isoformat()}.")
    if (profile.jcp_status or "none") in ("none", "expired"):
        n = sum(1 for p in db.scalars(select(PipelineEntry)).all() if p.stage in bidding.OPEN_STAGES and bidding.export_flags_for(p.opportunity)["flagged"])
        if n:
            out["alerts"].append(f"{n} tracked opportunit{'y needs' if n == 1 else 'ies need'} export-controlled drawings. Apply for JCP certification (DD Form 2345).")
    return out


# ------------------------------------------------------------------ frontend
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    import mimetypes

    mimetypes.add_type("application/manifest+json", ".webmanifest")  # home-screen install on iPhone and iPad
    _DIST_ROOT = FRONTEND_DIST.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (FRONTEND_DIST / path).resolve()
        if path and target.is_file() and target.is_relative_to(_DIST_ROOT):  # never serve files outside the build
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
