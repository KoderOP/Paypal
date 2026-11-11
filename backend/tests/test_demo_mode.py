"""Everything works without PayPal credentials: the built-in PayPal demo, end to end through the API.

No dependency overrides here: these tests exercise the same code path a user gets on a fresh
install with an empty backend/.env (PAYPAL_DEMO_MODE defaults to on).
"""
from urllib.parse import parse_qs, urlparse

import pytest

from app.ai.rules import plan_calls
from tests.conftest import TODAY


@pytest.fixture(scope="module", autouse=True)
def demo_data(client):
    content = client.get("/api/demo-files/paypal_activity").content
    r = client.post("/api/data/import", files={"file": ("pp.csv", content, "text/csv")}, data={"replace": "true"})
    assert r.status_code == 200, r.text
    yield


def _approve_and_return(client, order: dict, funding: str = "paypal") -> str:
    """What the buyer does on the demo approval page: approve, then follow the redirect back to FINORA."""
    token = parse_qs(urlparse(order["approve_url"]).query)["token"][0]
    assert urlparse(order["approve_url"]).path == "/paypal-demo/checkout" and token == order["paypal_order_id"]
    view = client.get(f"/api/paypal-demo/orders/{token}").json()
    assert view["status"] == "PAYER_ACTION_REQUIRED" and view["amount"] == order["amount"]
    redirect = client.post(f"/api/paypal-demo/orders/{token}/approve", json={"funding": funding}).json()["redirect"]
    back = client.get(redirect.replace("http://localhost:5173", ""), follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"].endswith(f"/checkout/{order['id']}")
    return token


def test_status_reports_demo_everywhere(client):
    assert client.get("/api/paypal-demo/status").json()["demo"] is True
    assert client.get("/api/settings").json()["paypal"]["environment"] == "demo"
    me = client.get("/api/auth/me").json()
    assert me["login_available"] and me["demo"]
    assert client.get("/api/subscriptions").json()["api_available"] is True


def test_pay_in_full_checkout_works_without_paypal(client):
    before = client.get("/api/dashboard").json()["kpis"]["current_balance"]
    order = client.post("/api/checkout/orders", json={"amount": 5000, "label": "Headphones", "option_id": "pay_now",
                                                      "acknowledged": True}).json()
    assert order["status"] == "awaiting_approval" and order["environment"] == "demo"
    _approve_and_return(client, order)
    assert client.get(f"/api/checkout/orders/{order['id']}").json()["status"] == "approved"
    done = client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).json()
    assert done["status"] == "captured" and done["capture_id"].startswith("DEMOCAP")
    assert client.get("/api/dashboard").json()["kpis"]["current_balance"] == before - 5000


def test_pay_later_checkout_works_without_paypal(client):
    order = client.post("/api/checkout/orders", json={"amount": 75000, "label": "Laptop", "option_id": "pay_in_4",
                                                      "acknowledged": True}).json()
    _approve_and_return(client, order, "paylater")
    done = client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).json()
    assert done["snapshot"]["recorded"] == {"kind": "obligations", "count": 4, "simulated_schedule": True}
    for o in client.get("/api/obligations").json():
        if o["category"] == "Pay Later":
            client.delete(f"/api/obligations/{o['id']}")


def test_demo_checkout_cancel_and_capture_guard(client):
    order = client.post("/api/checkout/orders", json={"amount": 1000, "label": "Shoes", "option_id": "pay_now",
                                                      "acknowledged": True}).json()
    assert client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).status_code == 409
    token = order["paypal_order_id"]
    redirect = client.post(f"/api/paypal-demo/orders/{token}/cancel").json()["redirect"]
    client.get(redirect.replace("http://localhost:5173", ""), follow_redirects=False)
    assert client.get(f"/api/checkout/orders/{order['id']}").json()["status"] == "cancelled"
    assert client.post(f"/api/paypal-demo/orders/{token}/approve", json={}).status_code == 409


def test_sign_in_works_without_paypal(client):
    r = client.get("/api/auth/paypal/login", follow_redirects=False)
    target = urlparse(r.headers["location"])
    q = parse_qs(target.query)
    assert target.path == "/paypal-demo/signin/authorize"  # same path shape as paypal.com/signin/authorize
    bad = client.post("/api/paypal-demo/authorize", json={"state": q["state"][0], "redirect_uri": "https://evil.example/cb",
                                                         "name": "X", "email": "x@example.com"})
    assert bad.status_code == 400  # no open redirect
    redirect = client.post("/api/paypal-demo/authorize", json={
        "state": q["state"][0], "redirect_uri": q["redirect_uri"][0], "name": "Asha Rao", "email": "asha@example.com"}).json()["redirect"]
    back = client.get(redirect.replace("http://localhost:5173", ""), follow_redirects=False)
    assert "signed_in=1" in back.headers["location"]
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] and me["identity"]["email"] == "asha@example.com"
    client.post("/api/auth/logout")
    client.cookies.clear()


def test_subscriptions_work_without_paypal(client):
    ids = [s["id"] for s in client.get("/api/paypal-demo/status").json()["subscriptions"]]
    netflix_id = next(i for i in ids if "NETFLIX" in i)
    before = client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"]
    linked = client.post("/api/subscriptions/link", json={"paypal_subscription_id": netflix_id}).json()
    assert linked["recurring_key"] == "out:netflix" and linked["status"] == "ACTIVE" and linked["next_billing_date"]
    assert client.post(f"/api/subscriptions/{linked['id']}/suspend", json={"confirm": True}).json()["status"] == "SUSPENDED"
    assert client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"] < before
    assert client.post(f"/api/subscriptions/{linked['id']}/activate", json={"confirm": True}).json()["status"] == "ACTIVE"
    assert client.post(f"/api/subscriptions/{linked['id']}/activate", json={"confirm": True}).status_code == 409
    client.delete(f"/api/subscriptions/{linked['id']}")
    assert client.post("/api/subscriptions/link", json={"paypal_subscription_id": "I-NOPE"}).status_code == 404


def test_demo_pages_disabled_with_real_mode(client, demo_off):
    assert client.get("/api/paypal-demo/status").json()["demo"] is False
    assert client.get("/api/paypal-demo/orders/DEMO1").status_code == 404


def test_stress_test_api(client):
    r = client.get("/api/stress").json()
    assert r["resilience"] in ("strong", "moderate", "fragile") and len(r["bands"]) == 91
    ids = {s["id"] for s in r["shocks"]}
    assert {"job_loss_1", "job_loss_3", "pay_cut", "medical", "costs_up", "late_30"} <= ids
    job3 = next(s for s in r["shocks"] if s["id"] == "job_loss_3")
    assert job3["solvent"] is False and job3["first_below_zero"]
    b = r["bands"][-1]
    assert b["p10"] <= b["p50"] <= b["p90"] and abs(b["p50"] - b["baseline"]) < 0.05 * b["baseline"]  # unbiased median
    assert r == client.get("/api/stress").json()  # fixed seed: reproducible


def test_job_loss_scenario_and_assistant(client):
    s = client.post("/api/simulations/scenario", json={"changes": [{"type": "income_loss", "months": 2}]}).json()
    assert s["applied"][0]["one_off_effect"] < 0 and s["simulated"]["min_balance"] < s["baseline"]["min_balance"]
    assert plan_calls("What if I lose my job for 2 months?", [], [])[0][1]["changes"] == [{"type": "income_loss", "months": 2}]
    assert plan_calls("What if I get a 20% pay cut?", [], [])[0][1]["changes"] == [{"type": "income_loss", "months": 1, "percent": 20.0}]
    chat = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "How resilient are my finances?"}]}).json()
    assert chat["tool_calls"][0]["tool"] == "run_stress_test"


def test_every_page_api_works_without_paypal(client):
    """One request behind every screen in the app, on a fresh install with no PayPal credentials."""
    for method, path, body in [
        ("GET", "/api/status", None), ("GET", "/api/dashboard", None), ("GET", "/api/twin", None),
        ("GET", "/api/alerts", None), ("GET", "/api/integrations/paypal", None), ("GET", "/api/crossborder", None),
        ("GET", "/api/subscriptions", None), ("GET", "/api/transactions", None), ("GET", "/api/settings", None),
        ("GET", "/api/stress", None), ("GET", "/api/simulations/saved", None), ("GET", "/api/checkout/orders", None),
        ("GET", "/api/assistant/status", None), ("GET", "/api/demo-files", None), ("GET", "/api/auth/me", None),
        ("POST", "/api/simulations/purchase", {"amount": 75000}),
        ("POST", "/api/simulations/payment-options", {"amount": 75000}),
        ("POST", "/api/simulations/affordability", {"amount": 75000}),
        ("POST", "/api/simulations/compare", {"scenarios": [{"name": "a", "changes": [{"type": "income_loss"}]}]}),
        ("POST", "/api/checkout/plan", {"amount": 100, "label": "Test", "on": TODAY.isoformat()}),
    ]:
        r = client.request(method, path, json=body)
        assert r.status_code in (200, 201), (path, r.status_code, r.text[:200])
