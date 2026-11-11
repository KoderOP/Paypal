from datetime import timedelta

import pytest

from tests.conftest import TODAY


@pytest.fixture(scope="module", autouse=True)
def demo_data(client):
    client.delete("/api/data")
    assert client.get("/api/status").json()["has_data"] is False
    assert client.get("/api/dashboard").status_code == 404
    content = client.get("/api/demo-files/paypal_activity").content
    r = client.post("/api/data/import", files={"file": ("pp.csv", content, "text/csv")}, data={"replace": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["format"] == "paypal_activity"
    yield


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_status_and_demo_files(client):
    st = client.get("/api/status").json()
    assert st["has_data"] and st["data_source"] == "paypal_activity"
    files = client.get("/api/demo-files").json()
    assert {f["id"] for f in files} == {"paypal_activity", "bank_statement", "transactions", "paypal_freelancer"}


def test_dashboard(client):
    d = client.get("/api/dashboard").json()
    assert d["kpis"]["current_balance"] == 110000.0
    assert d["history"][-1]["balance"] == 110000.0
    assert len(d["forecast"]["points"]) == 91


def test_paypal_overview(client):
    p = client.get("/api/integrations/paypal").json()
    assert p["linked"] and p["transaction_count"] > 100 and not p["configured"]
    assert client.post("/api/integrations/paypal/sync", json={"days": 30}).status_code == 400


def test_reimport_is_idempotent(client):
    content = client.get("/api/demo-files/paypal_activity").content
    r = client.post("/api/data/import", files={"file": ("pp.csv", content, "text/csv")}).json()
    assert r["imported"] == 0 and r["skipped_duplicates"] == r["rows"]


def test_transactions_filters(client):
    netflix = client.get("/api/transactions", params={"search": "netflix"}).json()
    assert netflix["total"] >= 5
    income = client.get("/api/transactions", params={"direction": "in"}).json()
    assert all(t["amount"] > 0 for t in income["items"])


def test_purchase_simulation(client):
    body = client.post("/api/simulations/purchase", json={"amount": 75000, "label": "Laptop"}).json()
    assert body["recommendation"]["verdict"] == "wait"
    assert [i["day"] for i in body["impacts"]] == [30, 60, 90]
    assert client.post("/api/simulations/purchase", json={"amount": -5}).status_code == 422
    far = (TODAY + timedelta(days=400)).isoformat()
    assert client.post("/api/simulations/purchase", json={"amount": 100, "purchase_date": far}).status_code == 422


def test_profile_name_and_buffer(client):
    r = client.put("/api/settings", json={"name": "  Priya Sharma "}).json()
    assert r["user_name"] == "Priya Sharma"
    assert client.put("/api/settings", json={"name": "   "}).status_code == 422
    assert client.put("/api/settings", json={"safety_buffer": 5000}).json()["assumptions"]["safety_buffer"] == 5000.0
    client.put("/api/settings", json={"safety_buffer": 20000})


def test_obligation_crud(client):
    due = (TODAY + timedelta(days=10)).isoformat()
    created = client.post("/api/obligations", json={"title": "Test fee", "amount": 1000, "due_on": due}).json()
    assert client.delete(f"/api/obligations/{created['id']}").status_code == 204


def test_bad_upload(client):
    bad = client.post("/api/data/import", files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert bad.status_code == 422
