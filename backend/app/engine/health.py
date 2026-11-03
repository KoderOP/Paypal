"""Financial health indicators — deterministic ratios with explicit thresholds."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel

from app.core.money import ratio
from app.engine.forecast import Forecast
from app.engine.twin import FinancialProfile

Status = Literal["good", "watch", "risk"]


class HealthIndicator(BaseModel):
    key: str
    label: str
    value: Decimal
    unit: Literal["percent", "months", "currency"]
    status: Status
    detail: str


def _status(value: Decimal, good: Decimal, watch: Decimal, higher_is_better: bool = True) -> Status:
    if higher_is_better:
        return "good" if value >= good else "watch" if value >= watch else "risk"
    return "good" if value <= good else "watch" if value <= watch else "risk"


def health_indicators(profile: FinancialProfile, forecast: Forecast) -> list[HealthIndicator]:
    spend = profile.avg_monthly_spending
    income = profile.monthly_income
    runway = (profile.current_balance / spend).quantize(Decimal("0.1"), ROUND_HALF_UP) if spend > 0 else Decimal("0")
    fixed = ratio(profile.recurring_outflow_monthly, income)
    subs = ratio(profile.subscriptions_monthly, income)
    buffer = forecast.assumptions.safety_buffer
    return [
        HealthIndicator(key="savings_rate", label="Savings rate", value=profile.savings_rate, unit="percent",
                        status=_status(profile.savings_rate, Decimal("0.20"), Decimal("0.10")),
                        detail="Share of regular income not spent (investments count as savings). Target ≥ 20%."),
        HealthIndicator(key="runway", label="Emergency runway", value=runway, unit="months",
                        status=_status(runway, Decimal("6"), Decimal("3")),
                        detail="Months your current balance covers average spending. Target ≥ 6 months."),
        HealthIndicator(key="fixed_cost_ratio", label="Fixed-cost ratio", value=fixed, unit="percent",
                        status=_status(fixed, Decimal("0.50"), Decimal("0.65"), higher_is_better=False),
                        detail="Recurring commitments (incl. SIPs) as a share of regular income."),
        HealthIndicator(key="subscription_load", label="Subscription load", value=subs, unit="percent",
                        status=_status(subs, Decimal("0.05"), Decimal("0.08"), higher_is_better=False),
                        detail="Subscriptions as a share of regular income."),
        HealthIndicator(key="projected_low", label="Lowest projected balance", value=forecast.min_balance, unit="currency",
                        status="good" if forecast.min_balance >= buffer else "watch" if forecast.min_balance >= 0 else "risk",
                        detail=f"Lowest point in the next {forecast.assumptions.horizon_days} days vs. your safety buffer."),
    ]
