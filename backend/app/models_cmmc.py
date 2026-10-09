"""CMMC Level 1 / NIST SP 800-171 compliance tracker tables."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

CONTROL_STATUSES = ["not_started", "planned", "partial", "implemented", "not_applicable"]


class CmmcControl(Base):
    """One row per framework (L1 or L2) and control ID; static text and weights live in cmmc_controls.py."""

    __tablename__ = "cmmc_controls"
    __table_args__ = (UniqueConstraint("framework", "control_id", name="uq_cmmc_framework_control"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    framework: Mapped[str] = mapped_column(String(10))  # L1 | L2
    control_id: Mapped[str] = mapped_column(String(30))  # AC.L1-b.1.i or 3.1.1
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    evidence: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    poam_due: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CmmcSettings(Base):
    """Single row: submission dates and scope notes."""

    __tablename__ = "cmmc_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sprs_submission_date: Mapped[str] = mapped_column(String(10), default="")
    affirmation_date: Mapped[str] = mapped_column(String(10), default="")
    scope_notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
