"""Lightweight quality system: nonconformances, corrective actions, calibration, quality documents and supplier approval."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

NCR_DISPOSITIONS = ["", "use_as_is", "rework", "repair", "scrap", "return_to_vendor"]
NCR_STATUSES = ["open", "dispositioned", "closed"]
NCR_SOURCES = ["receiving", "in_process", "final_inspection", "customer", "other"]
CAR_STATUSES = ["open", "verifying", "closed"]
INSTRUMENT_STATUSES = ["active", "out_of_service", "retired"]
APPROVAL_STATUSES = ["pending", "approved", "conditional", "disapproved"]
APPROVAL_BASES = ["survey", "iso_cert", "past_performance", "oem_or_authorized_distributor", "customer_directed", "other"]
SUPPLIER_CERT_TYPES = ["ISO 9001", "AS9100", "AS9120", "ISO 17025", "ITAR registration", "AWS welder cert", "IPC-A-610", "IPC/WHMA-A-620",
                       "IPC J-STD-001", "NADCAP", "Other"]


class NonconformanceReport(Base):
    __tablename__ = "quality_ncrs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)  # NCR-YYYY-NNN
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("job_purchases.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="in_process")
    part: Mapped[str] = mapped_column(String(200), default="")
    quantity: Mapped[float | None] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    containment: Mapped[str] = mapped_column(Text, default="")
    disposition: Mapped[str] = mapped_column(String(30), default="")
    disposition_by: Mapped[str] = mapped_column(String(60), default="")
    root_cause: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    opened_date: Mapped[str] = mapped_column(String(10), default="")
    closed_date: Mapped[str] = mapped_column(String(10), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CorrectiveAction(Base):
    __tablename__ = "quality_cars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)  # CAR-YYYY-NNN
    ncr_id: Mapped[int | None] = mapped_column(ForeignKey("quality_ncrs.id", ondelete="SET NULL"), nullable=True, index=True)
    problem: Mapped[str] = mapped_column(Text, default="")
    root_cause: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    opened_date: Mapped[str] = mapped_column(String(10), default="")
    due_date: Mapped[str] = mapped_column(String(10), default="")
    effectiveness_check: Mapped[str] = mapped_column(Text, default="")  # how and when you will confirm it worked
    effectiveness_date: Mapped[str] = mapped_column(String(10), default="")
    effective: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    closed_date: Mapped[str] = mapped_column(String(10), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Instrument(Base):
    """A measuring or test instrument on the calibration log."""

    __tablename__ = "quality_instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(60), default="")
    asset_id: Mapped[str] = mapped_column(String(60), default="")  # your ID tag
    serial: Mapped[str] = mapped_column(String(80), default="")
    manufacturer: Mapped[str] = mapped_column(String(120), default="")
    range_resolution: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    interval_days: Mapped[int] = mapped_column(Integer, default=365)
    last_cal_date: Mapped[str] = mapped_column(String(10), default="")
    cal_source: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    # [{"date": "YYYY-MM-DD", "source": "", "result": "pass|adjusted|fail", "notes": "", "filename": "", "stored_name": ""}]
    history: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QualityDocument(Base):
    """An editable quality manual or procedure with a simple revision history."""

    __tablename__ = "quality_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), default="")  # starter template key, blank for your own documents
    doc_number: Mapped[str] = mapped_column(String(30), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    version: Mapped[str] = mapped_column(String(20), default="A")
    effective_date: Mapped[str] = mapped_column(String(10), default="")
    content: Mapped[str] = mapped_column(Text, default="")  # markdown
    # [{"version": "A", "effective_date": "", "content": "...", "note": "", "replaced_at": "iso"}]
    history: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupplierApproval(Base):
    """Approval status for one vendor Organization (one row per organization)."""

    __tablename__ = "quality_supplier_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approval_date: Mapped[str] = mapped_column(String(10), default="")
    basis: Mapped[list] = mapped_column(JSON, default=list)  # values from APPROVAL_BASES
    scope: Mapped[str] = mapped_column(Text, default="")  # what they are approved to supply
    review_due: Mapped[str] = mapped_column(String(10), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupplierCert(Base):
    """A certification on file for a vendor, with an optional uploaded copy."""

    __tablename__ = "quality_supplier_certs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    cert_type: Mapped[str] = mapped_column(String(60), default="")
    number: Mapped[str] = mapped_column(String(120), default="")
    issuer: Mapped[str] = mapped_column(String(200), default="")
    expiration_date: Mapped[str] = mapped_column(String(10), default="")
    filename: Mapped[str] = mapped_column(String(300), default="")
    stored_name: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
