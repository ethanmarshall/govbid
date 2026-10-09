from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class CompanyProfile(Base):
    """Single-row table describing your business and its certifications."""

    __tablename__ = "company_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    uei: Mapped[str] = mapped_column(String(20), default="")
    cage: Mapped[str] = mapped_column(String(10), default="")
    sam_status: Mapped[str] = mapped_column(String(20), default="not_registered")  # active / pending / expired / not_registered
    sam_expiration: Mapped[str] = mapped_column(String(20), default="")
    state: Mapped[str] = mapped_column(String(2), default="")
    naics_codes: Mapped[list] = mapped_column(JSON, default=list)  # ["541511", ...]
    psc_codes: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    nsn_watchlist: Mapped[list] = mapped_column(JSON, default=list)  # NSNs or FSC prefixes for DIBBS
    # {"SDVOSB": "pending", "VOSB": "pending", "SB": "certified", "8A": "none", ...}
    certifications: Mapped[dict] = mapped_column(JSON, default=dict)
    # NAICS code -> True if you are small under that code's size standard
    small_under_naics: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Joint Certification Program (DD Form 2345): needed to download export-controlled drawings
    jcp_status: Mapped[str] = mapped_column(String(20), default="none")  # none / applied / approved / expired
    jcp_cert_number: Mapped[str] = mapped_column(String(40), default="")
    jcp_expiration: Mapped[str] = mapped_column(String(20), default="")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(30), index=True)  # sam / dibbs / forecast / manual
    external_id: Mapped[str] = mapped_column(String(120))
    solicitation_number: Mapped[str] = mapped_column(String(120), default="", index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    agency: Mapped[str] = mapped_column(String(500), default="")
    notice_type: Mapped[str] = mapped_column(String(80), default="")
    set_aside_code: Mapped[str] = mapped_column(String(20), default="", index=True)
    set_aside_desc: Mapped[str] = mapped_column(String(200), default="")
    naics: Mapped[str] = mapped_column(String(10), default="", index=True)
    psc: Mapped[str] = mapped_column(String(10), default="")
    nsn: Mapped[str] = mapped_column(String(20), default="")
    quantity: Mapped[str] = mapped_column(String(40), default="")
    posted_date: Mapped[str] = mapped_column(String(30), default="", index=True)
    response_deadline: Mapped[str] = mapped_column(String(40), default="", index=True)
    place_of_performance: Mapped[str] = mapped_column(String(200), default="")
    pop_state: Mapped[str] = mapped_column(String(2), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    description_url: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    contacts: Mapped[list] = mapped_column(JSON, default=list)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    estimated_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    analysis: Mapped["Analysis | None"] = relationship(back_populates="opportunity", uselist=False, cascade="all, delete-orphan")
    pipeline: Mapped["PipelineEntry | None"] = relationship(back_populates="opportunity", uselist=False, cascade="all, delete-orphan")


class Analysis(Base):
    """Requirements breakdown and compliance matrix for one opportunity."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), unique=True)
    method: Mapped[str] = mapped_column(String(20), default="heuristic")  # claude / heuristic
    summary: Mapped[str] = mapped_column(Text, default="")
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    compliance_matrix: Mapped[list] = mapped_column(JSON, default=list)
    source_files: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    opportunity: Mapped[Opportunity] = relationship(back_populates="analysis")


PIPELINE_STAGES = ["tracking", "evaluating", "bidding", "submitted", "won", "lost", "no_bid"]


class PipelineEntry(Base):
    __tablename__ = "pipeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), unique=True)
    stage: Mapped[str] = mapped_column(String(20), default="tracking")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    bid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    debrief: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    opportunity: Mapped[Opportunity] = relationship(back_populates="pipeline")


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SyncLog(Base):
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    added: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    requests_used: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- proposal and data packages
PACKAGE_KINDS = ["proposal", "tdp"]
PACKAGE_STATUSES = ["draft", "in_review", "final", "submitted"]
SECTION_STATUSES = ["not_started", "drafting", "review", "done"]
ITEM_STATUSES = ["not_started", "in_progress", "ready", "delivered", "accepted"]


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20), default="proposal")
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    due_date: Mapped[str] = mapped_column(String(40), default="")
    contract_number: Mapped[str] = mapped_column(String(80), default="")
    # Cover page and header details: solicitation_number, agency, poc_name, poc_email, poc_phone, validity_days, classification
    cover: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sections: Mapped[list["PackageSection"]] = relationship(back_populates="package", cascade="all, delete-orphan", order_by="PackageSection.position")
    items: Mapped[list["PackageItem"]] = relationship(back_populates="package", cascade="all, delete-orphan", order_by="PackageItem.position")
    opportunity: Mapped[Opportunity | None] = relationship()


class PackageSection(Base):
    __tablename__ = "package_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    volume: Mapped[str] = mapped_column(String(120), default="")
    number: Mapped[str] = mapped_column(String(20), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    guidance: Mapped[str] = mapped_column(Text, default="")  # what this section should cover
    content: Mapped[str] = mapped_column(Text, default="")  # markdown
    page_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    requirement_ids: Mapped[list] = mapped_column(JSON, default=list)  # compliance matrix row ids assigned here
    covered_ids: Mapped[list] = mapped_column(JSON, default=list)  # rows the writer marked as addressed
    page_break_before: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    package: Mapped[Package] = relationship(back_populates="sections")


class PackageItem(Base):
    """A deliverable or attachment: a CDRL line in a TDP, or a form/attachment in a proposal."""

    __tablename__ = "package_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    cdrl: Mapped[str] = mapped_column(String(20), default="")  # e.g. A001
    title: Mapped[str] = mapped_column(String(300), default="")
    did: Mapped[str] = mapped_column(String(40), default="")  # e.g. DI-SESS-81000
    category: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    due: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    files: Mapped[list] = mapped_column(JSON, default=list)

    package: Mapped[Package] = relationship(back_populates="items")


LIBRARY_CATEGORIES = ["Company overview", "Past performance", "Key personnel", "Management", "Quality", "Technical", "Boilerplate"]


class LibraryEntry(Base):
    """Reusable proposal content: capability statements, past performance write-ups, resumes, QC plans."""

    __tablename__ = "library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(60), default="Boilerplate")
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------- custom part pricing
QUOTE_STATUSES = ["draft", "ready", "submitted", "won", "lost", "no_bid"]


class PricingConfig(Base):
    """Single row: shop-rate overrides merged over pricing.DEFAULT_CONFIG."""

    __tablename__ = "pricing_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PartQuote(Base):
    __tablename__ = "part_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    nsn: Mapped[str] = mapped_column(String(20), default="")
    part_number: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    quoted_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quoted_unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(40), default="web")  # web | agent
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    opportunity: Mapped[Opportunity | None] = relationship()


class OpportunityChange(Base):
    """A change the amendment watch found on a tracked opportunity (new deadline, attachments, amendment, award)."""

    __tablename__ = "opportunity_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    field: Mapped[str] = mapped_column(String(40))
    old: Mapped[str] = mapped_column(Text, default="")
    new: Mapped[str] = mapped_column(Text, default="")
    notice_id: Mapped[str] = mapped_column(String(120), default="")
    seen: Mapped[bool] = mapped_column(default=False)
