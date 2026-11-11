"""Cross-border freelancer view: foreign income, PayPal fees, conversion cost and FX risk.

Everything is computed from transactions that carry their original-currency details (see
`Txn.fx`), i.e. the rate PayPal actually applied, never an assumed market rate. A reference
rate is used only when the user enters one, to estimate the conversion spread against it.
"""
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from app.core.money import ZERO, money, ratio, total
from app.engine.scenarios import FxChange, IncomeDelay, simulate_scenario
from app.engine.simulation import fmt_date, inr
from app.engine.twin import FinancialProfile
from app.engine.types import Assumptions, Money, Rate, Txn

SENSITIVITY = (Decimal("-5"), Decimal("-3"), Decimal("3"), Decimal("5"))
LATE_DAYS = 15
WITHDRAWAL_NOTE = (
    "PayPal India generally moves money you receive to your linked bank account automatically, so there's usually no "
    "withdrawal date to optimise. Check your PayPal settings. What you can control is how much you lose to fees and "
    "conversion, and how much risk you take on the exchange rate and on clients paying late."
)


class CurrencySummary(BaseModel):
    currency: str
    payments: int
    first_on: date
    last_on: date
    gross: Money
    fees: Money  # positive, in `currency`
    net: Money
    received_home: Money  # what landed in INR
    fee_pct: Decimal  # fees / gross
    fee_cost_home: Money  # fees valued at the average applied rate
    avg_rate: Rate  # INR per unit, weighted by amount converted
    latest_rate: Rate
    latest_rate_on: date
    reference_rate: Rate | None
    spread_pct: Decimal | None  # (reference - applied) / reference
    spread_cost_home: Money | None


class ForeignClient(BaseModel):
    merchant: str
    currency: str
    monthly_foreign: Money
    monthly_home: Money
    next_date: date
    share_of_income: Decimal


class FxSensitivity(BaseModel):
    change_pct: Money
    monthly_effect: Money
    end_balance_delta: Money
    min_balance: Money
    below_buffer: bool


class LateClient(BaseModel):
    merchant: str
    days: int
    min_balance: Money
    min_balance_date: date
    first_below_buffer: date | None
    baseline_min_balance: Money


class CrossBorder(BaseModel):
    as_of: date
    has_foreign: bool
    home_currency: str
    currencies: list[CurrencySummary]
    clients: list[ForeignClient]
    foreign_share: Decimal  # regular foreign income / regular income
    sensitivity: list[FxSensitivity]
    sensitivity_currency: str | None
    late_client: LateClient | None
    insights: list[str]
    withdrawal_note: str = WITHDRAWAL_NOTE
    disclaimer: str = ("Rates and fees come from your PayPal report. Projections hold today's patterns constant and "
                       "are estimates, not advice.")


def _rate(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def summarise_currencies(txns: list[Txn], reference_rates: dict[str, Decimal]) -> list[CurrencySummary]:
    by_cur: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.fx and t.amount > 0:
            by_cur[t.fx.currency].append(t)
    out = []
    for cur, items in sorted(by_cur.items()):
        gross = total(t.fx.gross for t in items)
        fees = total(-t.fx.fee for t in items)
        net = total(t.fx.net for t in items)
        home = total(t.amount for t in items)
        avg = _rate(home / net) if net else Decimal("0")
        latest = max(items, key=lambda t: t.posted_on)
        ref = reference_rates.get(cur)
        spread = ratio(ref - avg, ref) if ref else None
        out.append(CurrencySummary(
            currency=cur, payments=len(items), first_on=min(t.posted_on for t in items), last_on=latest.posted_on,
            gross=gross, fees=fees, net=net, received_home=home, fee_pct=ratio(fees, gross),
            fee_cost_home=money(fees * avg), avg_rate=avg, latest_rate=_rate(latest.fx.rate),
            latest_rate_on=latest.posted_on, reference_rate=ref, spread_pct=spread,
            spread_cost_home=money(net * (ref - avg)) if ref else None,
        ))
    return out


def cross_border(profile: FinancialProfile, txns: list[Txn], a: Assumptions,
                 reference_rates: dict[str, Decimal] | None = None) -> CrossBorder:
    refs = reference_rates or {}
    currencies = summarise_currencies(txns, refs)
    foreign_items = [r for r in profile.recurring_income if r.currency]
    clients = [ForeignClient(merchant=r.merchant, currency=r.currency or "", monthly_foreign=r.foreign_amount or ZERO,
                             monthly_home=r.amount, next_date=r.next_date,
                             share_of_income=ratio(r.amount, profile.monthly_income))
               for r in sorted(foreign_items, key=lambda r: -r.amount)]
    foreign_monthly = total(r.amount for r in foreign_items)
    share = ratio(foreign_monthly, profile.monthly_income)

    main_cur = clients[0].currency if clients else None
    sensitivity: list[FxSensitivity] = []
    if main_cur:
        for pct in SENSITIVITY:
            r = simulate_scenario(profile, a, [FxChange(percent=pct, currency=main_cur)])
            sensitivity.append(FxSensitivity(
                change_pct=pct, monthly_effect=r.monthly_effect,
                end_balance_delta=money(r.simulated.end_balance - r.baseline.end_balance),
                min_balance=r.simulated.min_balance, below_buffer=r.simulated.min_balance < a.safety_buffer))

    late = None
    if clients:
        top = clients[0]
        r = simulate_scenario(profile, a, [IncomeDelay(days=LATE_DAYS, merchant=top.merchant)])
        late = LateClient(merchant=top.merchant, days=LATE_DAYS, min_balance=r.simulated.min_balance,
                          min_balance_date=r.simulated.min_balance_date, first_below_buffer=r.simulated.first_below_buffer,
                          baseline_min_balance=r.baseline.min_balance)

    insights: list[str] = []
    for c in currencies:
        months = max(1, round((c.last_on - c.first_on).days / 30) + 1)
        insights.append(
            f"In about {months} month(s) you received {c.currency} {c.gross:,.2f} in {c.payments} payment(s). "
            f"PayPal fees took {c.currency} {c.fees:,.2f} ({(c.fee_pct * 100).quantize(Decimal('0.1'))}% of gross, "
            f"about {inr(c.fee_cost_home)}).")
        insights.append(f"PayPal converted at an average of ₹{c.avg_rate:.2f} per {c.currency}; the latest was "
                        f"₹{c.latest_rate:.2f} on {fmt_date(c.latest_rate_on)}.")
        if c.reference_rate and c.spread_cost_home is not None and c.spread_pct is not None:
            if c.spread_cost_home > 0:
                insights.append(f"Against the ₹{c.reference_rate} rate you entered, conversion cost about "
                                f"{inr(c.spread_cost_home)} ({(c.spread_pct * 100).quantize(Decimal('0.1'))}%).")
            else:
                insights.append(f"PayPal's average rate was at or better than the ₹{c.reference_rate} rate you entered.")
    if foreign_items and main_cur:
        three = next((s for s in sensitivity if s.change_pct == Decimal("-3")), None)
        insights.append(f"{(share * 100).quantize(Decimal('1'))}% of your regular income arrives in {main_cur}"
                        + (f", so a 3% drop in {main_cur}/INR costs you about {inr(abs(three.monthly_effect))}/month."
                           if three else "."))
    if late:
        verdict = (f"dips below your {inr(a.safety_buffer)} buffer on {fmt_date(late.first_below_buffer)}"
                   if late.first_below_buffer else f"stays above your {inr(a.safety_buffer)} buffer")
        insights.append(f"If {late.merchant} pays {late.days} days late, your balance bottoms at {inr(late.min_balance)} "
                        f"on {fmt_date(late.min_balance_date)} and {verdict}.")
    return CrossBorder(as_of=profile.as_of, has_foreign=bool(currencies or foreign_items), home_currency="INR",
                       currencies=currencies, clients=clients, foreign_share=share, sensitivity=sensitivity,
                       sensitivity_currency=main_cur, late_client=late, insights=insights)
