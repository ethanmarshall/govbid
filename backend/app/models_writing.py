"""Writing tools: stored evaluator reviews of proposal packages and capability statement settings."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ProposalReviewRun(Base):
    """One evaluator-style review of a package. Kept so the owner can compare runs over time."""

    __tablename__ = "proposal_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(20), default="rules")  # claude | rules
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CapabilitySettings(Base):
    """Single row (id=1): the editable parts of the one-page capability statement."""

    __tablename__ = "capability_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagline: Mapped[str] = mapped_column(String(300), default="")
    overview: Mapped[str] = mapped_column(Text, default="")
    competencies: Mapped[list] = mapped_column(JSON, default=list)
    differentiators: Mapped[list] = mapped_column(JSON, default=list)
    past_performance_ids: Mapped[list] = mapped_column(JSON, default=list)
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_title: Mapped[str] = mapped_column(String(200), default="")
    contact_phone: Mapped[str] = mapped_column(String(60), default="")
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    logo_file: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
