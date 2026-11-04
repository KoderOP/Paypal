"""Buy now, wait, or split it? Compare ways to pay for the same purchase.

Every option is a set of dated cash events that is projected with the same deterministic
engine as the baseline:

    pay_now    one payment today
    wait       one payment on the earliest safe date (goal solver), or on payday when buying
               now is already safe
    pay_later  PayPal Pay Later instalments (e.g. Pay in 4, Pay Monthly) built from plan terms

Fairness: each option is judged from its first payment until `horizon_days` after its *last*
payment, so a 12-month plan can't look safe just because the forecast window ended.

Pay Later terms here are inputs. PayPal decides real eligibility, APR and schedule at checkout,
so the defaults are labelled illustrative and every result carries `terms_note`.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import ZERO, money, total
from app.engine.forecast import baseline_events, project
from app.engine.goals import affordability_curve, earliest_safe_date
from app.engine.simulation import fmt_date, inr
from app.engine.twin import FinancialProfile
from app.engine.types import Assumptions, CashEvent, Money, add_months

OptionKind = Literal["pay_now", "wait", "pay_later"]
PayVerdict = Literal["pay_now", "wait", "split", "not_recommended"]


class PayLaterPlan(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    instalments: int = Field(ge=2, le=48)
    interval_days: int | None = Field(None, ge=7, le=31, description="Fixed spacing, e.g. 14 for Pay in 4")
    interval_months: int | None = Field(None, ge=1, le=3, description="Monthly spacing, e.g. 1 for Pay Monthly")
    first_payment_now: bool = True
    apr: Money = Field(Decimal("0"), ge=0, le=Decimal("60"))

    def schedule(self, amount: Decimal, start: date) -> list[tuple[date, Decimal]]:
        n = self.instalments
        if self.interval_days:
            step = lambda k: start + timedelta(days=self.interval_days * k)  # noqa: E731
        else:
            months = self.interval_months or 1
            step = lambda k: add_months(start, months * k, start.day)  # noqa: E731
        offset = 0 if self.first_payment_now else 1
        dates = [step(k + offset) for k in range(n)]
        if self.apr == 0:
            base = money(amount / n)
            amounts = [base] * (n - 1) + [money(amount - base * (n - 1))]
        else:
            # Standard amortisation at apr/12 per period, rounded to cents, last payment clears the balance.
            r = self.apr / Decimal(100) / Decimal(12)
            pmt = money(amount * r / (1 - (1 + r) ** -n))
            remaining, amounts = money(amount), []
            for k in range(n):
                interest = money(remaining * r)
                pay = pmt if k < n - 1 else money(remaining + interest)
                remaining = money(remaining + interest - pay)
                amounts.append(pay)
        return list(zip(dates, amounts))


DEFAULT_PLANS = [
    PayLaterPlan(id="pay_in_4", name="PayPal Pay in 4", instalments=4, interval_days=14, first_payment_now=True,
                 apr=Decimal("0")),
    PayLaterPlan(id="pay_monthly_12", name="PayPal Pay Monthly · 12 mo", instalments=12, interval_months=1,
                 first_payment_now=False, apr=Decimal("19.99")),
]

TERMS_NOTE = (
    "Pay Later terms shown are illustrative inputs. PayPal decides eligibility, APR and the exact schedule "
    "at checkout, and availability depends on your country and currency."
)


class Payment(BaseModel):
    on: date
    amount: Money


class PaymentOption(BaseModel):
    id: str
    kind: OptionKind
    name: str
    summary: str
    get_it_on: date
    payments: list[Payment]
    total_paid: Money
    extra_cost: Money
    apr: Money
    largest_payment: Money
    min_balance: Money
    min_balance_date: date
    days_below_buffer: int
    safe: bool
    series: list[Money]  # projected balance per day of `dates`, aligned with the baseline
    recommended: bool = False
    action: Literal["checkout", "plan"] | None = None
    funding: Literal["paypal", "paylater"] | None = None


class PaymentRecommendation(BaseModel):
    verdict: PayVerdict
    option_id: str | None
    least_risky_id: str
    headline: str
    explanation: list[str]


class PaymentComparison(BaseModel):
    as_of: date
    amount: Money
    label: str
    assumptions: Assumptions
    dates: list[date]
    baseline_series: list[Money]
    options: list[PaymentOption]
    recommendation: PaymentRecommendation
    terms_note: str = TERMS_NOTE
    disclaimer: str = (
        "Projections are deterministic estimates based on your past transactions and the stated assumptions. "
        "They are not guarantees, credit offers or financial advice."
    )


def _evaluate(profile: FinancialProfile, a: Assumptions, payments: list[tuple[date, Decimal]], label: str) -> dict:
    as_of = profile.as_of
    first = (payments[0][0] - as_of).days
    last = (payments[-1][0] - as_of).days
    horizon = last + a.horizon_days
    overlay = [CashEvent(on=d, amount=-amt, label=label, category="Shopping", kind="scenario") for d, amt in payments]
    fc = project(profile.current_balance, as_of, baseline_events(profile, a, horizon) + overlay, a, horizon)
    judged = fc.points[first:]
    low = min(judged, key=lambda p: (p.balance, p.on))
    return {
        "min_balance": low.balance,
        "min_balance_date": low.on,
        "days_below_buffer": sum(1 for p in judged if p.balance < a.safety_buffer),
        "safe": low.balance >= a.safety_buffer,
        "series": [p.balance for p in fc.points[: a.horizon_days + 1]],
    }


def compare_payment_options(profile: FinancialProfile, a: Assumptions, amount: Decimal, label: str = "Purchase",
                            plans: list[PayLaterPlan] | None = None) -> PaymentComparison:
    amount = money(amount)
    as_of = profile.as_of
    plans = DEFAULT_PLANS if plans is None else plans
    base = project(profile.current_balance, as_of, baseline_events(profile, a), a)
    dates = [p.on for p in base.points]

    def build(id_: str, kind: OptionKind, name: str, summary: str, payments: list[tuple[date, Decimal]],
              apr: Decimal = ZERO, action=None, funding=None) -> PaymentOption:
        paid = total(p for _, p in payments)
        return PaymentOption(
            id=id_, kind=kind, name=name, summary=summary, get_it_on=payments[0][0] if kind == "wait" else as_of,
            payments=[Payment(on=d, amount=p) for d, p in payments], total_paid=paid,
            extra_cost=money(paid - amount), apr=apr, largest_payment=max(p for _, p in payments),
            action=action, funding=funding, **_evaluate(profile, a, payments, label),
        )

    options = [build("pay_now", "pay_now", "Pay in full today", f"One payment of {inr(amount)} today.",
                     [(as_of, amount)], action="checkout", funding="paypal")]

    curve = affordability_curve(profile, a, a.horizon_days)
    earliest = earliest_safe_date(curve, amount, profile)
    if options[0].safe:
        wait_on = profile.next_income_date if profile.next_income_date and profile.next_income_date > as_of else None
        wait_why = "after your next income lands" if wait_on else None
    elif earliest.found:
        wait_on, wait_why = earliest.on, "the earliest date that keeps you above your buffer"
    else:
        best = max(curve, key=lambda p: (p.max_safe_spend, -p.day))
        wait_on, wait_why = best.on, "the least risky date in the forecast window"
    if wait_on and wait_on > as_of and (wait_on - as_of).days <= a.horizon_days:
        options.append(build("wait", "wait", f"Wait until {wait_on.strftime('%d %b')}",
                             f"One payment of {inr(amount)} on {fmt_date(wait_on)}, {wait_why}.",
                             [(wait_on, amount)], action="plan"))

    for plan in plans:
        sched = plan.schedule(amount, as_of)
        n, first_amt = len(sched), sched[0][1]
        spacing = f"every {plan.interval_days} days" if plan.interval_days else "monthly"
        start = "starting today" if plan.first_payment_now else f"starting {sched[0][0].strftime('%d %b')}"
        cost = "no interest" if plan.apr == 0 else f"{plan.apr}% APR (illustrative)"
        options.append(build(plan.id, "pay_later", plan.name,
                             f"{n} payments of about {inr(first_amt)} {spacing}, {start}; {cost}.",
                             sched, apr=plan.apr, action="checkout", funding="paylater"))

    return PaymentComparison(as_of=as_of, amount=amount, label=label, assumptions=a, dates=dates,
                             baseline_series=[p.balance for p in base.points], options=options,
                             recommendation=_recommend(options, amount, a))


def _recommend(options: list[PaymentOption], amount: Decimal, a: Assumptions) -> PaymentRecommendation:
    as_of = options[0].get_it_on
    buf = inr(a.safety_buffer)
    # Ranking among safe options: cheapest first, then soonest, then *no credit* (never suggest Pay Later
    # when paying in full is equally cheap, equally soon and still safe), then the bigger cushion.
    # Compare at whole-rupee granularity so paise left over from instalment rounding never decides the winner.
    least = max(options, key=lambda o: (_round_rupee(o.min_balance), -_round_rupee(o.extra_cost)))
    safe = sorted((o for o in options if o.safe),
                  key=lambda o: (_round_rupee(o.extra_cost), (o.get_it_on - as_of).days, o.kind == "pay_later",
                                 -_round_rupee(o.min_balance)))
    lines: list[str] = []
    for o in options:
        status = (f"lowest balance {inr(o.min_balance)} on {fmt_date(o.min_balance_date)}, above your {buf} buffer"
                  if o.safe else
                  f"drops to {inr(o.min_balance)} on {fmt_date(o.min_balance_date)}, below your {buf} buffer "
                  f"for {o.days_below_buffer} day(s)")
        cost = f"; costs {inr(o.extra_cost)} extra" if o.extra_cost > 0 else ""
        lines.append(f"{o.name}: {status}{cost}.")

    if not safe:
        return PaymentRecommendation(
            verdict="not_recommended", option_id=None, least_risky_id=least.id,
            headline="None of these options keep you above your buffer",
            explanation=lines + [f"The least risky choice is {least.name}, which still bottoms out at "
                                 f"{inr(least.min_balance)}. Consider a smaller amount or a later date."],
        )
    pick = safe[0]
    pick.recommended = True
    if pick.kind == "pay_now":
        verdict, headline = "pay_now", "Pay in full today. You can afford it."
    elif pick.kind == "wait":
        verdict, headline = "wait", f"Wait until {fmt_date(pick.get_it_on)}. It costs nothing extra."
    else:
        verdict, headline = "split", f"Split it with {pick.name}: get it today and stay above your buffer"
    paid_today = sum((p.amount for p in pick.payments if p.on == as_of), ZERO)
    why = [f"Recommended: {pick.name}. It is the cheapest option that keeps you above your {buf} buffer"
           + (f", and you pay {inr(paid_today)} today." if pick.kind == "pay_later" and paid_today else ".")]
    pricier_now = next((o for o in safe[1:] if o.get_it_on == as_of and o.extra_cost > pick.extra_cost), None)
    if pick.kind == "wait" and pricier_now:
        why.append(f"{pricier_now.name} would get it today but costs {inr(pricier_now.extra_cost)} more.")
    return PaymentRecommendation(verdict=verdict, option_id=pick.id, least_risky_id=least.id, headline=headline,
                                 explanation=why + lines)


def _round_rupee(v: Decimal) -> Decimal:
    """Whole-rupee value used only for ranking options, never for displayed or stored figures."""
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
