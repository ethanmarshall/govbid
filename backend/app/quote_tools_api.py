"""Quote tools API: live distributor pricing, customer quote documents, vendor RFQs and win/loss insights.

Routes use full paths so one router serves both /api/distributors/... and /api/quote-tools/...
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import distributors, quote_tools
from .db import get_db

router = APIRouter()


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except quote_tools.NotFound as exc:
        raise HTTPException(404, str(exc))
    except quote_tools.QuoteToolError as exc:
        raise HTTPException(400, str(exc))


# ---------------------------------------------------------------- distributors
class BomLine(BaseModel):
    mpn: str = ""
    manufacturer: str = ""
    qty: float = 1


class PriceBomIn(BaseModel):
    lines: list[BomLine] = Field(default_factory=list)
    quantities: list[int] | None = None


@router.get("/api/distributors/status")
def distributor_status():
    """Which distributor APIs have keys configured (environment variables)."""
    conf = distributors.configured()
    return {"configured": conf, "env": {"digikey": ["DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET"], "mouser": ["MOUSER_API_KEY"]},
            "cache_hours": distributors.CACHE_HOURS}


@router.post("/api/distributors/price-bom")
async def price_bom(body: PriceBomIn, db: Session = Depends(get_db)):
    """Live prices for a BOM. Returns {configured, results: [{mpn, best, offers, error?, by_quantity}]}."""
    if len(body.lines) > 500:
        raise HTTPException(400, "Price at most 500 lines at a time.")
    return await run_in_threadpool(distributors.price_bom, [ln.model_dump() for ln in body.lines], body.quantities, db=db)


@router.get("/api/distributors/search")
async def distributor_search(q: str = Query(""), db: Session = Depends(get_db)):
    """Offers for one manufacturer part number from every configured distributor."""
    return await run_in_threadpool(distributors.search, q, db=db)


# ---------------------------------------------------------------- customer quote settings
class SettingsIn(BaseModel):
    validity_days: int | None = None
    payment_terms: str | None = None
    fob: str | None = None
    shipping: str | None = None
    inspection_acceptance: str | None = None
    address: str | None = None
    footer_text: str | None = None


@router.get("/api/quote-tools/settings")
def get_settings(db: Session = Depends(get_db)):
    return quote_tools.settings_dict(quote_tools.get_settings(db))


@router.put("/api/quote-tools/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    return _guard(quote_tools.update_settings, db, body.model_dump(exclude_none=True))


# ---------------------------------------------------------------- win/loss insights (before /{quote_id} routes)
@router.get("/api/quote-tools/insights")
def get_insights(db: Session = Depends(get_db)):
    """Win rate, price against award and margins grouped by kind, process, material and FSC."""
    return quote_tools.insights(db)


# ---------------------------------------------------------------- RFQ records
class RfqUpdate(BaseModel):
    status: str | None = None
    due_date: str | None = None
    vendor_email: str | None = None


class PriceRow(BaseModel):
    quantity: int
    unit_price: float


class RfqResponseIn(BaseModel):
    prices: list[PriceRow] = Field(default_factory=list)
    lead_days: int | None = None
    tooling_charge: float | None = None
    freight: float | None = None
    quote_ref: str | None = None
    valid_until: str | None = None
    notes: str = ""


class DeclineIn(BaseModel):
    notes: str = ""


@router.get("/api/quote-tools/rfqs/{rfq_id}")
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    return _guard(lambda: quote_tools.rfq_dict(db, quote_tools._rfq(db, rfq_id)))


@router.put("/api/quote-tools/rfqs/{rfq_id}")
def put_rfq(rfq_id: int, body: RfqUpdate, db: Session = Depends(get_db)):
    return _guard(quote_tools.update_rfq, db, rfq_id, body.model_dump(exclude_none=True))


@router.delete("/api/quote-tools/rfqs/{rfq_id}")
def del_rfq(rfq_id: int, db: Session = Depends(get_db)):
    _guard(quote_tools.delete_rfq, db, rfq_id)
    return {"ok": True}


@router.post("/api/quote-tools/rfqs/{rfq_id}/response")
def rfq_response(rfq_id: int, body: RfqResponseIn, db: Session = Depends(get_db)):
    """Record the vendor's prices. Creates or updates a VendorQuote so make-or-buy compares it."""
    data = body.model_dump()
    data["prices"] = [p.model_dump() for p in body.prices]
    return _guard(quote_tools.record_response, db, rfq_id, data)


@router.post("/api/quote-tools/rfqs/{rfq_id}/decline")
def rfq_decline(rfq_id: int, body: DeclineIn, db: Session = Depends(get_db)):
    return _guard(quote_tools.decline_rfq, db, rfq_id, body.notes)


@router.get("/api/quote-tools/rfqs/{rfq_id}/mailto")
def rfq_mailto(rfq_id: int, db: Session = Depends(get_db)):
    r = _guard(lambda: quote_tools.rfq_dict(db, quote_tools._rfq(db, rfq_id)))
    return {"mailto": r["mailto"], "subject": r["subject"], "body": r["body"], "to": r["vendor_email"],
            "note": "A mailto link cannot attach files. Download the package and attach it to the email yourself."}


@router.get("/api/quote-tools/rfqs/{rfq_id}/package.zip")
def rfq_package(rfq_id: int, db: Session = Depends(get_db)):
    name, data = _guard(quote_tools.rfq_package, db, rfq_id)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- per saved quote
class CustomerQuoteIn(BaseModel):
    customer_name: str | None = None
    attn: str | None = None
    validity_days: int | None = None
    fob: str | None = None
    payment_terms: str | None = None
    shipping: str | None = None
    inspection_acceptance: str | None = None
    packaging: str | None = None
    quantities: list[int] | None = None
    notes: str | None = None


def _cq_opts(customer_name, attn, validity_days, fob, payment_terms, shipping, inspection_acceptance, packaging, quantities, notes) -> dict:
    return {"customer_name": customer_name, "attn": attn, "validity_days": validity_days, "fob": fob, "payment_terms": payment_terms,
            "shipping": shipping, "inspection_acceptance": inspection_acceptance, "packaging": packaging,
            "quantities": quantities, "notes": notes}


@router.get("/api/quote-tools/{quote_id}/customer-quote")
def customer_quote_preview(quote_id: int, db: Session = Depends(get_db)):
    """The customer quote as data (number, last-used options, lines) without changing the remembered options."""
    pq = _guard(quote_tools.get_quote, db, quote_id)
    avail = [b["quantity"] for b in (pq.result or {}).get("price_breaks") or []]
    d = _guard(quote_tools.customer_quote_data, db, quote_id, {"quantities": avail}, False)  # every line; options unchanged
    d["available_quantities"] = avail
    d["default_quantities"] = [pq.quoted_quantity] if pq.quoted_quantity in avail else avail  # the quantity being built
    d["settings"] = quote_tools.settings_dict(quote_tools.get_settings(db))
    return d


@router.put("/api/quote-tools/{quote_id}/customer-quote")
def customer_quote_save(quote_id: int, body: CustomerQuoteIn, db: Session = Depends(get_db)):
    """Remember the form values for this quote (the download links also remember them)."""
    return _guard(quote_tools.customer_quote_data, db, quote_id, body.model_dump(), True)


def _download_args(customer_name: str = "", attn: str = "", validity_days: int | None = None, fob: str = "", payment_terms: str = "",
                   shipping: str = "", inspection_acceptance: str = "", packaging: str = "", quantities: str = "", notes: str = "") -> dict:
    return _cq_opts(customer_name, attn, validity_days, fob, payment_terms, shipping, inspection_acceptance, packaging, quantities, notes)


@router.get("/api/quote-tools/{quote_id}/customer-quote.pdf")
def customer_quote_pdf(quote_id: int, opts: dict = Depends(_download_args), db: Session = Depends(get_db)):
    """PDF quotation for the customer. Query parameters override the saved defaults (quantities as 10,50,100)."""
    d = _guard(quote_tools.customer_quote_data, db, quote_id, opts, True)
    return Response(quote_tools.render_pdf(d), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{quote_tools._filename(d, "pdf")}"'})


@router.get("/api/quote-tools/{quote_id}/customer-quote.docx")
def customer_quote_docx(quote_id: int, opts: dict = Depends(_download_args), db: Session = Depends(get_db)):
    """Word quotation for the customer, same content as the PDF."""
    d = _guard(quote_tools.customer_quote_data, db, quote_id, opts, True)
    return Response(quote_tools.render_docx(d), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{quote_tools._filename(d, "docx")}"'})


class RfqIn(BaseModel):
    vendor_ids: list[int] = Field(default_factory=list)
    due_date: str = ""
    message: str = ""
    include_files: bool = True
    quantities: list[int] | None = None


@router.post("/api/quote-tools/{quote_id}/rfq")
def create_rfq(quote_id: int, body: RfqIn, db: Session = Depends(get_db)):
    """One RFQ per vendor with an email draft and a package. Files are held back for controlled technical data."""
    return _guard(quote_tools.create_rfqs, db, quote_id, body.vendor_ids, body.due_date, body.message, body.include_files, body.quantities)


@router.get("/api/quote-tools/{quote_id}/rfqs")
def list_rfqs(quote_id: int, db: Session = Depends(get_db)):
    _guard(quote_tools.get_quote, db, quote_id)
    return quote_tools.list_rfqs(db, quote_id)


@router.get("/api/quote-tools/{quote_id}/export-check")
def export_check(quote_id: int, db: Session = Depends(get_db)):
    """Whether the drawing or solicitation is export controlled or limited distribution (files would be held back)."""
    pq = _guard(quote_tools.get_quote, db, quote_id)
    return quote_tools.export_check(db, pq)


@router.get("/api/quote-tools/vendors")
def vendors(db: Session = Depends(get_db)):
    """Organizations of kind vendor with size, manufacturer status and an email contact, for the RFQ picker."""
    from .models_crm import Organization
    rows = db.query(Organization).filter(Organization.kind == "vendor").order_by(Organization.name).all()
    out = []
    for o in rows:
        contact, email = quote_tools._first_contact(o)
        out.append({"id": o.id, "name": o.name, "city": o.city, "state": o.state, "is_manufacturer": o.is_manufacturer,
                    "business_types": {k: v for k, v in (o.business_types or {}).items() if v}, "capabilities": o.capabilities,
                    "contact": contact, "email": email, "tags": o.tags or []})
    return out


# ---------------------------------------------------------------- calendar and dashboard hooks
def calendar_items(db: Session) -> list[dict]:
    """Vendor RFQ reply due dates (open RFQs only)."""
    return quote_tools.rfq_calendar_items(db)


def dashboard_items(db: Session) -> list[str]:
    """Vendor RFQs past their reply date."""
    return quote_tools.rfq_dashboard_items(db)
