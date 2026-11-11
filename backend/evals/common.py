"""Shared eval setup: an isolated SQLite database loaded with the synthetic PayPal demo file.

The app's clock is pinned (as in the test suite) so every run of an eval sees the same data and
gives the same numbers. Nothing here touches the developer's real database.
"""
import os
import platform
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

EVAL_TODAY = date(2026, 11, 3)
ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
sys.path.insert(0, str(ROOT.parent))


def setup_demo(persona_file: str = "paypal_activity"):
    """Create tables, import the demo PayPal Activity file, return (session, user)."""
    from app.core.database import Base, SessionLocal, engine
    from app.data.demo_files import render
    from app.data.sources.files import FORMAT_SOURCE, parse_file
    from app.services import repository
    from app.services.import_service import store_transactions
    from app.services.seed import ensure_user

    repository.today = lambda: EVAL_TODAY
    Base.metadata.create_all(engine)
    db = SessionLocal()
    user = ensure_user(db)
    _, content, _ = render(persona_file, EVAL_TODAY)
    parsed = parse_file(content, "auto")
    source = FORMAT_SOURCE[parsed.format]
    store_transactions(db, user, source, parsed.transactions, parsed.opening_balance, True, parsed.format,
                       origin="sample")
    return db, user


def run_info() -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=ROOT, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {"commit": commit, "python": platform.python_version(), "eval_today": EVAL_TODAY.isoformat()}
