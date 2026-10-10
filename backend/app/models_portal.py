"""Customer quote portal: requests customers submit from the public /quote page, and the portal settings."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

PORTAL_STATUSES = ("draft", "submitted", "reviewing", "confirmed", "declined", "closed")


class PortalRequest(Base):
    """One customer project: their files and choices, our pricing (internal), and where it stands."""

    __tablename__ = "portal_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # RQ-2026-0001, shown to the customer
    token: Mapped[str] = mapped_column(String(64))  # secret in the customer's status link
    status: Mapped[str] = mapped_column(String(20), default="draft")
    kind: Mapped[str] = mapped_column(String(20), default="manual")  # instant | estimate | manual
    # customer choices
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    material: Mapped[str] = mapped_column(String(80), default="")
    finish: Mapped[str] = mapped_column(String(80), default="")
    thickness: Mapped[float | None] = mapped_column(Float, nullable=True)  # DXF parts
    customer_notes: Mapped[str] = mapped_column(Text, default="")
    files: Mapped[list] = mapped_column(JSON, default=list)  # [{name, stored, kind, size, removed}]
    export_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    # contact (given on submit)
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    company: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    needed_by: Mapped[str] = mapped_column(String(20), default="")
    # pricing: public is what the customer saw; internal keeps specs, costs and reasons for the review
    public_result: Mapped[dict] = mapped_column(JSON, default=dict)
    internal: Mapped[dict] = mapped_column(JSON, default=dict)
    internal_notes: Mapped[str] = mapped_column(Text, default="")
    line_opts: Mapped[dict] = mapped_column(JSON, default=dict)  # per line: {qty, material, finish, process, final_unit_price}
    quote_ids: Mapped[list] = mapped_column(JSON, default=list)  # internal PartQuotes made from this request
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # what the customer site says about you: about, capabilities, experience, industries, quality, faq (blank keys use the defaults)
    site: Mapped[dict] = mapped_column(JSON, default=dict)
    show_codes: Mapped[bool] = mapped_column(Boolean, default=True)  # UEI, CAGE, NAICS and held certifications on the page
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PortalSettings(Base):
    """Single row (id=1). The portal is off until you turn it on (after setting real shop rates)."""

    __tablename__ = "portal_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str] = mapped_column(String(160), default="")  # blank: the company profile name
    tagline: Mapped[str] = mapped_column(String(300), default="Machined, sheet metal and 3D printed parts, cable harnesses and electromechanical assemblies.")
    intro: Mapped[str] = mapped_column(Text, default="Upload your files for an instant quote. Complex builds get an estimate and a review by an engineer before we confirm the order.")
    contact_email: Mapped[str] = mapped_column(String(160), default="")
    contact_phone: Mapped[str] = mapped_column(String(40), default="")
    notify_email: Mapped[str] = mapped_column(String(160), default="")  # blank: DIGEST_TO
    estimate_low_pct: Mapped[float] = mapped_column(Float, default=10.0)  # complex builds: shown as a range around our estimate
    estimate_high_pct: Mapped[float] = mapped_column(Float, default=35.0)
    incomplete_high_pct: Mapped[float] = mapped_column(Float, default=75.0)  # when parts still need a manual price
    review_days: Mapped[int] = mapped_column(Integer, default=2)
    max_quantity: Mapped[int] = mapped_column(Integer, default=10000)
    terms: Mapped[str] = mapped_column(Text, default="Instant quotes are valid for 30 days and are confirmed by us before the order is placed. "
                                                    "Estimates are not offers: we confirm the scope and price with you first. "
                                                    "Do not upload export-controlled (ITAR/EAR) or classified technical data.")
    # what the customer site says about you: about, capabilities, experience, industries, quality, faq (blank keys use the defaults)
    site: Mapped[dict] = mapped_column(JSON, default=dict)
    show_codes: Mapped[bool] = mapped_column(Boolean, default=True)  # UEI, CAGE, NAICS and held certifications on the page
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
