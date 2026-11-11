"""Composable what-if scenarios.

A scenario is a list of *changes*. Each change rewrites the baseline event list (removes,
shifts, scales or adds cash events), and the result is projected with the same deterministic
engine, so every figure traces back to transactions plus explicit assumptions. Changes stack:
"cancel 3 subscriptions *and* my salary is 15 days late" is one scenario with two changes.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.core.money import ZERO, money, total
from app.engine.forecast import Forecast, baseline_events, project
from app.engine.simulation import Impact, Risk, fmt_date, inr
from app.engine.twin import FinancialProfile, RecurringItem
from app.engine.types import Assumptions, CashEvent, Money, add_months


class PurchaseChange(BaseModel):
    type: Literal["purchase"] = "purchase"
    amount: Money = Field(gt=0, le=Decimal("100000000"))
    on: date | None = None  # default today
    label: str = Field("Purchase", max_length=80)


class CancelSubscriptions(BaseModel):
    type: Literal["cancel_subscriptions"] = "cancel_subscriptions"
    names: list[str] = Field(default_factory=list, max_length=20, description="Merchant names or recurring keys")
    count: int | None = Field(None, ge=1, le=20, description="Cancel the N most expensive subscriptions")


class IncomeDelay(BaseModel):
    type: Literal["income_delay"] = "income_delay"
    days: int = Field(ge=1, le=90)
    all_future: bool = False  # False: only the next income payment is late
    merchant: str | None = Field(None, max_length=120, description="Only this payer (e.g. one client) is late")


class IncreaseSavings(BaseModel):
    type: Literal["increase_savings"] = "increase_savings"
    percent: Money = Field(gt=0, le=Decimal("500"))


class ExpenseIncrease(BaseModel):
    type: Literal["expense_increase"] = "expense_increase"
    percent: Money = Field(ge=Decimal("-90"), le=Decimal("300"))


class AddSubscription(BaseModel):
    """What if I subscribe? A new monthly charge from `start` (default today) on the same day each month."""

    type: Literal["add_subscription"] = "add_subscription"
    amount: Money = Field(gt=0, le=Decimal("10000000"), description="Monthly price")
    label: str = Field("New subscription", max_length=80)
    start: date | None = None


class IncomeLoss(BaseModel):
    """Job loss or a pay cut: regular income drops by `percent` for the next `months` months."""

    type: Literal["income_loss"] = "income_loss"
    months: int = Field(1, ge=1, le=12)
    percent: Money = Field(Decimal("100"), gt=0, le=Decimal("100"))


class FxChange(BaseModel):
    """What if the exchange rate moves? Scales future recurring income received in `currency`.

    +3 means 1 USD buys 3% more INR (rupee weakens); -3 means USD/INR drops 3% (rupee strengthens).
    """

    type: Literal["fx_change"] = "fx_change"
    percent: Money = Field(ge=Decimal("-50"), le=Decimal("50"))
    currency: str = Field("USD", pattern=r"^[A-Z]{3}$")


class UnexpectedPayment(BaseModel):
    type: Literal["unexpected_payment"] = "unexpected_payment"
    amount: Money = Field(gt=0, le=Decimal("100000000"))
    on: date | None = None
    label: str = Field("Unexpected payment", max_length=80)


Change = Annotated[
    Union[PurchaseChange, CancelSubscriptions, IncomeDelay, IncreaseSavings, ExpenseIncrease, UnexpectedPayment,
          AddSubscription, FxChange, IncomeLoss],
    Field(discriminator="type"),
]


class AppliedChange(BaseModel):
    type: str
    description: str
    monthly_effect: Money  # + = more money each month, - = less (0 for one-offs)
    one_off_effect: Money


class ScenarioResult(BaseModel):
    as_of: date
    title: str
    assumptions: Assumptions
    applied: list[AppliedChange]
    notes: list[str]
    baseline: Forecast
    simulated: Forecast
    impacts: list[Impact]
    monthly_effect: Money
    risks: list[Risk]
    summary: list[str]


def _subs(profile: FinancialProfile) -> list[RecurringItem]:
    return sorted((r for r in profile.recurring_outflows if r.kind == "subscription"), key=lambda r: -r.amount)


def resolve_subscriptions(profile: FinancialProfile, change: CancelSubscriptions) -> tuple[list[RecurringItem], list[str]]:
    subs, notes, picked = _subs(profile), [], []
    for name in change.names:
        n = name.strip().lower()
        match = next((s for s in subs if n and (n == s.key or n in s.merchant.lower() or n in s.name.lower())), None)
        if match and match not in picked:
            picked.append(match)
        elif not match:
            notes.append(f"No active subscription matched '{name}'.")
    if change.count:  # named ones count toward N; fill the rest with the most expensive
        for s in subs:
            if len(picked) >= change.count:
                break
            if s not in picked:
                picked.append(s)
        if len(subs) < change.count:
            notes.append(f"Only {len(subs)} active subscription(s) were detected.")
    return picked, notes


def apply_changes(profile: FinancialProfile, a: Assumptions, changes: list, horizon: int
                  ) -> tuple[list[CashEvent], list[AppliedChange], list[str]]:
    as_of = profile.as_of
    end = as_of + timedelta(days=horizon)
    events = baseline_events(profile, a, horizon)
    applied: list[AppliedChange] = []
    notes: list[str] = []

    for c in changes:
        if isinstance(c, (PurchaseChange, UnexpectedPayment)):
            on = c.on or as_of
            if not as_of <= on <= end:
                raise ValueError(f"{c.label} date must be between {as_of} and {end}")
            events.append(CashEvent(on=on, amount=-c.amount, label=c.label,
                                    category="Shopping" if c.type == "purchase" else "Other", kind="scenario"))
            applied.append(AppliedChange(type=c.type, description=f"{c.label}: {inr(c.amount)} on {fmt_date(on)}",
                                         monthly_effect=ZERO, one_off_effect=-c.amount))

        elif isinstance(c, CancelSubscriptions):
            picked, n = resolve_subscriptions(profile, c)
            notes += n
            keys = {s.key for s in picked}
            events = [e for e in events if e.ref not in keys]
            if picked:
                saved = total(s.amount for s in picked)
                applied.append(AppliedChange(
                    type=c.type, monthly_effect=saved, one_off_effect=ZERO,
                    description=f"Cancel {', '.join(s.merchant for s in picked)} (saves {inr(saved)}/month)"))

        elif isinstance(c, IncomeDelay):
            payers = None
            if c.merchant:
                m = c.merchant.strip().lower()
                payers = {r.key for r in profile.recurring_income if m in r.merchant.lower() or m == r.key}
            income = sorted((e for e in events if e.kind == "income" and e.ref and (payers is None or e.ref in payers)),
                            key=lambda e: e.on)
            targets = income if c.all_future else income[:1]
            ids = {id(e) for e in targets}
            moved = [e.model_copy(update={"on": e.on + timedelta(days=c.days)}) for e in targets]
            events = [e for e in events if id(e) not in ids] + [e for e in moved if e.on <= end]
            if targets:
                payer = next((r.merchant for r in profile.recurring_income if r.key == targets[0].ref), "income")
                who = f"{payer}'s payment" if c.merchant else "income"
                what = (f"every {payer} payment" if c.merchant else "every income payment") if c.all_future \
                    else f"{who} due {fmt_date(targets[0].on)}"
                applied.append(AppliedChange(type=c.type, monthly_effect=ZERO, one_off_effect=ZERO,
                                             description=f"Delay {what} by {c.days} days"))
            elif c.merchant:
                notes.append(f"No regular income from '{c.merchant}' was detected, so there is nothing to delay.")
            else:
                notes.append("No regular income was detected, so there is nothing to delay.")

        elif isinstance(c, IncreaseSavings):
            savings = [r for r in profile.recurring_outflows if r.kind == "savings"]
            pct = c.percent / Decimal(100)
            if savings:
                keys = {r.key for r in savings}
                extra = [e.model_copy(update={"amount": money(e.amount * pct), "label": f"{e.label} (+{c.percent}%)"})
                         for e in events if e.ref in keys]
                monthly = money(total(r.amount for r in savings) * pct)
                desc = f"Raise monthly savings by {c.percent}% (+{inr(monthly)}/month to investments)"
            else:
                monthly = money(profile.monthly_income * pct)
                extra = [CashEvent(on=e.on, amount=-monthly, label="New savings", category="Investments", kind="scenario")
                         for e in events if e.kind == "income" and e.ref]
                desc = f"Start saving {c.percent}% of regular income ({inr(monthly)}/month)"
                notes.append("No existing savings were detected, so the percentage is applied to regular income.")
            events += extra
            applied.append(AppliedChange(type=c.type, description=desc, monthly_effect=-monthly, one_off_effect=ZERO))
            notes.append("Savings still belong to you, but they leave your spendable balance in this projection.")

        elif isinstance(c, AddSubscription):
            start = c.start or as_of
            if not as_of <= start <= end:
                raise ValueError(f"{c.label} must start between {as_of} and {end}")
            d, k = start, 0
            while d <= end:
                events.append(CashEvent(on=d, amount=-c.amount, label=c.label, category="Subscriptions", kind="scenario"))
                k += 1
                d = add_months(start, k, start.day)
            when = "today" if start == as_of else f"from {fmt_date(start)}"
            applied.append(AppliedChange(type=c.type, monthly_effect=-c.amount, one_off_effect=ZERO,
                                         description=f"Subscribe to {c.label} at {inr(c.amount)}/month, starting {when}"))

        elif isinstance(c, IncomeLoss):
            until = add_months(as_of, c.months, as_of.day)
            pct = c.percent / Decimal(100)
            hit = [e for e in events if e.kind == "income" and e.ref and e.on < until]
            events += [e.model_copy(update={"amount": -money(e.amount * pct), "label": "Income lost"}) for e in hit]
            lost = total(e.amount for e in hit) * pct
            what = "Lose all regular income" if c.percent == 100 else f"Regular income cut by {c.percent}%"
            applied.append(AppliedChange(type=c.type, monthly_effect=ZERO, one_off_effect=-money(lost),
                                         description=f"{what} for {c.months} month(s) ({inr(lost)} less)"))
            if not hit:
                notes.append("No regular income falls in that period, so this changes nothing.")

        elif isinstance(c, FxChange):
            foreign = [r for r in profile.recurring_income if r.currency == c.currency]
            if not foreign:
                notes.append(f"No regular income in {c.currency} was detected, so an exchange-rate move changes nothing.")
                continue
            keys, pct = {r.key for r in foreign}, c.percent / Decimal(100)
            events += [e.model_copy(update={"amount": money(e.amount * pct), "label": f"{c.currency}/INR move"})
                       for e in events if e.kind == "income" and e.ref in keys]
            monthly = money(total(r.amount for r in foreign) * pct)
            pair = f"{c.currency}/INR"
            applied.append(AppliedChange(
                type=c.type, monthly_effect=monthly, one_off_effect=ZERO,
                description=f"{pair} {'rises' if c.percent > 0 else 'drops'} {abs(c.percent)}%: your {c.currency} income "
                            f"is worth {'+' if monthly >= 0 else '-'}{inr(abs(monthly))}/month"))

        elif isinstance(c, ExpenseIncrease):
            pct = c.percent / Decimal(100)
            events += [e.model_copy(update={"amount": money(e.amount * pct), "label": "Spending change"})
                       for e in events if e.kind == "variable"]
            monthly = money(profile.variable_monthly * pct)
            word = "Increase" if c.percent > 0 else "Reduce"
            applied.append(AppliedChange(type=c.type, monthly_effect=-monthly, one_off_effect=ZERO,
                                         description=f"{word} day-to-day spending by {abs(c.percent)}% "
                                                     f"({'+' if monthly > 0 else '-'}{inr(abs(monthly))}/month)"))
    return events, applied, notes


class ComparedScenario(BaseModel):
    id: str
    name: str
    applied: list[AppliedChange]
    notes: list[str]
    series: list[Money]
    end_balance: Money
    end_delta: Money  # vs baseline, at the end of the horizon
    min_balance: Money
    min_balance_date: date
    first_below_buffer: date | None
    days_below_buffer: int
    safe: bool
    monthly_effect: Money
    impacts: list[Impact]
    best: bool = False


class ScenarioComparison(BaseModel):
    as_of: date
    assumptions: Assumptions
    dates: list[date]
    baseline_series: list[Money]
    baseline_end: Money
    baseline_min: Money
    scenarios: list[ComparedScenario]
    best_id: str | None
    summary: list[str]


def compare_scenarios(profile: FinancialProfile, a: Assumptions, named: list[tuple[str, list]]) -> ScenarioComparison:
    """Project up to four scenarios on the same baseline. Best = highest end balance among those that never dip
    below the safety buffer; if none are safe, nothing is marked best and the least risky one is named."""
    if not 1 <= len(named) <= 4:
        raise ValueError("Compare between 1 and 4 scenarios")
    results = [(f"s{i + 1}", name, simulate_scenario(profile, a, changes, name)) for i, (name, changes) in enumerate(named)]
    base = results[0][2].baseline
    out = [ComparedScenario(
        id=sid, name=name, applied=r.applied, notes=r.notes, series=[p.balance for p in r.simulated.points],
        end_balance=r.simulated.end_balance, end_delta=money(r.simulated.end_balance - base.end_balance),
        min_balance=r.simulated.min_balance, min_balance_date=r.simulated.min_balance_date,
        first_below_buffer=r.simulated.first_below_buffer, days_below_buffer=r.simulated.days_below_buffer,
        safe=r.simulated.min_balance >= a.safety_buffer, monthly_effect=r.monthly_effect, impacts=r.impacts,
    ) for sid, name, r in results]

    safe = [s for s in out if s.safe]
    best = max(safe, key=lambda s: (s.end_balance, s.min_balance)) if safe else None
    lines: list[str] = []
    if best:
        best.best = True
        vs = ("level with today's plan" if best.end_delta == 0 else
              f"{'+' if best.end_delta > 0 else '-'}{inr(abs(best.end_delta))} vs today's plan")
        lines.append(f"Best: {best.name}. It ends at {inr(best.end_balance)} in {a.horizon_days} days ({vs}) and never "
                     f"dips below your {inr(a.safety_buffer)} buffer.")
    else:
        least = max(out, key=lambda s: s.min_balance)
        lines.append(f"None of these stay above your {inr(a.safety_buffer)} buffer. The least risky is {least.name}, "
                     f"bottoming at {inr(least.min_balance)} on {fmt_date(least.min_balance_date)}.")
    for s in out:
        if s is best:
            continue
        lines.append(f"{s.name}: ends at {inr(s.end_balance)}, " + (
            f"lowest {inr(s.min_balance)} on {fmt_date(s.min_balance_date)}." if s.safe else
            f"dips below your buffer on {fmt_date(s.first_below_buffer)} for {s.days_below_buffer} day(s)."))
    return ScenarioComparison(as_of=profile.as_of, assumptions=a, dates=[p.on for p in base.points],
                              baseline_series=[p.balance for p in base.points], baseline_end=base.end_balance,
                              baseline_min=base.min_balance, scenarios=out, best_id=best.id if best else None,
                              summary=lines)


def simulate_scenario(profile: FinancialProfile, a: Assumptions, changes: list, title: str | None = None) -> ScenarioResult:
    if not changes:
        raise ValueError("A scenario needs at least one change")
    h = a.horizon_days
    events, applied, notes = apply_changes(profile, a, changes, h)
    baseline = project(profile.current_balance, profile.as_of, baseline_events(profile, a, h), a, h)
    simulated = project(profile.current_balance, profile.as_of, events, a, h)
    impacts = [Impact(day=d, on=baseline.points[d].on, baseline=baseline.balance_on_day(d),
                      scenario=simulated.balance_on_day(d),
                      delta=money(simulated.balance_on_day(d) - baseline.balance_on_day(d)))
               for d in (30, 60, 90) if d <= h]
    monthly = total(c.monthly_effect for c in applied)
    buf = a.safety_buffer

    risks: list[Risk] = []
    if simulated.first_below_zero:
        risks.append(Risk(level="critical", title="Projected overdraft",
                          detail=f"Balance goes negative on {fmt_date(simulated.first_below_zero)} "
                                 f"(lowest {inr(simulated.min_balance)})."))
    elif simulated.min_balance < buf:
        risks.append(Risk(level="high", title="Below safety buffer",
                          detail=f"Balance falls under {inr(buf)} on {fmt_date(simulated.first_below_buffer)} "
                                 f"for {simulated.days_below_buffer} day(s)."))
    if baseline.min_balance >= buf > simulated.min_balance:
        risks.append(Risk(level="medium", title="This scenario creates the shortfall",
                          detail=f"Without these changes your balance stays above {inr(buf)}."))
    if not risks:
        risks.append(Risk(level="low", title="No liquidity stress detected",
                          detail=f"Balance stays above {inr(buf)} for the next {h} days."))

    end_delta = money(simulated.end_balance - baseline.end_balance)
    summary = [
        "Changes: " + "; ".join(c.description for c in applied) + "." if applied else "No changes could be applied.",
        f"In {h} days your balance would be {inr(simulated.end_balance)} instead of {inr(baseline.end_balance)} "
        f"({'+' if end_delta >= 0 else '-'}{inr(abs(end_delta))}).",
        f"Lowest projected balance: {inr(simulated.min_balance)} on {fmt_date(simulated.min_balance_date)} "
        f"(baseline {inr(baseline.min_balance)}).",
    ]
    if monthly != 0:
        summary.append(f"Ongoing effect: {'+' if monthly > 0 else '-'}{inr(abs(monthly))} per month, "
                       f"{'+' if monthly > 0 else '-'}{inr(abs(monthly * 12))} per year.")
    return ScenarioResult(
        as_of=profile.as_of, title=title or ", ".join(c.type.replace("_", " ") for c in changes).capitalize(),
        assumptions=a, applied=applied, notes=notes, baseline=baseline, simulated=simulated, impacts=impacts,
        monthly_effect=monthly, risks=risks, summary=summary,
    )
