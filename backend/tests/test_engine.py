from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.money import money
from app.data.sources.synthetic import TARGET_CURRENT_BALANCE, SyntheticSource
from app.engine.forecast import forecast_baseline
from app.engine.simulation import PurchaseScenario, inr, simulate_purchase
from app.engine.twin import build_profile
from app.engine.types import Assumptions, ObligationIn, Txn

TODAY = date(2026, 11, 3)


@pytest.fixture(scope="module")
def profile():
    src = SyntheticSource(TODAY, seed=42)
    raw = src.fetch()
    txns = [Txn(posted_on=t.posted_on, description=t.description, merchant=t.merchant, category=t.category, amount=t.amount) for t in raw]
    balance = src.opening_balance(raw) + sum(t.amount for t in raw)
    obligations = [ObligationIn(**{k: v for k, v in o.items() if k != "notes"}) for o in src.obligations()]
    return build_profile(txns, balance, TODAY, obligations, Assumptions())


def test_synthetic_balance_is_derived_from_transactions(profile):
    assert profile.current_balance == TARGET_CURRENT_BALANCE


def test_synthetic_is_deterministic():
    a, b = SyntheticSource(TODAY, 42).fetch(), SyntheticSource(TODAY, 42).fetch()
    assert a == b


def test_salary_detected_twelve_days_out(profile):
    assert profile.monthly_income == Decimal("65000.00")
    assert profile.next_income_date == TODAY + timedelta(days=12)


def test_recurring_detection(profile):
    merchants = {r.merchant for r in profile.recurring_outflows}
    assert {"Landlord - Mr. Sharma", "Netflix", "Spotify", "Groww Mutual Fund", "BESCOM"} <= merchants
    assert "Uber" not in merchants and "BigBasket" not in merchants
    assert profile.subscriptions_monthly == Decimal("2500.00")


def test_forecast_math_is_consistent(profile):
    fc = forecast_baseline(profile, Assumptions())
    assert len(fc.points) == 91
    assert fc.end_balance == money(fc.start_balance + fc.total_inflow - fc.total_outflow)
    # Salary lands on its expected day.
    salary_day = next(p for p in fc.points if p.on == profile.next_income_date)
    assert any(e.kind == "income" and e.amount == Decimal("65000") for e in salary_day.events)


def test_purchase_shifts_balance_by_exact_amount(profile):
    sim = simulate_purchase(profile, Assumptions(), PurchaseScenario(amount=Decimal("75000"), purchase_date=TODAY))
    for i in sim.impacts:
        assert i.delta == Decimal("-75000.00")
    assert sim.simulated.end_balance == sim.baseline.end_balance - Decimal("75000")


def test_laptop_recommendation_waits_for_salary(profile):
    sim = simulate_purchase(profile, Assumptions(), PurchaseScenario(amount=Decimal("75000"), purchase_date=TODAY))
    assert sim.recommendation.verdict == "wait"
    assert sim.recommendation.recommended_date == profile.next_income_date
    assert sum(o.is_recommended for o in sim.timing_options) == 1


def test_small_purchase_is_safe_now(profile):
    sim = simulate_purchase(profile, Assumptions(), PurchaseScenario(amount=Decimal("5000"), purchase_date=TODAY))
    assert sim.recommendation.verdict == "safe_now"


def test_huge_purchase_not_recommended(profile):
    sim = simulate_purchase(profile, Assumptions(), PurchaseScenario(amount=Decimal("500000"), purchase_date=TODAY))
    assert sim.recommendation.verdict == "not_recommended"
    assert sim.risks[0].level == "critical"


def test_simulation_is_reproducible(profile):
    sc = PurchaseScenario(amount=Decimal("75000"), purchase_date=TODAY)
    assert simulate_purchase(profile, Assumptions(), sc) == simulate_purchase(profile, Assumptions(), sc)


def test_purchase_date_outside_horizon_rejected(profile):
    with pytest.raises(ValueError):
        simulate_purchase(profile, Assumptions(), PurchaseScenario(amount=Decimal("1"), purchase_date=TODAY + timedelta(days=200)))


def test_inr_formatting():
    assert inr(Decimal("110000")) == "₹1,10,000"
    assert inr(Decimal("-14049.6")) == "-₹14,050"
    assert inr(Decimal("999")) == "₹999"
    assert inr(Decimal("12345678")) == "₹1,23,45,678"


def test_money_rejects_float():
    with pytest.raises(TypeError):
        money(1.1)
