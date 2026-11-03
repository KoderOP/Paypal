"""Precise monetary arithmetic helpers. All financial math uses Decimal, never float."""
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """Normalise to a 2-dp Decimal. Floats are rejected to avoid silent precision loss."""
    if isinstance(value, float):
        raise TypeError("Use Decimal/str/int for money, not float")
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def total(values: Iterable[Decimal]) -> Decimal:
    return money(sum(values, ZERO))


def ratio(numerator: Decimal, denominator: Decimal, places: str = "0.0001") -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (numerator / denominator).quantize(Decimal(places), rounding=ROUND_HALF_UP)
