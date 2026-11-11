from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.data.demo_files import DEMO_FILES, render
from app.data.sources.files import CsvValidationError, parse_file
from app.data.sources.synthetic import TARGET_CURRENT_BALANCE
from app.engine.twin import build_profile
from app.engine.types import FxTxn, Txn
from app.integrations.paypal.source import PayPalNotConfigured, PayPalSource

TODAY = date(2026, 11, 3)


@pytest.mark.parametrize("file_id", [f.id for f in DEMO_FILES])
def test_demo_files_parse_and_reconcile(file_id):
    meta, content, suggested = render(file_id, TODAY)
    parsed = parse_file(content, "auto")
    assert parsed.format == meta.format
    opening = parsed.opening_balance if parsed.opening_balance is not None else suggested
    balance = opening + sum(t.amount for t in parsed.transactions)
    assert balance == TARGET_CURRENT_BALANCE

    txns = [Txn(posted_on=t.posted_on, description=t.description, merchant=t.merchant, category=t.category, amount=t.amount,
                fx=FxTxn(currency=t.fx.currency, gross=t.fx.gross, fee=t.fx.fee, net=t.fx.net, rate=t.fx.rate) if t.fx else None)
            for t in parsed.transactions]
    profile = build_profile(txns, balance, TODAY)
    assert profile.subscriptions_monthly == Decimal("2500.00")
    assert len(profile.recurring_outflows) >= 10
    if file_id == "paypal_freelancer":
        assert {r.merchant: r.currency for r in profile.recurring_income} == {
            "Brightline Labs LLC": "USD", "Northwind Studio Inc": "USD"}
        assert all(t.fx and t.fx.rate > 0 for t in parsed.transactions if "USD" in t.description)
    else:
        assert profile.monthly_income == Decimal("65000.00")


def test_bank_statement_newest_first_is_handled():
    csv = (
        "Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "03/10/2026,UPI/Swiggy/1/Food,300.00,,9700.00\n"
        "01/10/2026,NEFT/ACME/SALARY,,5000.00,10000.00\n"
    )
    parsed = parse_file(csv)
    assert parsed.format == "bank_statement"
    assert parsed.opening_balance == Decimal("5000.00")
    assert [t.amount for t in parsed.transactions] == [Decimal("5000.00"), Decimal("-300.00")]


def test_paypal_skips_non_completed_and_rejects_mixed_currency():
    base = "Date,Name,Type,Status,Currency,Net,Transaction ID,Balance\n"
    ok = parse_file(base + "01/10/2026,Netflix,Payment,Completed,INR,-649,A1,1000\n02/10/2026,X,Payment,Pending,INR,-5,A2,995\n")
    assert len(ok.transactions) == 1 and ok.warnings
    with pytest.raises(CsvValidationError):
        parse_file(base + "01/10/2026,A,P,Completed,INR,-1,B1,1\n01/10/2026,B,P,Completed,USD,-1,B2,1\n")


def test_validation_errors_report_lines():
    with pytest.raises(CsvValidationError) as exc:
        parse_file("date,description,amount\nnot-a-date,Thing,10\n")
    assert "line 2" in exc.value.errors[0]


def test_paypal_api_source_requires_credentials():
    with pytest.raises(PayPalNotConfigured):
        PayPalSource(Settings(paypal_client_id=None, paypal_client_secret=None)).fetch()


def test_paypal_api_source_maps_transactions():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path == "/v1/reporting/transactions":
            assert request.headers["Authorization"] == "Bearer tok"
            if request.url.params["start_date"].startswith("2026-10-04"):
                return httpx.Response(200, json={"total_pages": 1, "transaction_details": [
                    {"transaction_info": {"transaction_id": "9XY", "transaction_event_code": "T0006",
                                          "transaction_initiation_date": "2026-10-10T10:00:00+0000",
                                          "transaction_amount": {"currency_code": "INR", "value": "-649.00"},
                                          "transaction_status": "S"},
                     "payer_info": {"payer_name": {"alternate_full_name": "Netflix"}}},
                    {"transaction_info": {"transaction_id": "PENDING", "transaction_initiation_date": "2026-10-11T10:00:00+0000",
                                          "transaction_amount": {"value": "-5.00"}, "transaction_status": "P"}},
                ]})
            return httpx.Response(200, json={"total_pages": 1, "transaction_details": []})
        if request.url.path == "/v1/reporting/balances":
            return httpx.Response(200, json={"balances": [{"primary": True, "total_balance": {"currency_code": "INR", "value": "10000.00"}}]})
        return httpx.Response(404)

    s = Settings(paypal_client_id="id", paypal_client_secret="secret")
    src = PayPalSource(s, days=30, transport=httpx.MockTransport(handler), today=TODAY)
    txns = src.fetch()
    assert len(txns) == 1
    t = txns[0]
    assert t.external_id == "pp-9XY" and t.amount == Decimal("-649.00") and t.category == "Subscriptions"
    assert src.opening_balance == Decimal("10649.00")
