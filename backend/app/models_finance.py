"""Finance tables: invoices tracked against what is submitted in PIEE (WAWF), finance settings
(invoice numbering, Prompt Payment interest rates) and loans with draws and payments.

All of this is the owner's private data and stays in the local SQLite database."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

INVOICE_STATUSES = ["draft", "submitted", "rejected", "accepted", "paid"]
LOAN_PROGRAMS = ["sba_7a", "sba_express", "sba_504", "sba_microloan", "va_other", "line_of_credit", "other"]


class FinanceSettings(Base):
    """Single row (id=1)."""

    __tablename__ = "finance_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_prefix: Mapped[str] = mapped_column(String(20), default="INV-")
    next_invoice_seq: Mapped[int] = mapped_column(Integer, default=1)
    seq_width: Mapped[int] = mapped_column(Integer, default=4)
    # [{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "rate": 4.75}]  (annual percent, from fiscal.treasury.gov)
    prompt_pay_rates: Mapped[list] = mapped_column(JSON, default=list)
    remit_to: Mapped[str] = mapped_column(Text, default="")  # address block printed on invoices
    payment_terms: Mapped[str] = mapped_column(String(80), default="Net 30")
    invoice_footer: Mapped[str] = mapped_column(Text, default="")


class Invoice(Base):
    __tablename__ = "finance_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    customer: Mapped[str] = mapped_column(String(300), default="")
    contract_number: Mapped[str] = mapped_column(String(80), default="")
    delivery_order: Mapped[str] = mapped_column(String(80), default="")
    doc_type: Mapped[str] = mapped_column(String(30), default="combo")
    # [{"clin": "0001", "description": "", "quantity": 1, "unit": "EA", "unit_price": 0, "amount": 0}]
    lines: Mapped[list] = mapped_column(JSON, default=list)
    shipment_number: Mapped[str] = mapped_column(String(40), default="")
    ship_date: Mapped[str] = mapped_column(String(10), default="")  # delivery or service completion date
    invoice_date: Mapped[str] = mapped_column(String(10), default="")
    submitted_date: Mapped[str] = mapped_column(String(10), default="")  # date PIEE received it
    status: Mapped[str] = mapped_column(String(20), default="draft")
    acceptance_date: Mapped[str] = mapped_column(String(10), default="")
    acceptance_period_days: Mapped[int] = mapped_column(Integer, default=7)
    disputed: Mapped[bool] = mapped_column(Boolean, default=False)  # disagreement over quantity, quality or compliance
    due_date_override: Mapped[str] = mapped_column(String(10), default="")  # payment date set by the contract
    paid_date: Mapped[str] = mapped_column(String(10), default="")
    amount_paid: Mapped[float | None] = mapped_column(Float, nullable=True)
    interest_paid: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    history: Mapped[list] = mapped_column(JSON, default=list)  # [{"date", "status", "note"}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Loan(Base):
    __tablename__ = "finance_loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lender: Mapped[str] = mapped_column(String(200), default="")
    program: Mapped[str] = mapped_column(String(30), default="sba_7a")
    principal: Mapped[float] = mapped_column(Float, default=0.0)  # loan amount, or credit limit for a line of credit
    rate_type: Mapped[str] = mapped_column(String(10), default="fixed")  # fixed | variable
    rate: Mapped[float] = mapped_column(Float, default=0.0)  # current annual percent
    rate_base: Mapped[str] = mapped_column(String(120), default="")  # e.g. "Prime + 2.75%, adjusts quarterly"
    term_months: Mapped[int] = mapped_column(Integer, default=120)
    start_date: Mapped[str] = mapped_column(String(10), default="")
    first_payment_date: Mapped[str] = mapped_column(String(10), default="")
    amortizing: Mapped[bool] = mapped_column(Boolean, default=True)  # False = interest only (typical line of credit)
    payment_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # entered; blank = computed
    balance_basis: Mapped[str] = mapped_column(String(12), default="principal")  # principal | draws
    day_count: Mapped[str] = mapped_column(String(12), default="monthly")  # monthly | actual_365 | actual_360
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | paid_off
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LoanDraw(Base):
    __tablename__ = "finance_loan_draws"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("finance_loans.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String(10), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    purpose: Mapped[str] = mapped_column(String(200), default="")


class LoanPayment(Base):
    __tablename__ = "finance_loan_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("finance_loans.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String(10), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    principal_override: Mapped[float | None] = mapped_column(Float, nullable=True)  # from the lender statement
    interest_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")
