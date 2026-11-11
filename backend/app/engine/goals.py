"""Goal solver — answers the simulator's questions *backwards*.

    "What's the most I can spend (today / this month) and stay above my buffer?"
    "When is the earliest safe date to buy something that costs X?"

A one-off purchase of X on day d lowers every balance from d onward by exactly X, so the
largest safe amount on day d has a closed form — no search, no approximation:

    max_safe(d) = min(balance[d .. d + horizon]) - safety_buffer        (floored at 0)

The window after d is the full forecast horizon, the same fairness rule the timing
optimiser uses, so a late date can't look safe just because the forecast ended.
"""
from datetime import date, timedelta
from decimal import ROUND_FLOOR, Decimal

from pydantic import BaseModel

from app.core.money import ZERO, money
from app.engine.forecast import baseline_events, project
from app.engine.simulation import fmt_date, inr
from app.engine.twin import FinancialProfile
from app.engine.types import Assumptions, Money


class AffordabilityPoint(BaseModel):
    on: date
    day: int
    max_safe_spend: Money
    limiting_date: date  # the future day whose low balance caps the amount
    is_income_day: bool


class EarliestSafeDate(BaseModel):
    amount: Money
    found: bool
    on: date | None
    days_from_now: int | None
    max_safe_today: Money
    shortfall_today: Money
    explanation: str


class Affordability(BaseModel):
    as_of: date
    assumptions: Assumptions
    search_days: int
    max_safe_today: Money
    limiting_date_today: date
    month_end: date
    best_this_month: AffordabilityPoint
    best_in_window: AffordabilityPoint
    curve: list[AffordabilityPoint]
    earliest: EarliestSafeDate | None
    explanation: list[str]


def _floor_rupee(v: Decimal) -> Decimal:
    return money(max(ZERO, v).quantize(Decimal("1"), rounding=ROUND_FLOOR))


def affordability_curve(profile: FinancialProfile, a: Assumptions, search_days: int) -> list[AffordabilityPoint]:
    horizon = search_days + a.horizon_days
    fc = project(profile.current_balance, profile.as_of, baseline_events(profile, a, horizon), a, horizon)
    balances = [p.balance for p in fc.points]
    out: list[AffordabilityPoint] = []
    for d in range(search_days + 1):
        window = range(d, d + a.horizon_days + 1)
        low_idx = min(window, key=lambda i: (balances[i], i))
        out.append(AffordabilityPoint(
            on=fc.points[d].on,
            day=d,
            max_safe_spend=_floor_rupee(balances[low_idx] - a.safety_buffer),
            limiting_date=fc.points[low_idx].on,
            is_income_day=any(e.kind == "income" for e in fc.points[d].events),
        ))
    return out


def earliest_safe_date(curve: list[AffordabilityPoint], amount: Decimal, profile: FinancialProfile) -> EarliestSafeDate:
    amount = money(amount)
    today = curve[0]
    hit = next((p for p in curve if p.max_safe_spend >= amount), None)
    shortfall = money(max(ZERO, amount - today.max_safe_spend))
    if hit is None:
        best = max(curve, key=lambda p: (p.max_safe_spend, -p.day))
        surplus = money(profile.monthly_income - profile.avg_monthly_spending - profile.avg_monthly_investments)
        gap = money(amount - best.max_safe_spend)
        tail = (f" At your monthly surplus of {inr(surplus)} that gap closes in about "
                f"{(gap / surplus).quantize(Decimal('0.1'))} month(s)." if surplus > 0 else "")
        return EarliestSafeDate(
            amount=amount, found=False, on=None, days_from_now=None, max_safe_today=today.max_safe_spend,
            shortfall_today=shortfall,
            explanation=(f"No date in the next {len(curve) - 1} days keeps you above your buffer after spending "
                         f"{inr(amount)}. The most you could safely spend is {inr(best.max_safe_spend)} "
                         f"on {fmt_date(best.on)}, {inr(gap)} short.{tail}"),
        )
    when = "today" if hit.day == 0 else f"on {fmt_date(hit.on)} ({hit.day} day(s) from now)"
    return EarliestSafeDate(
        amount=amount, found=True, on=hit.on, days_from_now=hit.day, max_safe_today=today.max_safe_spend,
        shortfall_today=shortfall,
        explanation=(f"The earliest safe date to spend {inr(amount)} is {when}." if hit.day == 0 else
                     f"The earliest safe date to spend {inr(amount)} is {when}. Today you could safely spend "
                     f"up to {inr(today.max_safe_spend)}, which is {inr(shortfall)} short."),
    )


def solve_affordability(profile: FinancialProfile, a: Assumptions, search_days: int = 60,
                        amount: Decimal | None = None) -> Affordability:
    curve = affordability_curve(profile, a, search_days)
    today = curve[0]
    nxt = profile.as_of.replace(day=28) + timedelta(days=4)
    month_end = nxt - timedelta(days=nxt.day)
    in_month = [p for p in curve if p.on <= month_end]
    pick = lambda pts: max(pts, key=lambda p: (p.max_safe_spend, -p.day))  # noqa: E731
    best_month, best_all = pick(in_month), pick(curve)

    lines = [
        f"Today you can spend up to {inr(today.max_safe_spend)} and stay above your {inr(a.safety_buffer)} "
        f"buffer. The tightest point is {fmt_date(today.limiting_date)}.",
    ]
    if best_month.day > 0 and best_month.max_safe_spend > today.max_safe_spend:
        lines.append(f"This month the most you can spend is {inr(best_month.max_safe_spend)}, if you buy on "
                     f"{fmt_date(best_month.on)}.")
    if best_all.on > month_end and best_all.max_safe_spend > best_month.max_safe_spend:
        lines.append(f"In the next {search_days} days your spending room peaks at {inr(best_all.max_safe_spend)} on "
                     f"{fmt_date(best_all.on)}.")
    earliest = earliest_safe_date(curve, amount, profile) if amount is not None and amount > 0 else None
    if earliest:
        lines.append(earliest.explanation)
    return Affordability(
        as_of=profile.as_of, assumptions=a, search_days=search_days, max_safe_today=today.max_safe_spend,
        limiting_date_today=today.limiting_date, month_end=month_end, best_this_month=best_month,
        best_in_window=best_all, curve=curve, earliest=earliest, explanation=lines,
    )
