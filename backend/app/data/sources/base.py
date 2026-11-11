"""Pluggable transaction sources.

Every source (synthetic, CSV, PayPal, bank aggregators…) yields `NormalizedTransaction`s.
The rest of the system — twin engine, forecasting, simulation — only ever sees the
normalised shape, so adding a source never touches the financial core.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class FxInfo:
    """Original-currency details for a transaction converted into the home currency (e.g. USD → INR)."""

    currency: str
    gross: Decimal  # foreign amount before PayPal's fee
    fee: Decimal  # PayPal fee in the foreign currency (≤ 0)
    net: Decimal  # gross + fee: what was converted
    rate: Decimal  # home currency per 1 unit of foreign currency, as actually applied
    rate_source: str  # paypal_conversion | nearest_conversion


@dataclass(frozen=True)
class NormalizedTransaction:
    external_id: str
    posted_on: date
    description: str
    merchant: str
    category: str
    amount: Decimal  # signed, in the home currency: + credit, - debit
    fx: FxInfo | None = None


class TransactionSource(Protocol):
    name: str

    def fetch(self) -> list[NormalizedTransaction]: ...
