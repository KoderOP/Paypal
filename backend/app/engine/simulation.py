"""What-if simulation engine.

A scenario is an *event overlay* on the baseline forecast: it adds, removes or shifts
cash events. The overlay is projected with the same deterministic engine, so every figure
in a result is traceable to transactions + explicit assumptions. Narrative text is built
from computed numbers — an LLM may later rephrase it but never computes figures.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import ZERO, money
from app.engine.forecast import Forecast, baseline_events, project
from app.engine.twin import FinancialProfile
from app.engine.types import Assumptions, CashEvent, Money

RiskLevel = Literal["critical", "high", "medium", "low", "info"]
Verdict = Literal["safe_now", "wait", "not_recommended"]


def inr(v: Decimal) -> str:
    """Indian digit grouping, e.g. 110000 -> ₹1,10,000."""
    q = int(abs(v).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    s = str(q)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{'-' if v < 0 else ''}₹{s}"


def fmt_date(d: date) -> str:
    return d.strftime("%d %b %Y")


class PurchaseScenario(BaseModel):
    amount: Money = Field(gt=0, le=Decimal("100000000"))
    purchase_date: date
    label: str = Field("Laptop purchase", min_length=1, max_length=80)
    category: str = "Shopping"

    def overlay(self) -> list[CashEvent]:
        return [CashEvent(on=self.purchase_date, amount=-self.amount, label=self.label, category=self.category, kind="scenario")]


class Impact(BaseModel):
    day: int
    on: date
    baseline: Money
    scenario: Money
    delta: Money


class Risk(BaseModel):
    level: RiskLevel
    title: str
    detail: str


class TimingOption(BaseModel):
    label: str
    purchase_date: date
    days_from_now: int
    balance_after_purchase: Money
    min_balance: Money  # over the 90 days following the purchase
    min_balance_date: date
    days_below_buffer: int
    safe: bool
    is_selected: bool
    is_recommended: bool = False


class Recommendation(BaseModel):
    verdict: Verdict
    recommended_date: date | None
    headline: str
    explanation: list[str]


class PurchaseSimulation(BaseModel):
    scenario: PurchaseScenario
    as_of: date
    assumptions: Assumptions
    starting_balance: Money
    baseline: Forecast
    simulated: Forecast
    impacts: list[Impact]
    risks: list[Risk]
    timing_options: list[TimingOption]
    recommendation: Recommendation
    runway_months_before: Decimal
    runway_months_after: Decimal
    monthly_surplus: Money
    months_to_recover: Decimal | None
    disclaimer: str = (
        "Projections are deterministic estimates based on your past transactions and the stated "
        "assumptions. They are not guarantees or financial advice."
    )


def _evaluate_timing(profile: FinancialProfile, a: Assumptions, sc: PurchaseScenario, label: str, selected: date) -> TimingOption:
    """Project far enough that every candidate is judged on a full horizon *after* the purchase."""
    offset = (sc.purchase_date - profile.as_of).days
    horizon = offset + a.horizon_days
    events = baseline_events(profile, a, horizon) + sc.overlay()
    fc = project(profile.current_balance, profile.as_of, events, a, horizon)
    after = fc.points[offset:]
    low = min(after, key=lambda p: (p.balance, p.on))
    return TimingOption(
        label=label,
        purchase_date=sc.purchase_date,
        days_from_now=offset,
        balance_after_purchase=after[0].balance,
        min_balance=low.balance,
        min_balance_date=low.on,
        days_below_buffer=sum(1 for p in after if p.balance < a.safety_buffer),
        safe=low.balance >= a.safety_buffer,
        is_selected=sc.purchase_date == selected,
    )


def _months(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def simulate_purchase(profile: FinancialProfile, a: Assumptions, sc: PurchaseScenario) -> PurchaseSimulation:
    as_of = profile.as_of
    last_day = as_of + timedelta(days=a.horizon_days)
    if not as_of <= sc.purchase_date <= last_day:
        raise ValueError(f"purchase_date must be between {as_of} and {last_day}")

    base_events = baseline_events(profile, a)
    baseline = project(profile.current_balance, as_of, base_events, a)
    simulated = project(profile.current_balance, as_of, base_events + sc.overlay(), a)

    impacts = [
        Impact(
            day=d,
            on=baseline.points[d].on,
            baseline=baseline.balance_on_day(d),
            scenario=simulated.balance_on_day(d),
            delta=money(simulated.balance_on_day(d) - baseline.balance_on_day(d)),
        )
        for d in (30, 60, 90)
        if d <= a.horizon_days
    ]

    # Candidate purchase dates: the requested date, today, and each expected income date.
    candidates: dict[date, str] = {as_of: "Today"}
    for p in baseline.points:
        if any(e.kind == "income" for e in p.events):
            candidates.setdefault(p.on, f"After income on {p.on.strftime('%d %b')}")
    candidates.setdefault(sc.purchase_date, "Your chosen date")
    options = [
        _evaluate_timing(profile, a, sc.model_copy(update={"purchase_date": d}), label, sc.purchase_date)
        for d, label in sorted(candidates.items())
    ]

    selected = next(o for o in options if o.is_selected)
    earliest_safe = next((o for o in options if o.safe), None)
    best = max(options, key=lambda o: (o.min_balance, -o.days_from_now))

    # Cash-flow fundamentals (all computed, never guessed).
    monthly_spend = profile.avg_monthly_spending
    surplus = money(profile.monthly_income - monthly_spend - profile.avg_monthly_investments)
    runway_before = _months(profile.current_balance / monthly_spend) if monthly_spend > 0 else Decimal("0")
    runway_after = _months(selected.balance_after_purchase / monthly_spend) if monthly_spend > 0 else Decimal("0")
    months_to_recover = _months(sc.amount / surplus) if surplus > 0 else None

    buffer = a.safety_buffer
    explanation: list[str] = [
        f"Your balance today is {inr(profile.current_balance)}. Regular income of {inr(profile.monthly_income)}/month"
        + (f" is next expected on {fmt_date(profile.next_income_date)}." if profile.next_income_date else "."),
        f"Recurring commitments total {inr(profile.recurring_outflow_monthly)}/month, plus about "
        f"{inr(baseline.daily_variable_spend)}/day of day-to-day spending"
        + (f" and {len(profile.obligations)} upcoming obligation(s)." if profile.obligations else "."),
    ]
    if selected.safe:
        verdict: Verdict = "safe_now"
        rec_date = sc.purchase_date
        when = "today" if sc.purchase_date == as_of else f"on {fmt_date(sc.purchase_date)}"
        headline = f"You can afford this {when}"
        explanation.append(
            f"Buying {when} keeps your lowest projected balance at {inr(selected.min_balance)} "
            f"({fmt_date(selected.min_balance_date)}), above your {inr(buffer)} safety buffer."
        )
        if best.purchase_date != selected.purchase_date and best.min_balance - selected.min_balance >= Decimal("5000"):
            explanation.append(
                f"Waiting until {fmt_date(best.purchase_date)} would give you a larger cushion "
                f"(lowest balance {inr(best.min_balance)})."
            )
    elif earliest_safe:
        verdict = "wait"
        rec_date = earliest_safe.purchase_date
        headline = f"Wait until {fmt_date(earliest_safe.purchase_date)} to buy"
        explanation.append(
            f"Buying on {fmt_date(selected.purchase_date)} would push your balance down to {inr(selected.min_balance)} "
            f"on {fmt_date(selected.min_balance_date)} — below your {inr(buffer)} safety buffer"
            + (f" for {selected.days_below_buffer} day(s)." if selected.days_below_buffer else ".")
        )
        explanation.append(
            f"Purchasing on {fmt_date(earliest_safe.purchase_date)} keeps your lowest "
            f"projected balance at {inr(earliest_safe.min_balance)}, so you never dip below the buffer."
        )
    else:
        verdict = "not_recommended"
        rec_date = None
        shortfall = money(buffer - best.min_balance)
        headline = "Not recommended within the forecast window"
        explanation.append(
            f"Every purchase date we tested takes your balance below the {inr(buffer)} safety buffer. "
            f"The best option ({fmt_date(best.purchase_date)}) still bottoms out at {inr(best.min_balance)}, "
            f"a shortfall of {inr(shortfall)}."
        )
        if surplus > 0:
            explanation.append(
                f"At your current monthly surplus of {inr(surplus)}, closing that gap takes about "
                f"{_months(shortfall / surplus)} month(s) — or consider a lower budget or EMI."
            )
    if months_to_recover is not None:
        explanation.append(
            f"The purchase equals about {months_to_recover} month(s) of your current surplus of {inr(surplus)}."
        )

    for o in options:
        o.is_recommended = rec_date is not None and o.purchase_date == rec_date

    risks: list[Risk] = []
    if simulated.first_below_zero:
        risks.append(Risk(level="critical", title="Projected overdraft",
                          detail=f"Balance goes negative on {fmt_date(simulated.first_below_zero)} "
                                 f"(lowest {inr(simulated.min_balance)})."))
    elif simulated.min_balance < buffer:
        risks.append(Risk(level="high", title="Below safety buffer",
                          detail=f"Balance falls under {inr(buffer)} on {fmt_date(simulated.first_below_buffer)} "
                                 f"and stays below for {simulated.days_below_buffer} day(s)."))
    if runway_after < 1:
        risks.append(Risk(level="high", title="Emergency runway under 1 month",
                          detail=f"Runway drops from {runway_before} to {runway_after} months of spending."))
    elif runway_after < 3:
        risks.append(Risk(level="medium", title="Thin emergency runway",
                          detail=f"Runway drops from {runway_before} to {runway_after} months (3+ months recommended)."))
    if profile.monthly_income > 0 and sc.amount > profile.monthly_income:
        risks.append(Risk(level="medium", title="Large relative to income",
                          detail=f"This purchase is {_months(sc.amount / profile.monthly_income)}× your monthly regular income."))
    if months_to_recover is not None:
        risks.append(Risk(level="info", title="Savings recovery time",
                          detail=f"About {months_to_recover} month(s) of surplus to rebuild the {inr(sc.amount)}."))
    elif surplus <= 0:
        risks.append(Risk(level="high", title="No monthly surplus",
                          detail="Your spending and investments currently meet or exceed regular income."))
    if not any(r.level in ("critical", "high") for r in risks):
        risks.insert(0, Risk(level="low", title="No liquidity stress detected",
                             detail=f"Balance stays above {inr(buffer)} throughout the forecast."))

    return PurchaseSimulation(
        scenario=sc,
        as_of=as_of,
        assumptions=a,
        starting_balance=profile.current_balance,
        baseline=baseline,
        simulated=simulated,
        impacts=impacts,
        risks=risks,
        timing_options=options,
        recommendation=Recommendation(verdict=verdict, recommended_date=rec_date, headline=headline, explanation=explanation),
        runway_months_before=runway_before,
        runway_months_after=runway_after,
        monthly_surplus=surplus,
        months_to_recover=months_to_recover,
    )
