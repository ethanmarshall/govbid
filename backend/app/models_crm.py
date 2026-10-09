"""Contacts, teaming partners, primes, vendors and the interaction log (shared by CRM, teaming and make-or-buy)."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ORG_KINDS = ["prime", "agency", "vendor", "teaming_partner", "apex_sbdc", "other"]
ORG_STAGES = ["identified", "contacted", "meeting", "registered_supplier", "active", "inactive"]
INTERACTION_KINDS = ["email", "call", "meeting", "event", "portal", "note"]


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="other")
    stage: Mapped[str] = mapped_column(String(30), default="identified")
    website: Mapped[str] = mapped_column(String(500), default="")
    supplier_portal: Mapped[str] = mapped_column(String(500), default="")
    uei: Mapped[str] = mapped_column(String(20), default="")
    cage: Mapped[str] = mapped_column(String(10), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(2), default="")
    naics_codes: Mapped[list] = mapped_column(JSON, default=list)
    capabilities: Mapped[str] = mapped_column(Text, default="")
    # small-business status as registered in SAM: {"SB": true, "SDVOSB": true, "WOSB": false, "8A": false, "HUBZone": false}
    business_types: Mapped[dict] = mapped_column(JSON, default=dict)
    is_manufacturer: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(30), default="manual")  # manual | sam_entity | seed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="organization", cascade="all, delete-orphan", order_by="Interaction.date.desc()")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    organization: Mapped[Organization] = relationship(back_populates="contacts")


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    kind: Mapped[str] = mapped_column(String(20), default="note")
    summary: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str] = mapped_column(Text, default="")
    follow_up_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD, blank = none
    done: Mapped[bool] = mapped_column(Boolean, default=False)

    organization: Mapped[Organization] = relationship(back_populates="interactions")


class VendorQuote(Base):
    """An outside shop's price for a part quote (make-or-buy)."""

    __tablename__ = "vendor_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    part_quote_id: Mapped[int] = mapped_column(ForeignKey("part_quotes.id", ondelete="CASCADE"))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    vendor_name: Mapped[str] = mapped_column(String(300), default="")  # kept even if the organization is deleted
    prices: Mapped[list] = mapped_column(JSON, default=list)  # [{"quantity": 10, "unit_price": 42.0}]
    tooling_charge: Mapped[float] = mapped_column(Float, default=0.0)
    freight: Mapped[float] = mapped_column(Float, default=0.0)
    lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_ref: Mapped[str] = mapped_column(String(120), default="")
    valid_until: Mapped[str] = mapped_column(String(10), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    organization: Mapped[Organization | None] = relationship()
