"""Shared logic for shop rates and saved part quotes, used by the REST API and the MCP server."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import pricing
from .models import QUOTE_STATUSES, Opportunity, PartQuote, PricingConfig


def get_overrides(db: Session) -> dict:
    row = db.get(PricingConfig, 1)
    return dict(row.overrides or {}) if row else {}


def get_config(db: Session) -> dict:
    return pricing.merged_config(get_overrides(db))


def update_config(db: Session, changes: dict, replace: bool = False) -> dict:
    """Merge `changes` into the saved overrides (or replace them) and return the full effective config."""
    row = db.get(PricingConfig, 1) or PricingConfig(id=1, overrides={})
    base = {} if replace else dict(row.overrides or {})

    def merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    merge(base, changes or {})
    merged = pricing.merged_config(base)
    _validate_numbers(merged)
    for name, m in merged["materials"].items():
        missing = [k for k in ("density", "price_per_lb", "machinability", "cut_factor") if k not in m]
        if missing:
            raise pricing.SpecError(f"Material '{name}' is missing {', '.join(missing)}")
    for name, f in merged["finishes"].items():
        missing = [k for k in ("per_part", "lot_min") if k not in f]
        if missing:
            raise pricing.SpecError(f"Finish '{name}' is missing {', '.join(missing)}")
    techs = merged["additive"]["technologies"]
    for name, m in merged["additive"]["materials"].items():
        missing = [k for k in ("tech", "price_per_cm3", "density") if k not in m]
        if missing:
            raise pricing.SpecError(f"3D print material '{name}' is missing {', '.join(missing)}")
        if m["tech"] not in techs:
            raise pricing.SpecError(f"3D print material '{name}' uses unknown technology '{m['tech']}'")
    for name, t in techs.items():
        if t.get("cm3_per_hour", 0) <= 0:
            raise pricing.SpecError(f"{name} cm3_per_hour must be above zero")
    try:
        pricing.estimate(pricing.EXAMPLE_SPEC, base)  # fail fast if the new rates break the model
    except (TypeError, KeyError, ZeroDivisionError) as exc:
        raise pricing.SpecError(f"Those rates break the estimate: {exc}")
    row.overrides = base
    db.add(row)
    db.commit()
    return pricing.merged_config(base)


def _validate_numbers(cfg: dict, path: str = "") -> None:
    """Every rate, hour, price and factor must be a non-negative number."""
    for k, v in cfg.items():
        here = f"{path}{k}"
        if isinstance(v, dict):
            _validate_numbers(v, here + ".")
        elif k in ("currency", "note", "label", "tech"):
            if not isinstance(v, str) or (k == "tech" and not v):
                raise pricing.SpecError(f"{here} must be text")
            continue
        elif k == "pricing_mode":  # extrusion builds
            if v not in ("cut_to_length", "stock"):
                raise pricing.SpecError(f"{here} must be cut_to_length or stock")
            continue
        elif k == "packs_build":
            if not isinstance(v, bool):
                raise pricing.SpecError(f"{here} must be true or false")
            continue
        elif k == "max_in":
            if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 for x in v)):
                raise pricing.SpecError(f"{here} must be three positive numbers (inches)")
            continue
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            raise pricing.SpecError(f"{here} must be a number, got {v!r}")
        elif v < 0:
            raise pricing.SpecError(f"{here} cannot be negative")


def reset_config(db: Session) -> dict:
    row = db.get(PricingConfig, 1)
    if row:
        row.overrides = {}
        db.commit()
    return pricing.merged_config({})


def run_estimate(db: Session, spec: dict) -> dict:
    return pricing.estimate(spec, get_overrides(db))


def price_spec(spec: dict, overrides: dict | None = None) -> dict:
    """Price any saved quote spec with the model for its kind. `overrides` are the saved shop-rate overrides
    (every model merges them onto the defaults). Used by save_quote and by box builds for linked quotes."""
    kind = spec.get("kind")
    if kind == "extrusion_build":  # T-slot builds price with their own model
        from .extrusion import estimate_spec
        return estimate_spec(spec, overrides)
    if kind in ("harness", "panel", "labels"):  # electrical quoters price with their own models
        from .electrical import estimate_spec as electrical_estimate
        return electrical_estimate(spec, overrides)
    if kind == "flat_dxf":  # DXF flat parts price with their own nesting and cut model
        from .flat import estimate_spec as flat_estimate
        return flat_estimate(spec, overrides)
    if kind == "assembly":  # STEP assemblies: each body priced from the model, plus joining
        from .assembly import estimate_spec as assembly_estimate
        return assembly_estimate(spec, overrides)
    if kind == "box_build":  # electromechanical assemblies: enclosure, PCBs, wiring, components, linked quotes
        from .box_build import estimate_spec as box_estimate
        return box_estimate(spec, overrides)
    return pricing.estimate(spec, overrides)


def quote_dict(q: PartQuote, full: bool = True) -> dict:
    d = {
        "id": q.id, "name": q.name, "nsn": q.nsn, "part_number": q.part_number, "status": q.status,
        "opportunity_id": q.opportunity_id,
        "opportunity_title": q.opportunity.title if q.opportunity else None,
        "solicitation_number": q.opportunity.solicitation_number if q.opportunity else None,
        "quoted_quantity": q.quoted_quantity, "quoted_unit_price": q.quoted_unit_price,
        "notes": q.notes, "created_by": q.created_by,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        "price_breaks": (q.result or {}).get("price_breaks", []),
        "cad_file": ((q.spec or {}).get("cad") or {}).get("filename"),
        "kind": (q.spec or {}).get("kind") or ("drawing" if (q.spec or {}).get("drawing") and not (q.spec or {}).get("cad") else "part"),
    }
    if full:
        d["spec"] = q.spec
        d["result"] = q.result
    return d


def save_quote(db: Session, spec: dict, *, opportunity_id: int | None = None, status: str = "draft",
               quoted_quantity: int | None = None, quoted_unit_price: float | None = None,
               notes: str = "", created_by: str = "web", quote_id: int | None = None) -> dict:
    if status not in QUOTE_STATUSES:
        raise pricing.SpecError(f"status must be one of {QUOTE_STATUSES}")
    if opportunity_id is not None and not db.get(Opportunity, opportunity_id):
        raise pricing.SpecError(f"Opportunity {opportunity_id} not found")
    result = price_spec(spec, get_overrides(db))
    cad_notes = (spec.get("cad") or {}).get("notes") or []
    if cad_notes:  # keep the geometry-based assumptions from an instant quote
        result["assumptions"] = list(cad_notes) + result["assumptions"]
    q = db.get(PartQuote, quote_id) if quote_id else None
    if quote_id and not q:
        raise pricing.SpecError(f"Quote {quote_id} not found")
    q = q or PartQuote(created_by=created_by)
    q.spec, q.result = spec, result
    q.name = spec.get("name") or q.name or "Untitled part"
    q.nsn, q.part_number = spec.get("nsn") or "", spec.get("part_number") or ""
    q.opportunity_id = opportunity_id if opportunity_id is not None else q.opportunity_id
    q.status, q.notes = status, notes or q.notes
    if quoted_quantity is not None:
        q.quoted_quantity = quoted_quantity
    if quoted_unit_price is not None:
        q.quoted_unit_price = quoted_unit_price
    elif q.quoted_quantity:
        row = next((b for b in result["price_breaks"] if b["quantity"] == q.quoted_quantity), None)
        if row:
            q.quoted_unit_price = row["unit_price"]
    db.add(q)
    db.commit()
    db.refresh(q)
    if q.status in ("won", "lost") and q.nsn and q.quoted_unit_price:
        try:  # keep the NSN price history current with your own outcomes
            from .nsn_history import record_quote_outcome
            record_quote_outcome(db, q)
        except Exception:  # noqa: BLE001  (history is a convenience; never block saving a quote)
            db.rollback()
    return quote_dict(q)


def list_quotes(db: Session, status: str = "", opportunity_id: int | None = None, q: str = "", limit: int = 50) -> list[dict]:
    stmt = select(PartQuote).order_by(PartQuote.updated_at.desc())
    if status:
        stmt = stmt.where(PartQuote.status == status)
    if opportunity_id:
        stmt = stmt.where(PartQuote.opportunity_id == opportunity_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(PartQuote.name.ilike(like) | PartQuote.nsn.ilike(like) | PartQuote.part_number.ilike(like))
    return [quote_dict(x, full=False) for x in db.scalars(stmt.limit(limit)).all()]


def get_quote(db: Session, quote_id: int) -> dict:
    q = db.get(PartQuote, quote_id)
    if not q:
        raise pricing.SpecError(f"Quote {quote_id} not found")
    return quote_dict(q)


def delete_quote(db: Session, quote_id: int) -> None:
    q = db.get(PartQuote, quote_id)
    if q:  # SQLite does not enforce the foreign keys, so remove or detach dependent rows here
        from .models_crm import VendorQuote
        from .models_jobs import Job
        from .models_quote_tools import CustomerQuoteDoc, VendorRFQ
        db.query(VendorQuote).filter(VendorQuote.part_quote_id == quote_id).delete()
        db.query(VendorRFQ).filter(VendorRFQ.part_quote_id == quote_id).delete()
        db.query(CustomerQuoteDoc).filter(CustomerQuoteDoc.part_quote_id == quote_id).delete()  # its number stays retired
        db.query(Job).filter(Job.part_quote_id == quote_id).update({Job.part_quote_id: None})
        db.delete(q)
        db.commit()
