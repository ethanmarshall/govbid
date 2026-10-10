"""Customer quote portal endpoints.

Public (no login, open in app/auth.py), under /api/public/:
  GET  /info                         company name, choices, limits (no rates or costs)
  POST /quote                        files + quantity, material, finish, thickness, notes -> priced request {ref, token, ...}
  GET  /quote/{ref}?token=           the customer's view of their request
  POST /quote/{ref}/options          change quantity, material, finish or thickness and reprice (drafts only)
  POST /quote/{ref}/submit           contact details -> submitted for review; emails you
Rate limited per address and site-wide. The token in the link is the only key to a request.

Internal (login), under /api/portal/: list and review requests, download files, set status and notes,
save the priced items as internal part quotes, delete, and the portal settings.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import portal
from . import auth
from .auth import _client
from .db import SessionLocal, get_db
from .models_portal import PORTAL_STATUSES, PortalRequest

log = logging.getLogger(__name__)
public = APIRouter(prefix="/api/public")
internal = APIRouter(prefix="/api/portal")


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except portal.PortalError as exc:
        raise HTTPException(400, str(exc))


def _limit(limiter: portal.Limiter, request: Request):
    if not limiter.hit(_client(request)):
        raise HTTPException(429, "Too many requests from here. Please wait a while and try again.")


# ================================================================ public
def _owner(request: Request) -> bool:
    """You, signed in to GovBid Pro (only when a password is set). Lets you preview the page before it opens."""
    return auth.enabled() and auth.valid_session(request.cookies.get(auth.COOKIE))


@public.get("/info")
def info(request: Request, db: Session = Depends(get_db)):
    return {**portal.public_info(db), "owner": _owner(request)}


@public.post("/quote")
async def new_quote(request: Request, files: list[UploadFile] = File(default=[]), quantity: int = Form(1), material: str = Form(""),
                    finish: str = Form(""), thickness: str = Form(""), notes: str = Form(""), export_controlled: bool = Form(False),
                    website: str = Form(""), preview: bool = Form(False), db: Session = Depends(get_db)):
    if website:  # hidden field: only bots fill it in
        raise HTTPException(400, "Could not process the request.")
    _limit(portal.QUOTE_LIMIT, request)
    uploads = []
    total = 0
    for f in files[: portal.MAX_FILES + 1]:
        data = await f.read(portal.MAX_FILE + 1)
        total += len(data)
        if total > portal.MAX_TOTAL + portal.MAX_FILE:
            raise HTTPException(413, "The files are too large.")
        uploads.append((f.filename or "file", data))
    data = {"quantity": quantity, "material": material, "finish": finish, "thickness": thickness, "notes": notes,
            "export_controlled": export_controlled}
    req = await run_in_threadpool(_guard, portal.create, db, uploads, data, _client(request), preview and _owner(request))
    return {**portal.public_view(req), "token": req.token}


@public.post("/concept")
async def new_concept(request: Request, background: BackgroundTasks, payload: str = Form(...), files: list[UploadFile] = File(default=[]),
                      website: str = Form(""), db: Session = Depends(get_db)):
    """A project idea without drawings: who they are, the concept, goals, must-haves, conditions, and optional sketches or photos.
    payload is JSON: {contact: {name, company, email, phone, accept_terms, export_controlled}, concept: {...}}."""
    import json as _json

    from . import portal_concept

    if website:
        raise HTTPException(400, "Could not process the request.")
    _limit(portal.SUBMIT_LIMIT, request)
    try:
        body = _json.loads(payload)
    except ValueError:
        raise HTTPException(400, "Could not read the form.")
    uploads = []
    total = 0
    for f in files[: portal.MAX_FILES + 1]:
        data = await f.read(portal.MAX_FILE + 1)
        total += len(data)
        if total > portal.MAX_TOTAL + portal.MAX_FILE:
            raise HTTPException(413, "The files are too large.")
        uploads.append((f.filename or "file", data))
    try:
        req = await run_in_threadpool(portal_concept.create, db, body.get("concept") or {}, body.get("contact") or {}, uploads, _client(request))
    except (portal_concept.ConceptError, portal.PortalError) as exc:
        raise HTTPException(400, str(exc))
    background.add_task(_notify, req.id)
    return {**portal.public_view(req), "token": req.token}


def _customer(db: Session, ref: str, token: str) -> PortalRequest:
    return _guard(portal.get_for_customer, db, ref, token)


@public.get("/quote/{ref}")
def view(ref: str, token: str = "", db: Session = Depends(get_db)):
    req = _customer(db, ref, token)
    portal.ensure_job(req)  # big models: keep reading (also after a server restart)
    return portal.public_view(req)


@public.get("/quote/{ref}/pdf")
def quote_pdf(ref: str, request: Request, token: str = "", db: Session = Depends(get_db)):
    """The customer's copy of the quote, with the private link back to it."""
    _limit(portal.REPRICE_LIMIT, request)
    from . import portal_pdf

    try:
        req = portal.get_for_customer(db, ref, token)
    except portal.PortalError:
        # opened in a browser tab, so answer with a page a person can read (not JSON saved as a broken .pdf)
        return HTMLResponse("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                            "<title>Quote not found</title><body style='font:17px/1.5 system-ui,sans-serif;max-width:34em;margin:12vh auto;padding:0 20px;color:#15212c'>"
                            "<h1 style='font-size:24px'>Quote not found</h1><p>This quote link is not valid. It may have a typo, or the quote "
                            "was removed after 30 days without being sent to us.</p><p><a href='/quote' style='color:#2356c4'>Start a new quote</a></p>",
                            status_code=404)
    base = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    link = f"{base}/quote/status/{req.ref}?t={req.token}"
    sheets = {}
    for it in (req.public_result or {}).get("items") or []:
        key = (it.get("view") or {}).get("key")
        if key and key not in sheets:
            sh = portal.view_sheet(req, key)
            if sh:
                sheets[key] = sh
    pdf = portal_pdf.render(portal.public_view(req), portal.public_info(db), link, portal.DRAFT_DAYS, sheets)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{req.ref}.pdf"',
                                                                 "Cache-Control": "no-store"})


SVG_HEADERS = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "Cache-Control": "private, max-age=86400",
               "X-Content-Type-Options": "nosniff"}


def _svg(req: PortalRequest, key: str) -> Response:
    from . import portal_views

    sheet = portal.view_sheet(req, key) or portal.build_lazy_view(req, key)
    if not sheet:
        raise HTTPException(404, "No drawing for this item.")
    return Response(portal_views.to_svg(sheet), media_type="image/svg+xml", headers=SVG_HEADERS)


@public.get("/quote/{ref}/views/{key}.svg")
def quote_views(ref: str, key: str, request: Request, token: str = "", db: Session = Depends(get_db)):
    """Front, top, right and isometric views of one item, drawn from the customer's files."""
    _limit(portal.REPRICE_LIMIT, request)
    return _svg(_customer(db, ref, token), key)


class OptionsIn(BaseModel):
    token: str
    lines: dict | None = None  # {line key: {qty, material, finish, process, process_material}}
    quantity: int | None = None
    material: str | None = None
    finish: str | None = None
    thickness: float | None = None


@public.post("/quote/{ref}/options")
async def options(ref: str, body: OptionsIn, request: Request, db: Session = Depends(get_db)):
    _limit(portal.REPRICE_LIMIT, request)
    req = _customer(db, ref, body.token)
    data = body.model_dump(exclude={"token"}, exclude_unset=True)
    req = await run_in_threadpool(_guard, portal.reprice, db, req, data)
    return portal.public_view(req)


class SubmitIn(BaseModel):
    token: str
    name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    needed_by: str = ""
    notes: str = ""
    accept_terms: bool = False


def _notify(req_id: int) -> None:
    db = SessionLocal()
    try:
        req = db.get(PortalRequest, req_id)
        if req:
            portal.notify(req, portal.get_settings(db))
    except Exception as exc:  # noqa: BLE001  (email is best effort; the request is saved either way)
        log.warning("Portal notification for request %s not sent: %s", req_id, exc)
    finally:
        db.close()


@public.post("/quote/{ref}/submit")
def submit(ref: str, body: SubmitIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    _limit(portal.SUBMIT_LIMIT, request)
    req = _customer(db, ref, body.token)
    req = _guard(portal.submit, db, req, body.model_dump(exclude={"token"}))
    background.add_task(_notify, req.id)
    return portal.public_view(req)


# ================================================================ internal (login required)
@internal.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return portal.settings_dict(portal.get_settings(db))


@internal.put("/settings")
def put_settings(body: dict, db: Session = Depends(get_db)):
    return _guard(portal.update_settings, db, body)


@internal.get("/requests")
def list_requests(status: str = "", include_drafts: bool = False, db: Session = Depends(get_db)):
    stmt = select(PortalRequest).order_by(PortalRequest.id.desc())
    if status:
        stmt = stmt.where(PortalRequest.status == status)
    elif not include_drafts:
        stmt = stmt.where(PortalRequest.status != "draft")
    return [portal.internal_dict(r) for r in db.scalars(stmt.limit(300)).all()]


def _req(db: Session, rid: int) -> PortalRequest:
    r = db.get(PortalRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    return r


@internal.get("/requests/{rid}")
def get_request(rid: int, db: Session = Depends(get_db)):
    return portal.internal_dict(_req(db, rid), full=True)


class UpdateIn(BaseModel):
    status: str | None = None
    internal_notes: str | None = None


@internal.put("/requests/{rid}")
def update_request(rid: int, body: UpdateIn, db: Session = Depends(get_db)):
    r = _req(db, rid)
    if body.status is not None:
        if body.status not in PORTAL_STATUSES:
            raise HTTPException(400, f"status must be one of {PORTAL_STATUSES}")
        r.status = body.status
    if body.internal_notes is not None:
        r.internal_notes = body.internal_notes[:10000]
    db.commit()
    return portal.internal_dict(r, full=True)


@internal.get("/requests/{rid}/files/{index}")
def download_file(rid: int, index: int, db: Session = Depends(get_db)):
    r = _req(db, rid)
    files = r.files or []
    if not 0 <= index < len(files) or files[index].get("removed"):
        raise HTTPException(404, "File not found")
    p = _guard(portal.file_path, r, files[index])
    if not p.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(p, filename=files[index]["name"])


@internal.get("/requests/{rid}/views/{key}.svg")
def request_views(rid: int, key: str, db: Session = Depends(get_db)):
    return _svg(_req(db, rid), key)


class LinesIn(BaseModel):
    lines: dict  # {line key: {final_unit_price | qty | material | finish | process}}; null clears a value


@internal.put("/requests/{rid}/lines")
async def set_lines(rid: int, body: LinesIn, db: Session = Depends(get_db)):
    """Your changes to lines in review. A final unit price replaces the tool's for the customer and is recorded
    as a calibration sample (real price next to the tool's), so the tool learns from every job."""
    from . import calibration

    r = _req(db, rid)
    before = {ln["key"]: ln for ln in (r.internal or {}).get("items") or []}
    r.line_opts = _guard(portal.merge_line_opts, r.line_opts or {}, body.lines, portal.get_settings(db).max_quantity * 100, True)
    await run_in_threadpool(portal.price_request, db, r)
    db.commit()
    for key, ch in body.lines.items():
        fp = (ch or {}).get("final_unit_price")
        ln = before.get(key)
        if fp and ln and ln.get("raw_unit_price"):
            proc = (ln.get("calibration") or {}).get("process") or ("cnc_5axis" if (ln.get("process_label") or "").startswith("5-axis") else ln.get("process")) or ln["kind"]
            calibration.add(db, source="review", process=proc, name=ln["name"], material=ln.get("material") or "", quantity=int(ln.get("qty") or 1),
                            tool_unit_price=float(ln["raw_unit_price"]), actual_unit_price=float(fp), ref=f"{r.ref}#{key}"[:60],
                            note="Final price set in review")
    return portal.internal_dict(r, full=True)


@internal.post("/requests/{rid}/to-quotes")
def to_quotes(rid: int, db: Session = Depends(get_db)):
    r = _req(db, rid)
    ids = portal.to_quotes(db, r)
    kinds = {it["kind"] for it in (r.internal or {}).get("items") or [] if it.get("spec")}
    return {"quote_ids": ids, "tabs": sorted({portal.tab_for(k) for k in kinds}), **portal.internal_dict(r, full=True)}


@internal.post("/requests/{rid}/reprice")
async def reprice_internal(rid: int, db: Session = Depends(get_db)):
    """Price again with today's shop rates (does not change what the customer was shown until they look again)."""
    r = _req(db, rid)
    shown = dict(r.public_result or {})
    portal.reset_big(r)  # big models are read again too
    await run_in_threadpool(portal.price_request, db, r)
    r.internal = {**(r.internal or {}), "shown_to_customer": shown}
    db.commit()
    portal.ensure_job(r)
    return portal.internal_dict(r, full=True)


@internal.delete("/requests/{rid}")
def delete_request(rid: int, db: Session = Depends(get_db)):
    portal.delete_request(db, _req(db, rid))
    return {"ok": True}
