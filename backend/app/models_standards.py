"""Standards library: documents the owner saved, attached, imported or saw cited in solicitations."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

STANDARD_SOURCES = ["catalog", "solicitation", "manual", "import"]


class StandardEntry(Base):
    __tablename__ = "standard_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    publisher: Mapped[str] = mapped_column(String(120), default="")
    free: Mapped[bool] = mapped_column(Boolean, default=False)
    in_library: Mapped[bool] = mapped_column(Boolean, default=False)  # the owner saved it
    revision_on_file: Mapped[str] = mapped_column(String(40), default="")
    file_name: Mapped[str] = mapped_column(String(300), default="")  # stored under UPLOAD_DIR/standards/
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # catalog | solicitation | manual | import
    status: Mapped[str] = mapped_column(String(120), default="")  # from an imported list (Active, Cancelled, ...)
    doc_date: Mapped[str] = mapped_column(String(40), default="")  # from an imported list
    listed_revision: Mapped[str] = mapped_column(String(40), default="")  # revision shown in an imported list
    # [{opportunity_id, solicitation_number, title, cited_as, revision, seen_at}]
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
