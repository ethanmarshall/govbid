"""NSN award history: past awards and our own won/lost quotes, used as reference prices."""
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

AWARD_SOURCES = ["dibbs_import", "manual", "quote_won", "quote_lost", "sam_award"]


class AwardRecord(Base):
    __tablename__ = "nsn_awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 4-2-3-4 with dashes ("5340-01-480-5627"); NIIN-only records store "01-480-5627" (FSC unknown)
    nsn: Mapped[str] = mapped_column(String(20), default="", index=True)
    niin: Mapped[str] = mapped_column(String(9), default="", index=True)  # 9 digits, used for matching
    part_number: Mapped[str] = mapped_column(String(80), default="")
    nomenclature: Mapped[str] = mapped_column(String(200), default="")
    cage: Mapped[str] = mapped_column(String(10), default="")  # awardee CAGE
    awardee: Mapped[str] = mapped_column(String(300), default="")
    contract_number: Mapped[str] = mapped_column(String(80), default="")
    award_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_of_issue: Mapped[str] = mapped_column(String(10), default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # see AWARD_SOURCES
    quote_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # PartQuote behind quote_won/quote_lost
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
