"""Recompetes and buyers: USAspending response cache and the recompete watch list."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

TRACK_STATUSES = ["watching", "outreach", "presolicitation", "solicitation_posted", "bid", "no_bid", "closed"]


class MarketCache(Base):
    """One cached USAspending API response, keyed by a hash of method, path and request body."""

    __tablename__ = "market_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    method: Mapped[str] = mapped_column(String(6), default="POST")
    path: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrackedRecompete(Base):
    """An incumbent contract the owner is watching because it may be recompeted."""

    __tablename__ = "tracked_recompetes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_internal_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    award_id: Mapped[str] = mapped_column(String(120), default="")
    recipient: Mapped[str] = mapped_column(String(300), default="")
    recipient_uei: Mapped[str] = mapped_column(String(20), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    agency: Mapped[str] = mapped_column(String(300), default="")
    sub_agency: Mapped[str] = mapped_column(String(300), default="")
    office: Mapped[str] = mapped_column(String(300), default="")
    start_date: Mapped[str] = mapped_column(String(10), default="")
    end_date: Mapped[str] = mapped_column(String(10), default="", index=True)
    naics: Mapped[str] = mapped_column(String(10), default="")
    psc: Mapped[str] = mapped_column(String(10), default="")
    set_aside: Mapped[str] = mapped_column(String(200), default="")
    extent_competed: Mapped[str] = mapped_column(String(200), default="")
    offers: Mapped[str] = mapped_column(String(20), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="watching")
    notes: Mapped[str] = mapped_column(Text, default="")
    reminder_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD, blank = none
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
