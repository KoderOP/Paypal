"""Compare scenarios, assistant follow-ups, cross-border freelancer mode and proactive alerts."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ai.rules import plan_calls, plan_followup
from app.data.sources.files import CsvValidationError, parse_file
from app.data.sources.synthetic import SyntheticSource
from app.engine.alerts import build_alerts
from app.engine.crossborder import cross_border
from app.engine.forecast import forecast_baseline
from app.engine.scenarios import (
    CancelSubscriptions, FxChange, IncomeDelay, PurchaseChange, compare_scenarios, simulate_scenario,
)
from app.engine.twin import build_profile
from app.engine.types import Assumptions, FxTxn, ObligationIn, Txn, add_months
from tests.conftest import TODAY

A = Assumptions()


def _txns(raw) -> list[Txn]:
    return [Txn(posted_on=t.posted_on, description=t.description, merchant=t.merchant, category=t.category,
                amount=t.amount, fx=FxTxn(currency=t.fx.currency, gross=t.fx.gross, fee=t.fx.fee, net=t.fx.net,
                                          rate=t.fx.rate) if t.fx else None) for t in raw]


def _profile(persona: str, as_of: date = TODAY, obligations=None):
    src = SyntheticSource(TODAY, 42, persona)
    raw = src.fetch()
    txns = _txns(raw)
    balance = src.opening_balance(raw) + sum(t.amount for t in raw)
    return build_profile(txns, balance, as_of, obligations or [], A), txns


@pytest.fixture(scope="module")
def salaried():
    return _profile("salaried")


@pytest.fixture(scope="module")
def freelancer():
    return _profile("freelancer")


# ---- Compare -----------------------------------------------------------------------------------------
def test_compare_cancel_vs_delay_laptop_vs_both(salaried):
    profile, _ = salaried
    payday = profile.next_income_date
    laptop_later = PurchaseChange(amount=Decimal("75000"), on=payday, label="Laptop")
    c = compare_scenarios(profile, A, [
        ("Cancel 3 subscriptions", [CancelSubscriptions(count=3)]),
        ("Laptop on payday", [laptop_later]),
        ("Both", [CancelSubscriptions(count=3), laptop_later]),
        ("Laptop today", [PurchaseChange(amount=Decimal("75000"), label="Laptop")]),
    ])
    by = {s.name: s for s in c.scenarios}
    assert [s.id for s in c.scenarios] == ["s1", "s2", "s3", "s4"]
    assert not by["Laptop today"].safe and by["Laptop on payday"].safe and by["Both"].safe
    assert by["Both"].end_balance > by["Laptop on payday"].end_balance  # cancelling still helps
    assert c.best_id == by["Cancel 3 subscriptions"].id and sum(s.best for s in c.scenarios) == 1
    assert all(len(s.series) == len(c.dates) == len(c.baseline_series) for s in c.scenarios)
    assert c.summary[0].startswith("Best: Cancel 3 subscriptions")
    with pytest.raises(ValueError):
        compare_scenarios(profile, A, [("x", [CancelSubscriptions(count=1)])] * 5)


def test_compare_when_nothing_is_safe(salaried):
    profile, _ = salaried
    c = compare_scenarios(profile, A, [("Car", [PurchaseChange(amount=Decimal("900000"), label="Car")])])
    assert c.best_id is None and c.summary[0].startswith("None of these stay above")


# ---- Cross-border ------------------------------------------------------------------------------------
def test_freelancer_income_is_foreign(freelancer):
    profile, _ = freelancer
    assert {r.merchant: r.currency for r in profile.recurring_income} == {
        "Brightline Labs LLC": "USD", "Northwind Studio Inc": "USD"}
    brightline = next(r for r in profile.recurring_income if r.merchant == "Brightline Labs LLC")
    assert brightline.foreign_amount == Decimal("573.30")  # $600 gross minus the illustrative 4.4% + $0.30 fee
    assert brightline.next_date == TODAY + timedelta(days=12)


def test_fx_change_scales_only_foreign_income(freelancer, salaried):
    profile, _ = freelancer
    r = simulate_scenario(profile, A, [FxChange(percent=Decimal("-3"))])
    expected = -(sum(x.amount for x in profile.recurring_income) * Decimal("0.03")).quantize(Decimal("0.01"))
    assert r.monthly_effect == expected and r.simulated.end_balance < r.baseline.end_balance
    s = simulate_scenario(salaried[0], A, [FxChange(percent=Decimal("-3"))])
    assert s.applied == [] and "No regular income in USD" in s.notes[0]


def test_one_client_pays_late(freelancer):
    profile, _ = freelancer
    r = simulate_scenario(profile, A, [IncomeDelay(days=15, merchant="Northwind")])
    assert "Northwind Studio Inc's payment" in r.applied[0].description
    nxt = next(x for x in profile.recurring_income if x.merchant.startswith("Northwind")).next_date
    moved = next(p for p in r.simulated.points if p.on == nxt + timedelta(days=15))
    assert any(e.kind == "income" for e in moved.events)
    assert simulate_scenario(profile, A, [IncomeDelay(days=5, merchant="Nobody")]).notes


def test_cross_border_summary(freelancer):
    profile, txns = freelancer
    cb = cross_border(profile, txns, A, {"USD": Decimal("84.00")})
    usd = cb.currencies[0]
    foreign = [t for t in txns if t.fx]
    assert usd.currency == "USD" and usd.payments == len(foreign)
    assert usd.fees == sum(-t.fx.fee for t in foreign) and usd.received_home == sum(t.amount for t in foreign)
    assert Decimal("80") < usd.avg_rate < Decimal("84")  # 3% illustrative spread under ~84
    assert usd.spread_cost_home > 0 and Decimal("0.02") < usd.spread_pct < Decimal("0.05")
    assert [s.change_pct for s in cb.sensitivity] == [-5, -3, 3, 5]
    assert cb.sensitivity[0].monthly_effect < 0 < cb.sensitivity[-1].monthly_effect
    assert cb.late_client.merchant == "Brightline Labs LLC" and cb.foreign_share == Decimal("1.0000")
    assert any("PayPal fees took USD" in line for line in cb.insights)
    assert not cross_border(*_profile("salaried"), A).has_foreign


HEADER = "Date,Time,Name,Type,Status,Currency,Gross,Fee,Net,Balance,Transaction ID,Reference Txn ID\n"


def test_multicurrency_parse_nearest_rate_and_transfers():
    csv = HEADER + (
        "01/10/2026,10:00:00,Acme Inc,Payment Received,Completed,USD,100.00,-4.70,95.30,95.30,R1,\n"
        "01/10/2026,10:01:00,,General Currency Conversion,Completed,USD,-95.30,0.00,-95.30,0.00,C1,R1\n"
        "01/10/2026,10:01:00,,General Currency Conversion,Completed,INR,7900.37,0.00,7900.37,17900.37,C2,R1\n"
        "05/10/2026,09:00:00,Beta LLC,Payment Received,Completed,USD,50.00,-2.50,47.50,47.50,R2,\n"
        "06/10/2026,09:00:00,Bank,General Withdrawal,Completed,INR,-5000.00,0.00,-5000.00,12900.37,W1,\n"
    )
    p = parse_file(csv)
    by = {t.external_id: t for t in p.transactions}
    assert by["pp-R1"].amount == Decimal("7900.37") and by["pp-R1"].fx.rate_source == "paypal_conversion"
    assert by["pp-R2"].fx.rate_source == "nearest_conversion"
    assert by["pp-R2"].amount == (Decimal("47.50") * by["pp-R1"].fx.rate).quantize(Decimal("0.01"))
    assert by["pp-W1"].category == "Transfer" and len(p.transactions) == 3
    assert p.opening_balance == Decimal("10000.00") and any("nearest" in w for w in p.warnings)
    with pytest.raises(CsvValidationError):
        parse_file(HEADER + "01/10/2026,10:00:00,X,Payment Received,Completed,EUR,10,0,10,10,E1,\n"
                            "01/10/2026,11:00:00,Y,Payment,Completed,INR,-1,0,-1,99,I1,\n")


def test_transfers_are_not_income_or_spending():
    txns = [Txn(posted_on=TODAY - timedelta(days=30 * k), description="General Withdrawal", merchant="Bank",
                category="Transfer", amount=Decimal("-5000")) for k in range(1, 5)]
    p = build_profile(txns, Decimal("1000"), TODAY)
    assert p.recurring_outflows == [] and p.avg_monthly_spending == 0 and p.months == []


# ---- Alerts ------------------------------------------------------------------------------------------
def _alerts(profile, txns):
    return build_alerts(profile, forecast_baseline(profile, A), txns, A)


def test_alerts_late_income_and_due_soon(salaried):
    _, txns = salaried
    late = build_profile(txns, Decimal("110000"), TODAY + timedelta(days=16),
                         [ObligationIn(title="Phone · Pay Later 2/4", category="Pay Later", amount=Decimal("18750"),
                                       due_on=TODAY + timedelta(days=17))], A)
    kinds = {a.kind: a for a in _alerts(late, txns)}
    assert "Acme Technologies hasn't paid yet (4 days late)" == kinds["income_late"].title
    assert kinds["due_soon"].title.startswith("Pay Later instalment due tomorrow: ₹18,750")


def test_alerts_below_buffer_and_ids_are_stable(salaried):
    profile, txns = salaried
    tight = profile.model_copy(update={"obligations": [ObligationIn(title="Big bill", category="Other",
                                                                    amount=Decimal("90000"), due_on=TODAY + timedelta(days=5))]})
    alerts = _alerts(tight, txns)
    assert alerts[0].level in ("critical", "warning") and alerts[0].kind in ("below_zero", "below_buffer")
    assert [a.id for a in alerts] == [a.id for a in _alerts(tight, txns)]


def test_alerts_bill_before_income_and_price_increase():
    def monthly(day, merchant, cat, amount, months=6, bump=None):
        """`months` payments on `day` of each month, the latest one last month; `bump` = the latest amount."""
        return [Txn(posted_on=add_months(TODAY.replace(day=day), -k, day), description=merchant, merchant=merchant,
                    category=cat, amount=Decimal(bump if bump and k == 1 else amount))
                for k in range(months, 0, -1)]
    txns = (monthly(8, "Employer", "Income", 50000) + monthly(5, "Landlord", "Rent", -15000)
            + monthly(10, "Spotify", "Subscriptions", -119, bump=-149))
    p = build_profile(txns, Decimal("60000"), TODAY)
    kinds = {a.kind: a for a in build_alerts(p, forecast_baseline(p, A), txns, A)}
    assert "due 3 days before Employer pays you" in kinds["bill_before_income"].title
    assert kinds["price_increase"].title == "Spotify went up 25%: ₹119 → ₹149"


# ---- Assistant: FX intents + follow-ups --------------------------------------------------------------
SUBS, PAYERS = ["Netflix", "Spotify"], ["Brightline Labs LLC", "Northwind Studio Inc"]


@pytest.mark.parametrize("q,pct", [
    ("What if USD/INR drops 3%?", -3.0), ("What if the dollar rises 2%?", 2.0),
    ("What if the rupee strengthens by 3%?", -3.0), ("What if the rupee weakens 4%?", 4.0),
])
def test_fx_intents(q, pct):
    [(tool, args)] = plan_calls(q, SUBS, PAYERS)
    assert tool == "simulate_scenario" and args["changes"] == [{"type": "fx_change", "percent": pct, "currency": "USD"}]


def test_client_late_and_cross_border_routing():
    [(_, args)] = plan_calls("What if Brightline pays 15 days late?", SUBS, PAYERS)
    assert args["changes"][0] == {"type": "income_delay", "days": 15, "all_future": False, "merchant": "Brightline Labs LLC"}
    assert plan_calls("When should I withdraw to my bank?", SUBS, PAYERS)[0][0] == "get_cross_border_summary"
    assert plan_calls("How much am I losing to PayPal fees?", SUBS, PAYERS)[0][0] == "get_cross_border_summary"


def test_follow_up_builds_on_previous_scenario():
    ctx = {"tool": "simulate_scenario", "arguments": {"changes": [{"type": "cancel_subscriptions", "count": 3}]}}
    calls, built_on = plan_followup("And what if my salary is also late?", ctx, SUBS)
    assert [c["type"] for c in calls[0][1]["changes"]] == ["cancel_subscriptions", "income_delay"]
    assert built_on == "cancelled subscriptions"

    ctx2 = {"tool": "simulate_scenario", "arguments": {"changes": calls[0][1]["changes"]}}
    calls, _ = plan_followup("What about 20 days?", ctx2, SUBS)
    assert calls[0][1]["changes"][1]["days"] == 20 and len(calls[0][1]["changes"]) == 2

    calls, built_on = plan_followup("What if I cancel three subscriptions?", ctx2, SUBS)  # not a follow-up
    assert built_on is None and len(calls[0][1]["changes"]) == 1


def test_follow_up_from_purchase_and_amount_tweak():
    ctx = {"tool": "compare_payment_options", "arguments": {"amount": 75000.0, "label": "Laptop"}}
    calls, built_on = plan_followup("And what if my salary is also delayed by 10 days?", ctx, SUBS)
    assert calls[0][0] == "simulate_scenario" and built_on == "Laptop"
    assert calls[0][1]["changes"][0] == {"type": "purchase", "amount": 75000.0, "label": "Laptop"}
    calls, _ = plan_followup("What about ₹50,000 instead?", ctx, SUBS)
    assert calls == [("compare_payment_options", {"amount": 50000.0, "label": "Laptop"})]


# ---- API ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def freelancer_data(client):
    content = client.get("/api/demo-files/paypal_freelancer").content
    r = client.post("/api/data/import", files={"file": ("pp.csv", content, "text/csv")}, data={"replace": "true"})
    assert r.status_code == 200, r.text
    yield
    content = client.get("/api/demo-files/paypal_activity").content
    client.post("/api/data/import", files={"file": ("pp.csv", content, "text/csv")}, data={"replace": "true"})


def test_crossborder_api(client, freelancer_data):
    cb = client.get("/api/crossborder").json()
    assert cb["has_foreign"] and cb["currencies"][0]["currency"] == "USD" and cb["currencies"][0]["spread_cost_home"] is None
    cb = client.put("/api/crossborder/reference-rate", json={"currency": "USD", "rate": 84}).json()
    assert cb["currencies"][0]["reference_rate"] == 84.0 and cb["currencies"][0]["spread_cost_home"] > 0
    cb = client.put("/api/crossborder/reference-rate", json={"currency": "USD", "rate": None}).json()
    assert cb["currencies"][0]["reference_rate"] is None
    chat = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "What if USD/INR drops 3%?"}]}).json()
    assert chat["tool_calls"][0]["summary"]["monthly_effect"] < 0


def test_compare_and_saved_api(client, freelancer_data):
    body = {"scenarios": [{"name": "USD −3%", "changes": [{"type": "fx_change", "percent": -3}]},
                          {"name": "Client late", "changes": [{"type": "income_delay", "days": 15, "merchant": "Brightline"}]}]}
    r = client.post("/api/simulations/compare", json=body)
    assert r.status_code == 200 and len(r.json()["scenarios"]) == 2
    assert client.post("/api/simulations/compare", json={"scenarios": body["scenarios"] * 3}).status_code == 422
    assert client.post("/api/simulations/compare", json={"scenarios": [{"name": "x", "changes": [{"type": "nope"}]}]}).status_code == 422
    saved = client.post("/api/simulations/saved", json=body["scenarios"][0]).json()
    assert saved["changes"][0]["type"] == "fx_change"
    assert any(s["id"] == saved["id"] for s in client.get("/api/simulations/saved").json())
    assert client.delete(f"/api/simulations/saved/{saved['id']}").status_code == 204


def test_alerts_api_dismiss_and_restore(client, freelancer_data):
    due = (TODAY + timedelta(days=1)).isoformat()
    o = client.post("/api/obligations", json={"title": "Phone · Pay Later 2/4", "category": "Pay Later",
                                              "amount": 18750, "due_on": due}).json()
    alerts = client.get("/api/alerts").json()["alerts"]
    due_soon = next(a for a in alerts if a["kind"] == "due_soon")
    assert due_soon["title"] == "Pay Later instalment due tomorrow: ₹18,750"
    after = client.post("/api/alerts/dismiss", json={"id": due_soon["id"]}).json()
    assert all(a["id"] != due_soon["id"] for a in after["alerts"]) and after["dismissed"] == 1
    assert client.post("/api/alerts/dismiss", json={"id": "made-up"}).json()["dismissed"] == 1  # unknown ids ignored
    assert client.post("/api/alerts/restore").json()["dismissed"] == 0
    client.delete(f"/api/obligations/{o['id']}")


def test_assistant_follow_up_api(client, freelancer_data):
    first = client.post("/api/assistant/chat", json={"messages": [
        {"role": "user", "content": "What if I cancel three subscriptions?"}]}).json()
    assert first["context"]["tool"] == "simulate_scenario"
    second = client.post("/api/assistant/chat", json={
        "messages": [{"role": "user", "content": "What if I cancel three subscriptions?"},
                     {"role": "assistant", "content": first["reply"]},
                     {"role": "user", "content": "And what if Brightline also pays 15 days late?"}],
        "context": first["context"]}).json()
    assert second["built_on"] == "cancelled subscriptions"
    assert [a["type"] for a in second["tool_calls"][0]["summary"]["applied"]] == ["cancel_subscriptions", "income_delay"]
