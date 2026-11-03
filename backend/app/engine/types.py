"""Engine data types. The engine is pure: no DB, no network, no LLM — same inputs, same outputs."""
import calendar
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer

# Money is computed as Decimal everywhere; serialised to a JSON number (2dp) only at the API edge.
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


class Txn(BaseModel):
    posted_on: date
    description: str
    merchant: str
    category: str
    amount: Money  # signed


class ObligationIn(BaseModel):
    title: str
    category: str
    amount: Money  # positive = owed
    due_on: date


class Assumptions(BaseModel):
    """Configurable, explicit forecast assumptions — returned with every result for reproducibility."""

    horizon_days: int = Field(90, ge=7, le=365)
    safety_buffer: Money = Field(Decimal("20000"), ge=0)
    lookback_days: int = Field(90, ge=30, le=365, description="Window used for averages and variable spend")
    variable_spend_multiplier: Money = Field(Decimal("1"), ge=0, le=5)
    include_obligations: bool = True
    include_irregular_income: bool = False


EventKind = Literal["income", "recurring", "obligation", "variable", "scenario"]


class CashEvent(BaseModel):
    on: date
    amount: Money  # signed
    label: str
    category: str
    kind: EventKind


def add_months(d: date, months: int, day: int | None = None) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(day or d.day, calendar.monthrange(y, m)[1]))
