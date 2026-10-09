"""Proposal pricing workbook: indirect rates, labor categories and price builds."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class IndirectRates(Base):
    """Single row (id=1): the company's current indirect rates and how each is applied."""

    __tablename__ = "wb_indirect_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fringe_pct: Mapped[float] = mapped_column(Float, default=30.0)
    overhead_pct: Mapped[float] = mapped_column(Float, default=40.0)
    ga_pct: Mapped[float] = mapped_column(Float, default=12.0)
    profit_pct: Mapped[float] = mapped_column(Float, default=8.0)
    material_handling_pct: Mapped[float] = mapped_column(Float, default=0.0)
    overhead_base: Mapped[str] = mapped_column(String(30), default="labor_fringe")  # labor | labor_fringe
    ga_base: Mapped[str] = mapped_column(String(30), default="total_cost_input")  # total_cost_input | value_added | labor_overhead
    fee_base: Mapped[str] = mapped_column(String(30), default="total_cost")  # total_cost | cost_less_pass_through
    # Owner's expected annual numbers used by the rate calculator
    calc_inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LaborCategory(Base):
    __tablename__ = "wb_labor_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0)  # direct (unburdened) rate
    annual_salary: Mapped[float | None] = mapped_column(Float, nullable=True)  # if set, hourly = salary / 2080
    calc_category: Mapped[str] = mapped_column(String(200), default="")  # GSA CALC+ labor category name to compare with
    calc_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PriceBuild(Base):
    """A priced proposal: CLINs with labor, materials, subcontracts, ODCs and part lines."""

    __tablename__ = "wb_price_builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True)
    # Snapshot of the indirect rates (same keys as IndirectRates) so an old bid does not move when rates change
    rates: Mapped[dict] = mapped_column(JSON, default=dict)
    set_aside: Mapped[bool] = mapped_column(default=False)  # apply the FAR 52.219-14 check
    # [{"clin","description","kind": services|supplies,"quantity","unit","nsn",
    #   "labor":[{"category_id","hours","rate"}], "materials":[{"description","cost"}],
    #   "subcontracts":[{"name","cost","similarly_situated","lower_tier_non_ss"}],
    #   "odcs":[{"description","cost","kind": odc|travel}],
    #   "parts":[{"part_quote_id","description","quantity","unit_price"}]}]
    clins: Mapped[list] = mapped_column(JSON, default=list)
    # [{"name","source": manual|nsn_history|usaspending,"note","prices": {"0001": 1234.0}, "total": float|None}]
    competitors: Mapped[list] = mapped_column(JSON, default=list)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
