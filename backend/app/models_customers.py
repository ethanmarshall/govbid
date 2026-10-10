"""Customer accounts on the public site (separate from the staff login)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)  # stored lower case
    password_hash: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(120), default="")
    company: Mapped[str] = mapped_column(String(160), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    # [{label, name, company, line1, line2, city, state, zip, country, phone}] the first is the default
    addresses: Mapped[list] = mapped_column(JSON, default=list)
    session_version: Mapped[int] = mapped_column(Integer, default=1)  # bump to sign out everywhere (password change)
    reset_hash: Mapped[str] = mapped_column(String(128), default="")
    reset_expires: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # payment terms you approved: 0 = pay the invoice before we start; 30 = net 30 (we start, they pay within 30 days)
    net_terms_days: Mapped[int] = mapped_column(Integer, default=0)
    terms_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_request_note: Mapped[str] = mapped_column(Text, default="")
    staff_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
