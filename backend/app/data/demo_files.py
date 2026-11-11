"""Downloadable demo files. They contain SYNTHETIC data (clearly labelled) rendered in the
same formats real users upload: a PayPal Activity report, a bank statement and a plain
transaction CSV. Generated relative to today so the demo story always holds."""
import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.data.sources.base import NormalizedTransaction
from app.data.sources.synthetic import SyntheticSource


@dataclass(frozen=True)
class DemoFile:
    id: str
    title: str
    format: str
    filename: str
    description: str


DEMO_FILES = [
    DemoFile("paypal_activity", "PayPal Activity report (demo)", "paypal_activity", "finora-demo-paypal-activity.csv",
             "6 months of synthetic PayPal activity in the Activity → Statements CSV layout, with running balance."),
    DemoFile("bank_statement", "Bank statement (demo)", "bank_statement", "finora-demo-bank-statement.csv",
             "6 months of synthetic salary-account entries in a typical Indian bank statement layout."),
    DemoFile("transactions", "Transaction list (demo)", "transactions", "finora-demo-transactions.csv",
             "Categorised transactions as exported by a budgeting app. Needs an opening balance."),
    DemoFile("paypal_freelancer", "PayPal Activity report: freelancer with US clients (demo)", "paypal_activity",
             "finora-demo-paypal-freelancer.csv",
             "6 months of synthetic cross-border PayPal activity: USD client payments with PayPal fees, PayPal's "
             "USD→INR conversions and INR spending. Fees and rates are illustrative."),
]
PERSONA = {"paypal_freelancer": "freelancer"}


def _ref(t: NormalizedTransaction, n: int = 12) -> str:
    return hashlib.sha1(t.external_id.encode()).hexdigest().upper()[:n]


def _write(header: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _paypal_type(t: NormalizedTransaction) -> str:
    if t.amount > 0:
        return "Payment Received"
    if t.category in ("Subscriptions", "Utilities"):
        return "PreApproved Payment Bill User Payment"
    if t.category in ("Rent", "Investments", "Other"):
        return "General Payment"
    return "Express Checkout Payment"


def _paypal_multicurrency(txns: list[NormalizedTransaction], opening: Decimal) -> str:
    """PayPal's cross-border layout: the USD receipt (gross, fee, net), then PayPal's two conversion legs
    (USD out, INR in) linked to it by Reference Txn ID. Balances run per currency."""
    header = ["Date", "Time", "TimeZone", "Name", "Type", "Status", "Currency", "Gross", "Fee", "Net", "Balance",
              "Transaction ID", "Reference Txn ID"]
    rows, inr = [], opening
    for i, t in enumerate(txns):
        d = t.posted_on.strftime("%d/%m/%Y")
        hh, mm = 9 + i % 12, (i * 7) % 60
        tid = _ref(t, 17)
        if t.fx:
            f = t.fx
            rows.append([d, f"{hh:02d}:{mm:02d}:00", "Asia/Kolkata", t.merchant, "Payment Received", "Completed", f.currency,
                         f"{f.gross:.2f}", f"{f.fee:.2f}", f"{f.net:.2f}", f"{f.net:.2f}", tid, ""])
            rows.append([d, f"{hh:02d}:{mm:02d}:30", "Asia/Kolkata", "", "General Currency Conversion", "Completed", f.currency,
                         f"{-f.net:.2f}", "0.00", f"{-f.net:.2f}", "0.00", _ref(t, 16) + "A", tid])
            inr += t.amount
            rows.append([d, f"{hh:02d}:{mm:02d}:30", "Asia/Kolkata", "", "General Currency Conversion", "Completed", "INR",
                         f"{t.amount:.2f}", "0.00", f"{t.amount:.2f}", f"{inr:.2f}", _ref(t, 16) + "B", tid])
            continue
        inr += t.amount
        rows.append([d, f"{hh:02d}:{mm:02d}:00", "Asia/Kolkata", t.merchant, _paypal_type(t), "Completed", "INR",
                     f"{t.amount:.2f}", "0.00", f"{t.amount:.2f}", f"{inr:.2f}", tid, ""])
    return _write(header, rows)


def render(file_id: str, today: date, seed: int = 42) -> tuple[DemoFile, str, Decimal]:
    meta = next((f for f in DEMO_FILES if f.id == file_id), None)
    if meta is None:
        raise KeyError(file_id)
    src = SyntheticSource(today, seed, PERSONA.get(file_id, "salaried"))
    txns = src.fetch()
    opening = src.opening_balance(txns)
    if file_id == "paypal_freelancer":
        return meta, _paypal_multicurrency(txns, opening), opening

    if meta.format == "transactions":
        rows = [[t.posted_on.isoformat(), t.description, f"{t.amount:.2f}", t.category, t.merchant] for t in txns]
        return meta, _write(["date", "description", "amount", "category", "merchant"], rows), opening

    balance = opening
    rows = []
    if meta.format == "bank_statement":
        for t in txns:
            balance += t.amount
            if t.category == "Income":
                narration = f"NEFT/{t.merchant.upper()} PVT LTD/SALARY {t.posted_on.strftime('%b').upper()}"
            elif t.category == "Investments":
                narration = f"ACH/{t.merchant.upper()}/SIP"
            else:
                narration = f"UPI/{t.merchant}/{_ref(t, 10)}/{t.description}"
            d = t.posted_on.strftime("%d/%m/%Y")
            rows.append([d, narration, _ref(t, 10), d,
                         f"{-t.amount:.2f}" if t.amount < 0 else "", f"{t.amount:.2f}" if t.amount > 0 else "", f"{balance:.2f}"])
        header = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
        return meta, _write(header, rows), opening

    for i, t in enumerate(txns):
        balance += t.amount
        name = f"{t.merchant} Pvt Ltd" if t.category == "Income" and t.merchant == "Acme Technologies" else t.merchant
        rows.append([t.posted_on.strftime("%d/%m/%Y"), f"{9 + i % 12:02d}:{(i * 7) % 60:02d}:00", "Asia/Kolkata", name,
                     _paypal_type(t), "Completed", "INR", f"{t.amount:.2f}", "0.00", f"{t.amount:.2f}", _ref(t, 17), f"{balance:.2f}"])
    header = ["Date", "Time", "TimeZone", "Name", "Type", "Status", "Currency", "Gross", "Fee", "Net", "Transaction ID", "Balance"]
    return meta, _write(header, rows), opening
