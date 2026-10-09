"""Tables for quote tools: distributor price cache, customer quote numbers and settings, vendor RFQs."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

RFQ_STATUSES = ["sent", "awaiting", "responded", "declined"]


class DistributorCache(Base):
    """Normalized offers from one distributor for one manufacturer part number, kept for 24 hours."""

    __tablename__ = "distributor_cache"
    __table_args__ = (UniqueConstraint("distributor", "mpn_key", name="uq_distributor_mpn"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    distributor: Mapped[str] = mapped_column(String(20))  # digikey | mouser
    mpn_key: Mapped[str] = mapped_column(String(120), index=True)  # upper-cased MPN
    offers: Mapped[list] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuoteToolSettings(Base):
    """Single row (id=1): defaults for customer quote documents."""

    __tablename__ = "quote_tool_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    payment_terms: Mapped[str] = mapped_column(String(120), default="Net 30")
    fob: Mapped[str] = mapped_column(String(120), default="Destination")
    shipping: Mapped[str] = mapped_column(String(300), default="Freight included in unit prices to the FOB point.")
    inspection_acceptance: Mapped[str] = mapped_column(String(200), default="Per the solicitation")
    address: Mapped[str] = mapped_column(Text, default="")  # letterhead mailing address, one line per row
    footer_text: Mapped[str] = mapped_column(Text, default="Thank you for the opportunity to quote.")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerQuoteDoc(Base):
    """The customer-facing quote number (Q-YYYY-NNNN) for a saved part quote, plus the last form values used."""

    __tablename__ = "customer_quote_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    part_quote_id: Mapped[int] = mapped_column(ForeignKey("part_quotes.id", ondelete="CASCADE"), unique=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VendorRFQ(Base):
    """A request for quote sent to one vendor for one saved part quote."""

    __tablename__ = "vendor_rfqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    part_quote_id: Mapped[int] = mapped_column(ForeignKey("part_quotes.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    vendor_name: Mapped[str] = mapped_column(String(300), default="")
    vendor_email: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="sent")
    due_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    message: Mapped[str] = mapped_column(Text, default="")
    quantities: Mapped[list] = mapped_column(JSON, default=list)
    include_files: Mapped[bool] = mapped_column(Boolean, default=False)
    files_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    vendor_quote_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_notes: Mapped[str] = mapped_column(Text, default="")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
