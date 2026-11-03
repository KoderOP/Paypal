"""API-specific request/response schemas (engine models are reused where possible)."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.engine.forecast import Forecast
from app.engine.health import HealthIndicator
from app.engine.twin import CategorySpend, FinancialProfile, MonthSummary, RecurringItem
from app.engine.types import Assumptions, CashEvent, Money, ObligationIn


class BalancePoint(BaseModel):
    on: date
    balance: Money


class Kpis(BaseModel):
    current_balance: Money
    monthly_income: Money
    monthly_expenditure: Money
    monthly_investments: Money
    savings_rate: Decimal
    projected_balance_30: Money
    projected_balance_90: Money
    upcoming_obligations_total: Money
    subscriptions_monthly: Money
    next_income_date: date | None


class DashboardResponse(BaseModel):
    as_of: date
    user_name: str
    data_source: str
    kpis: Kpis
    health: list[HealthIndicator]
    history: list[BalancePoint]
    forecast: Forecast
    months: list[MonthSummary]
    categories: list[CategorySpend]
    upcoming_events: list[CashEvent]
    recurring: list[RecurringItem]
    obligations: list[ObligationIn]
    assumptions: Assumptions


class TwinResponse(BaseModel):
    profile: FinancialProfile
    assumptions: Assumptions


class TransactionOut(BaseModel):
    id: int
    posted_on: date
    description: str
    merchant: str
    category: str
    amount: Money
    source: str


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class ObligationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    category: str = Field("Other", min_length=1, max_length=60)
    amount: Money = Field(gt=0, le=Decimal("100000000"))
    due_on: date
    notes: str = Field("", max_length=255)


class ObligationOut(ObligationCreate):
    id: int


class PurchaseRequest(BaseModel):
    amount: Money = Field(Decimal("75000"), gt=0, le=Decimal("100000000"))
    purchase_date: date | None = None  # defaults to today
    label: str = Field("Laptop purchase", min_length=1, max_length=80)
    safety_buffer: Money | None = Field(None, ge=0)


class ScenarioInfo(BaseModel):
    type: str
    title: str
    description: str
    status: Literal["available", "planned"]


class SettingsOut(BaseModel):
    user_name: str
    currency: str
    data_source: str | None
    has_data: bool
    assumptions: Assumptions
    paypal: dict
    ai_configured: bool


class SettingsUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    safety_buffer: Money | None = Field(None, ge=0, le=Decimal("100000000"))


class StatusOut(BaseModel):
    has_data: bool
    user_name: str
    data_source: str | None
    transaction_count: int


class DemoFileOut(BaseModel):
    id: str
    title: str
    format: str
    filename: str
    description: str
    suggested_opening_balance: Money | None


class ImportResult(BaseModel):
    format: str
    source: str
    rows: int
    imported: int
    skipped_duplicates: int
    account_id: int
    opening_balance: Money
    warnings: list[str] = []


class PayPalSyncRequest(BaseModel):
    days: int = Field(180, ge=1, le=1095)
    replace: bool = False
