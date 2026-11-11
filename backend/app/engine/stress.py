"""Stress testing: how resilient are your finances to shocks?

Two parts, both labelled as estimates:

1. Shock library: each shock is an ordinary scenario (same engine as the simulator) such as
   job loss, a pay cut, a medical emergency, living costs +30%, a late salary or (for foreign
   income) a currency drop. Reported: lowest balance, days under the buffer, and whether you
   stay solvent and above the buffer.
2. Spending uncertainty (Monte Carlo): spending varies. Each simulated path scales every 30-day block
   by a "how heavy is this month" factor and every day by a day-level factor; both spreads come from
   your own history (month-to-month and day-to-day coefficients of variation of variable spending).
   The seed is fixed, so the same data always gives the same bands. Reported: 10th/50th/90th percentile balance per day and the share of paths
   that dip under the buffer or below zero.

Resilience label (explicit thresholds): strong = runway ≥ 3 months, ≤ 10% chance under buffer and
every shock survived (≥ 0); fragile = runway < 1 month, or > 40% chance under buffer, or half or
more shocks go negative; otherwise moderate.
"""
import math
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean, pstdev
from typing import Literal

from pydantic import BaseModel

from app.core.money import money, total
from app.engine.forecast import baseline_events, project
from app.engine.scenarios import (
    ExpenseIncrease, FxChange, IncomeDelay, IncomeLoss, UnexpectedPayment, simulate_scenario,
)
from app.engine.simulation import fmt_date, inr
from app.engine.twin import FinancialProfile
from app.engine.types import Assumptions, Money, Txn

PATHS = 400
SEED = 7
MIN_CV, MAX_CV = 0.15, 1.5
MIN_MONTH_CV, MAX_MONTH_CV = 0.10, 0.60


class ShockResult(BaseModel):
    id: str
    name: str
    description: str
    changes: list[dict]
    min_balance: Money
    min_balance_date: date
    first_below_buffer: date | None
    first_below_zero: date | None
    days_below_buffer: int
    end_balance: Money
    solvent: bool  # never below zero
    above_buffer: bool


class Band(BaseModel):
    on: date
    p10: Money
    p50: Money
    p90: Money
    baseline: Money


class StressReport(BaseModel):
    as_of: date
    assumptions: Assumptions
    runway_months: Decimal  # months the balance lasts with no income (savings paused)
    monthly_burn: Money
    shocks: list[ShockResult]
    shocks_survived: int
    bands: list[Band]
    paths: int
    spending_cv: Decimal  # day-to-day
    monthly_cv: Decimal  # month-to-month
    chance_below_buffer: Decimal  # share of paths
    chance_below_zero: Decimal
    p10_lowest: Money
    resilience: Literal["strong", "moderate", "fragile"]
    summary: list[str]
    disclaimer: str = ("Estimates, not predictions. Shocks hold everything else constant; the spending ranges use your own "
                       "past variability with a fixed random seed.")


def _shock_library(profile: FinancialProfile) -> list[tuple[str, str, str, list]]:
    monthly = profile.monthly_income
    medical = money(max(Decimal("25000"), (monthly * Decimal("0.75")).quantize(Decimal("1000"))))
    shocks = [
        ("job_loss_1", "Job loss: 1 month", "No regular income for the next month.", [IncomeLoss(months=1)]),
        ("job_loss_3", "Job loss: 3 months", "No regular income for the next three months.", [IncomeLoss(months=3)]),
        ("pay_cut", "Pay cut of 30%", "Regular income is 30% lower for three months.",
         [IncomeLoss(months=3, percent=Decimal("30"))]),
        ("medical", f"Medical emergency ({inr(medical)})", "An unplanned bill today, about three quarters of a month's income.",
         [UnexpectedPayment(amount=medical, label="Medical emergency")]),
        ("costs_up", "Living costs +30%", "Day-to-day spending rises 30% (prices, a new city, a family change).",
         [ExpenseIncrease(percent=Decimal("30"))]),
        ("late_30", "Income 30 days late", "Your next regular payment arrives a month late.", [IncomeDelay(days=30)]),
    ]
    foreign = sorted({r.currency for r in profile.recurring_income if r.currency})
    for cur in foreign[:1]:
        shocks.append((f"fx_{cur.lower()}", f"{cur}/INR drops 10%", f"Your {cur} income is worth 10% less.",
                       [FxChange(percent=Decimal("-10"), currency=cur)]))
    return shocks


def _spending_cv(txns: list[Txn], profile: FinancialProfile, a: Assumptions) -> float:
    """Variability of daily variable spending over the look-back window (non-recurring debits)."""
    recurring = {r.merchant.strip().lower() for r in profile.recurring_outflows}
    start = profile.as_of - timedelta(days=a.lookback_days)
    by_day: dict[date, float] = {start + timedelta(days=i): 0.0 for i in range(a.lookback_days)}
    for t in txns:
        if t.amount < 0 and start <= t.posted_on < profile.as_of and t.merchant.strip().lower() not in recurring \
                and t.category not in ("Investments", "Transfer"):
            by_day[t.posted_on] += float(-t.amount)
    values = list(by_day.values())
    avg = mean(values) if values else 0.0
    return min(MAX_CV, max(MIN_CV, pstdev(values) / avg)) if avg > 0 else MIN_CV


def _monthly_cv(txns: list[Txn], profile: FinancialProfile) -> float:
    """Variability between whole months of variable spending (30-day windows over the history).

    Day-level noise averages out over a quarter; real overspending tends to come in bad months, so
    each simulated 30-day block also gets its own factor with this spread.
    """
    recurring = {r.merchant.strip().lower() for r in profile.recurring_outflows}
    windows = [0.0] * 6
    for t in txns:
        idx = (profile.as_of - t.posted_on).days - 1
        if t.amount < 0 and 0 <= idx < 180 and t.merchant.strip().lower() not in recurring \
                and t.category not in ("Investments", "Transfer"):
            windows[idx // 30] += float(-t.amount)
    used = [w for w in windows if w > 0]
    if len(used) < 2:
        return MIN_MONTH_CV
    return min(MAX_MONTH_CV, max(MIN_MONTH_CV, pstdev(used) / mean(used)))


def _floored_mean(sigma: float, floor: float) -> float:
    """E[max(floor, X)] for X ~ N(1, sigma). Dividing by it keeps clipped random factors unbiased (mean 1)."""
    z = (1.0 - floor) / sigma
    phi = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return floor + (1.0 - floor) * cdf + sigma * phi


def _pct(sorted_vals: list[float], q: float) -> float:
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def _m(x: float) -> Decimal:
    return money(Decimal(str(round(x, 2))))


def stress_test(profile: FinancialProfile, txns: list[Txn], a: Assumptions) -> StressReport:
    h, buf = a.horizon_days, a.safety_buffer
    shocks: list[ShockResult] = []
    for sid, name, desc, changes in _shock_library(profile):
        r = simulate_scenario(profile, a, changes, name)
        s = r.simulated
        shocks.append(ShockResult(
            id=sid, name=name, description=desc, changes=[c.model_dump(mode="json") for c in changes],
            min_balance=s.min_balance, min_balance_date=s.min_balance_date, first_below_buffer=s.first_below_buffer,
            first_below_zero=s.first_below_zero, days_below_buffer=s.days_below_buffer, end_balance=s.end_balance,
            solvent=s.first_below_zero is None, above_buffer=s.min_balance >= buf))
    survived = sum(1 for s in shocks if s.solvent)

    # Monte Carlo on variable spend: balance = (projection without variable spend) - cumulative random spend.
    events = baseline_events(profile, a)
    fixed = project(profile.current_balance, profile.as_of, [e for e in events if e.kind != "variable"], a)
    base = project(profile.current_balance, profile.as_of, events, a)
    daily = float(base.daily_variable_spend)
    cv, month_cv = _spending_cv(txns, profile, a), _monthly_cv(txns, profile)
    rng = random.Random(SEED)
    day_norm, month_norm = _floored_mean(cv, 0.0), _floored_mean(month_cv, 0.3)
    paths: list[list[float]] = []
    for _ in range(PATHS):
        spent, path, block = 0.0, [], 1.0
        for i, p in enumerate(fixed.points):
            if i % 30 == 0:  # a new month: draw how heavy this month's spending is
                block = max(0.3, rng.gauss(1.0, month_cv)) / month_norm
            spent += daily * block * max(0.0, rng.gauss(1.0, cv)) / day_norm
            path.append(float(p.balance) - spent)
        paths.append(path)
    bands = []
    for i, p in enumerate(fixed.points):
        col = sorted(path[i] for path in paths)
        bands.append(Band(on=p.on, p10=_m(_pct(col, 0.10)), p50=_m(_pct(col, 0.50)), p90=_m(_pct(col, 0.90)),
                          baseline=base.points[i].balance))
    lows = sorted(min(path) for path in paths)
    below_buf = Decimal(sum(1 for x in lows if x < float(buf))) / PATHS
    below_zero = Decimal(sum(1 for x in lows if x < 0)) / PATHS

    burn = total([r.amount for r in profile.recurring_outflows if r.kind != "savings"] + [profile.variable_monthly])
    runway = (profile.current_balance / burn).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if burn > 0 else Decimal("0")

    if runway < 1 or below_buf > Decimal("0.4") or survived * 2 <= len(shocks):
        label = "fragile"
    elif runway >= 3 and below_buf <= Decimal("0.1") and survived == len(shocks):
        label = "strong"
    else:
        label = "moderate"
    worst = min(shocks, key=lambda s: s.min_balance)
    lines = [
        f"With no income at all, your {inr(profile.current_balance)} lasts about {runway} month(s) at {inr(burn)}/month "
        "of bills and day-to-day spending (savings paused).",
        f"Across {PATHS} simulated spending paths, {(below_buf * 100).quantize(Decimal('1'))}% dip below your "
        f"{inr(buf)} buffer and {(below_zero * 100).quantize(Decimal('1'))}% go negative in the next {h} days.",
        f"You stay solvent in {survived} of {len(shocks)} shocks. The hardest is {worst.name}: lowest "
        f"{inr(worst.min_balance)} on {fmt_date(worst.min_balance_date)}.",
    ]
    if runway < 3:
        target = money(burn * 3 - profile.current_balance)
        lines.append(f"A 3-month emergency fund would need about {inr(target)} more.")
    return StressReport(
        as_of=profile.as_of, assumptions=a, runway_months=runway, monthly_burn=burn, shocks=shocks,
        shocks_survived=survived, bands=bands, paths=PATHS, spending_cv=Decimal(str(round(cv, 3))),
        monthly_cv=Decimal(str(round(month_cv, 3))),
        chance_below_buffer=below_buf.quantize(Decimal("0.001")), chance_below_zero=below_zero.quantize(Decimal("0.001")),
        p10_lowest=_m(_pct(lows, 0.10)), resilience=label, summary=lines)
