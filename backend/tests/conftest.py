import os
import tempfile
from datetime import date

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["FINORA_IGNORE_ENV_FILES"] = "1"  # never read the developer's .env (keys, sandbox currency, …)
os.environ["CHAT_RATE_LIMIT_PER_MINUTE"] = "0"  # tests call the chat endpoint many times; test_agent enables it explicitly
for _k in ("GROQ_API_KEY", "OPENAI_API_KEY", "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
    os.environ[_k] = ""  # overrides backend/.env too: never let a developer's real keys reach the test suite

# The demo data is generated relative to "today", and the demo storyline (a ₹75k laptop is unsafe
# today but safe on payday) depends on which bills fall before payday. Pin the app's clock so the
# suite gives the same answer every day. All app code reads the date via repository.today().
TODAY = date(2026, 11, 3)


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import repository

    repository.today = lambda: TODAY
    with TestClient(app) as c:
        yield c


@pytest.fixture
def demo_off(monkeypatch):
    """No PayPal credentials *and* the built-in PayPal demo disabled (PAYPAL_DEMO_MODE=false)."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "paypal_demo_mode", False)
