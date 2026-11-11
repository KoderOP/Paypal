"""Proactive alerts: things worth knowing *before* they happen, computed from the twin.

Each rule is deterministic and explainable. Alert ids include the date they refer to, so a
dismissed alert comes back when the situation recurs (e.g. next month's rent).

Rules
- below_zero / below_buffer   the baseline forecast goes negative / under the safety buffer
- bill_before_income          a large bill (≥ 10% of regular income, or rent) falls 1–5 days before income
- due_soon                    an obligation (incl. Pay Later instalments, planned purchases) is due within 3 days
- income_late                 a regular income payment is more than 2 days past its usual date
- price_increase              a subscription's latest charge is ≥ 10% (and ≥ ₹20) above the previous one
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel

from app.core.money import money
from app.engine.forecast import Forecast
from app.engine.simulation import fmt_date, inr
from app.engine.twin import FinancialProfile, merchant_key
from app.engine.types import Assumptions, Money, Txn, add_months

AlertLevel = Literal["critical", "warning", "info"]
LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}
BILL_WINDOW = (1, 5)
DUE_SOON_DAYS = 3
LATE_GRACE_DAYS = 2
PRICE_JUMP = Decimal("0.10")


class AlertAction(BaseModel):
    label: str
    to: str


class Alert(BaseModel):
    id: str
    kind: str
    level: AlertLevel
    title: str
    detail: str
    on: date | None
    amount: Money | None = None
    action: AlertAction | None = None


def _when(d: date, today: date) -> str:
    n = (d - today).days
    return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days ({d.strftime('%d %b')})"


def build_alerts(profile: FinancialProfile, fc: Forecast, txns: list[Txn], a: Assumptions) -> list[Alert]:
    today = profile.as_of
    out: list[Alert] = []
    balance_on = {p.on: p.balance for p in fc.points}

    # 1. Liquidity: negative or under the buffer.
    if fc.first_below_zero:
        out.append(Alert(id=f"below_zero:{fc.first_below_zero}", kind="below_zero", level="critical", on=fc.first_below_zero,
                         amount=fc.min_balance, title=f"Your balance is projected to go negative on {fmt_date(fc.first_below_zero)}",
                         detail=f"Lowest point {inr(fc.min_balance)} on {fmt_date(fc.min_balance_date)}. Moving a payment or "
                                "cutting spending before then avoids it.",
                         action=AlertAction(label="Find what you can afford", to="/simulator")))
    elif fc.first_below_buffer:
        out.append(Alert(id=f"below_buffer:{fc.first_below_buffer}", kind="below_buffer", level="warning",
                         on=fc.first_below_buffer, amount=fc.min_balance,
                         title=f"Your balance will dip below your {inr(a.safety_buffer)} buffer on {fmt_date(fc.first_below_buffer)}",
                         detail=f"It bottoms at {inr(fc.min_balance)} on {fmt_date(fc.min_balance_date)} and stays under the "
                                f"buffer for {fc.days_below_buffer} day(s).",
                         action=AlertAction(label="See the forecast", to="/")))

    # 2. Big bills landing just before income.
    big = max(Decimal("2000"), profile.monthly_income * Decimal("0.10"))
    income_days = [(p.on, e) for p in fc.points for e in p.events if e.kind == "income" and e.ref]
    seen_bills: set[str] = set()
    for p in fc.points:
        if (p.on - today).days > 45:
            break
        for e in p.events:
            if e.kind != "recurring" or e.ref in seen_bills or (-e.amount < big and e.category != "Rent"):
                continue
            nxt = next(((d, inc) for d, inc in income_days if 0 < (d - p.on).days), None)
            if not nxt or not BILL_WINDOW[0] <= (nxt[0] - p.on).days <= BILL_WINDOW[1]:
                continue
            seen_bills.add(e.ref or e.label)
            gap = (nxt[0] - p.on).days
            payer = next((r.merchant for r in profile.recurring_income if r.key == nxt[1].ref), "your income")
            bill = next((r.merchant for r in profile.recurring_outflows if r.key == e.ref), e.label)
            tight = balance_on.get(p.on, Decimal("0")) < a.safety_buffer
            out.append(Alert(
                id=f"bill_before_income:{e.ref}:{p.on}", kind="bill_before_income", level="warning" if tight else "info",
                on=p.on, amount=-e.amount,
                title=f"{bill} ({inr(-e.amount)}) is due {gap} day{'s' if gap > 1 else ''} before {payer} pays you",
                detail=f"Due {fmt_date(p.on)}; income expected {fmt_date(nxt[0])}. Your balance that day is projected at "
                       f"{inr(balance_on.get(p.on, Decimal('0')))}" + (", under your buffer." if tight else "."),
                action=AlertAction(label="Plan around it", to="/simulator")))

    # 3. Obligations due soon (Pay Later instalments, planned purchases, renewals…).
    for o in profile.obligations:
        days = (o.due_on - today).days
        if not 0 <= days <= DUE_SOON_DAYS:
            continue
        after = balance_on.get(o.due_on)
        tight = after is not None and after < a.safety_buffer
        what = "Pay Later instalment" if o.category == "Pay Later" else o.title
        out.append(Alert(
            id=f"due_soon:{o.title}:{o.due_on}", kind="due_soon", level="warning" if tight else "info", on=o.due_on,
            amount=o.amount, title=f"{what} due {_when(o.due_on, today)}: {inr(o.amount)}",
            detail=(f"{o.title}. " if what != o.title else "") + (
                f"Your balance after paying is projected at {inr(after)}" + (", under your buffer." if tight else ".")
                if after is not None else "Make sure the money is in place."),
            action=AlertAction(label="View upcoming payments", to="/")))

    # 4. Regular income that hasn't arrived on time.
    for r in profile.recurring_income:
        if r.last_date is None:
            continue
        expected = add_months(r.last_date, 1, r.day_of_month)
        late_by = (today - expected).days
        if late_by > LATE_GRACE_DAYS:
            out.append(Alert(
                id=f"income_late:{r.key}:{expected}", kind="income_late", level="warning", on=expected, amount=r.amount,
                title=f"{r.merchant} hasn't paid yet ({late_by} days late)",
                detail=f"It usually arrives around day {r.day_of_month} of the month ({inr(r.amount)}), expected "
                       f"{fmt_date(expected)}. Your forecast still assumes the next payment on {fmt_date(r.next_date)}.",
                action=AlertAction(label="Simulate a delay",
                                   to="/assistant?" + urlencode({"q": f"What if {r.merchant} pays 15 days late?"}))))

    # 5. Subscription / bill price increases.
    by_merchant: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.amount < 0:
            by_merchant[merchant_key(t.merchant)].append(t)
    for r in profile.recurring_outflows:
        # Subscriptions only: utility bills legitimately vary month to month and would raise false alarms.
        if r.kind != "subscription" or r.source != "detected":
            continue
        hist = sorted(by_merchant.get(r.key, []), key=lambda t: t.posted_on)
        if len(hist) < 2 or (today - hist[-1].posted_on).days > 45:
            continue
        prev, last = -hist[-2].amount, -hist[-1].amount
        if last - prev >= Decimal("20") and prev > 0 and (last - prev) / prev >= PRICE_JUMP:
            pct = ((last - prev) / prev * 100).quantize(Decimal("1"))
            out.append(Alert(
                id=f"price_increase:{r.key}:{hist[-1].posted_on}", kind="price_increase", level="info",
                on=hist[-1].posted_on, amount=money(last - prev),
                title=f"{r.merchant} went up {pct}%: {inr(prev)} → {inr(last)}",
                detail=f"Charged {fmt_date(hist[-1].posted_on)}. That's {inr((last - prev) * 12)} more a year.",
                action=AlertAction(label="Review subscriptions", to="/subscriptions")))

    out.sort(key=lambda x: (LEVEL_ORDER[x.level], x.on or today + timedelta(days=999)))
    return out
