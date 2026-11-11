"""Deterministic daily cash-flow forecast.

Balance(day) = Balance(day-1) + Σ events(day). Events come from:
  • detected recurring income/outflows on their typical day of month,
  • known obligations on their due dates,
  • estimated variable (day-to-day) spending spread evenly per day,
  • optional scenario overlays (see simulation.py).
Day 0 is `as_of` (today); history runs up to yesterday.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel

from app.core.money import ZERO, money
from app.engine.twin import WINDOW, FinancialProfile
from app.engine.types import Assumptions, CashEvent, Money, add_months


class DayPoint(BaseModel):
    on: date
    day: int
    balance: Money
    inflow: Money
    outflow: Money
    events: list[CashEvent]  # discrete events (variable spend omitted for brevity)


class Forecast(BaseModel):
    start_date: date
    start_balance: Money
    assumptions: Assumptions
    points: list[DayPoint]
    end_balance: Money
    min_balance: Money
    min_balance_date: date
    total_inflow: Money
    total_outflow: Money
    daily_variable_spend: Money
    first_below_buffer: date | None
    first_below_zero: date | None
    days_below_buffer: int

    def balance_on_day(self, day: int) -> Decimal:
        return self.points[min(day, len(self.points) - 1)].balance


def daily_variable_spend(profile: FinancialProfile, a: Assumptions) -> Decimal:
    return money(profile.variable_monthly * a.variable_spend_multiplier / WINDOW)


def baseline_events(profile: FinancialProfile, a: Assumptions, horizon_days: int | None = None) -> list[CashEvent]:
    start = profile.as_of
    end = start + timedelta(days=horizon_days if horizon_days is not None else a.horizon_days)
    events: list[CashEvent] = []

    for item in profile.recurring_income + profile.recurring_outflows:
        d = item.next_date
        while d <= end:
            if d >= start:
                events.append(
                    CashEvent(
                        on=d,
                        amount=item.amount if item.direction == "in" else -item.amount,
                        label=item.name,
                        category=item.category,
                        kind="income" if item.direction == "in" else "recurring",
                        ref=item.key,
                    )
                )
            d = add_months(d, 1, item.day_of_month)

    if a.include_obligations:
        for o in profile.obligations:
            if start <= o.due_on <= end:
                events.append(CashEvent(on=o.due_on, amount=-o.amount, label=o.title, category=o.category, kind="obligation"))

    if a.include_irregular_income and profile.irregular_income_lookback > 0:
        per_day = money(profile.irregular_income_lookback / max(1, a.lookback_days))
        d = start
        while d <= end:
            events.append(CashEvent(on=d, amount=per_day, label="Irregular income (avg)", category="Other Income", kind="income"))
            d += timedelta(days=1)

    per_day = daily_variable_spend(profile, a)
    if per_day > 0:
        d = start
        while d <= end:
            events.append(CashEvent(on=d, amount=-per_day, label="Day-to-day spending (estimated)", category="Variable", kind="variable"))
            d += timedelta(days=1)
    return events


def project(
    start_balance: Decimal, as_of: date, events: list[CashEvent], a: Assumptions, horizon_days: int | None = None
) -> Forecast:
    horizon = horizon_days if horizon_days is not None else a.horizon_days
    by_day: dict[date, list[CashEvent]] = defaultdict(list)
    for e in events:
        by_day[e.on].append(e)

    balance = money(start_balance)
    points: list[DayPoint] = []
    tot_in = tot_out = ZERO
    first_buf = first_zero = None
    below = 0
    variable = ZERO
    for i in range(horizon + 1):
        d = as_of + timedelta(days=i)
        day_events = by_day.get(d, [])
        inflow = sum((e.amount for e in day_events if e.amount > 0), ZERO)
        outflow = sum((-e.amount for e in day_events if e.amount < 0), ZERO)
        variable = next((-e.amount for e in day_events if e.kind == "variable"), variable)
        balance = money(balance + inflow - outflow)
        tot_in += inflow
        tot_out += outflow
        if balance < a.safety_buffer:
            below += 1
            first_buf = first_buf or d
        if balance < 0:
            first_zero = first_zero or d
        discrete = sorted((e for e in day_events if e.kind != "variable"), key=lambda e: e.amount)
        points.append(DayPoint(on=d, day=i, balance=balance, inflow=money(inflow), outflow=money(outflow), events=discrete))

    low = min(points, key=lambda p: (p.balance, p.on))
    return Forecast(
        start_date=as_of,
        start_balance=money(start_balance),
        assumptions=a,
        points=points,
        end_balance=points[-1].balance,
        min_balance=low.balance,
        min_balance_date=low.on,
        total_inflow=money(tot_in),
        total_outflow=money(tot_out),
        daily_variable_spend=money(variable),
        first_below_buffer=first_buf,
        first_below_zero=first_zero,
        days_below_buffer=below,
    )


def forecast_baseline(profile: FinancialProfile, a: Assumptions) -> Forecast:
    return project(profile.current_balance, profile.as_of, baseline_events(profile, a), a)
