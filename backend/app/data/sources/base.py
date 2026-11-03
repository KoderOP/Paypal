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
class NormalizedTransaction:
    external_id: str
    posted_on: date
    description: str
    merchant: str
    category: str
    amount: Decimal  # signed: + credit, - debit


class TransactionSource(Protocol):
    name: str

    def fetch(self) -> list[NormalizedTransaction]: ...
