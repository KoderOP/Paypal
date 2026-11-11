"""Engine tests: Buy now / wait / split, goal solver, composable scenarios, assistant parser + guardrail."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ai import guardrail
from app.ai.rules import find_amount, plan_calls
from app.data.sources.synthetic import SyntheticSource
from app.engine.goals import solve_affordability
from app.engine.payment_options import DEFAULT_PLANS, PayLaterPlan, compare_payment_options
from app.engine.scenarios import (
    AddSubscription, CancelSubscriptions, ExpenseIncrease, IncomeDelay, IncreaseSavings, PurchaseChange, simulate_scenario,
)
from app.engine.simulation import PurchaseScenario, simulate_purchase
from app.engine.twin import RecurringItem, build_profile, with_added, without_cancelled
from app.engine.types import Assumptions, ObligationIn, Txn

TODAY = date(2026, 11, 3)
A = Assumptions()


@pytest.fixture(scope="module")
def profile():
    src = SyntheticSource(TODAY, seed=42)
    raw = src.fetch()
    txns = [Txn(posted_on=t.posted_on, description=t.description, merchant=t.merchant, category=t.category, amount=t.amount) for t in raw]
    balance = src.opening_balance(raw) + sum(t.amount for t in raw)
    obligations = [ObligationIn(**{k: v for k, v in o.items() if k != "notes"}) for o in src.obligations()]
    return build_profile(txns, balance, TODAY, obligations, A)


# ---- Pay Later schedules ----------------------------------------------------------------------------
def test_pay_in_4_schedule_is_exact():
    sched = DEFAULT_PLANS[0].schedule(Decimal("75000"), TODAY)
    assert [d for d, _ in sched] == [TODAY + timedelta(days=14 * k) for k in range(4)]
    assert sum(a for _, a in sched) == Decimal("75000.00")
    odd = DEFAULT_PLANS[0].schedule(Decimal("100.01"), TODAY)
    assert sum(a for _, a in odd) == Decimal("100.01")


def test_pay_monthly_amortises_interest():
    sched = DEFAULT_PLANS[1].schedule(Decimal("75000"), TODAY)
    assert len(sched) == 12 and sched[0][0] == date(2026, 12, 3)
    paid = sum(a for _, a in sched)
    assert Decimal("83000") < paid < Decimal("83700")  # ~₹8.4k interest at 19.99% APR
    zero = PayLaterPlan(id="z", name="Zero", instalments=6, interval_months=1, apr=Decimal("0"))
    assert sum(a for _, a in zero.schedule(Decimal("60000"), TODAY)) == Decimal("60000.00")


# ---- Buy now / wait / split -------------------------------------------------------------------------
def test_laptop_split_beats_waiting_and_paying_now(profile):
    c = compare_payment_options(profile, A, Decimal("75000"), "Laptop")
    by = {o.id: o for o in c.options}
    assert set(by) == {"pay_now", "wait", "pay_in_4", "pay_monthly_12"}
    assert not by["pay_now"].safe and by["pay_now"].min_balance == Decimal("13800.16")
    assert by["wait"].safe and by["wait"].get_it_on == profile.next_income_date
    assert by["pay_in_4"].safe and by["pay_in_4"].extra_cost == 0
    assert by["pay_monthly_12"].extra_cost > 0
    assert c.recommendation.verdict == "split" and c.recommendation.option_id == "pay_in_4"
    assert sum(o.recommended for o in c.options) == 1
    assert all(len(o.series) == len(c.dates) == len(c.baseline_series) for o in c.options)


def test_pay_now_series_shifts_by_exact_amount(profile):
    c = compare_payment_options(profile, A, Decimal("75000"), "Laptop")
    now = next(o for o in c.options if o.id == "pay_now")
    assert all(b - s == Decimal("75000") for b, s in zip(c.baseline_series, now.series))


def test_small_purchase_pay_now(profile):
    c = compare_payment_options(profile, A, Decimal("5000"), "Headphones")
    assert c.recommendation.verdict == "pay_now"


def test_without_free_split_wait_wins(profile):
    c = compare_payment_options(profile, A, Decimal("75000"), "Laptop", plans=[DEFAULT_PLANS[1]])
    assert c.recommendation.verdict == "wait"
    assert any("costs" in line for line in c.recommendation.explanation)


def test_huge_purchase_not_recommended(profile):
    c = compare_payment_options(profile, A, Decimal("900000"), "Car")
    assert c.recommendation.verdict == "not_recommended" and c.recommendation.option_id is None
    assert not any(o.recommended for o in c.options)


def test_comparison_is_reproducible(profile):
    assert compare_payment_options(profile, A, Decimal("75000")) == compare_payment_options(profile, A, Decimal("75000"))


# ---- Goal solver -------------------------------------------------------------------------------------
def test_max_safe_today_is_exact(profile):
    g = solve_affordability(profile, A, 60)
    x = g.max_safe_today
    assert x == Decimal("68800.00")

    def lowest(amount):
        sim = simulate_purchase(profile, A, PurchaseScenario(amount=amount, purchase_date=TODAY))
        return next(o for o in sim.timing_options if o.is_selected).min_balance

    assert lowest(x) >= A.safety_buffer
    assert lowest(x + 1) < A.safety_buffer


def test_earliest_safe_date_for_laptop_is_payday(profile):
    g = solve_affordability(profile, A, 60, Decimal("75000"))
    assert g.earliest.found and g.earliest.on == profile.next_income_date and g.earliest.days_from_now == 12
    assert g.best_this_month.on <= g.month_end == date(2026, 11, 30)


def test_unreachable_amount_reports_gap(profile):
    g = solve_affordability(profile, A, 30, Decimal("5000000"))
    assert not g.earliest.found and "short" in g.earliest.explanation


# ---- Scenarios ---------------------------------------------------------------------------------------
def test_cancel_three_subscriptions(profile):
    subs = sorted((r for r in profile.recurring_outflows if r.kind == "subscription"), key=lambda r: -r.amount)
    r = simulate_scenario(profile, A, [CancelSubscriptions(count=3)])
    saved = sum(s.amount for s in subs[:3])
    assert r.monthly_effect == saved
    assert r.impacts[-1].delta > 0


def test_cancel_by_name(profile):
    r = simulate_scenario(profile, A, [CancelSubscriptions(names=["netflix", "nope"])])
    assert "Netflix" in r.applied[0].description and any("nope" in n for n in r.notes)


def test_income_delay_lowers_the_low_point(profile):
    r = simulate_scenario(profile, A, [IncomeDelay(days=15)])
    assert r.simulated.min_balance < r.baseline.min_balance
    salary_day = profile.next_income_date
    moved = next(p for p in r.simulated.points if p.on == salary_day + timedelta(days=15))
    assert any(e.kind == "income" for e in moved.events)


def test_increase_savings_ten_percent(profile):
    r = simulate_scenario(profile, A, [IncreaseSavings(percent=Decimal("10"))])
    assert r.monthly_effect == Decimal("-1000.00")  # 10% of the ₹10,000 SIP


def test_expense_increase_scales_variable_spend(profile):
    r = simulate_scenario(profile, A, [ExpenseIncrease(percent=Decimal("20"))])
    assert r.simulated.end_balance < r.baseline.end_balance


def test_combined_scenario(profile):
    r = simulate_scenario(profile, A, [PurchaseChange(amount=Decimal("75000"), label="Laptop"), IncomeDelay(days=15)])
    assert len(r.applied) == 2 and r.risks[0].level in ("critical", "high")


def test_scenario_rejects_out_of_window_purchase(profile):
    with pytest.raises(ValueError):
        simulate_scenario(profile, A, [PurchaseChange(amount=Decimal("1"), on=TODAY + timedelta(days=400))])


def test_add_subscription_scenario(profile):
    r = simulate_scenario(profile, A, [AddSubscription(amount=Decimal("499"), label="Gym", start=TODAY + timedelta(days=5))])
    charges = [p for p in r.simulated.points if any(e.label == "Gym" for e in p.events)]
    assert [p.on for p in charges] == [date(2026, 11, 8), date(2026, 12, 8), date(2027, 1, 8)]
    assert r.monthly_effect == Decimal("-499") and r.impacts[-1].delta == Decimal("-1497.00")


def test_with_added_merges_and_dedupes(profile):
    def item(key, merchant, nxt):
        return RecurringItem(key=key, name=merchant, merchant=merchant, category="Subscriptions", kind="subscription",
                             direction="out", amount=Decimal("1500"), day_of_month=nxt.day, occurrences=0,
                             last_date=None, next_date=nxt, source="manual")
    gym = item("manual:1", "Cult Gym", TODAY - timedelta(days=3))  # stale date rolls forward
    dup = item("manual:2", "Netflix", TODAY)  # already detected → ignored
    p2 = with_added(profile, [gym, dup])
    added = [r for r in p2.recurring_outflows if r.source == "manual"]
    assert [r.key for r in added] == ["manual:1"] and added[0].next_date == date(2026, 11, 30)
    assert p2.subscriptions_monthly == profile.subscriptions_monthly + Decimal("1500")
    assert with_added(profile, []) is profile


def test_without_cancelled_recomputes_totals(profile):
    netflix = next(r for r in profile.recurring_outflows if r.merchant == "Netflix")
    p2 = without_cancelled(profile, {netflix.key})
    assert p2.subscriptions_monthly == profile.subscriptions_monthly - netflix.amount
    assert without_cancelled(profile, set()) is profile


# ---- Assistant parser + guardrail --------------------------------------------------------------------
SUBS = ["Netflix", "Spotify", "Amazon Prime"]


@pytest.mark.parametrize("q,tool", [
    ("What happens if I buy a laptop worth ₹75,000 this month?", "compare_payment_options"),
    ("What's the most I can spend this month?", "find_affordability"),
    ("What if I cancel three subscriptions?", "simulate_scenario"),
    ("What if my income is delayed by 15 days?", "simulate_scenario"),
    ("What if I increase my monthly savings by 10%?", "simulate_scenario"),
    ("What if I add a ₹499/month gym membership?", "simulate_scenario"),
    ("hello", "get_financial_snapshot"),
])
def test_rules_route_questions(q, tool):
    assert plan_calls(q, SUBS)[0][0] == tool


def test_rules_extract_arguments():
    [(_, args)] = plan_calls("What if I cancel three subscriptions?", SUBS)
    assert args["changes"] == [{"type": "cancel_subscriptions", "names": [], "count": 3}]
    [(_, args)] = plan_calls("Cancel Netflix and Spotify and my salary is delayed 2 weeks", SUBS)
    types = [c["type"] for c in args["changes"]]
    assert types == ["cancel_subscriptions", "income_delay"] and args["changes"][1]["days"] == 14
    assert args["changes"][0]["names"] == ["Netflix", "Spotify"]
    [(_, args)] = plan_calls("Can I buy a laptop worth ₹75,000?", SUBS)
    assert args == {"amount": 75000.0, "label": "Laptop"}
    [(_, args)] = plan_calls("What if I add a ₹499/month gym membership?", SUBS)
    assert args["changes"] == [{"type": "add_subscription", "amount": 499.0, "label": "Gym membership"}]
    [(_, args)] = plan_calls("What if I subscribe to youtube premium for ₹129 a month and cancel Netflix?", SUBS)
    assert args["changes"] == [{"type": "cancel_subscriptions", "names": ["Netflix"], "count": None},
                               {"type": "add_subscription", "amount": 129.0, "label": "Youtube premium"}]
    [(_, args)] = plan_calls("What if I cancel my ₹649 Netflix subscription?", SUBS)
    assert [c["type"] for c in args["changes"]] == ["cancel_subscriptions"]


def test_amount_parsing():
    assert find_amount("a ₹1.2 lakh vacation") == Decimal("120000")
    assert find_amount("phone for 40k") == Decimal("40000")
    assert find_amount("in 2026 spend rs 5,000") == Decimal("5000")
    assert find_amount("delayed by 15 days") is None


def test_guardrail():
    tools = [{"options": [{"min_balance": 46210.06, "first_payment": 18750.0}], "monthly": 649.0}]
    assert guardrail.check("Pay ₹18,750 today; your low is ₹46,210.", tools)[0]
    assert guardrail.check("That's about ₹7,788 a year.", tools)[0]  # 649 × 12
    ok, bad = guardrail.check("You'd save ₹99,999.", tools)
    assert not ok and bad == [Decimal("99999")]
