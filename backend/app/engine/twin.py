"""Financial Digital Twin — derives a structured behavioural profile from raw transactions.

Detection rules (deterministic, documented):
- Recurring: same merchant & direction, ≥3 occurrences, median interval 25–35 days,
  ≤1 occurrence per calendar month in ≥80% of months, amount spread (max-min)/median ≤ 40%,
  last seen within 45 days. Projected amount = median of the last 3 occurrences.
- Variable spend: non-recurring debits. Monthly rate per category = median of the last three
  30-day windows (robust to one-off spikes such as a flight or medical bill).
- Investments (SIP etc.) are treated as savings, not spending.
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal

from pydantic import BaseModel

from app.core.money import ZERO, money, ratio, total
from app.data.categorize import ESSENTIAL_CATEGORIES, SAVINGS_CATEGORIES, TRANSFER_CATEGORIES
from app.engine.types import Assumptions, Money, ObligationIn, Txn, add_months

MONTHLY_INTERVAL = (25, 35)
MAX_AMOUNT_SPREAD = Decimal("0.40")
ACTIVE_WITHIN_DAYS = 45
WINDOW = 30


class RecurringItem(BaseModel):
    key: str
    name: str
    merchant: str
    category: str
    kind: Literal["income", "subscription", "housing", "bill", "savings", "other"]
    direction: Literal["in", "out"]
    amount: Money
    day_of_month: int
    occurrences: int
    last_date: date | None  # None for items added by the user or from PayPal before any payment is seen
    next_date: date
    # detected = learned from transactions · manual = added by the user · paypal = PayPal Subscriptions API
    source: Literal["detected", "manual", "paypal"] = "detected"
    # Set when this income arrives in a foreign currency (e.g. a US client paying in USD via PayPal).
    currency: str | None = None
    foreign_amount: Money | None = None  # median net received in `currency`, after PayPal's fee


class CategorySpend(BaseModel):
    category: str
    monthly_average: Money
    recurring_monthly: Money
    variable_monthly: Money
    share: Decimal
    essential: bool


class MonthSummary(BaseModel):
    month: str
    income: Money
    spending: Money
    investments: Money
    net: Money
    partial: bool


class FinancialProfile(BaseModel):
    as_of: date
    current_balance: Money
    history_start: date | None
    transaction_count: int
    recurring_income: list[RecurringItem]
    recurring_outflows: list[RecurringItem]
    categories: list[CategorySpend]
    months: list[MonthSummary]
    monthly_income: Money  # regular (recurring) income
    avg_monthly_income: Money  # all income incl. irregular, over lookback
    irregular_income_lookback: Money
    avg_monthly_spending: Money  # excl. investments
    avg_monthly_investments: Money
    essential_monthly: Money
    variable_monthly: Money
    recurring_outflow_monthly: Money
    subscriptions_monthly: Money
    savings_rate: Decimal  # (regular income - spending) / regular income
    next_income_date: date | None
    obligations: list[ObligationIn]


def _norm(merchant: str) -> str:
    return re.sub(r"\s+", " ", merchant.strip().lower())


def _kind(category: str, direction: str) -> str:
    if direction == "in":
        return "income"
    return {"Subscriptions": "subscription", "Rent": "housing", "Utilities": "bill", "Investments": "savings"}.get(
        category, "other"
    )


def detect_recurring(txns: list[Txn], as_of: date) -> list[RecurringItem]:
    groups: dict[tuple[str, str], list[Txn]] = defaultdict(list)
    for t in txns:
        if t.category in TRANSFER_CATEGORIES:
            continue  # moving your own money between accounts is neither income nor a bill
        groups[(_norm(t.merchant), "in" if t.amount > 0 else "out")].append(t)

    items: list[RecurringItem] = []
    for (key, direction), group in groups.items():
        if len(group) < 3:
            continue
        group.sort(key=lambda t: t.posted_on)
        dates = [t.posted_on for t in group]
        intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
        if not MONTHLY_INTERVAL[0] <= median(intervals) <= MONTHLY_INTERVAL[1]:
            continue
        months = [(d.year, d.month) for d in dates]
        if len(set(months)) < 0.8 * len(months):
            continue
        amounts = [abs(t.amount) for t in group]
        med = Decimal(median(amounts))
        if med == 0 or (max(amounts) - min(amounts)) / med > MAX_AMOUNT_SPREAD:
            continue
        last = dates[-1]
        if (as_of - last).days > ACTIVE_WITHIN_DAYS:
            continue
        dom = int(round(median(d.day for d in dates)))
        nxt = add_months(last, 1, dom)
        while nxt < as_of:
            nxt = add_months(nxt, 1, dom)
        latest = group[-1]
        recent_fx = [t.fx for t in group[-3:] if t.fx]
        foreign = recent_fx[-1].currency if len(recent_fx) >= 2 else None  # most recent payments were foreign
        items.append(
            RecurringItem(
                currency=foreign,
                foreign_amount=money(Decimal(median(f.net for f in recent_fx))) if foreign else None,
                key=f"{direction}:{key}",
                # PayPal rows read "<PayPal type> · <merchant>"; the merchant is the readable name.
                name=latest.merchant if latest.description.endswith(f" · {latest.merchant}") else latest.description,
                merchant=latest.merchant,
                category=latest.category,
                kind=_kind(latest.category, direction),
                direction=direction,
                amount=money(Decimal(median(amounts[-3:]))),
                day_of_month=dom,
                occurrences=len(group),
                last_date=last,
                next_date=nxt,
            )
        )
    items.sort(key=lambda i: (i.direction != "in", -i.amount))
    return items


def merchant_key(merchant: str) -> str:
    """The key a detected outflow from this merchant gets, used to spot duplicates of added items."""
    return f"out:{_norm(merchant)}"


def with_added(profile: "FinancialProfile", added: list[RecurringItem]) -> "FinancialProfile":
    """Merge recurring outflows the user added (or that come from PayPal) into the twin.

    An added item whose merchant is already *detected* from transactions is skipped: once real
    payments appear in the history, the detected item takes over, so nothing is counted twice.
    Next dates in the past roll forward to the next occurrence on or after `as_of`.
    """
    detected = {r.key for r in profile.recurring_outflows}
    fresh: list[RecurringItem] = []
    for item in added:
        if merchant_key(item.merchant) in detected or item.key in detected:
            continue
        nxt = item.next_date
        while nxt < profile.as_of:
            nxt = add_months(nxt, 1, item.day_of_month)
        fresh.append(item.model_copy(update={"next_date": nxt}))
    if not fresh:
        return profile
    outs = profile.recurring_outflows + fresh
    return profile.model_copy(update={
        "recurring_outflows": outs,
        "recurring_outflow_monthly": total(r.amount for r in outs),
        "subscriptions_monthly": total(r.amount for r in outs if r.kind == "subscription"),
    })


def without_cancelled(profile: "FinancialProfile", cancelled_keys: set[str]) -> "FinancialProfile":
    """Drop recurring outflows the user has cancelled (via PayPal or manually) from future projections.

    History is untouched; only what the twin *expects* to happen changes. Totals are recomputed.
    """
    keep = [r for r in profile.recurring_outflows if r.key not in cancelled_keys]
    if len(keep) == len(profile.recurring_outflows):
        return profile
    return profile.model_copy(update={
        "recurring_outflows": keep,
        "recurring_outflow_monthly": total(r.amount for r in keep),
        "subscriptions_monthly": total(r.amount for r in keep if r.kind == "subscription"),
    })


def _month_summaries(txns: list[Txn], as_of: date) -> list[MonthSummary]:
    buckets: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"income": ZERO, "spending": ZERO, "investments": ZERO})
    for t in txns:
        if t.category in TRANSFER_CATEGORIES:
            continue
        b = buckets[t.posted_on.strftime("%Y-%m")]
        if t.amount > 0:
            b["income"] += t.amount
        elif t.category in SAVINGS_CATEGORIES:
            b["investments"] += -t.amount
        else:
            b["spending"] += -t.amount
    first = min((t.posted_on for t in txns), default=as_of)
    out = []
    for month in sorted(buckets):
        b = buckets[month]
        partial = month == as_of.strftime("%Y-%m") or (month == first.strftime("%Y-%m") and first.day > 1)
        out.append(
            MonthSummary(
                month=month,
                income=money(b["income"]),
                spending=money(b["spending"]),
                investments=money(b["investments"]),
                net=money(b["income"] - b["spending"] - b["investments"]),
                partial=partial,
            )
        )
    return out


def build_profile(
    txns: list[Txn],
    current_balance: Decimal,
    as_of: date,
    obligations: list[ObligationIn] | None = None,
    assumptions: Assumptions | None = None,
) -> FinancialProfile:
    a = assumptions or Assumptions()
    recurring = detect_recurring(txns, as_of)
    recurring_keys = {r.key for r in recurring}
    rec_in = [r for r in recurring if r.direction == "in"]
    rec_out = [r for r in recurring if r.direction == "out"]

    lb_start = as_of - timedelta(days=a.lookback_days)
    window_txns = [t for t in txns if lb_start <= t.posted_on < as_of and t.category not in TRANSFER_CATEGORIES]
    history_days = (as_of - min((t.posted_on for t in txns), default=as_of)).days
    span = Decimal(max(1, min(a.lookback_days, history_days)))
    per_month = lambda amount: money(amount * WINDOW / span)  # noqa: E731

    income_lb = total(t.amount for t in window_txns if t.amount > 0)
    rec_income_lb = total(
        t.amount for t in window_txns if t.amount > 0 and f"in:{_norm(t.merchant)}" in recurring_keys
    )
    spend_lb = total(-t.amount for t in window_txns if t.amount < 0 and t.category not in SAVINGS_CATEGORIES)
    invest_lb = total(-t.amount for t in window_txns if t.amount < 0 and t.category in SAVINGS_CATEGORIES)

    # Category breakdown: recurring part from detected items, variable part = median of 30-day windows.
    by_cat_total: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for t in window_txns:
        if t.amount < 0:
            by_cat_total[t.category] += -t.amount
    rec_by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in rec_out:
        rec_by_cat[r.category] += r.amount

    n_windows = max(1, min(3, int(span) // WINDOW))
    var_windows: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO] * n_windows)
    for t in txns:
        if t.amount >= 0 or f"out:{_norm(t.merchant)}" in recurring_keys or t.category in TRANSFER_CATEGORIES:
            continue
        idx = (as_of - t.posted_on).days - 1
        if 0 <= idx < n_windows * WINDOW:
            var_windows[t.category][idx // WINDOW] += -t.amount
    var_by_cat = {c: money(Decimal(median(w))) for c, w in var_windows.items()}

    categories: list[CategorySpend] = []
    spend_cats = set(by_cat_total) | set(rec_by_cat) | set(var_by_cat)
    spend_total_monthly = per_month(spend_lb) or Decimal("1")
    for c in spend_cats:
        if c in SAVINGS_CATEGORIES:
            continue
        monthly = per_month(by_cat_total.get(c, ZERO))
        categories.append(
            CategorySpend(
                category=c,
                monthly_average=monthly,
                recurring_monthly=money(rec_by_cat.get(c, ZERO)),
                variable_monthly=var_by_cat.get(c, ZERO),
                share=ratio(monthly, spend_total_monthly),
                essential=c in ESSENTIAL_CATEGORIES,
            )
        )
    categories.sort(key=lambda c: -c.monthly_average)

    monthly_income = total(r.amount for r in rec_in)
    avg_spending = per_month(spend_lb)
    upcoming = sorted(
        [o for o in (obligations or []) if o.due_on >= as_of], key=lambda o: o.due_on
    )
    return FinancialProfile(
        as_of=as_of,
        current_balance=money(current_balance),
        history_start=min((t.posted_on for t in txns), default=None),
        transaction_count=len(txns),
        recurring_income=rec_in,
        recurring_outflows=rec_out,
        categories=categories,
        months=_month_summaries(txns, as_of),
        monthly_income=monthly_income,
        avg_monthly_income=per_month(income_lb),
        irregular_income_lookback=money(income_lb - rec_income_lb),
        avg_monthly_spending=avg_spending,
        avg_monthly_investments=per_month(invest_lb),
        essential_monthly=total(c.monthly_average for c in categories if c.essential),
        variable_monthly=total(c.variable_monthly for c in categories),
        recurring_outflow_monthly=total(r.amount for r in rec_out),
        subscriptions_monthly=total(r.amount for r in rec_out if r.kind == "subscription"),
        savings_rate=ratio(monthly_income - avg_spending, monthly_income),
        next_income_date=min((r.next_date for r in rec_in), default=None),
        obligations=upcoming,
    )
