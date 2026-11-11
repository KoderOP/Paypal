"""Grounding guardrail: every money figure, percentage and date in an AI answer must come from a tool.

The language model never computes. After it drafts an answer we extract three kinds of claims
and check each against the values present in the tool results (and tool arguments) it received:

  money        ₹ / Rs / INR amounts, incl. "₹1.2 lakh", "₹45K", "Rs. 3,000". Allowed if it matches a
               tool number (or a simple ×12 / ÷12 conversion of one) to the precision it was
               written with: "₹1,68,391" must match to the rupee; "₹1.68 lakh" may be off by up
               to ₹500, "₹68.8K" by ₹50, "₹70,000" by ₹5,000, never by more than 2%.
               (A flat 1% tolerance let digit transpositions through; see evals/guardrail_redteam.py.)
  percentages  "42.4%", "3 percent". Allowed if within 0.5 points of a tool number, or of a tool
               ratio expressed as a percentage (0.424 → 42.4%).
  dates        "23 Nov", "November 23", "23 Nov 2026", "2026-11-23". Allowed if that calendar day
               appears in the tool results. (Weekday names and relative words are not checked.)

Anything else counts as invented, and the agent replaces the draft with the deterministic answer
composed from the same tool results. `check_claims` returns a structured report for the UI trace;
`check` keeps the original money-only (ok, bad) contract.
"""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

MONEY = re.compile(r"(?:₹|rs\.?\s|inr\s)\s*(-?\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lac|l|cr|crore)?\b", re.I)
PERCENT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent\b|per cent\b)", re.I)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
ISO_DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DAY_MON = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}\b\.?(?:,?\s+(20\d\d))?", re.I)
MON_DAY = re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(20\d\d))?", re.I)
MULT = {"k": 1_000, "thousand": 1_000, "l": 100_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
        "cr": 10_000_000, "crore": 10_000_000}


def money_claims(text: str) -> list[tuple[Decimal, Decimal]]:
    """(amount, allowed error) for each rupee figure, the error set by the precision it was written with."""
    out = []
    for m in MONEY.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            v = Decimal(raw)
        except InvalidOperation:
            continue
        mult = Decimal(MULT.get((m.group(2) or "").lower(), 1))
        if "." in raw:
            unit = Decimal(1).scaleb(-len(raw.split(".")[1]))
        else:
            digits = raw.lstrip("-")
            zeros = len(digits) - len(digits.rstrip("0")) if digits.strip("0") else 0
            unit = Decimal(1).scaleb(zeros)
        amount = abs(v * mult)
        tol = max(Decimal("1"), min(unit * mult / 2, amount * Decimal("0.02")))
        out.append((amount, tol))
    return out


def figures_in_text(text: str) -> list[Decimal]:
    return [a for a, _ in money_claims(text)]


def percents_in_text(text: str) -> list[Decimal]:
    return [abs(Decimal(m.group(1))) for m in PERCENT.finditer(text)]


def dates_in_text(text: str) -> list[tuple[int | None, int, int]]:
    """(year or None, month, day) for each calendar date mentioned."""
    out: list[tuple[int | None, int, int]] = []
    for m in ISO_DATE.finditer(text):
        out.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in DAY_MON.finditer(text):
        out.append((int(m.group(3)) if m.group(3) else None, MONTHS[m.group(2)[:3].lower()], int(m.group(1))))
    for m in MON_DAY.finditer(text):
        out.append((int(m.group(3)) if m.group(3) else None, MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
    return [d for d in out if 1 <= d[1] <= 12 and 1 <= d[2] <= 31]


def _numbers(tool_payloads: list[dict]) -> list[Decimal]:
    nums: list[Decimal] = []
    for payload in tool_payloads:
        # ensure_ascii=False: "₹12,469" must not become "\u20b912469" (whose "9" would glue onto the number).
        blob = ISO_DATE.sub(" ", json.dumps(payload, default=str, ensure_ascii=False))  # dates are not numbers
        nums += [abs(Decimal(raw)) for raw in NUMBER.findall(blob.replace(",", ""))]
    return nums


def allowed_figures(tool_payloads: list[dict]) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for v in _numbers(tool_payloads):
        allowed |= {v, v * 12, v / 12}
    return allowed


def allowed_percents(tool_payloads: list[dict]) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for v in _numbers(tool_payloads):
        allowed |= {v, v * 100}
    return allowed


def allowed_dates(tool_payloads: list[dict]) -> set[date]:
    """ISO dates in tool results, plus dates written out in the engine's own sentences ("15 Nov 2026")."""
    out: set[date] = set()
    for payload in tool_payloads:
        blob = json.dumps(payload, default=str, ensure_ascii=False)
        years = sorted({int(y) for y, _, _ in ISO_DATE.findall(blob)}) or [None]
        for y, m, d in dates_in_text(blob):
            for year in ([y] if y else years):
                if year is None:
                    continue
                try:
                    out.add(date(year, m, d))
                except ValueError:
                    continue
    return out


def check(text: str, tool_payloads: list[dict], flat_tolerance: Decimal | None = None) -> tuple[bool, list[Decimal]]:
    """Money-only check: (ok, invented amounts).

    flat_tolerance (e.g. Decimal("0.01")) replaces the precision-aware rule with the old flat
    relative tolerance; it exists only for the ablation in evals/guardrail_redteam.py.
    """
    allowed = allowed_figures(tool_payloads)
    claims = money_claims(text)
    if flat_tolerance is not None:
        claims = [(v, max(Decimal("1"), v * flat_tolerance)) for v, _ in claims]
    bad = [v for v, tol in claims if v != 0 and not any(abs(v - a) <= tol for a in allowed)]
    return not bad, bad


def check_claims(text: str, tool_payloads: list[dict], flat_tolerance: Decimal | None = None) -> dict:
    """Full grounding report: counts of checked claims and the ones no tool produced."""
    money_ok, bad_money = check(text, tool_payloads, flat_tolerance)
    pct_allowed = allowed_percents(tool_payloads)
    pcts = percents_in_text(text)
    bad_pct = [p for p in pcts if p != 0 and not any(abs(p - a) <= Decimal("0.5") for a in pct_allowed)]
    known = allowed_dates(tool_payloads)
    dates = dates_in_text(text)
    bad_dates = [f"{d:02d}/{m:02d}" + (f"/{y}" if y else "") for y, m, d in dates
                 if not any(k.month == m and k.day == d and (y is None or k.year == y) for k in known)]
    return {
        "ok": money_ok and not bad_pct and not bad_dates,
        "checked": {"money": len(figures_in_text(text)), "percent": len(pcts), "dates": len(dates)},
        "invented": {"money": [float(v) for v in bad_money], "percent": [float(v) for v in bad_pct],
                     "dates": bad_dates},
    }
