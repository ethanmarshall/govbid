"""Customer quote portal: price what a customer uploads, decide instant vs estimate vs manual review.

Routing (each uploaded file becomes one or more items, all at the customer's quantity):
  STEP, one solid         -> instant (Instant quote engine), material and finish from the customer or the drawing
  STEP, several solids    -> estimate (split into bodies, priced as an assembly)
  PDF drawing, no model   -> instant when the drawing read is confident, else estimate; assembly drawings become a box build estimate
  PDF next to a STEP      -> read for material, finish and export markings only
  DXF                     -> instant (flat parts), needs a sheet thickness
  PCB files (Gerbers zip, drill, pick-and-place, BOM) -> estimate (box build with that board)
  anything else           -> kept for the review, priced by hand
The request is "instant" only when every item is; one estimate makes it an estimate, one unpriceable item
makes it a manual review. Estimates are shown as a range (settings), wider when parts still need a manual price.

What the customer sees (public_result) never includes costs, margins, rates or internal warnings.
Uploads are never sent to an outside service. A drawing marked export-controlled or with a limited
distribution statement is deleted on arrival and the request goes to manual review.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import isolate, portal_read, pricing, quotes
from .config import UPLOAD_DIR
from .models_portal import PORTAL_STATUSES, PortalRequest, PortalSettings

PORTAL_DIR = UPLOAD_DIR / "portal"
MAX_FILES = 8
MAX_FILE = 150 * 1024 * 1024
MAX_TOTAL = 250 * 1024 * 1024
MAX_NOTES = 3000
DRAFT_DAYS = 30  # unsubmitted requests (and their files) are removed after this

KINDS = {
    "step": (".step", ".stp"),
    "pdf": (".pdf",),
    "dxf": (".dxf",),
    "pcb": (".zip", ".gbr", ".ger", ".gtl", ".gbl", ".gko", ".gm1", ".drl", ".xln", ".pos", ".csv", ".xlsx", ".tsv"),
    "ref": (".png", ".jpg", ".jpeg", ".txt", ".docx"),
}
ACCEPT = ",".join(e for v in KINDS.values() for e in v)
PROCESS_LABEL = {"cnc_mill": "CNC machined", "cnc_lathe": "CNC turned", "sheet_metal": "Sheet metal", "3d_print": "3D printed",
                 "laser_cut": "Laser cut", "waterjet": "Waterjet cut", "plasma": "Plasma cut", "router": "Router cut"}
STATUS_LABEL = {"draft": "Quote not submitted", "submitted": "Submitted, waiting for review", "reviewing": "In review",
                "confirmed": "Confirmed", "declined": "Declined", "closed": "Closed"}


class PortalError(ValueError):
    pass


# ================================================================ settings
def get_settings(db: Session) -> PortalSettings:
    s = db.get(PortalSettings, 1)
    if s is None:
        s = PortalSettings(id=1)
        db.add(s)
        db.commit()
    return s


SETTINGS_FIELDS = ("enabled", "display_name", "tagline", "intro", "contact_email", "contact_phone", "notify_email", "estimate_low_pct",
                   "estimate_high_pct", "incomplete_high_pct", "review_days", "max_quantity", "terms", "show_codes")

# What the customer site says about you until you change it in Portal settings. Written to be true of a small
# veteran-owned shop that designs, builds and tests; edit every line so it matches what you actually do.
DEFAULT_SITE = {
    "about": "We are a veteran-owned small business that designs, builds and tests custom parts and electromechanical equipment. "
             "Send us a model or a drawing and we will build to it, or tell us what the part has to do and we will help you get to a design.",
    "capabilities": [
        {"title": "CNC machining", "text": "Milled and turned parts in aluminum, steel, stainless and engineering plastics, from one prototype to production runs."},
        {"title": "Sheet metal", "text": "Laser and waterjet cut flat parts, press brake forming, PEM hardware, brackets, panels and enclosures."},
        {"title": "Welded assemblies and frames", "text": "Welded steel and aluminum assemblies, and T-slot aluminum extrusion frames."},
        {"title": "3D printing", "text": "Fixtures, prototypes and low-volume parts in engineering plastics."},
        {"title": "Cable harnesses", "text": "Harnesses built to your drawing, with labels, sleeving and continuity testing on every one."},
        {"title": "Control panels", "text": "Panel layout, wiring, labeling and testing."},
        {"title": "Box builds", "text": "Complete electromechanical assemblies: enclosure, circuit boards, switches, displays, power, wiring, integration and functional test."},
        {"title": "Circuit boards", "text": "Boards built through a contract manufacturer from your Gerbers and BOM, then inspected and tested by us."},
        {"title": "Engineering support", "text": "Electrical and mechanical design, drawings, and a manufacturability review before you commit to a build."},
    ],
    "experience": [
        "Electrical engineering with mechanical design experience.",
        "Design of custom training equipment and power distribution.",
        "Temperature monitoring panels, including RTD measurement over long lead lengths.",
        "Work on nuclear power training programs, where documentation and quality requirements are strict.",
    ],
    "industries": ["Defense and government", "Training equipment", "Industrial equipment", "Test and research labs"],
    "quality": [
        "Every part is inspected to your drawing. A first article inspection report is available when you need one.",
        "Material certifications and a certificate of conformance on request.",
        "Domestic and DFARS-compliant materials sourced when your contract calls for them.",
        "Export-controlled technical data is never handled through this website.",
    ],
    "faq": [
        {"q": "What files should I send?", "a": "A STEP model gives the fastest and most accurate price. A PDF drawing tells us tolerances, finishes and notes, so send both if you have them. For flat parts, a DXF and the sheet thickness. For circuit boards, one zip with the Gerbers, drill file, BOM and pick-and-place file."},
        {"q": "Is the instant price final?", "a": "It is our price for the part as we read it from your files. We confirm every order with you before we start, and if anything in your files changes the price, we tell you first."},
        {"q": "Why did I get an estimate instead of a price?", "a": "Assemblies, box builds, circuit boards and drawings our software cannot read with confidence get a price range. An engineer reviews your files and confirms the price with you within {review_days} business days."},
        {"q": "How do I save my quote?", "a": "Every quote gets a reference number and a private link. Use Save as PDF or Copy link next to your price. This browser also keeps a list under Your saved quotes. Quotes you have not sent to us are kept for 30 days."},
        {"q": "Is there a minimum order?", "a": "No. One part is fine, and the price per part drops as the quantity goes up."},
        {"q": "Are my files kept private?", "a": "Your files are stored on our server for quoting and for building your order. They are not sent to any outside service. Quotes you do not send to us are deleted with their files after 30 days."},
        {"q": "Can you take export-controlled (ITAR or EAR) work?", "a": "Do not upload controlled data here. Check the export-controlled box, send your contact details, and we will talk with you about whether we can take the work and how to transfer the data."},
        {"q": "How do I pay?", "a": "We agree on payment terms when we confirm your order. Purchase orders are welcome."},
    ],
}
SITE_LIMITS = {"capabilities": 24, "experience": 20, "industries": 20, "quality": 20, "faq": 30}


def site_content(s: PortalSettings) -> dict:
    """The site text: what you saved, with defaults for anything you never set."""
    saved = s.site or {}
    return {k: saved[k] if k in saved else v for k, v in DEFAULT_SITE.items()}


def _clean_site(v: dict) -> dict:
    if not isinstance(v, dict):
        raise PortalError("site must be an object")
    out: dict = {}
    if "about" in v:
        out["about"] = str(v["about"] or "")[:3000]
    for k in ("experience", "industries", "quality"):
        if k in v:
            out[k] = [str(x).strip()[:400] for x in (v[k] or []) if str(x).strip()][: SITE_LIMITS[k]]
    if "capabilities" in v:
        out["capabilities"] = [{"title": str(c.get("title") or "").strip()[:80], "text": str(c.get("text") or "").strip()[:500]}
                               for c in (v["capabilities"] or []) if isinstance(c, dict) and str(c.get("title") or "").strip()][: SITE_LIMITS["capabilities"]]
    if "faq" in v:
        out["faq"] = [{"q": str(c.get("q") or "").strip()[:200], "a": str(c.get("a") or "").strip()[:1500]}
                      for c in (v["faq"] or []) if isinstance(c, dict) and str(c.get("q") or "").strip()][: SITE_LIMITS["faq"]]
    return out


def settings_dict(s: PortalSettings) -> dict:
    return {**{k: getattr(s, k) for k in SETTINGS_FIELDS}, "site": site_content(s), "site_defaults": DEFAULT_SITE}


def update_settings(db: Session, changes: dict) -> dict:
    s = get_settings(db)
    for k, v in (changes or {}).items():
        if k == "site" and v is not None:
            s.site = {**(s.site or {}), **_clean_site(v)}
            continue
        if k not in SETTINGS_FIELDS or v is None:
            continue
        if k in ("enabled", "show_codes"):
            v = bool(v)
        elif k in ("estimate_low_pct", "estimate_high_pct", "incomplete_high_pct"):
            v = float(v)
            if not 0 <= v <= 300:
                raise PortalError(f"{k} must be between 0 and 300")
        elif k in ("review_days", "max_quantity"):
            v = int(v)
            if v < 0 or (k == "max_quantity" and v < 1):
                raise PortalError(f"{k} must be a positive number")
        else:
            v = str(v)[:3000]
        setattr(s, k, v)
    db.commit()
    return settings_dict(s)


def public_info(db: Session) -> dict:
    """What the public page needs: who you are, choices, limits. No rates or costs."""
    from .models import CompanyProfile

    s = get_settings(db)
    cfg = quotes.get_config(db)
    prof = db.scalars(select(CompanyProfile)).first()
    from .flat import materials as flat_materials

    return {"enabled": s.enabled, "name": s.display_name or (prof.name if prof else "") or "Quote request",
            "tagline": s.tagline, "intro": s.intro, "contact_email": s.contact_email, "contact_phone": s.contact_phone,
            "terms": s.terms, "review_days": s.review_days, "max_quantity": s.max_quantity,
            "materials": sorted(cfg["materials"]), "print_materials": sorted(cfg["additive"]["materials"]),
            "sheet_materials": sorted(flat_materials(cfg)), "finishes": sorted(cfg["finishes"]),
            "accept": ACCEPT, "max_files": MAX_FILES, "max_file_mb": MAX_FILE // (1024 * 1024), "keep_days": DRAFT_DAYS,
            "site": site_content(s), "company": _company_codes(prof) if s.show_codes else None}


def _company_codes(prof) -> dict | None:
    """Registration codes and only the certifications you actually hold (pending ones are not shown)."""
    if not prof:
        return None
    from .eligibility import CERT_LABELS

    certs = [CERT_LABELS.get(k, k) for k, v in (prof.certifications or {}).items() if v == "certified" and k != "SB"]
    if (prof.certifications or {}).get("SB") == "certified":
        certs.insert(0, "Small business")
    out = {"uei": prof.uei or "", "cage": prof.cage or "", "naics": list(prof.naics_codes or [])[:12], "certifications": certs}
    return out if any(out.values()) else None


# ================================================================ abuse limits
class Limiter:
    """Sliding-window counts per client address plus a site-wide cap (in memory, one instance)."""

    def __init__(self, per_ip: int, per_all: int, window_s: int):
        self.per_ip, self.per_all, self.window = per_ip, per_all, window_s
        self.ip: dict[str, deque] = defaultdict(deque)
        self.all: deque = deque()

    def hit(self, key: str) -> bool:
        now = time.time()
        for q in (self.ip[key], self.all):
            while q and now - q[0] > self.window:
                q.popleft()
        if len(self.ip[key]) >= self.per_ip or len(self.all) >= self.per_all:
            return False
        self.ip[key].append(now)
        self.all.append(now)
        return True

    def clear(self):
        self.ip.clear()
        self.all.clear()


QUOTE_LIMIT = Limiter(per_ip=20, per_all=300, window_s=3600)
REPRICE_LIMIT = Limiter(per_ip=120, per_all=2000, window_s=3600)
SUBMIT_LIMIT = Limiter(per_ip=5, per_all=60, window_s=3600)


def ip_hash(ip: str) -> str:
    return hashlib.sha256(f"{ip}|{os.getenv('SESSION_SECRET', '')}".encode()).hexdigest()[:32]


# ================================================================ files
def kind_of(name: str) -> str | None:
    low = name.lower()
    return next((k for k, exts in KINDS.items() if low.endswith(exts)), None)


def _safe(name: str) -> str:
    base = Path(name or "file").name
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "file")[:100]


def req_dir(req: PortalRequest) -> Path:
    return PORTAL_DIR / req.ref


def store_files(req: PortalRequest, uploads: list[tuple[str, bytes]]) -> None:
    if len(uploads) > MAX_FILES:
        raise PortalError(f"Upload {MAX_FILES} files or fewer (zip PCB files together).")
    total = 0
    out = []
    d = req_dir(req)
    d.mkdir(parents=True, exist_ok=True)
    for i, (name, data) in enumerate(uploads):
        k = kind_of(name)
        if not k:
            raise PortalError(f"{Path(name).name}: that file type is not accepted. Send STEP, PDF, DXF or PCB files.")
        if not data:
            raise PortalError(f"{Path(name).name} is empty.")
        if len(data) > MAX_FILE:
            raise PortalError(f"{Path(name).name} is larger than {MAX_FILE // (1024 * 1024)} MB.")
        total += len(data)
        if total > MAX_TOTAL:
            raise PortalError(f"The files add up to more than {MAX_TOTAL // (1024 * 1024)} MB.")
        stored = f"{i + 1:02d}_{_safe(name)}"
        (d / stored).write_bytes(data)
        out.append({"name": Path(name).name[:120], "stored": stored, "kind": k, "size": len(data), "removed": False})
    req.files = out


def file_path(req: PortalRequest, f: dict) -> Path:
    p = (req_dir(req) / f["stored"]).resolve()
    if not p.is_relative_to(req_dir(req).resolve()):
        raise PortalError("Bad file name")
    return p


def remove_file(req: PortalRequest, f: dict) -> None:
    try:
        file_path(req, f).unlink(missing_ok=True)
    except OSError:
        pass
    f["removed"] = True


# ================================================================ pricing
def _qtys(n: int) -> list[int]:
    return [1, n] if n > 1 else [1]


def _at(breaks: list[dict], n: int) -> dict:
    return next((b for b in breaks if b["quantity"] == n), breaks[-1])


def _item(name: str, route: str, desc: str, breaks: list[dict] | None, n: int, *, kind: str, spec: dict | None = None,
          public_reason: str = "", internal_reasons: list[str] | None = None, incomplete: bool = False,
          facts: list[dict] | None = None, view: dict | None = None) -> dict:
    b = _at(breaks, n) if breaks else None
    return {"name": name, "route": route, "desc": desc, "kind": kind, "spec": spec, "public_reason": public_reason,
            "facts": facts or [], "view": view,
            "internal_reasons": internal_reasons or [], "incomplete": incomplete,
            "unit_price": b["unit_price"] if b else None, "unit_cost": b.get("unit_cost") if b else None,
            "margin_pct": b.get("margin_pct") if b else None, "lead_days": b.get("lead_time_days") if b else None,
            "one_unit_price": breaks[0]["unit_price"] if breaks else None}


def _mat_source(req: PortalRequest, cfg: dict, mat: str, drawing_mat: str | None) -> str:
    if (req.material or "").strip() == mat:
        return "chosen"
    if drawing_mat and drawing_mat == mat:
        return "drawing"
    return "default"


def _fin_source(req: PortalRequest, finishes: list[str]) -> str:
    return "chosen" if req.finish else ("drawing" if finishes else "")


VIEW_NOTES = {"model": "Drawn from your 3D model.",
              "flat": "Your flat pattern, shown at the sheet thickness. Bends are not formed in this view.",
              "envelope": "A block at the overall size we read, to check the size only. The real part has more detail."}


def _view(req: PortalRequest, key_parts: tuple, make_shape, kind: str) -> dict | None:
    """Three-view drawing for an item, cached in the request folder. Never fails the quote."""
    from . import portal_views as pv

    try:
        key = pv.cache_key(*key_parts, kind, 2)
        folder = req_dir(req) / "views"
        if pv.load(folder, key) is None:
            pv.save(folder, key, pv.build_sheet(make_shape(), kind=kind))
        return {"key": key, "kind": kind, "note": VIEW_NOTES[kind]}
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).info("No views for %s: %s", req.ref, exc)
        return None


def _iso_split(file_id: str) -> bool:
    """Helper process: split a big assembly into its bodies (cached by assembly.split)."""
    from .assembly import split

    split(file_id)
    return True


def view_sheet(req: PortalRequest, key: str) -> dict | None:
    from . import portal_views as pv

    if not re.fullmatch(r"[0-9a-f]{20}", key or ""):
        return None
    return pv.load(req_dir(req) / "views", key)


def _material(req: PortalRequest, cfg: dict, drawing_mat: str | None) -> tuple[str, bool]:
    """(material, is_print). The customer's choice wins, then the drawing's, then 6061."""
    m = (req.material or "").strip()
    if m in cfg["additive"]["materials"]:
        return m, True
    if m in cfg["materials"]:
        return m, False
    if drawing_mat and drawing_mat in cfg["materials"]:
        return drawing_mat, False
    return "6061-T6 aluminum", False


def _finishes(req: PortalRequest, cfg: dict, is_print: bool, drawing_finishes: list[str]) -> list[str]:
    pool = cfg["additive"]["finishes"] if is_print else cfg["finishes"]
    if req.finish and req.finish in pool:
        return [req.finish]
    if req.finish == "none":
        return []
    return [f for f in drawing_finishes if f in pool]


def _read_pdfs(req: PortalRequest) -> tuple[list[dict], bool]:
    """Read every drawing (no outside service). Export-controlled ones are deleted. Returns reads and whether any was controlled."""
    from . import drawing

    reads, controlled = [], False
    for f in req.files:
        if f["kind"] != "pdf" or f["removed"]:
            continue
        try:
            r = drawing.read_drawing(file_path(req, f), use_ai=False)
        except Exception:  # noqa: BLE001  (a bad PDF is reviewed by hand)
            reads.append({"file": f, "read": None})
            continue
        letter = (r.get("distribution") or {}).get("letter") or ""
        if r.get("export_controlled") or (letter and letter != "A"):
            remove_file(req, f)
            controlled = True
            continue
        reads.append({"file": f, "read": r})
    return reads, controlled


def price_request(db: Session, req: PortalRequest) -> None:
    """Price the request from its stored files and options; fills req.kind, req.public_result and req.internal."""
    from . import box_build, cad, cad_quote, drawing_assembly, drawing_quote, flat, pcb_files
    from . import portal_views as pv

    s = get_settings(db)
    cfg = quotes.get_config(db)
    over = quotes.get_overrides(db)
    n = max(1, min(int(req.quantity or 1), s.max_quantity))
    req.quantity = n
    q = _qtys(n)
    items: list[dict] = []

    if req.export_controlled:
        _finish(req, s, [], manual_reason="You told us the project includes export-controlled technical data. Do not upload it here: "
                                          "send your contact details and we will arrange a secure way to receive it.")
        return
    reads, controlled = _read_pdfs(req)
    if controlled:
        req.export_controlled = True
        _finish(req, s, [], manual_reason="A drawing you uploaded is marked export-controlled or limited distribution, so we deleted it "
                                          "without reading further. Send your contact details and we will arrange a secure transfer.")
        return
    drawing_mat = next((r["read"]["material"]["mapped"] for r in reads if r["read"] and (r["read"].get("material") or {}).get("mapped")), None)
    drawing_fin = [x["mapped"] for r in reads if r["read"] for x in (r["read"].get("finishes") or []) if x.get("mapped")]
    steps = [f for f in req.files if f["kind"] == "step" and not f["removed"]]
    dxfs = [f for f in req.files if f["kind"] == "dxf" and not f["removed"]]
    pcbs = [f for f in req.files if f["kind"] == "pcb" and not f["removed"]]
    refs = [f for f in req.files if f["kind"] == "ref" and not f["removed"]]

    # ---- STEP models
    for f in steps:
        name = Path(f["name"]).stem
        if f.get("size", 0) > isolate.BIG_FILE:  # big model: read in the background, the page updates when it is done
            st = _prep_state(req, f)
            if st.get("status") == "failed":
                items.append(_item(name, "manual", "3D model", None, n, kind="step",
                                   public_reason="Your model is too large or detailed to read automatically, so an engineer will price it.",
                                   internal_reasons=[st.get("error", "")]))
                continue
            if st.get("status") != "done":
                items.append(_item(name, "processing", "3D model", None, n, kind="step",
                                   public_reason="Your model is large, so we are reading it now. This page updates on its own when it is ready, "
                                                 "usually within a few minutes. You can also save the link and come back."))
                continue
        try:
            stored = cad_quote.store_upload(file_path(req, f).read_bytes(), f["name"])
        except (cad.CadError, Exception) as exc:  # noqa: BLE001
            items.append(_item(name, "manual", "3D model", None, n, kind="step", public_reason="We could not read this model automatically.",
                               internal_reasons=[str(exc)]))
            continue
        solids = (stored.get("geometry") or {}).get("solids", 1) or 1
        mat, is_print = _material(req, cfg, drawing_mat)
        msrc = _mat_source(req, cfg, mat, drawing_mat)
        step_path = file_path(req, f)
        big = f.get("size", 0) > isolate.BIG_FILE
        view = None if big and pv.load(req_dir(req) / "views", pv.cache_key(stored["file_id"], "model", 2)) is None \
            else _view(req, (stored["file_id"],), lambda p=step_path: cad.load_step(p), "model")
        if solids > 1 and _prep_state(req, f).get("split_error"):
            bb = (stored.get("geometry") or {}).get("bounding_box") or {}
            facts = [portal_read.row("Overall size", portal_read._size(bb.get("length"), bb.get("width"), bb.get("height"))),
                     portal_read.row("Parts in the model", solids), portal_read.material_row(mat, msrc)]
            items.append(_item(name, "manual", f"Assembly ({solids} parts)", None, n, kind="assembly", view=view, facts=facts,
                               public_reason=f"Your model has {solids} separate parts and is very large, so an engineer will price it.",
                               internal_reasons=[_prep_state(req, f)["split_error"]]))
            continue
        if solids > 1:
            try:
                from .assembly import quote_assembly, split

                sp = split(stored["file_id"])
                bodies = [{"file_id": g["file_id"], "name": g.get("name") or "body", "qty": g.get("qty", 1),
                           "process": "3d_print" if is_print else g.get("suggested_process") or "auto", "material": mat,
                           "finishes": _finishes(req, cfg, is_print, drawing_fin)} for g in sp["groups"]]
                joining = {"weld_process": "mig", "weld_length_in": sp.get("weld_estimate_in") or 0, "assembly_minutes": 10 * len(bodies),
                           "inspection_minutes": 10}
                r = quote_assembly(bodies, joining, q, over)
                spec = {"kind": "assembly", "name": name, "quantities": q, "bodies": bodies, "joining": joining,
                        "cad": {"file_id": stored["file_id"], "filename": f["name"], "notes": [], "options": {"assembly": True}}}
                items.append(_item(name, "estimate", f"Assembly of {len(bodies)} part types, {mat}", r["price_breaks"], n, kind="assembly", spec=spec,
                                   public_reason=f"Your model has {solids} separate parts, so an engineer will confirm how it goes together.",
                                   internal_reasons=r.get("warnings", [])[:6], incomplete=bool(r.get("incomplete")),
                                   facts=portal_read.step_assembly(stored.get("geometry") or {}, sp["groups"], mat, msrc), view=view))
            except Exception as exc:  # noqa: BLE001
                items.append(_item(name, "manual", f"Assembly ({solids} parts)", None, n, kind="assembly",
                                   public_reason=f"Your model has {solids} separate parts; we will price it by hand.", internal_reasons=[str(exc)], view=view))
            continue
        opts = {"material": mat, "finishes": _finishes(req, cfg, is_print, drawing_fin), "quantities": q, "filename": f["name"], "name": name}
        if is_print:
            opts["process"] = "3d_print"
        try:
            r = cad_quote.quote(stored["file_id"], opts, over)
        except (pricing.SpecError, cad.CadError, KeyError, ValueError) as exc:
            items.append(_item(name, "manual", "3D model", None, n, kind="step", public_reason="This part needs a quick look before we can price it.",
                               internal_reasons=[str(exc)], view=view))
            continue
        est = r["estimate"]
        plabel = PROCESS_LABEL.get(r["process"], r["process"])
        facts = portal_read.step_part(stored.get("geometry") or {}, mat, msrc, opts["finishes"], _fin_source(req, opts["finishes"]), plabel,
                                      (cfg["materials"].get(mat) or cfg["additive"]["materials"].get(mat) or {}).get("density"))
        items.append(_item(name, "instant", f"{plabel}, {mat}"
                           + (f", {', '.join(opts['finishes'])}" if opts["finishes"] else ""), est["price_breaks"], n, kind="part",
                           spec=r["spec"], internal_reasons=est.get("warnings", [])[:6], facts=facts, view=view))

    # ---- drawings with no model: price the drawing itself
    if not steps:
        for rd in reads:
            f, read = rd["file"], rd["read"]
            name = Path(f["name"]).stem
            if not read or not read.get("text_found", True):
                items.append(_item(name, "manual", "Drawing", None, n, kind="drawing", public_reason="We will read this drawing by hand."))
                continue
            path = file_path(req, f)
            try:
                asm = drawing_assembly.analyze(path, read)
            except Exception:  # noqa: BLE001
                asm = None
            if asm:
                bb = asm["box_build"]
                spec = {**{k: v for k, v in bb.items() if k not in ("evidence", "assumptions", "fabricated")}, "kind": "box_build", "quantities": q}
                try:
                    r = box_build.price(spec, over)
                    enc = bb.get("enclosure") or {}
                    view = None
                    if enc.get("length_in") and enc.get("width_in"):
                        dimsv = (enc["length_in"], enc["width_in"], enc.get("height_in") or 1)
                        view = _view(req, ("env",) + tuple(dimsv), lambda d=dimsv: pv.box_shape(*d), "envelope")
                    items.append(_item(bb.get("name") or name, "estimate", "Assembly from your drawing", r["price_breaks"], n, kind="box_build", spec=spec,
                                       public_reason="Your drawing is an assembly with custom parts, so an engineer will confirm the build.",
                                       internal_reasons=[i["item"] + ": " + i["reason"] for i in r.get("incomplete", [])][:8],
                                       incomplete=bool(r.get("incomplete")), facts=portal_read.box_build(bb), view=view))
                except Exception as exc:  # noqa: BLE001
                    items.append(_item(name, "manual", "Assembly drawing", None, n, kind="box_build",
                                       public_reason="Your drawing is an assembly; we will price it by hand.", internal_reasons=[str(exc)]))
                continue
            from . import drawing as drawing_mod

            text, _ = drawing_mod.extract_pdf_text(path)
            geom = drawing_quote.extract_geometry(read, text)
            o = {"quantities": q}
            if req.material in cfg["materials"]:
                o["material"] = req.material
            if req.finish and req.finish in cfg["finishes"]:
                o["finishes"] = [req.finish]
            try:
                r = drawing_quote.quote(read, geom, o, over)
            except (pricing.SpecError, ValueError) as exc:
                items.append(_item(name, "manual", "Drawing", None, n, kind="drawing", public_reason="We will read this drawing by hand.",
                                   internal_reasons=[str(exc)]))
                continue
            rv = r["review"]
            route = "estimate" if rv["manual_required"] else "instant"
            plabel = PROCESS_LABEL.get(r["spec"]["process"], r["spec"]["process"])
            dmat = r["inputs"]["material"]
            dsrc = "chosen" if o.get("material") else ("drawing" if (read.get("material") or {}).get("mapped") == dmat else "default")
            dfin = r["spec"].get("finishes") or []
            env = geom.get("envelope_in") or {}
            view = None
            tg = geom.get("turned") or {}
            if tg.get("max_diameter") and (tg.get("length") or env.get("length")):
                dimsv = (tg["max_diameter"], tg.get("length") or env["length"])
                view = _view(req, ("cyl",) + tuple(dimsv), lambda d=dimsv: pv.cylinder_shape(*d), "envelope")
            elif env.get("length") and env.get("width"):
                h = env.get("height") or geom.get("sheet_thickness") or 0.1
                dimsv = (env["length"], env["width"], h)
                view = _view(req, ("env",) + tuple(dimsv), lambda d=dimsv: pv.box_shape(*d), "envelope")
            facts = portal_read.drawing_part(read, geom, dmat, dsrc, dfin, "chosen" if o.get("finishes") else ("drawing" if dfin else ""), plabel,
                                             [("The size we read looks too large for one part." if "cost" in x else x) for x in rv.get("reasons") or []])
            items.append(_item(name, route, f"{plabel}, {dmat} (from your drawing)",
                               r["estimate"]["price_breaks"], n, kind="part", spec=r["spec"],
                               public_reason="Some sizes on your drawing need to be confirmed by an engineer." if route == "estimate" else "",
                               internal_reasons=rv["reasons"] + r["estimate"].get("warnings", [])[:4], facts=facts, view=view))

    # ---- DXF flat parts
    if dxfs:
        if not req.thickness:
            items.append(_item(", ".join(Path(f["name"]).stem for f in dxfs)[:80], "needs_input", "Flat parts (DXF)", None, n, kind="flat",
                               public_reason="Choose the sheet thickness to price your DXF parts."))
        else:
            try:
                parsed = flat.parse_files([(f["name"], file_path(req, f).read_bytes()) for f in dxfs], keep_shapes=True)
                shapes = {p["id"]: p.pop("shape", None) for p in parsed["parts"]}
                mats = flat.materials(cfg)
                mat = req.material if req.material in mats else (drawing_mat if drawing_mat in mats else "A36 / 1018 steel")
                cls = flat.material_class(mat)
                process = "router" if cls in ("wood", "plastic", "composite") and "acrylic" not in mat.lower() else ("waterjet" if req.thickness > 0.75 else "laser_cut")
                options = {"material": mat, "thickness": float(req.thickness), "process": process}
                if req.finish and req.finish in cfg["finishes"]:
                    options["finishes"] = [req.finish]
                r = flat.estimate(parsed["parts"], options, q, over)
                spec = {"kind": "flat_dxf", "name": "Flat parts", "quantities": q, "parts": [flat.clean_part(p) for p in parsed["parts"]],
                        "options": options, "material": mat, "source": {"files": []}}
                big = max(parsed["parts"], key=lambda p: p.get("outer_area") or 0, default=None)
                view = None
                if big and shapes.get(big["id"]):
                    sh, t = shapes[big["id"]], float(req.thickness)
                    view = _view(req, ("dxf", [f["stored"] for f in dxfs], big["id"], t),
                                 lambda sh=sh, t=t: pv.flat_shape(sh["outer"], sh["holes"], t), "flat")
                    if view and len(parsed["parts"]) > 1:
                        view["note"] = f"{big.get('name')}, the largest of your {len(parsed['parts'])} parts. " + view["note"]
                msrc = "chosen" if req.material == mat else ("drawing" if drawing_mat == mat else "default")
                plabel = PROCESS_LABEL.get(process, process)
                items.append(_item(f"{len(parsed['parts'])} flat part(s)", "instant", f"{plabel}, {mat}, {req.thickness:g} in",
                                   r["price_breaks"], n, kind="flat", spec=spec, internal_reasons=r.get("warnings", [])[:6],
                                   facts=portal_read.flat_parts(parsed["parts"], float(req.thickness), mat, msrc, plabel), view=view))
            except Exception as exc:  # noqa: BLE001
                items.append(_item("Flat parts (DXF)", "manual", "Flat parts", None, n, kind="flat",
                                   public_reason="We could not read these DXF files automatically.", internal_reasons=[str(exc)]))

    # ---- circuit boards
    if pcbs:
        try:
            got = pcb_files.parse_files([(f["name"], file_path(req, f).read_bytes()) for f in pcbs])
            board = box_build.blank_pcb(name="Circuit board", **got["board"])
            board["bom_lines"] = got["bom_lines"]
            spec = {"kind": "box_build", "name": "Circuit board assembly", "quantities": q, "enclosure": {"source": "none"}, "pcbs": [board]}
            r = box_build.price(spec, over)
            view = None
            if board.get("width_in") and board.get("height_in"):
                dimsv = (board["width_in"], board["height_in"], board.get("thickness_in") or 0.062)
                view = _view(req, ("pcb",) + tuple(dimsv), lambda d=dimsv: pv.box_shape(*d), "envelope")
            items.append(_item("Circuit board assembly", "estimate", f"{board['layers']} layer board" + (f", {board['width_in']:g} x {board['height_in']:g} in" if board.get("width_in") else ""),
                               r["price_breaks"], n, kind="box_build", spec=spec, public_reason="Circuit boards are always reviewed by an engineer before we confirm.",
                               internal_reasons=got["warnings"] + r.get("warnings", [])[:4],
                               facts=portal_read.pcb(got["board"], got.get("found") or {}, len(got.get("bom_lines") or [])), view=view))
        except Exception as exc:  # noqa: BLE001
            items.append(_item("Circuit board files", "manual", "Circuit board", None, n, kind="pcb",
                               public_reason="We will review your board files by hand.", internal_reasons=[str(exc)]))

    if refs and not items:
        items.append(_item("Reference files", "manual", "Images or documents", None, n, kind="ref", public_reason="We will review the files you sent."))
    if not req.files and not items:
        _finish(req, s, [], manual_reason="Tell us about the project in the notes and send your contact details; we will get back to you.")
        return
    _finish(req, s, items)


def _round_est(v: float) -> float:
    if v >= 1000:
        return float(round(v / 10) * 10)
    if v >= 100:
        return float(round(v))
    return round(v, 2)


def _finish(req: PortalRequest, s: PortalSettings, items: list[dict], manual_reason: str = "") -> None:
    n = req.quantity
    routes = {i["route"] for i in items}
    if "processing" in routes and not manual_reason:
        kind = "processing"
    elif manual_reason or not items or "manual" in routes:
        kind = "manual"
    elif "needs_input" in routes:
        kind = "needs_input"
    elif "estimate" in routes:
        kind = "estimate"
    else:
        kind = "instant"
    priced = [i for i in items if i["unit_price"] is not None]
    unit = sum(i["unit_price"] for i in priced)
    lead = max([i["lead_days"] or 0 for i in priced] or [0])
    pub_items = []
    low = high = 0.0
    for i in items:
        row = {"name": i["name"], "desc": i["desc"], "route": i["route"], "note": i["public_reason"], "facts": i.get("facts") or [],
               "view": i.get("view")}
        if i["unit_price"] is not None:
            if i["route"] == "estimate":
                hi_pct = s.incomplete_high_pct if i["incomplete"] else s.estimate_high_pct
                lo, hi = i["unit_price"] * (1 - s.estimate_low_pct / 100), i["unit_price"] * (1 + hi_pct / 100)
                row.update(unit_low=_round_est(lo), unit_high=_round_est(hi))
                low += lo
                high += hi
            else:
                row.update(unit_price=i["unit_price"])
                low += i["unit_price"]
                high += i["unit_price"]
        pub_items.append(row)
    out = {"kind": kind, "quantity": n, "items": pub_items, "review_days": s.review_days, "lead_days": None}
    if kind == "instant":
        out.update(unit_price=round(unit, 2), total=round(unit * n, 2), lead_days=int(lead),
                   message="This is an instant quote. Submit it and we will confirm the order with you before we start.")
    elif kind == "estimate":
        out.update(unit_low=_round_est(low), unit_high=_round_est(high), total_low=_round_est(low * n), total_high=_round_est(high * n),
                   lead_days=int(lead + s.review_days),
                   message=f"This is a complex build, so this is an estimate. An engineer will review your files and reach out within "
                           f"{s.review_days} business day{'s' if s.review_days != 1 else ''} to confirm your project needs and the final cost "
                           "before we complete the order.")
    elif kind == "needs_input":
        out.update(message="Almost there: answer the question below to see your price.")
    elif kind == "processing":
        out.update(message="Your model is large, so we are reading it now. This page updates on its own when the price is ready, "
                           "usually within a few minutes. You can save the link and come back.")
    else:
        out.update(message=manual_reason or "We need to look at this one by hand. Submit it with your contact details and an engineer will "
                                            f"reach out within {s.review_days} business day{'s' if s.review_days != 1 else ''} with a price.")
    req.kind = kind
    req.public_result = out
    req.internal = {"priced_at": datetime.utcnow().isoformat(timespec="seconds"), "unit_total": round(unit, 2),
                    "items": [{k: v for k, v in i.items()} for i in items]}


# ================================================================ big models in the background
_jobs: dict[str, threading.Thread] = {}
_jobs_lock = threading.Lock()
_heavy = threading.Semaphore(1)  # one big model at a time: each can use most of the server's memory


def _prep_path(req: PortalRequest, f: dict) -> Path:
    return req_dir(req) / "prep" / f"{f['stored']}.json"


def _prep_state(req: PortalRequest, f: dict) -> dict:
    try:
        return json.loads(_prep_path(req, f).read_text())
    except (OSError, ValueError):
        return {}


def _iso_analyze(step_path: str, filename: str) -> dict:
    """Helper process 1: store and measure a big model (cached by its content)."""
    from . import cad, cad_quote

    data = Path(step_path).read_bytes()
    if "ISO-10303" not in data[:2000].decode("latin-1", "replace").upper():
        raise cad.CadError("That is not a STEP file.")
    fid = cad.file_id_for(data)
    sp, meta = cad_quote.CAD_DIR / f"{fid}.step", cad_quote.CAD_DIR / f"{fid}.json"
    if not sp.exists():
        sp.write_bytes(data)
    del data
    if not meta.exists():
        cad_quote._analyze_to_cache(str(sp), str(meta))
    solids = (json.loads(meta.read_text()).get("geometry") or {}).get("solids", 1)
    return {"file_id": fid, "solids": solids}


def _iso_draw(file_id: str, views_dir: str) -> bool:
    """Helper process 3: the three-view drawing of a big model."""
    from . import cad, cad_quote
    from . import portal_views as pv

    key = pv.cache_key(file_id, "model", 2)
    if pv.load(Path(views_dir), key) is None:
        pv.save(Path(views_dir), key, pv.build_sheet(cad.load_step(cad_quote.CAD_DIR / f"{file_id}.step"), kind="model"))
    return True


def _prepare_big(req: PortalRequest, f: dict) -> dict:
    """Read one big model in three separate helper processes (each starts with empty memory):
    measure it, split an assembly into its parts, draw it. Only the first must succeed."""
    limit = int(os.getenv("CAD_BIG_TIME_S", "1500"))
    out = isolate.run(f"{__name__}:_iso_analyze", str(file_path(req, f)), f["name"], timeout=limit)
    if out.get("solids", 1) > 1:
        try:
            isolate.run(f"{__name__}:_iso_split", out["file_id"], timeout=limit)
        except isolate.IsolatedError as exc:
            out["split_error"] = str(exc)
    try:
        isolate.run(f"{__name__}:_iso_draw", out["file_id"], str(req_dir(req) / "views"), timeout=limit)
    except isolate.IsolatedError as exc:
        out["draw_error"] = str(exc)
    return out


def _run_job(ref: str) -> None:
    from .db import SessionLocal

    try:
        with _heavy:
            for attempt in range(30):  # the request is committed just after the job starts
                db = SessionLocal()
                req = db.scalar(select(PortalRequest).where(PortalRequest.ref == ref))
                if req is not None:
                    break
                db.close()
                time.sleep(1)
            else:
                return
            try:
                for f in req.files or []:
                    if f["kind"] != "step" or f.get("removed") or f.get("size", 0) <= isolate.BIG_FILE or _prep_state(req, f).get("status"):
                        continue
                    pp = _prep_path(req, f)
                    pp.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        out = _prepare_big(req, f)
                        pp.write_text(json.dumps({"status": "done", **out}))
                    except isolate.IsolatedError as exc:
                        pp.write_text(json.dumps({"status": "failed", "error": str(exc)}))
                db.refresh(req)
                price_request(db, req)
                db.commit()
            finally:
                db.close()
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("Background reading for %s failed: %s", ref, exc)
    finally:
        with _jobs_lock:
            _jobs.pop(ref, None)


def ensure_job(req: PortalRequest) -> None:
    """Start (or restart, after a server restart) the background reading of a request's big models."""
    if (req.public_result or {}).get("kind") != "processing":
        return
    with _jobs_lock:
        t = _jobs.get(req.ref)
        if t and t.is_alive():
            return
        t = threading.Thread(target=_run_job, args=(req.ref,), daemon=True, name=f"cad-{req.ref}")
        _jobs[req.ref] = t
        t.start()


# ================================================================ requests
def _new_ref(db: Session) -> str:
    year = date.today().year
    prefix = f"RQ-{year}-"
    last = db.scalar(select(func.max(PortalRequest.ref)).where(PortalRequest.ref.like(prefix + "%")))
    n = int(last[len(prefix):]) + 1 if last else 1
    return f"{prefix}{n:04d}"


def purge_stale(db: Session) -> int:
    """Delete drafts nobody submitted (and their files) after DRAFT_DAYS."""
    cutoff = datetime.utcnow() - timedelta(days=DRAFT_DAYS)
    old = db.scalars(select(PortalRequest).where(PortalRequest.status == "draft", PortalRequest.created_at < cutoff)).all()
    for r in old:
        shutil.rmtree(req_dir(r), ignore_errors=True)
        db.delete(r)
    if old:
        db.commit()
    return len(old)


def _clean_opts(req: PortalRequest, data: dict, max_qty: int) -> None:
    if "quantity" in data and data["quantity"] not in (None, ""):
        try:
            qn = int(float(data["quantity"]))
        except (TypeError, ValueError):
            raise PortalError("Quantity must be a whole number.")
        if not 1 <= qn <= max_qty:
            raise PortalError(f"Quantity must be between 1 and {max_qty:,}.")
        req.quantity = qn
    for k in ("material", "finish"):
        if k in data and data[k] is not None:
            setattr(req, k, str(data[k])[:80])
    if "thickness" in data:
        t = data["thickness"]
        try:
            t = float(t) if t not in (None, "") else None
        except (TypeError, ValueError):
            raise PortalError("Thickness must be a number in inches.")
        if t is not None and not 0.005 <= t <= 6:
            raise PortalError("Thickness must be between 0.005 and 6 inches.")
        req.thickness = t
    if "notes" in data and data["notes"] is not None:
        req.customer_notes = str(data["notes"])[:MAX_NOTES]


def create(db: Session, uploads: list[tuple[str, bytes]], data: dict, ip: str, preview: bool = False) -> PortalRequest:
    """preview: you, signed in, trying the page while it is still closed to customers."""
    s = get_settings(db)
    if not s.enabled and not preview:
        raise PortalError("Online quoting is not open yet.")
    purge_stale(db)
    req = PortalRequest(ref=_new_ref(db), token=secrets.token_urlsafe(24), status="draft", ip_hash=ip_hash(ip),
                        export_controlled=bool(data.get("export_controlled")))
    _clean_opts(req, data, s.max_quantity)
    if not req.quantity:
        req.quantity = 1
    db.add(req)
    db.flush()
    try:
        if req.export_controlled:
            req.files = []  # controlled data is never stored here
        else:
            store_files(req, uploads)
        price_request(db, req)
        if preview and not s.enabled:
            req.internal = {**(req.internal or {}), "preview": True}
    except Exception:
        db.rollback()
        shutil.rmtree(PORTAL_DIR / req.ref, ignore_errors=True)
        raise
    db.commit()
    ensure_job(req)
    return req


def get_for_customer(db: Session, ref: str, token: str) -> PortalRequest:
    import hmac

    req = db.scalar(select(PortalRequest).where(PortalRequest.ref == ref))
    if not req or not token or not hmac.compare_digest(req.token, token):
        raise PortalError("Quote not found. Check the link.")
    return req


def reprice(db: Session, req: PortalRequest, data: dict) -> PortalRequest:
    if req.status not in ("draft",):
        raise PortalError("This request was already submitted. Contact us to change it.")
    _clean_opts(req, data, get_settings(db).max_quantity)
    price_request(db, req)
    db.commit()
    ensure_job(req)
    return req


EMAIL_RX = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


def submit(db: Session, req: PortalRequest, data: dict) -> PortalRequest:
    if req.status != "draft":
        raise PortalError("This request was already submitted.")
    name = str(data.get("name") or "").strip()[:120]
    email = str(data.get("email") or "").strip()[:160]
    if not name:
        raise PortalError("Enter your name.")
    if not EMAIL_RX.match(email):
        raise PortalError("Enter a valid email address.")
    if not data.get("accept_terms"):
        raise PortalError("Please accept the terms.")
    req.contact_name, req.email = name, email
    req.company = str(data.get("company") or "").strip()[:160]
    req.phone = re.sub(r"[^0-9+()\-. x]", "", str(data.get("phone") or ""))[:40]
    nb = str(data.get("needed_by") or "")[:10]
    req.needed_by = nb if re.fullmatch(r"\d{4}-\d{2}-\d{2}", nb) else ""
    if data.get("notes"):
        req.customer_notes = (req.customer_notes + "\n" if req.customer_notes else "") + str(data["notes"])[:MAX_NOTES]
    req.status = "submitted"
    req.submitted_at = datetime.utcnow()
    db.commit()
    return req


def public_view(req: PortalRequest) -> dict:
    """Everything the customer may see about their request."""
    return {"ref": req.ref, "status": req.status, "status_label": STATUS_LABEL.get(req.status, req.status), "quantity": req.quantity,
            "material": req.material, "finish": req.finish, "thickness": req.thickness, "notes": req.customer_notes,
            "files": [{"name": f["name"], "kind": f["kind"], "removed": f.get("removed", False)} for f in req.files or []],
            "export_controlled": req.export_controlled, "result": req.public_result or {},
            "submitted": req.status != "draft", "created": req.created_at.date().isoformat() if req.created_at else ""}


def notify(req: PortalRequest, s: PortalSettings) -> str:
    """Email you about a submitted request. Raises when email is not set up."""
    from .cli import send_email

    r = req.public_result or {}
    price = (f"${r.get('unit_price'):,.2f} per unit, ${r.get('total'):,.2f} for {req.quantity}" if r.get("kind") == "instant"
             else f"${r.get('unit_low'):,.0f} to ${r.get('unit_high'):,.0f} per unit (estimate)" if r.get("kind") == "estimate" else "no price (manual review)")
    app_url = (os.getenv("APP_URL") or "").rstrip("/")
    body = (f"New quote request {req.ref} ({r.get('kind', 'manual')})\n\n"
            f"From: {req.contact_name} <{req.email}>{', ' + req.company if req.company else ''}{', ' + req.phone if req.phone else ''}\n"
            f"Quantity: {req.quantity}\nPrice shown: {price}\nNeeded by: {req.needed_by or 'not given'}\n"
            f"Files: {', '.join(f['name'] for f in req.files or []) or 'none'}\n"
            f"{'EXPORT-CONTROLLED: the customer flagged controlled data or a controlled drawing was deleted. Arrange a secure transfer.' if req.export_controlled else ''}\n\n"
            f"Notes: {req.customer_notes or 'none'}\n\nReview it: {app_url}/customer-requests?id={req.id}\n")
    return send_email(f"Quote request {req.ref}: {req.contact_name}", body, to=s.notify_email or None)


# ================================================================ internal
def internal_dict(req: PortalRequest, full: bool = False) -> dict:
    d = {"id": req.id, "ref": req.ref, "status": req.status, "kind": req.kind, "quantity": req.quantity, "contact_name": req.contact_name,
         "company": req.company, "email": req.email, "phone": req.phone, "needed_by": req.needed_by,
         "export_controlled": req.export_controlled, "created_at": req.created_at.isoformat() if req.created_at else None,
         "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None, "quote_ids": req.quote_ids or [],
         "public_result": req.public_result or {}, "files": req.files or []}
    if full:
        d.update(material=req.material, finish=req.finish, thickness=req.thickness, customer_notes=req.customer_notes,
                 internal=req.internal or {}, internal_notes=req.internal_notes, token=req.token)
    return d


def to_quotes(db: Session, req: PortalRequest) -> list[int]:
    """Save every priced item as an internal part quote (linked back to this request in its notes)."""
    ids = []
    for it in (req.internal or {}).get("items") or []:
        spec = it.get("spec")
        if not spec:
            continue
        spec = {**spec, "name": spec.get("name") or it["name"]}
        try:
            q = quotes.save_quote(db, spec, status="draft", quoted_quantity=req.quantity,
                                  notes=f"From customer request {req.ref} ({req.contact_name or 'not submitted'}{', ' + req.company if req.company else ''}).",
                                  created_by="portal")
            ids.append(q["id"])
        except (pricing.SpecError, ValueError):
            continue
    req.quote_ids = list(dict.fromkeys((req.quote_ids or []) + ids))
    db.commit()
    return ids


def delete_request(db: Session, req: PortalRequest) -> None:
    shutil.rmtree(req_dir(req), ignore_errors=True)
    db.delete(req)
    db.commit()


def tab_for(kind: str) -> str:
    return {"box_build": "box", "flat_dxf": "flat", "assembly": "instant"}.get(kind, "instant")


__all__ = ["PortalError", "PORTAL_STATUSES"]
