"""Data provenance and financial consistency.

Sample (fictional) data, user-imported files, PayPal Transaction Search records and FINORA checkout captures must stay
distinguishable, never merge, and never inflate or double-count the balance. Runs in PayPal demo mode (no credentials).
"""
import sqlite3
import tempfile
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, func, select

from app.ai.tools import run_tool
from app.core.database import SessionLocal, ensure_columns
from app.data.models import Account, Obligation, Transaction
from app.services import repository as repo


@pytest.fixture(autouse=True)
def fresh_sample(client):
    r = client.post("/api/data/sample", json={"file_id": "paypal_activity", "replace": True})
    assert r.status_code == 200, r.text
    assert r.json()["origin"] == "sample"
    yield


def _ledger_balance() -> Decimal:
    with SessionLocal() as db:
        user = repo.get_primary_user(db)
        opening = db.scalar(select(func.coalesce(func.sum(Account.opening_balance), 0)).where(Account.user_id == user.id))
        txns = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).join(Account).where(Account.user_id == user.id))
        return Decimal(opening) + Decimal(txns)


def _origins() -> dict[str, int]:
    with SessionLocal() as db:
        user = repo.get_primary_user(db)
        return {f"{p['origin']}/{p['environment']}": p["count"] for p in repo.provenance(db, user)}


def _capture(client, amount: int, label: str, option: str = "pay_now") -> dict:
    order = client.post("/api/checkout/orders", json={"amount": amount, "label": label, "option_id": option,
                                                      "acknowledged": True}).json()
    token = parse_qs(urlparse(order["approve_url"]).query)["token"][0]
    redirect = client.post(f"/api/paypal-demo/orders/{token}/approve",
                           json={"funding": "paylater" if option != "pay_now" else "paypal"}).json()["redirect"]
    client.get(redirect.replace("http://localhost:5173", ""), follow_redirects=False)
    return client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).json()


# ---- Provenance is recorded, reported and never merged -----------------------------------------------------
def test_sample_data_is_labelled_everywhere(client):
    s = client.get("/api/status").json()
    assert s["sample_count"] == s["transaction_count"] > 200
    assert [p["origin"] for p in s["provenance"]] == ["sample"] and s["provenance"][0]["synthetic"]
    t = client.get("/api/transactions", params={"page_size": 5}).json()["items"]
    assert all(x["origin"] == "sample" and x["origin_label"] == "Sample data (fictional)" for x in t)
    assert client.get("/api/dashboard").json()["provenance"][0]["origin"] == "sample"
    pp = client.get("/api/integrations/paypal").json()
    assert pp["transaction_count"] == 0 and not pp["linked"] and pp["sample_transactions"] == s["transaction_count"]


def test_uploaded_sample_file_is_still_sample_but_a_real_file_is_user_import(client):
    content = client.get("/api/demo-files/paypal_activity").content
    r = client.post("/api/data/import", files={"file": ("renamed.csv", content, "text/csv")}, data={"replace": "true"})
    assert r.json()["origin"] == "sample"  # recognised by the SAMPLE id prefix even when renamed
    own = "date,description,amount,category,merchant\n2026-10-01,Salary,50000,Income,Employer\n2026-10-02,Rent,-12000,Rent,Landlord\n"
    r = client.post("/api/data/import", files={"file": ("mine.csv", own, "text/csv")},
                    data={"replace": "true", "opening_balance": "1000"})
    assert r.json()["origin"] == "user_import"
    assert client.get("/api/status").json()["sample_count"] == 0


def test_demo_sync_after_sample_does_not_inflate_balance(client):
    # Regression: an all-duplicate sync used to create an empty account whose opening balance doubled the balance.
    before = client.get("/api/dashboard").json()["kpis"]["current_balance"]
    r = client.post("/api/integrations/paypal/sync", json={"days": 30}).json()
    assert r["imported"] == 0
    assert client.get("/api/dashboard").json()["kpis"]["current_balance"] == before
    assert set(_origins()) == {"sample/None"}


def test_checkout_capture_goes_to_its_own_account_and_reconciles(client):
    before = Decimal(str(client.get("/api/dashboard").json()["kpis"]["current_balance"]))
    done = _capture(client, 5000, "Headphones")
    assert done["status"] == "captured"
    assert _origins() == {"sample/None": _origins()["sample/None"], "paypal_checkout/demo": 1}
    after = Decimal(str(client.get("/api/dashboard").json()["kpis"]["current_balance"]))
    assert after == before - 5000 == _ledger_balance()
    row = client.get("/api/transactions", params={"origin": "paypal_checkout"}).json()["items"][0]
    assert row["origin_label"] == "PayPal checkout (Orders API) · demo mode (simulated)"
    # Duplicate capture is refused as a no-op: same order, no second transaction.
    again = client.post(f"/api/checkout/orders/{done['id']}/capture", json={"confirm": True}).json()
    assert again["capture_id"] == done["capture_id"] and _origins()["paypal_checkout/demo"] == 1


def test_capturing_a_planned_purchase_removes_the_plan(client):
    # Regression: "plan it for payday" + later paying it counted the purchase twice in the forecast.
    on = client.get("/api/dashboard").json()["as_of"]
    client.post("/api/checkout/plan", json={"amount": 4000, "label": "Speaker", "on": on})
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).where(Obligation.title == "Planned: Speaker")) == 1
    done = _capture(client, 4000, "Speaker")
    assert done["snapshot"]["recorded"]["replaced_planned"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).where(Obligation.title == "Planned: Speaker")) == 0


def test_reset_marks_captured_orders_as_no_longer_in_the_twin(client):
    done = _capture(client, 3000, "Charger")
    client.post("/api/data/sample", json={"file_id": "paypal_activity", "replace": True})
    order = client.get(f"/api/checkout/orders/{done['id']}").json()
    assert order["status"] == "captured" and order["snapshot"]["recorded"]["cleared_from_twin"] is True
    assert "paypal_checkout/demo" not in _origins()


def test_pay_later_capture_is_marked_as_a_simulated_schedule(client):
    done = _capture(client, 20000, "Phone", option="pay_in_4")
    assert done["snapshot"]["recorded"] == {"kind": "obligations", "count": 4, "simulated_schedule": True}


# ---- One snapshot: dashboard, agent tools and simulator agree -------------------------------------------------
def test_dashboard_agent_and_simulator_use_the_same_snapshot(client):
    d = client.get("/api/dashboard").json()
    with SessionLocal() as db:
        user = repo.get_primary_user(db)
        snap = run_tool("get_financial_snapshot", {}, db, user).summary
    sim = client.post("/api/simulations/payment-options", json={"amount": 75000, "label": "Laptop"}).json()
    assert d["as_of"] == snap["as_of"] == sim["as_of"]
    assert d["kpis"]["current_balance"] == snap["current_balance"] == float(_ledger_balance())
    assert d["kpis"]["monthly_income"] == snap["monthly_income"]
    assert d["forecast"]["points"][0]["balance"] == sim["baseline_series"][0]


# ---- Migration of databases created before provenance tracking --------------------------------------------------
def test_old_database_gets_provenance_columns_marked_unknown():
    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, source TEXT)")
        c.execute("INSERT INTO accounts (name, source) VALUES ('PayPal account', 'paypal')")
    eng = create_engine(f"sqlite:///{path}")
    assert sorted(ensure_columns(eng)) == ["accounts.environment", "accounts.origin"]
    assert ensure_columns(eng) == []  # idempotent
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT origin, environment FROM accounts").fetchone() == ("unknown", None)


def test_agent_says_when_the_item_was_already_paid(client):
    # The audit case: a laptop captured earlier must not look like it's still only proposed.
    _capture(client, 5000, "Laptop")
    with SessionLocal() as db:
        out = run_tool("compare_payment_options", {"amount": 75000, "label": "Laptop"}, db, repo.get_primary_user(db))
    assert out.summary["already_paid"]["status"] == "captured" and out.summary["already_paid"]["paid_on"]
    assert out.lines[0].startswith("Note: you already paid for Laptop") and "buying another" in out.lines[0]


def test_fictional_and_real_data_never_share_a_ledger(client):
    # A real file added to the sample profile would blend fictional and real money into one balance.
    own = "date,description,amount,category,merchant\n2026-10-01,Salary,50000,Income,Employer\n"
    r = client.post("/api/data/import", files={"file": ("mine.csv", own, "text/csv")}, data={"replace": "false"})
    assert r.status_code == 409 and "fictional sample profile" in r.json()["detail"]
    # Replacing works, and then loading the sample on top of real data is refused the same way.
    assert client.post("/api/data/import", files={"file": ("mine.csv", own, "text/csv")},
                       data={"replace": "true", "opening_balance": "100"}).json()["origin"] == "user_import"
    r = client.post("/api/data/sample", json={"file_id": "paypal_activity", "replace": False})
    assert r.status_code == 409 and "real data" in r.json()["detail"]


def test_demo_preview_is_engine_output_and_touches_no_data(client):
    before = client.get("/api/status").json()["transaction_count"]
    p = client.get("/api/demo-preview").json()
    assert p["sample"] and p["amount"] == 75000 and p["transactions"] > 200
    assert client.get("/api/status").json()["transaction_count"] == before  # read-only: the twin is untouched
    sim = client.post("/api/simulations/payment-options", json={"amount": 75000, "label": "Laptop"}).json()
    # The fresh_sample fixture loaded the same profile, so the preview equals the engine's answer for it.
    assert p["recommendation"]["option_id"] == sim["recommendation"]["option_id"] == "pay_in_4"
    assert [o["min_balance"] for o in p["options"]] == [o["min_balance"] for o in sim["options"]]
    assert next(o for o in p["options"] if o["id"] == "pay_now")["safe"] is False
