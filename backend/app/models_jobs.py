"""Awarded work (jobs). Shared by job tracking, quality records, invoicing and supplier scorecards."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

JOB_STATUSES = ["awarded", "in_work", "inspection", "shipped", "invoiced", "paid", "closed", "cancelled"]
OPERATION_STATUSES = ["not_started", "in_progress", "done", "hold"]
RECORD_TYPES = ["material_cert", "inspection_report", "first_article", "coc", "test_report", "packing_list",
                "receiving_report", "drawing", "photo", "other"]


class Job(Base):
    """One award (contract, purchase order or delivery order) you have to deliver."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    part_quote_id: Mapped[int | None] = mapped_column(ForeignKey("part_quotes.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    customer: Mapped[str] = mapped_column(String(300), default="")  # agency / buying office or prime
    contract_number: Mapped[str] = mapped_column(String(80), default="")  # PIID
    delivery_order: Mapped[str] = mapped_column(String(80), default="")
    cage_ship_to: Mapped[str] = mapped_column(String(20), default="")  # ship-to DoDAAC/CAGE if given
    # [{"clin": "0001", "description": "", "nsn": "", "part_number": "", "quantity": 10, "unit": "EA", "unit_price": 42.0, "due_date": "YYYY-MM-DD"}]
    clins: Mapped[list] = mapped_column(JSON, default=list)
    award_date: Mapped[str] = mapped_column(String(10), default="")
    due_date: Mapped[str] = mapped_column(String(10), default="")  # earliest delivery due
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="awarded")
    fob: Mapped[str] = mapped_column(String(20), default="")  # origin | destination
    inspection_acceptance: Mapped[str] = mapped_column(String(20), default="")  # origin | destination
    shipped_date: Mapped[str] = mapped_column(String(10), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Shipping details (added by the jobs feature; all defaulted)
    carrier: Mapped[str] = mapped_column(String(80), default="")
    tracking_number: Mapped[str] = mapped_column(String(120), default="")
    packaging_level: Mapped[str] = mapped_column(String(40), default="")  # commercial | MIL-STD-2073 level/codes, free text
    packaging_notes: Mapped[str] = mapped_column(Text, default="")  # MIL-STD-129 marking, MIL-STD-2073 codes, free text
    iuid_required: Mapped[bool] = mapped_column(Boolean, default=False)


class JobOperation(Base):
    """One step on a job's traveler (work order)."""

    __tablename__ = "job_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200), default="")
    op_type: Mapped[str] = mapped_column(String(40), default="")  # quote operation type when built from a quote
    work_center: Mapped[str] = mapped_column(String(200), default="")  # in-house cell or outside vendor
    planned_date: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    signoff_initials: Mapped[str] = mapped_column(String(10), default="")
    signoff_date: Mapped[str] = mapped_column(String(10), default="")
    qty_good: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_rejected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class JobPurchase(Base):
    """A purchase order you placed with a vendor for a job (material, outside processing, buy-out parts)."""

    __tablename__ = "job_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    vendor_name: Mapped[str] = mapped_column(String(300), default="")
    po_number: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    ordered_date: Mapped[str] = mapped_column(String(10), default="")
    promised_date: Mapped[str] = mapped_column(String(10), default="")
    received_date: Mapped[str] = mapped_column(String(10), default="")
    qty_accepted: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty_rejected: Mapped[float | None] = mapped_column(Float, nullable=True)
    certs_received: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobRecord(Base):
    """An uploaded quality record for a job (material cert, inspection report, first article, C of C...)."""

    __tablename__ = "job_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40), default="other")
    clin: Mapped[str] = mapped_column(String(20), default="")
    filename: Mapped[str] = mapped_column(String(300), default="")
    stored_name: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
