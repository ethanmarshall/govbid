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

from . import checkout, isolate, portal_concept, portal_read, pricing, quotes
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
    "ref": (".png", ".jpg", ".jpeg", ".heic", ".webp", ".gif", ".txt", ".docx", ".doc", ".pptx", ".mp4", ".mov"),
}
ACCEPT = ",".join(e for v in KINDS.values() for e in v)
PROCESS_LABEL = {"cnc_mill": "CNC machined", "cnc_lathe": "CNC turned", "sheet_metal": "Sheet metal", "3d_print": "3D printed",
                 "laser_cut": "Laser cut", "waterjet": "Waterjet cut", "plasma": "Plasma cut", "router": "Router cut"}
STATUS_LABEL = {"draft": "Quote not submitted", "submitted": "Submitted, waiting for review", "reviewing": "In review",
                "confirmed": "Confirmed", "ordered": "Ordered", "in_production": "In production", "shipped": "Shipped",
                "declined": "Declined", "closed": "Closed"}


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
                   "estimate_high_pct", "incomplete_high_pct", "review_days", "max_quantity", "terms", "show_codes",
                   "pay_instructions", "agreement_template")

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
        {"q": "How do I pay?", "a": "Quotes with a firm price can be ordered online by card or purchase order. Card payments go through Stripe, so your card number never reaches us. For jobs that need a review, we agree on payment terms when we confirm the order. Purchase orders are welcome."},
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
    from sqlalchemy.orm import object_session

    from .finance_api import get_settings as finance_settings

    db = object_session(s)
    remit = (finance_settings(db).remit_to or "") if db is not None else ""
    from .agreement import DEFAULT_TEMPLATE, PLACEHOLDERS

    return {**{k: getattr(s, k) for k in SETTINGS_FIELDS}, "remit_to": remit, "site": site_content(s), "site_defaults": DEFAULT_SITE,
            "agreement_default": DEFAULT_TEMPLATE, "agreement_placeholders": PLACEHOLDERS}


def update_settings(db: Session, changes: dict) -> dict:
    s = get_settings(db)
    for k, v in (changes or {}).items():
        if k == "site" and v is not None:
            s.site = {**(s.site or {}), **_clean_site(v)}
            continue
        if k == "remit_to" and v is not None:  # the address printed on invoices (shared with Invoices and finance)
            from .finance_api import get_settings as finance_settings

            finance_settings(db).remit_to = str(v)[:600]
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
        elif k == "agreement_template":
            v = str(v)[:20000]
            if v.strip():
                try:
                    from .agreement import _Safe

                    v.format_map(_Safe())
                except (ValueError, IndexError) as exc:
                    raise PortalError("The order agreement has a stray { or }. Use them only around placeholders like {buyer}.") from exc
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

    return {"enabled": s.enabled, "name": s.display_name or (prof.name if prof else "") or "Valley Power Systems LLC",
            "tagline": s.tagline, "intro": s.intro, "contact_email": s.contact_email, "contact_phone": s.contact_phone,
            "terms": s.terms, "review_days": s.review_days, "max_quantity": s.max_quantity,
            "materials": sorted(cfg["materials"]), "print_materials": sorted(cfg["additive"]["materials"]),
            "sheet_materials": sorted(flat_materials(cfg)), "finishes": sorted(cfg["finishes"]),
            "accept": ACCEPT, "max_files": MAX_FILES, "max_file_mb": MAX_FILE // (1024 * 1024), "keep_days": DRAFT_DAYS,
            "site": site_content(s), "company": _company_codes(prof) if s.show_codes else None,
            "concept_options": portal_concept.OPTIONS, "must_have_hints": portal_concept.MUST_HAVE_HINTS,
            "checkout_methods": checkout.methods()}


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
SIGN_LIMIT = Limiter(per_ip=20, per_all=300, window_s=3600)  # signing the order agreement (typos happen)


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


def build_lazy_view(req: PortalRequest, key: str) -> dict | None:
    """Parts of an assembly get their drawing when someone first looks at it (small part files only)."""
    from . import cad, cad_quote
    from . import portal_views as pv

    if not re.fullmatch(r"[0-9a-f]{20}", key or ""):
        return None
    src = next(((it.get("view") or {}).get("src") for it in (req.public_result or {}).get("items") or []
                if (it.get("view") or {}).get("key") == key), None)
    if not src or not re.fullmatch(r"[0-9a-f]{8,64}", src):
        return None
    p = cad_quote.CAD_DIR / f"{src}.step"
    if not p.exists() or p.stat().st_size > isolate.BIG_FILE:
        return None
    try:
        sheet = pv.build_sheet(cad.load_step(p), kind="model")
    except Exception:  # noqa: BLE001
        return None
    pv.save(req_dir(req) / "views", key, sheet)
    return sheet


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
    """Price the request line by line from its stored files and options (see portal_lines.py).
    Fills req.kind, req.public_result (what the customer sees) and req.internal (costs, margins, specs)."""
    from . import box_build, cad, cad_quote, drawing_assembly, drawing_quote, pcb_files
    from . import portal_lines as PL
    from . import portal_views as pv

    if req.kind == "concept":  # an idea, read by an engineer: nothing to price automatically
        return
    s = get_settings(db)
    cfg = quotes.get_config(db)
    over = quotes.get_overrides(db)
    req.quantity = max(1, min(int(req.quantity or 1), s.max_quantity))
    n = req.quantity
    lines: list[dict] = []

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
    ctx = PL.Ctx(db, req, s, cfg, over)
    drawing_mat = next((r["read"]["material"]["mapped"] for r in reads if r["read"] and (r["read"].get("material") or {}).get("mapped")), None)
    drawing_fin = [x["mapped"] for r in reads if r["read"] for x in (r["read"].get("finishes") or []) if x.get("mapped")]
    steps = [f for f in req.files if f["kind"] == "step" and not f["removed"]]
    dxfs = [f for f in req.files if f["kind"] == "dxf" and not f["removed"]]
    pcbs = [f for f in req.files if f["kind"] == "pcb" and not f["removed"]]
    refs = [f for f in req.files if f["kind"] == "ref" and not f["removed"]]
    pairs, loose_reads = PL.pair_drawings(steps, reads)

    # ---- STEP models
    for f in steps:
        name = Path(f["name"]).stem
        key = f["stored"]
        if f.get("size", 0) > isolate.BIG_FILE:  # big model: read in the background, the page updates when it is done
            st = _prep_state(req, f)
            if st.get("status") == "failed":
                lines.append(PL.new_line(key, name, "part", "manual", desc="3D model", qty=ctx.qty(key, 1),
                                         public_reason="Your model is too large or detailed to read automatically, so an engineer will price it.",
                                         internal_reasons=[st.get("error", "")]))
                continue
            if st.get("status") != "done":
                lines.append(PL.new_line(key, name, "part", "processing", desc="3D model", qty=ctx.qty(key, 1),
                                         public_reason="Your model is large, so we are reading it now. This page updates on its own when it is ready, "
                                                       "usually within a few minutes. You can also save the link and come back."))
                continue
        try:
            stored = cad_quote.store_upload(file_path(req, f).read_bytes(), f["name"])
        except (cad.CadError, Exception) as exc:  # noqa: BLE001
            lines.append(PL.new_line(key, name, "part", "manual", desc="3D model", qty=ctx.qty(key, 1),
                                     public_reason="We could not read this model automatically.", internal_reasons=[str(exc)]))
            continue
        geom = stored.get("geometry") or {}
        solids = geom.get("solids", 1) or 1
        paired = pairs.get(key)
        pread = (paired or {}).get("read") or {}
        pmat = (pread.get("material") or {}).get("mapped")
        mat, _is_print = _material(req, cfg, pmat or drawing_mat)
        msrc = _mat_source(req, cfg, mat, pmat or drawing_mat)
        pfin = [x["mapped"] for x in (pread.get("finishes") or []) if x.get("mapped")] if paired else drawing_fin
        fins = _finishes(req, cfg, _is_print, pfin)
        defaults = {"material": mat, "material_source": msrc, "finishes": fins, "finish_source": _fin_source(req, fins)}
        step_path = file_path(req, f)
        big = f.get("size", 0) > isolate.BIG_FILE
        vkey = pv.cache_key(stored["file_id"], "model", 2)
        view = None if big and pv.load(req_dir(req) / "views", vkey) is None \
            else _view(req, (stored["file_id"],), lambda p=step_path: cad.load_step(p), "model")

        if solids == 1:
            lines.append(PL.part_line(ctx, key, stored["file_id"], name, defaults=defaults, paired=paired, geometry=geom, view=view))
            continue

        # an assembly: one line per part (identical bodies grouped), bought parts, and the assembly itself
        if _prep_state(req, f).get("split_error"):
            bb = geom.get("bounding_box") or {}
            facts = [portal_read.row("Overall size", portal_read._size(bb.get("length"), bb.get("width"), bb.get("height"))),
                     portal_read.row("Parts in the model", solids)]
            lines.append(PL.new_line(key, name, "assembly", "manual", desc=f"Assembly ({solids} parts)", qty=ctx.qty(key, 1), view=view, facts=facts,
                                     public_reason=f"Your model has {solids} separate parts and is very large, so an engineer will price it.",
                                     internal_reasons=[_prep_state(req, f)["split_error"]]))
            continue
        try:
            from .assembly import split

            sp = split(stored["file_id"])
        except Exception as exc:  # noqa: BLE001
            lines.append(PL.new_line(key, name, "assembly", "manual", desc=f"Assembly ({solids} parts)", qty=ctx.qty(key, 1), view=view,
                                     public_reason=f"Your model has {solids} separate parts; we will price it by hand.", internal_reasons=[str(exc)]))
            continue
        from .assembly import is_bought

        for g in sp["groups"]:  # decided now, not from the cache, so naming rules can improve
            g["bought"] = all(is_bought(x) for x in (g.get("raw_names") or [g["name"]]))
        made = [g for g in sp["groups"] if not g.get("bought")] or sp["groups"]
        bought = [g for g in sp["groups"] if g.get("bought") and g not in made]
        totals: dict[str, int] = {}
        for g in made + bought:
            totals[g["name"]] = totals.get(g["name"], 0) + 1
        seen: dict[str, int] = {}
        for g in made + bought:  # several bodies of one named part: "guide vanes, piece 2"
            base = g["name"]
            if totals[base] > 1:
                seen[base] = seen.get(base, 0) + 1
                g["name"] = f"{base}, piece {seen[base]}"
        for g in made:
            gkey = f"{key}#g{g['group']}"
            gview = {"key": pv.cache_key(g["file_id"], "model", 2), "kind": "model", "note": VIEW_NOTES["model"], "src": g["file_id"]}
            lines.append(PL.part_line(ctx, gkey, g["file_id"], g["name"], group=name, qty_per=int(g.get("qty", 1)), defaults=defaults,
                                      paired=paired, view=gview, raw_names=g.get("raw_names")))
        for g in bought:
            lines.append(PL.bought_line(ctx, f"{key}#g{g['group']}", g["name"], g.get("raw_names") or [g["name"]], int(g.get("qty", 1)), name))
        afacts = portal_read.step_assembly(geom, made, mat, msrc, bought=bought)
        afacts = [r for r in afacts if not r["label"][:1].isdigit()]  # the part rows are lines of their own now
        lines.append(PL.assembly_line(ctx, f"{key}#asm", name, made, bought, geom, view, afacts))

    # ---- drawings with no model
    for rd in loose_reads:
        f, read = rd["file"], rd["read"]
        name = Path(f["name"]).stem
        key = f["stored"]
        qty = ctx.qty(key, 1)
        o_line = ctx.opt(key)
        if not read or not read.get("text_found", True):
            lines.append(PL.new_line(key, name, "drawing", "manual", desc="Drawing", qty=qty, public_reason="We will read this drawing by hand."))
            continue
        path = file_path(req, f)
        try:
            asm = drawing_assembly.analyze(path, read)
        except Exception:  # noqa: BLE001
            asm = None
        if asm:
            bb = asm["box_build"]
            spec = {**{k: v for k, v in bb.items() if k not in ("evidence", "assumptions", "fabricated")}, "kind": "box_build", "quantities": [qty]}
            enc = bb.get("enclosure") or {}
            view = None
            if enc.get("length_in") and enc.get("width_in"):
                dimsv = (enc["length_in"], enc["width_in"], enc.get("height_in") or 1)
                view = _view(req, ("env",) + tuple(dimsv), lambda d=dimsv: pv.box_shape(*d), "envelope")
            try:
                r = box_build.price(spec, over)
                lines.append(_item_line(ctx, key, _item(bb.get("name") or name, "estimate", "Assembly from your drawing", r["price_breaks"], qty,
                                                        kind="box_build", spec=spec, view=view, facts=portal_read.box_build(bb),
                                                        public_reason="Your drawing is an assembly with custom parts, so an engineer will confirm the build.",
                                                        internal_reasons=[i["item"] + ": " + i["reason"] for i in r.get("incomplete", [])][:8],
                                                        incomplete=bool(r.get("incomplete"))), qty, "box_build"))
            except Exception as exc:  # noqa: BLE001
                lines.append(PL.new_line(key, name, "box_build", "manual", desc="Assembly drawing", qty=qty, view=view,
                                         public_reason="Your drawing is an assembly; we will price it by hand.", internal_reasons=[str(exc)]))
            continue
        from . import drawing as drawing_mod

        text, _ = drawing_mod.extract_pdf_text(path)
        geom = drawing_quote.extract_geometry(read, text)
        o = {"quantities": [qty]}
        lm = o_line.get("material") or req.material
        if lm in cfg["materials"]:
            o["material"] = lm
        lf = o_line.get("finish") if o_line.get("finish") not in (None, "") else req.finish
        if lf and lf in cfg["finishes"]:
            o["finishes"] = [lf]
        try:
            r = drawing_quote.quote(read, geom, o, over)
        except (pricing.SpecError, ValueError) as exc:
            lines.append(PL.new_line(key, name, "drawing", "manual", desc="Drawing", qty=qty, public_reason="We will read this drawing by hand.",
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
        ln = _item_line(ctx, key, _item(name, route, f"{plabel}, {dmat} (from your drawing)", r["estimate"]["price_breaks"], qty, kind="part",
                                        spec=r["spec"], facts=facts, view=view,
                                        public_reason="Some sizes on your drawing need to be confirmed by an engineer." if route == "estimate" else "",
                                        internal_reasons=rv["reasons"] + r["estimate"].get("warnings", [])[:4]), qty, "drawing")
        ln.update(material=dmat, process=r["spec"]["process"], process_label=plabel,
                  editable={"qty": True, "material": True, "finish": True, "process": False})
        lines.append(ln)

    # ---- DXF flat parts
    if dxfs:
        lines += PL.flat_lines(ctx, dxfs, {}, drawing_mat)

    # ---- circuit boards
    if pcbs:
        key = "pcb"
        qty = ctx.qty(key, 1)
        try:
            got = pcb_files.parse_files([(f["name"], file_path(req, f).read_bytes()) for f in pcbs])
            board = box_build.blank_pcb(name="Circuit board", **got["board"])
            board["bom_lines"] = got["bom_lines"]
            spec = {"kind": "box_build", "name": "Circuit board assembly", "quantities": [qty], "enclosure": {"source": "none"}, "pcbs": [board]}
            r = box_build.price(spec, over)
            view = None
            if board.get("width_in") and board.get("height_in"):
                dimsv = (board["width_in"], board["height_in"], board.get("thickness_in") or 0.062)
                view = _view(req, ("pcb",) + tuple(dimsv), lambda d=dimsv: pv.box_shape(*d), "envelope")
            lines.append(_item_line(ctx, key, _item("Circuit board assembly", "estimate", f"{board['layers']} layer board" + (
                f", {board['width_in']:g} x {board['height_in']:g} in" if board.get("width_in") else ""), r["price_breaks"], qty, kind="box_build",
                spec=spec, public_reason="Circuit boards are always reviewed by an engineer before we confirm.",
                internal_reasons=got["warnings"] + r.get("warnings", [])[:4],
                facts=portal_read.pcb(got["board"], got.get("found") or {}, len(got.get("bom_lines") or [])), view=view), qty, "pcb"))
        except Exception as exc:  # noqa: BLE001
            lines.append(PL.new_line(key, "Circuit board files", "pcb", "manual", desc="Circuit board", qty=qty,
                                     public_reason="We will review your board files by hand.", internal_reasons=[str(exc)]))

    if refs and not lines:
        lines.append(PL.new_line("refs", "Reference files", "ref", "manual", desc="Images or documents", qty=n,
                                 public_reason="We will review the files you sent."))
    if not req.files and not lines:
        _finish(req, s, [], manual_reason="Tell us about the project in the notes and send your contact details; we will get back to you.")
        return
    _finish(req, s, lines)


def _item_line(ctx, key: str, it: dict, qty: int, process: str) -> dict:
    """An older-style priced item as a line (drawings, boards): calibrated, with the customer's final price applied."""
    from . import portal_lines as PL

    raw = it.get("unit_price")
    price, f, why = (PL._price_calibrated(ctx.fs, process, raw) if raw is not None else (None, 1.0, ""))
    ln = PL.new_line(key, it["name"], it["kind"], it["route"], qty=qty, desc=it["desc"], raw_unit_price=raw, unit_price=price,
                     unit_cost=it.get("unit_cost"), margin_pct=round((price - it["unit_cost"]) / price * 100, 1) if price and it.get("unit_cost") else None,
                     lead_days=it.get("lead_days"), calibration={"factor": f, "why": why, "process": process} if f != 1 else None,
                     facts=it.get("facts") or [], view=it.get("view"), public_reason=it.get("public_reason") or "",
                     internal_reasons=it.get("internal_reasons") or [], spec=it.get("spec"), incomplete=bool(it.get("incomplete")))
    return PL.apply_final(ctx, ln)


def _round_est(v: float) -> float:
    if v >= 1000:
        return float(round(v / 10) * 10)
    if v >= 100:
        return float(round(v))
    return round(v, 2)


def _finish(req: PortalRequest, s: PortalSettings, lines: list[dict], manual_reason: str = "") -> None:
    """Totals and the customer's view from the priced lines. A line's estimate range uses the portal settings;
    lines priced by an engineer (manual) or waiting (processing, needs_input) carry no price."""
    n = req.quantity
    routes = {ln["route"] for ln in lines}
    priced = [ln for ln in lines if ln.get("unit_price") is not None and ln["route"] in ("instant", "estimate")]
    if manual_reason or not lines:
        kind = "manual"
    elif "processing" in routes:
        kind = "processing"
    elif "needs_input" in routes:
        kind = "needs_input"
    elif not priced:
        kind = "manual"
    elif routes - {"instant"}:
        kind = "estimate"
    else:
        kind = "instant"
    low = high = exact = 0.0
    pub = []
    for ln in lines:
        row = {k: ln.get(k) for k in ("key", "name", "group", "kind", "route", "qty", "qty_per", "material", "finish", "process", "process_label",
                                       "desc", "facts", "view", "lead_days")}
        row["note"] = ln.get("public_reason") or ""
        row["editable"] = ln.get("editable") or {}
        row["options"] = {"processes": [{k: x.get(k) for k in ("process", "material", "label", "unit_price", "note")}
                                        for x in ((ln.get("options") or {}).get("processes") or [])]}
        row["confirmed"] = ln.get("final_unit_price") is not None
        u = ln.get("unit_price")
        q = int(ln.get("qty") or 1)
        if u is not None and ln["route"] == "estimate":
            hi_pct = s.incomplete_high_pct if ln.get("incomplete") else s.estimate_high_pct
            lo_u, hi_u = u * (1 - s.estimate_low_pct / 100), u * (1 + hi_pct / 100)
            row.update(unit_low=_round_est(lo_u), unit_high=_round_est(hi_u), total_low=_round_est(lo_u * q), total_high=_round_est(hi_u * q))
            low += lo_u * q
            high += hi_u * q
        elif u is not None and ln["route"] == "instant":
            row.update(unit_price=round(u, 2), total=round(u * q, 2))
            low += u * q
            high += u * q
            exact += u * q
        pub.append(row)
    lead = max([ln.get("lead_days") or 0 for ln in priced] or [0])
    unpriced = [ln for ln in lines if ln["route"] == "manual"]
    out = {"kind": kind, "quantity": n, "items": pub, "lines": len(pub), "review_days": s.review_days, "lead_days": None,
           "unpriced_lines": len(unpriced)}
    days = f"{s.review_days} business day{'s' if s.review_days != 1 else ''}"
    if kind == "instant":
        out.update(total=round(exact, 2), unit_price=round(exact / n, 2), lead_days=int(lead),
                   message="This price is firm. Order it here, or send it for review if you want an engineer to check it first.")
    elif kind == "estimate":
        out.update(total_low=_round_est(low), total_high=_round_est(high), unit_low=_round_est(low / n), unit_high=_round_est(high / n),
                   lead_days=int(lead + s.review_days),
                   message=("This is a complex build, so this is an estimate. " if not unpriced else
                            f"{len(unpriced)} line{'s' if len(unpriced) != 1 else ''} will be priced by an engineer, so this is an estimate for the rest. ")
                           + f"An engineer will review your files and reach out within {days} to confirm your project needs and the final cost "
                             "before we complete the order.")
    elif kind == "needs_input":
        out.update(message="Almost there: answer the question below to see your price.")
    elif kind == "processing":
        out.update(message="Your model is large, so we are reading it now. This page updates on its own when the price is ready, "
                           "usually within a few minutes. You can save the link and come back.")
    else:
        out.update(message=manual_reason or "We need to look at this one by hand. Submit it with your contact details and an engineer will "
                                            f"reach out within {days} with a price.")
    req.kind = kind
    req.public_result = out
    req.internal = {"priced_at": datetime.utcnow().isoformat(timespec="seconds"), "total": round(low, 2),
                    "items": [dict(ln) for ln in lines]}


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


def reset_big(req: PortalRequest) -> None:
    """Read big models again from the start (after a fix, or on a bigger server)."""
    shutil.rmtree(req_dir(req) / "prep", ignore_errors=True)


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
    if data.get("lines"):
        req.line_opts = merge_line_opts(req.line_opts or {}, data["lines"], max_qty)


LINE_PROCESSES = {"cnc_mill", "cnc_lathe", "sheet_metal", "3d_print"}


def merge_line_opts(current: dict, changes: dict, max_qty: int, internal: bool = False) -> dict:
    """Validate and merge per-line choices {line key: {qty, material, finish, process, process_material}}.
    internal adds final_unit_price (your price in review). A value of null removes that choice."""
    if not isinstance(changes, dict) or len(changes) > 300:
        raise PortalError("Line options are not valid.")
    out = {k: dict(v) for k, v in (current or {}).items()}
    for key, ch in changes.items():
        key = str(key)[:120]
        if not isinstance(ch, dict):
            continue
        cur = out.get(key, {})
        for k, v in ch.items():
            if v is None or v == "":
                cur.pop(k, None)
                continue
            if k == "qty":
                try:
                    v = int(float(v))
                except (TypeError, ValueError):
                    raise PortalError("Quantity must be a whole number.")
                if not 1 <= v <= max_qty:
                    raise PortalError(f"Quantity must be between 1 and {max_qty:,}.")
            elif k in ("material", "finish", "process_material"):
                v = str(v)[:80]
            elif k == "process":
                if v not in LINE_PROCESSES:
                    raise PortalError("Unknown process.")
            elif k == "thickness":
                v = float(v)
                if not 0.005 <= v <= 6:
                    raise PortalError("Thickness must be between 0.005 and 6 inches.")
            elif k == "final_unit_price" and internal:
                v = round(float(v), 2)
                if v <= 0:
                    raise PortalError("The price must be above zero.")
            else:
                continue
            cur[k] = v
        if cur:
            out[key] = cur
        else:
            out.pop(key, None)
    return out


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
    if (req.order or {}).get("status") == "awaiting_payment":
        checkout.retire_session(req)  # changed after starting a card payment: close that page and start checkout again
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
            "submitted": req.status != "draft", "created": req.created_at.date().isoformat() if req.created_at else "",
            **(portal_concept.public(req) if req.kind == "concept" else {}),
            "order": checkout.public_order(req), "checkout": _checkout_state(req)}


def _checkout_state(req: PortalRequest) -> dict:
    ok, why = checkout.eligible(req)
    return {"eligible": ok, "why": why, "methods": checkout.methods()}


def notify(req: PortalRequest, s: PortalSettings) -> str:
    """Email you about a submitted request. Raises when email is not set up."""
    from .cli import send_email

    r = req.public_result or {}
    app_url = (os.getenv("APP_URL") or "").rstrip("/")
    o = req.order or {}
    if o.get("status") in ("paid", "po_received", "invoiced", "invoice_due"):
        lines = "\n".join(f"  {l['qty']} x {l['name']}{' (' + l['group'] + ')' if l['group'] else ''}: ${l['unit_price']:,.2f} each, ${l['total']:,.2f}"
                          for l in o.get("lines") or [])
        a = o.get("ship_to") or {}
        body = (f"New ORDER {req.ref}: ${o.get('amount', 0):,.2f}, "
                f"{_how_paid(o)}\n\n"
                f"From: {req.contact_name} <{req.email}>{', ' + req.company if req.company else ''}{', ' + req.phone if req.phone else ''}\n"
                f"Ship to: {a.get('name', '')}, {a.get('company', '')} {a.get('line1', '')} {a.get('line2', '')}, {a.get('city', '')}, {a.get('state', '')} {a.get('zip', '')}\n"
                f"Needed by: {req.needed_by or 'not given'}\nBilling email: {o.get('billing_email') or req.email}\n\n{lines}\n\n"
                f"Notes: {o.get('notes') or 'none'}\n\nOpen it: {app_url}/customer-requests?id={req.id}\n")
        return send_email(f"Order {req.ref}: ${o.get('amount', 0):,.2f} from {req.contact_name}", body, to=s.notify_email or None)
    if req.kind == "concept":
        brief = "\n\n".join(f"{a}:\n{b}" for a, b in portal_concept.brief_lines(req.concept or {}))
        body = (f"New project idea {req.ref}\n\nFrom: {req.contact_name} <{req.email}>{', ' + req.company if req.company else ''}"
                f"{', ' + req.phone if req.phone else ''}\nFiles: {', '.join(f['name'] for f in req.files or []) or 'none'}\n"
                f"{'EXPORT-CONTROLLED: they said the project involves controlled data. Arrange a secure transfer.' if req.export_controlled else ''}\n\n"
                f"{brief}\n\nReview it: {app_url}/customer-requests?id={req.id}\n")
        return send_email(f"Project idea {req.ref}: {(req.concept or {}).get('title') or req.contact_name}", body, to=s.notify_email or None)
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
         "public_result": req.public_result or {}, "files": req.files or [],
         "concept_title": (req.concept or {}).get("title", "") if req.kind == "concept" else "",
         "order": req.order or {}, "customer_id": req.customer_id}
    if full:
        d.update(material=req.material, finish=req.finish, thickness=req.thickness, customer_notes=req.customer_notes,
                 internal=req.internal or {}, internal_notes=req.internal_notes, token=req.token, line_opts=req.line_opts or {},
                 concept=[{"label": a, "text": b} for a, b in portal_concept.brief_lines(req.concept or {})] if req.kind == "concept" else [])
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
            q = quotes.save_quote(db, spec, status="draft", quoted_quantity=int(it.get("qty") or req.quantity),
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


def _how_paid(o: dict) -> str:
    po = f", PO {o['po_number']}" if o.get("po_number") else ""
    if o.get("status") == "paid":
        return f"PAID{' online' if o.get('paid_online') or o.get('method') == 'card' else ''}{po}"
    if o.get("status") == "invoiced":
        return f"invoice {o.get('invoice_number', '')}, net {o.get('terms_days')}, due {o.get('due_date', '')}{po}: start the work"
    if o.get("status") == "invoice_due":
        return f"invoice {o.get('invoice_number', '')} due on receipt{po}: start when it is paid"
    return f"purchase order {o.get('po_number') or ''}"


def confirm_to_customer(req: PortalRequest, s: PortalSettings, status_url: str) -> None:
    """A short, fixed-text order confirmation to the customer's own address (only when email is set up)."""
    from .cli import send_email

    o = req.order or {}
    if o.get("status") == "awaiting_signature":
        body = (f"Thank you for your order {req.ref} (${o.get('amount', 0):,.2f}).\n\nBefore we start, please read and sign the order agreement. "
                f"It takes a minute, online:\n{status_url}\n\nWe send the invoice and start your order once it is signed.\n\n"
                f"{s.display_name or ''}\n{s.contact_email or ''} {s.contact_phone or ''}\n")
        send_email(f"Please sign the order agreement for {req.ref}", body, to=req.email, allow_customer=True)
        return
    how = ("Your payment was received." if o.get("status") == "paid"
           else f"Invoice {o.get('invoice_number', '')} is attached to your order page. Terms: net {o.get('terms_days')}, due {o.get('due_date', '')}."
           if o.get("status") == "invoiced"
           else f"Invoice {o.get('invoice_number', '')} is on your order page. It is due on receipt, and we start your order when it is paid."
           if o.get("status") == "invoice_due" else f"We received your purchase order {o.get('po_number', '')}.")
    body = (f"Thank you for your order {req.ref}.\n\n{how} Total: ${o.get('amount', 0):,.2f}.\n\n"
            "We will confirm the delivery date with you shortly. You can check your order here:\n"
            f"{status_url}\n\n{s.display_name or ''}\n{s.contact_email or ''} {s.contact_phone or ''}\n")
    send_email(f"Order {req.ref} received", body, to=req.email, allow_customer=True)
