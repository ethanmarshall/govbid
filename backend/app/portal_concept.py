"""Project concepts: customers with an idea but no drawings yet.

They describe what they want built, the goals, the must-haves they will not trade away, and the conditions it has
to work in; they can attach sketches, photos or reference documents. It arrives in Customer requests as a submitted
request of kind "concept" with its own ref, and the customer gets a status link like any other request.
Nothing is priced automatically: an engineer reads it and replies.
"""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime

from sqlalchemy.orm import Session

# Choices shown on the form. Kept here so the page and the server agree on them.
OPTIONS = {
    "stages": ["Just an idea", "Sketches or notes", "Something similar exists", "A prototype or partial CAD", "Drawings in progress"],
    "help": ["Engineering and design", "Drawings and 3D models", "A prototype", "Production", "Testing and certification",
             "Manuals and documentation", "Finding and buying parts"],
    "environments": ["Indoors", "Outdoors and weather", "Vehicle or heavy vibration", "Wet, washdown or marine", "Shipboard",
                     "High heat", "Extreme cold", "Dusty or dirty", "Field or military use"],
    "standards": ["MIL-STD-810 (environment)", "MIL-STD-461 (EMI)", "MIL-STD-1472 (human factors)", "UL listing", "CE marking",
                  "IP rating (water and dust)", "NEMA enclosure rating", "Buy American or DFARS materials", "RoHS"],
    "power": ["120 VAC", "240 VAC", "3-phase AC", "12 VDC", "24 VDC", "28 VDC (military vehicle)", "Battery powered", "No power needed",
              "Not sure"],
    "volumes": ["1 (one of a kind)", "2 to 10", "11 to 100", "101 to 1,000", "More than 1,000", "Not sure yet"],
    "budgets": ["Under $5,000", "$5,000 to $25,000", "$25,000 to $100,000", "$100,000 to $500,000", "Over $500,000", "Not sure yet"],
    "contact_methods": ["Email", "Phone call", "Video call"],
}
# Quick picks for the must-have list (customers can type their own too).
MUST_HAVE_HINTS = ["Fits within a size limit", "Weighs less than a limit", "Runs on the power we have", "Works in our temperature range",
                   "Meets a military or industry standard", "Connects to equipment we already have", "Safe for operators or students",
                   "Easy to maintain in the field", "Delivered by a fixed date", "Stays within a budget"]

TEXT = {"title": 120, "description": 4000, "goals": 3000, "users": 1000, "environment_notes": 1500, "standards_other": 500,
        "size_limits": 800, "interfaces": 1500, "quantity_annual": 120, "nice_to_haves": 3000, "contract_ref": 200, "end_customer": 200,
        "best_time": 120, "heard": 200, "notes": 3000, "budget_notes": 300}
CHOICE = {"stage": "stages", "quantity_first": "volumes", "budget": "budgets", "contact_method": "contact_methods"}
MULTI = {"help": "help", "environment": "environments", "standards": "standards", "power": "power"}
FLAGS = ("deadline_firm", "government", "nda")
SECTION_LABELS = {
    "title": "Project", "stage": "Where it stands", "description": "The idea", "goals": "Goals and what success looks like",
    "users": "Who uses it", "must_haves": "Must haves (not negotiable)", "nice_to_haves": "Nice to have", "environment": "Where it works",
    "environment_notes": "Conditions", "standards": "Standards", "standards_other": "Other standards", "power": "Power available",
    "size_limits": "Size and weight limits", "interfaces": "What it connects to", "quantity_first": "First order",
    "quantity_annual": "Later, per year", "budget": "Budget", "budget_notes": "Budget notes", "needed_by": "Needed by",
    "deadline_firm": "Deadline is firm", "help": "Help wanted", "government": "For a government contract", "contract_ref": "Contract or solicitation",
    "end_customer": "End customer", "nda": "Wants an NDA first", "contact_method": "Contact by", "best_time": "Best time", "heard": "Heard about us",
    "notes": "Anything else",
}


class ConceptError(ValueError):
    pass


def clean(data: dict) -> dict:
    """Validate and trim what the customer sent. Unknown keys are dropped; choices must be from OPTIONS."""
    out: dict = {}
    for k, n in TEXT.items():
        v = str(data.get(k) or "").strip()
        if v:
            out[k] = v[:n]
    for k, opt in CHOICE.items():
        v = str(data.get(k) or "").strip()
        if v in OPTIONS[opt]:
            out[k] = v
    for k, opt in MULTI.items():
        vals = data.get(k) or []
        if isinstance(vals, str):
            vals = [vals]
        vals = [v for v in vals if v in OPTIONS[opt]]
        if vals:
            out[k] = list(dict.fromkeys(vals))
    must = data.get("must_haves") or []
    if isinstance(must, str):
        must = [x for x in must.split("\n")]
    must = [str(x).strip()[:300] for x in must if str(x).strip()][:30]
    if must:
        out["must_haves"] = must
    for k in FLAGS:
        if data.get(k) in (True, "true", "on", "1", 1):
            out[k] = True
    nb = str(data.get("needed_by") or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", nb):
        out["needed_by"] = nb
    if not out.get("title") and not out.get("description"):
        raise ConceptError("Tell us about the project: give it a name or describe the idea.")
    if len(out.get("description", "")) < 20:
        raise ConceptError("Describe the idea in a sentence or two, so we know what you have in mind.")
    return out


def brief_lines(c: dict) -> list[tuple[str, str]]:
    """The concept as (label, text) pairs in a sensible reading order, for email, PDF and the review page."""
    rows = []
    for k in ("title", "stage", "description", "goals", "users", "must_haves", "nice_to_haves", "environment", "environment_notes",
              "standards", "standards_other", "power", "size_limits", "interfaces", "quantity_first", "quantity_annual", "budget",
              "budget_notes", "needed_by", "deadline_firm", "help", "government", "contract_ref", "end_customer", "nda",
              "contact_method", "best_time", "heard", "notes"):
        v = c.get(k)
        if v in (None, "", [], False):
            continue
        if isinstance(v, list):
            v = "\n".join(f"- {x}" for x in v) if k == "must_haves" else ", ".join(v)
        elif v is True:
            v = "Yes"
        rows.append((SECTION_LABELS.get(k, k), str(v)))
    return rows


def create(db: Session, data: dict, contact: dict, uploads: list[tuple[str, bytes]], ip: str):
    from . import portal
    from .models_portal import PortalRequest

    concept = clean(data)
    name = str(contact.get("name") or "").strip()[:120]
    email = str(contact.get("email") or "").strip()[:160]
    if not name:
        raise ConceptError("Enter your name.")
    if not portal.EMAIL_RX.match(email):
        raise ConceptError("Enter a valid email address so we can reply.")
    if not contact.get("accept_terms"):
        raise ConceptError("Please confirm the note about export-controlled data.")
    controlled = bool(contact.get("export_controlled"))
    s = portal.get_settings(db)
    portal.purge_stale(db)
    req = PortalRequest(ref=portal._new_ref(db), token=secrets.token_urlsafe(24), status="submitted", kind="concept",
                        ip_hash=portal.ip_hash(ip), export_controlled=controlled, quantity=1)
    req.contact_name, req.email = name, email
    req.company = str(contact.get("company") or "").strip()[:160]
    req.phone = re.sub(r"[^0-9+()\-. x]", "", str(contact.get("phone") or ""))[:40]
    req.needed_by = concept.get("needed_by", "")
    req.customer_notes = concept.get("notes", "")
    req.concept = concept
    req.submitted_at = datetime.utcnow()
    db.add(req)
    db.flush()
    try:
        if controlled:
            req.files = []
        else:
            portal.store_files(req, uploads)
    except Exception:
        db.rollback()
        raise
    days = f"{s.review_days} business day{'s' if s.review_days != 1 else ''}"
    req.public_result = {
        "kind": "concept", "quantity": 1, "items": [],
        "message": (f"Thanks. An engineer will read your project and reach out within {days} with questions, ideas and next steps. "
                    "Once we understand what you need, we will send a budget estimate, and a firm quote when the design is defined."
                    + (" We will send an NDA before you share details, as you asked." if concept.get("nda") else "")),
    }
    db.commit()
    return req


def public(req) -> dict:
    """The customer's own brief, without contact details, for their status page."""
    return {"concept": [{"label": a, "text": b} for a, b in brief_lines(req.concept or {})]}


__all__ = ["OPTIONS", "MUST_HAVE_HINTS", "ConceptError", "clean", "brief_lines", "create", "public", "date"]
