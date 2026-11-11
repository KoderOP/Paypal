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


class FxDetail(Base):
    """Original-currency details of a transaction received in a foreign currency and converted.

    Kept in its own table (one row per converted transaction) so existing databases need no
    migration. `Transaction.amount` is always the home-currency amount actually credited.
    """

    __tablename__ = "fx_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), unique=True)
    currency: Mapped[str] = mapped_column(String(3))
    gross: Mapped[Decimal] = mapped_column(MONEY)
    fee: Mapped[Decimal] = mapped_column(MONEY)
    net: Mapped[Decimal] = mapped_column(MONEY)
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    rate_source: Mapped[str] = mapped_column(String(30))


class DemoPayPalObject(Base):
    """State of FINORA's built-in PayPal demo (orders, sign-in codes, subscriptions). Only used without credentials."""

    __tablename__ = "demo_paypal_objects"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_demo_pp_kind_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))  # order | order_request | auth_code | subscription
    key: Mapped[str] = mapped_column(String(120))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SavedScenario(Base):
    """A named what-if (list of scenario changes) saved for side-by-side comparison."""

    __tablename__ = "saved_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    changes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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


class CheckoutOrder(Base):
    """A PayPal Orders API checkout started from a simulation.

    Lifecycle: created → awaiting_approval (buyer sent to PayPal) → approved (buyer returned)
    → captured (user confirmed in FINORA) | cancelled | failed. Nothing is captured without an
    explicit confirmation request from the user after PayPal approval.
    """

    __tablename__ = "checkout_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    option_id: Mapped[str] = mapped_column(String(40))  # pay_now | pay_in_4 | pay_monthly_12 | …
    funding: Mapped[str] = mapped_column(String(20))  # paypal | paylater
    label: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24), default="created")
    approve_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    capture_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64))  # PayPal-Request-Id (idempotency)
    # Simulation snapshot at the moment the user confirmed: schedule, low balance, safe flag.
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AddedSubscription(Base):
    """A subscription the user added by hand, e.g. one just started that has no payment history yet.

    It is projected monthly from `next_billing_date`. Once the same merchant is detected from
    transactions, the detected item replaces it in the twin (see engine.twin.with_added).
    """

    __tablename__ = "added_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), default="Subscriptions")
    amount: Mapped[Decimal] = mapped_column(MONEY)  # per month, positive
    next_billing_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LinkedSubscription(Base):
    """A PayPal subscription (Subscriptions API, id I-…) linked to a recurring item in the twin."""

    __tablename__ = "linked_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "paypal_subscription_id", name="uq_linked_sub"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    paypal_subscription_id: Mapped[str] = mapped_column(String(64))
    recurring_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
