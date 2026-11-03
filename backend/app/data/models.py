"""Financial data layer — SQLAlchemy ORM models.

Balances are never stored as free-standing numbers: an account's balance is always
`opening_balance + SUM(transactions.amount)`. Amounts are signed (credit > 0, debit < 0).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

MONEY = Numeric(14, 2)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    # Per-user forecast assumptions (e.g. safety buffer). Engine defaults fill gaps.
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    accounts: Mapped[list["Account"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    obligations: Mapped[list["Obligation"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    institution: Mapped[str] = mapped_column(String(120), default="")
    account_type: Mapped[str] = mapped_column(String(30), default="savings")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    opening_date: Mapped[date] = mapped_column(Date)
    # Where the data comes from: synthetic | csv | paypal
    source: Mapped[str] = mapped_column(String(20), default="synthetic")

    user: Mapped[User] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "external_id", name="uq_txn_account_external"),
        Index("ix_txn_account_date", "account_id", "posted_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    posted_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(255))
    merchant: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)  # signed: + credit, - debit
    source: Mapped[str] = mapped_column(String(20), default="synthetic")
    external_id: Mapped[str] = mapped_column(String(120))  # id in the source system, for idempotent imports
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="transactions")


class Obligation(Base):
    """A known future one-off outflow (insurance renewal, fees, planned payments)."""

    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    amount: Mapped[Decimal] = mapped_column(MONEY)  # positive = money owed
    due_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(String(255), default="")

    user: Mapped[User] = relationship(back_populates="obligations")
