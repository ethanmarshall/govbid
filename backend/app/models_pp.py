"""Past performance log: contracts, subcontracts, employment and project work usable as relevant experience."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

PP_ROLES = ["prime", "sub", "commercial", "personal_project", "employment"]


class PastPerformance(Base):
    __tablename__ = "past_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    customer: Mapped[str] = mapped_column(String(300), default="")
    agency: Mapped[str] = mapped_column(String(300), default="")
    contract_number: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(30), default="prime")
    contract_type: Mapped[str] = mapped_column(String(60), default="")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[str] = mapped_column(String(10), default="")
    end_date: Mapped[str] = mapped_column(String(10), default="")
    naics: Mapped[str] = mapped_column(String(20), default="")
    psc: Mapped[str] = mapped_column(String(20), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    results: Mapped[str] = mapped_column(Text, default="")
    relevance_keywords: Mapped[list] = mapped_column(JSON, default=list)
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    contact_phone: Mapped[str] = mapped_column(String(60), default="")
    cpars_rating: Mapped[str] = mapped_column(String(60), default="")
    can_use_as_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
