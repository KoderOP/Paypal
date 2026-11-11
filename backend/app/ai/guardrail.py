"""Figure guardrail: every rupee amount in an AI answer must come from a tool result.

We extract ₹ / Rs / INR amounts (incl. "₹1.2 lakh", "₹45K") from the draft and check each one
against the numbers present in the tool results the model actually received. Rounding is
allowed (within 1%, or ₹1), as are simple yearly/monthly conversions (×12, ÷12) of a tool
figure. Anything else counts as invented and the draft is rejected.
"""
import json
import re
from decimal import Decimal, InvalidOperation

MONEY = re.compile(r"(?:₹|rs\.?\s|inr\s)\s*(-?\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lac|l|cr|crore)?\b", re.I)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
MULT = {"k": 1_000, "thousand": 1_000, "l": 100_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
        "cr": 10_000_000, "crore": 10_000_000}


def figures_in_text(text: str) -> list[Decimal]:
    out = []
    for m in MONEY.finditer(text):
        try:
            v = Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            continue
        out.append(abs(v * MULT.get((m.group(2) or "").lower(), 1)))
    return out


def allowed_figures(tool_payloads: list[dict]) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for payload in tool_payloads:
        blob = json.dumps(payload, default=str)
        for raw in NUMBER.findall(blob.replace(",", "")):
            v = abs(Decimal(raw))
            allowed |= {v, v * 12, v / 12}
    return allowed


def _close(v: Decimal, allowed: set[Decimal]) -> bool:
    return any(abs(v - a) <= max(Decimal("1"), a * Decimal("0.01")) for a in allowed)


def check(text: str, tool_payloads: list[dict]) -> tuple[bool, list[Decimal]]:
    allowed = allowed_figures(tool_payloads)
    bad = [v for v in figures_in_text(text) if v != 0 and not _close(v, allowed)]
    return not bad, bad
