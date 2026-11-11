"""API tests: checkout (Orders), subscriptions, Sign in with PayPal, planning endpoints and the assistant.

PayPal and the LLM are replaced by in-memory fakes through FastAPI dependency overrides,
so no network or credentials are needed.
"""
import itertools
import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.ai.llm import LlmClient, get_llm
from app.core.config import Settings, get_settings
from app.engine.types import add_months
from app.integrations.paypal.client import PayPalClient, get_paypal_client
from app.main import app
from tests.conftest import TODAY

ORDER_IDS = itertools.count(1)  # PayPal order ids are globally unique; the test DB outlives each fake


class FakePayPal:
    """Just enough of PayPal's REST API for the flows FINORA uses."""

    def __init__(self):
        self.orders: dict[str, dict] = {}
        self.subs = {"I-NETFLIX": {"status": "ACTIVE", "plan_id": "P-NF", "amount": "199.00"},
                     "I-OTHER": {"status": "ACTIVE", "plan_id": None, "amount": "199.00"},
                     "I-GYM": {"status": "ACTIVE", "plan_id": None, "amount": "1499.00"}}  # no payment history
        self.calls: list[tuple[str, str]] = []
        self.request_ids: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p, m = req.url.path, req.method
        self.calls.append((m, p))
        if "PayPal-Request-Id" in req.headers:
            self.request_ids.append(req.headers["PayPal-Request-Id"])
        if p == "/v1/oauth2/token":
            form = parse_qs(req.content.decode())
            if form.get("grant_type") == ["authorization_code"]:
                users = {"good": "tok-priya", "good2": "tok-arjun"}
                code = form["code"][0]
                return httpx.Response(200, json={"access_token": users[code]}) if code in users else httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "app-tok"})
        if p == "/v1/identity/openidconnect/userinfo":
            people = {"Bearer tok-priya": ("abc", "Priya Sharma", "priya@example.com"),
                      "Bearer tok-arjun": ("xyz", "Arjun Rao", "arjun@example.com")}
            uid, name, email = people[req.headers["Authorization"]]
            return httpx.Response(200, json={"user_id": f"https://www.paypal.com/webapps/auth/identity/user/{uid}",
                                             "name": name, "email": email, "email_verified": True})
        if p == "/v2/checkout/orders" and m == "POST":
            body = json.loads(req.content)
            oid = f"ORDER{next(ORDER_IDS)}"
            ctx = body["payment_source"]["paypal"]["experience_context"]
            assert ctx["user_action"] == "CONTINUE" and ctx["return_url"].endswith("/api/checkout/return")
            self.orders[oid] = {"status": "PAYER_ACTION_REQUIRED", "amount": body["purchase_units"][0]["amount"]}
            return httpx.Response(200, json={"id": oid, "status": "PAYER_ACTION_REQUIRED", "links": [
                {"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"}]})
        if p.startswith("/v2/checkout/orders/"):
            oid = p.split("/")[4]
            if p.endswith("/capture"):
                if self.orders[oid]["status"] != "APPROVED":
                    return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_NOT_APPROVED", "description": "Payer has not approved"}]})
                self.orders[oid]["status"] = "COMPLETED"
                return httpx.Response(201, json={"status": "COMPLETED", "purchase_units": [
                    {"payments": {"captures": [{"id": f"CAP-{oid}", "status": "COMPLETED"}]}}]})
            return httpx.Response(200, json={"id": oid, "status": self.orders[oid]["status"]})
        if p.startswith("/v1/billing/plans/"):
            return httpx.Response(200, json={"id": "P-NF", "name": "Netflix Premium", "billing_cycles": [
                {"tenure_type": "REGULAR", "pricing_scheme": {"fixed_price": {"value": "649", "currency_code": "INR"}}}]})
        if p.startswith("/v1/billing/subscriptions/"):
            parts = p.split("/")
            sid = parts[4]
            if sid not in self.subs:
                return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})
            if len(parts) == 6:
                if sid == "I-OTHER":
                    return httpx.Response(403, json={"name": "NOT_AUTHORIZED", "message": "Not the merchant"})
                self.subs[sid]["status"] = {"cancel": "CANCELLED", "suspend": "SUSPENDED", "activate": "ACTIVE"}[parts[5]]
                return httpx.Response(204)
            s = self.subs[sid]
            billing = {"last_payment": {"amount": {"value": s["amount"], "currency_code": "INR"}}}
            if s["status"] == "ACTIVE":  # like PayPal, no next billing time once cancelled
                billing["next_billing_time"] = "2026-12-01T10:00:00Z"
            return httpx.Response(200, json={"id": sid, "status": s["status"], "plan_id": s["plan_id"], "billing_info": billing})
        return httpx.Response(404, json={"name": "NOT_FOUND"})

    def approve(self, oid: str):
        self.orders[oid]["status"] = "APPROVED"


@pytest.fixture
def fake_pp():
    fake = FakePayPal()
    settings = Settings(paypal_client_id="id", paypal_client_secret="secret")
    app.dependency_overrides[get_paypal_client] = lambda: PayPalClient(settings, httpx.MockTransport(fake))
    yield fake
    app.dependency_overrides.pop(get_paypal_client, None)


@pytest.fixture(scope="module", autouse=True)
def demo_data(client):
    content = client.get("/api/demo-files/paypal_activity").content
    r = client.post("/api/data/import", files={"file": ("pp.csv", content, "text/csv")}, data={"replace": "true"})
    assert r.status_code == 200, r.text
    yield


# ---- Planning endpoints --------------------------------------------------------------------------------
def test_payment_options_endpoint(client):
    r = client.post("/api/simulations/payment-options", json={"amount": 75000, "label": "Laptop"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommendation"]["option_id"] == "pay_in_4"
    assert [o["id"] for o in body["options"]] == ["pay_now", "wait", "pay_in_4", "pay_monthly_12"]
    assert client.get("/api/simulations/pay-later-plans").json()["plans"][0]["id"] == "pay_in_4"


def test_affordability_endpoint(client):
    body = client.post("/api/simulations/affordability", json={"amount": 75000, "search_days": 60}).json()
    assert body["earliest"]["days_from_now"] == 12 and len(body["curve"]) == 61  # payday is always 12 days out
    x = body["max_safe_today"]
    assert 0 < x < 75000

    def selected_low(amount):
        sim = client.post("/api/simulations/purchase", json={"amount": amount}).json()
        return next(o for o in sim["timing_options"] if o["is_selected"])["min_balance"]

    assert selected_low(x) >= 20000 > selected_low(x + 1)  # the solver's answer is exactly the limit


def test_scenario_endpoint(client):
    r = client.post("/api/simulations/scenario", json={"changes": [{"type": "cancel_subscriptions", "count": 3},
                                                                  {"type": "income_delay", "days": 15}]})
    assert r.status_code == 200 and len(r.json()["applied"]) == 2
    assert client.post("/api/simulations/scenario", json={"changes": [{"type": "teleport"}]}).status_code == 422
    assert all(s["status"] == "available" for s in client.get("/api/simulations/scenarios").json())


# ---- Checkout (Orders API) ---------------------------------------------------------------------------
def test_checkout_requires_credentials_and_acknowledgement(client, demo_off):
    body = {"amount": 75000, "label": "Laptop", "option_id": "pay_now", "acknowledged": True}
    assert client.post("/api/checkout/orders", json=body).status_code == 400
    assert client.post("/api/checkout/orders", json={**body, "acknowledged": False}).status_code == 422


def test_pay_now_checkout_flow_records_transaction(client, fake_pp):
    before = client.get("/api/dashboard").json()["kpis"]["current_balance"]
    r = client.post("/api/checkout/orders", json={"amount": 75000, "label": "Laptop", "option_id": "pay_now", "acknowledged": True})
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "awaiting_approval" and "checkoutnow" in order["approve_url"]
    assert order["snapshot"]["safe"] is False  # the user was shown the risk before paying

    # Capturing before PayPal approval is refused.
    assert client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).status_code == 409

    fake_pp.approve(order["paypal_order_id"])
    ret = client.get(f"/api/checkout/return?token={order['paypal_order_id']}&PayerID=X", follow_redirects=False)
    assert ret.status_code == 303 and ret.headers["location"].endswith(f"/checkout/{order['id']}")
    assert client.get(f"/api/checkout/orders/{order['id']}").json()["status"] == "approved"

    assert client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": False}).status_code == 422
    done = client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).json()
    assert done["status"] == "captured" and done["capture_id"] == f"CAP-{order['paypal_order_id']}"
    assert client.get("/api/dashboard").json()["kpis"]["current_balance"] == before - 75000
    assert client.get("/api/transactions", params={"search": "PayPal checkout"}).json()["total"] == 1
    # Idempotent: capturing again is a no-op, and every write carried a PayPal-Request-Id.
    assert client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).json()["status"] == "captured"
    # The premature capture was refused locally, so PayPal saw exactly one create and one capture.
    assert len(fake_pp.request_ids) == 2 and fake_pp.request_ids[1] == f"{fake_pp.request_ids[0]}-capture"


def test_pay_later_checkout_records_instalments(client, fake_pp):
    order = client.post("/api/checkout/orders", json={"amount": 75000, "label": "Phone", "option_id": "pay_in_4",
                                                      "acknowledged": True}).json()
    assert order["funding"] == "paylater" and order["snapshot"]["terms_note"]
    fake_pp.approve(order["paypal_order_id"])
    client.get(f"/api/checkout/return?token={order['paypal_order_id']}", follow_redirects=False)
    done = client.post(f"/api/checkout/orders/{order['id']}/capture", json={"confirm": True}).json()
    assert done["snapshot"]["recorded"] == {"kind": "obligations", "count": 4, "simulated_schedule": True}
    instalments = [o for o in client.get("/api/obligations").json() if o["category"] == "Pay Later"]
    assert len(instalments) == 4 and sum(o["amount"] for o in instalments) == 75000


def test_checkout_cancel_and_plan(client, fake_pp):
    order = client.post("/api/checkout/orders", json={"amount": 1000, "label": "Shoes", "option_id": "pay_now",
                                                      "acknowledged": True}).json()
    client.get(f"/api/checkout/cancel?token={order['paypal_order_id']}", follow_redirects=False)
    assert client.get(f"/api/checkout/orders/{order['id']}").json()["status"] == "cancelled"
    wait = client.post("/api/checkout/orders", json={"amount": 1000, "label": "Shoes", "option_id": "wait", "acknowledged": True})
    assert wait.status_code == 422  # "wait" is planned, not paid
    planned = client.post("/api/checkout/plan", json={"amount": 1000, "label": "Shoes", "on": TODAY.isoformat()})
    assert planned.status_code == 201 and planned.json()["title"] == "Planned: Shoes"


# ---- Subscriptions -----------------------------------------------------------------------------------
def test_subscriptions_overview_and_manual_cancel(client):
    ov = client.get("/api/subscriptions").json()
    netflix = next(d for d in ov["detected"] if d["merchant"] == "Netflix")
    before = client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"]
    assert client.post("/api/subscriptions/mark", json={"recurring_key": netflix["key"], "cancelled": True}).status_code == 200
    assert client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"] == before - netflix["amount"]
    assert client.get("/api/subscriptions").json()["totals"]["monthly_cancelled"] == netflix["amount"]
    client.post("/api/subscriptions/mark", json={"recurring_key": netflix["key"], "cancelled": False})
    assert client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"] == before
    assert client.post("/api/subscriptions/mark", json={"recurring_key": "out:nobody", "cancelled": True}).status_code == 404


def test_link_and_cancel_paypal_subscription(client, fake_pp):
    assert client.post("/api/subscriptions/link", json={"paypal_subscription_id": "I-MISSING"}).status_code == 404
    linked = client.post("/api/subscriptions/link", json={"paypal_subscription_id": "I-NETFLIX"}).json()
    assert linked["name"] == "Netflix Premium" and linked["amount"] == 649.0 and linked["recurring_key"] == "out:netflix"
    before = client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"]

    assert client.post(f"/api/subscriptions/{linked['id']}/cancel", json={"confirm": False}).status_code == 422
    done = client.post(f"/api/subscriptions/{linked['id']}/cancel", json={"confirm": True}).json()
    assert done["status"] == "CANCELLED"
    assert ("POST", "/v1/billing/subscriptions/I-NETFLIX/cancel") in fake_pp.calls
    assert client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"] < before

    back = client.post(f"/api/subscriptions/{linked['id']}/activate", json={"confirm": True}).json()
    assert back["status"] == "ACTIVE" and client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"] == before
    assert client.delete(f"/api/subscriptions/{linked['id']}").status_code == 204


def test_third_party_subscription_cancel_is_explained(client, fake_pp):
    linked = client.post("/api/subscriptions/link", json={"paypal_subscription_id": "I-OTHER"}).json()
    r = client.post(f"/api/subscriptions/{linked['id']}/cancel", json={"confirm": True})
    assert r.status_code == 403 and "Automatic payments" in r.json()["detail"]["message"]
    client.delete(f"/api/subscriptions/{linked['id']}")


def _subs_monthly(client) -> float:
    return client.get("/api/dashboard").json()["kpis"]["subscriptions_monthly"]


def test_add_edit_remove_subscription(client):
    before = _subs_monthly(client)
    past = (TODAY - timedelta(days=1)).isoformat()
    assert client.post("/api/subscriptions/added", json={"name": "Gym", "amount": 1500, "next_billing_date": past}).status_code == 422
    added = client.post("/api/subscriptions/added", json={"name": "Cult Gym Pro", "amount": 1500,
                                                          "next_billing_date": TODAY.isoformat()})
    assert added.status_code == 201, added.text
    a = added.json()
    assert _subs_monthly(client) == before + 1500

    row = next(d for d in client.get("/api/subscriptions").json()["detected"] if d["key"] == a["key"])
    assert row["source"] == "manual" and row["added"]["id"] == a["id"] and row["occurrences"] == 0

    edited =client.put(f"/api/subscriptions/added/{a['id']}", json={"name": "Cult Gym Pro", "amount": 2000,
                                                                     "next_billing_date": TODAY.isoformat()})
    assert edited.json()["amount"] == 2000 and _subs_monthly(client) == before + 2000

    # Mark cancelled / restore works on added items too.
    client.post("/api/subscriptions/mark", json={"recurring_key": a["key"], "cancelled": True})
    assert _subs_monthly(client) == before
    client.post("/api/subscriptions/mark", json={"recurring_key": a["key"], "cancelled": False})

    assert client.delete(f"/api/subscriptions/added/{a['id']}").status_code == 204
    assert _subs_monthly(client) == before
    assert client.delete(f"/api/subscriptions/added/{a['id']}").status_code == 404


def test_added_subscription_not_double_counted_once_detected(client):
    before = _subs_monthly(client)
    a = client.post("/api/subscriptions/added", json={"name": "Netflix", "amount": 649,
                                                      "next_billing_date": TODAY.isoformat()}).json()
    ov = client.get("/api/subscriptions").json()
    assert _subs_monthly(client) == before  # Netflix is already detected from history
    assert [s["id"] for s in ov["superseded"]] == [a["id"]]
    client.delete(f"/api/subscriptions/added/{a['id']}")


def test_paypal_subscription_without_history_enters_forecast(client, fake_pp):
    before = _subs_monthly(client)
    linked = client.post("/api/subscriptions/link", json={"paypal_subscription_id": "I-GYM"}).json()
    assert linked["recurring_key"] is None and linked["amount"] == 1499.0
    assert _subs_monthly(client) == before + 1499
    row = next(d for d in client.get("/api/subscriptions").json()["detected"] if d["key"] == "paypal:I-GYM")
    assert row["source"] == "paypal" and row["linked"]["id"] == linked["id"]

    client.post(f"/api/subscriptions/{linked['id']}/cancel", json={"confirm": True})
    assert _subs_monthly(client) == before  # cancelled on PayPal → out of the forecast
    row = next(d for d in client.get("/api/subscriptions").json()["detected"] if d["key"] == "paypal:I-GYM")
    assert row["cancelled"] and row["cancelled_via"] == "paypal"  # still listed, as cancelled
    client.delete(f"/api/subscriptions/{linked['id']}")
    assert _subs_monthly(client) == before


def test_what_if_i_subscribe(client):
    r = client.post("/api/simulations/scenario", json={"changes": [{"type": "add_subscription", "amount": 499, "label": "Gym"}]})
    body = r.json()
    assert r.status_code == 200 and body["monthly_effect"] == -499
    today = TODAY
    charges = sum(1 for k in range(5) if add_months(today, k, today.day) <= today + timedelta(days=90))
    assert body["impacts"][-1]["delta"] == -499 * charges  # one charge today, then monthly
    chat = client.post("/api/assistant/chat", json={"messages": [
        {"role": "user", "content": "What if I add a ₹499/month gym membership?"}]}).json()
    call = chat["tool_calls"][0]
    assert call["tool"] == "simulate_scenario" and call["arguments"]["changes"][0]["label"] == "Gym membership"


# ---- Sign in with PayPal -------------------------------------------------------------------------------
@pytest.fixture
def login_settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "paypal_client_id", "id")
    monkeypatch.setattr(s, "paypal_client_secret", "secret")
    return s


def test_login_unavailable_without_credentials(client, demo_off):
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is False and me["login_available"] is False
    r = client.get("/api/auth/paypal/login", follow_redirects=False)
    assert r.status_code == 303 and "error=not_configured" in r.headers["location"]


def _sign_in(client, code: str) -> dict:
    r = client.get("/api/auth/paypal/login", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    ok = client.get("/api/auth/paypal/callback", params={"code": code, "state": state}, follow_redirects=False)
    assert ok.status_code == 303 and "signed_in=1" in ok.headers["location"]
    return client.get("/api/auth/me").json()


def test_sign_in_with_paypal_flow(client, fake_pp, login_settings):
    r = client.get("/api/auth/paypal/login", follow_redirects=False)
    target = urlparse(r.headers["location"])
    q = parse_qs(target.query)
    assert target.netloc == "www.sandbox.paypal.com" and target.path == "/signin/authorize"
    assert q["scope"] == ["openid profile email"] and q["redirect_uri"][0].endswith("/api/auth/paypal/callback")

    bad = client.get("/api/auth/paypal/callback", params={"code": "good", "state": "forged"}, follow_redirects=False)
    assert "error=state_mismatch" in bad.headers["location"]

    me = _sign_in(client, "good")
    assert me["authenticated"] and me["identity"]["email"] == "priya@example.com"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["authenticated"] is False

    # Open to everyone: a different PayPal account signs in just as freely.
    me = _sign_in(client, "good2")
    assert me["identity"]["name"] == "Arjun Rao"
    client.post("/api/auth/logout")

    # A tampered session cookie is ignored.
    client.cookies.set("finora_session", "eyJwYXlwYWxfdXNlcl9pZCI6ImFiYyJ9.forged")
    assert client.get("/api/auth/me").json()["authenticated"] is False
    client.cookies.clear()


def test_every_feature_works_signed_out(client):
    client.cookies.clear()
    assert client.get("/api/auth/me").json()["authenticated"] is False
    for method, path, body in [
        ("GET", "/api/dashboard", None), ("GET", "/api/twin", None), ("GET", "/api/transactions", None),
        ("GET", "/api/subscriptions", None), ("GET", "/api/settings", None), ("GET", "/api/integrations/paypal", None),
        ("POST", "/api/simulations/purchase", {"amount": 75000}),
        ("POST", "/api/simulations/payment-options", {"amount": 75000}),
        ("POST", "/api/simulations/affordability", {"amount": 75000}),
        ("POST", "/api/simulations/scenario", {"changes": [{"type": "income_delay", "days": 15}]}),
        ("POST", "/api/assistant/chat", {"messages": [{"role": "user", "content": "What's the most I can spend?"}]}),
        ("GET", "/api/checkout/orders", None),
    ]:
        r = client.request(method, path, json=body)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])


# ---- Assistant -----------------------------------------------------------------------------------------
def test_assistant_rules_mode(client):
    r = client.post("/api/assistant/chat", json={"messages": [
        {"role": "user", "content": "What happens if I buy a laptop worth ₹75,000 this month?"}]})
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "rules" and body["verified"]
    assert body["tool_calls"][0]["tool"] == "compare_payment_options"
    assert body["tool_calls"][0]["card"]["kind"] == "payment_options"
    assert "Pay in 4" in body["reply"]

    r = client.post("/api/assistant/chat", json={"messages": [
        {"role": "user", "content": "What if I cancel three subscriptions and my salary is delayed by 15 days?"}]})
    call = r.json()["tool_calls"][0]
    assert call["tool"] == "simulate_scenario" and len(call["summary"]["applied"]) == 2


def _llm_override(responses: list[dict]):
    replies = iter(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        sent = json.loads(req.content)
        assert sent["tools"] and sent["messages"][0]["role"] == "system"
        return httpx.Response(200, json={"choices": [{"message": next(replies)}]})

    s = Settings(openai_api_key="test-key")
    app.dependency_overrides[get_llm] = lambda: LlmClient(s, httpx.MockTransport(handler))


def _tool_call(name: str, args: dict) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def test_assistant_llm_mode_passes_guardrail(client):
    _llm_override([_tool_call("compare_payment_options", {"amount": 75000, "label": "Laptop"}),
                   {"role": "assistant", "content": "Use PayPal Pay in 4: ₹18,750 today and your low stays above ₹20,000."}])
    try:
        body = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "Can I buy a ₹75k laptop?"}]}).json()
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert body["mode"] == "llm" and body["guardrail"] == "passed" and "₹18,750" in body["reply"]


def test_assistant_llm_invented_figure_is_replaced(client):
    _llm_override([_tool_call("compare_payment_options", {"amount": 75000, "label": "Laptop"}),
                   {"role": "assistant", "content": "Sure! You'll still have ₹91,234 left."}])
    try:
        body = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "Can I buy a ₹75k laptop?"}]}).json()
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert body["guardrail"] == "replaced" and "91,234" not in body["reply"] and "₹91,234" in body["note"]
    assert body["tool_calls"][0]["card"]["recommendation"]["headline"] in body["reply"]  # may follow an "already paid" note


# ---- Cross-currency checkout (USD sandbox, INR profile) --------------------------------------------------
def _start(client, amount=75000):
    return client.post("/api/checkout/orders", json={"amount": amount, "label": "Laptop", "option_id": "pay_now",
                                                     "acknowledged": True})


def test_cross_currency_checkout_is_refused_without_a_rate(client, fake_pp, monkeypatch):
    monkeypatch.setattr(get_settings(), "paypal_checkout_currency", "USD")
    monkeypatch.setattr(get_settings(), "paypal_checkout_fx_rate", None)
    r = _start(client)
    assert r.status_code == 400 and "PAYPAL_CHECKOUT_FX_RATE" in r.json()["detail"]
    assert not any(p == "/v2/checkout/orders" for _, p in fake_pp.calls)  # nothing sent to PayPal


def test_cross_currency_checkout_converts_the_amount(client, fake_pp, monkeypatch):
    from decimal import Decimal
    monkeypatch.setattr(get_settings(), "paypal_checkout_currency", "USD")
    monkeypatch.setattr(get_settings(), "paypal_checkout_fx_rate", Decimal("84"))
    r = _start(client)
    assert r.status_code == 201, r.text
    body = r.json()
    sent = next(o["amount"] for o in fake_pp.orders.values())
    assert sent == {"currency_code": "USD", "value": "892.86"}  # ₹75,000 / 84, not $75,000
    assert body["amount"] == 75000 and body["currency"] == "INR"  # the twin keeps the home amount
    assert body["snapshot"]["paypal_charge"] == {"currency": "USD", "amount": "892.86", "rate": "84"}
