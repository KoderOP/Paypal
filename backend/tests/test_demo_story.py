"""The landing page's live demo asks "Should I buy a ₹75,000 laptop?". The demo data is generated
relative to the real date, so the story must hold whatever day a judge runs it: paying in full is
unsafe, and PayPal Pay in 4 is safe and recommended."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.data.demo_files import render
from app.data.sources.files import parse_file
from app.engine.payment_options import compare_payment_options
from app.engine.twin import build_profile
from app.engine.types import Assumptions, Txn

DEMO_AMOUNT = Decimal("75000")


@pytest.mark.parametrize("offset", range(0, 366, 9))
def test_demo_story_holds_on_any_date(offset):
    today = date(2026, 1, 1) + timedelta(days=offset)
    _, content, _ = render("paypal_activity", today)
    parsed = parse_file(content, "auto")
    txns = [Txn(posted_on=t.posted_on, description=t.description, merchant=t.merchant, category=t.category, amount=t.amount)
            for t in parsed.transactions]
    balance = parsed.opening_balance + sum((t.amount for t in txns), Decimal(0))
    a = Assumptions()
    c = compare_payment_options(build_profile(txns, balance, today, None, a), a, DEMO_AMOUNT, "Laptop")
    opts = {o.id: o for o in c.options}
    assert not opts["pay_now"].safe, today
    assert opts["pay_in_4"].safe, today
    assert c.recommendation.option_id == "pay_in_4", (today, c.recommendation.headline)
