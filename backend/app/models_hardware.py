"""Bought hardware (bearings, fasteners, catalog parts) with prices, and the samples used to calibrate pricing."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HardwareItem(Base):
    """One catalog part you buy. Priced from the McMaster-Carr API when it is connected, or by hand.

    match: comma-separated words or phrases; a part in a customer's model whose name contains all the words of
    any phrase is priced as this item (for example "608 bearing" or "m5 x 10 socket head").
    """

    __tablename__ = "hardware_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    part_number: Mapped[str] = mapped_column(String(40), index=True, default="")
    vendor: Mapped[str] = mapped_column(String(40), default="McMaster-Carr")
    description: Mapped[str] = mapped_column(String(300), default="")
    match: Mapped[str] = mapped_column(String(400), default="")
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # per piece
    pack_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # as listed (a pack of 100 screws, say)
    pack_qty: Mapped[int] = mapped_column(Integer, default=1)
    price_breaks: Mapped[list] = mapped_column(JSON, default=list)  # [{min_qty, amount, uom}] as the vendor lists them
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | mcmaster
    url: Mapped[str] = mapped_column(String(300), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    priced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CalibrationSample(Base):
    """A real price for a part next to what the tool priced it at. Per-process correction factors come from these."""

    __tablename__ = "calibration_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="benchmark")  # benchmark | review
    process: Mapped[str] = mapped_column(String(30), index=True)  # cnc_mill, cnc_5axis, cnc_lathe, sheet_metal, 3d_print, flat, ...
    name: Mapped[str] = mapped_column(String(200), default="")
    material: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    tool_unit_price: Mapped[float] = mapped_column(Float)  # the raw (uncalibrated) tool price
    actual_unit_price: Mapped[float] = mapped_column(Float)  # the real quote or the price you settled on
    vendor: Mapped[str] = mapped_column(String(80), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    file_id: Mapped[str] = mapped_column(String(40), default="")
    ref: Mapped[str] = mapped_column(String(60), default="")  # RQ-2026-0005#line, a saved quote id, ...
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
