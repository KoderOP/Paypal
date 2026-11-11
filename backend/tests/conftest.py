import os
import tempfile
from datetime import date

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"

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
