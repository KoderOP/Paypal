"""Deterministic intent parser: turns a question into engine tool calls without an LLM.

Used when no OPENAI_API_KEY is set (and as a fallback if the LLM call fails). It understands
the simulator's core questions, for example:
  "What if I buy a laptop worth ₹75,000 this month?"         → compare_payment_options
  "What's the most I can spend this month?"                  → find_affordability
  "When can I safely buy a ₹1.2 lakh vacation?"             → find_affordability(amount)
  "What if I cancel three subscriptions?"                    → simulate_scenario(cancel)
  "What if my income is delayed by 15 days?"                 → simulate_scenario(income_delay)
  "What if I increase my monthly savings by 10%?"            → simulate_scenario(increase_savings)
  "What if I add a ₹499/month gym membership?"               → simulate_scenario(add_subscription)
  "Cancel Netflix and Spotify and delay salary 2 weeks"      → one combined scenario
"""
import re
from decimal import Decimal, InvalidOperation

WORD_NUM = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10}
MULT = {"k": 1_000, "thousand": 1_000, "l": 100_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
        "cr": 10_000_000, "crore": 10_000_000}
AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lac|l|cr|crore)?\b"
    r"|\b(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lac|cr|crore)\b"
    r"|\b(\d{1,3}(?:,\d{2,3})+|\d{4,9})\b(?!\s*(?:days?|%|percent))",
    re.I,
)
STOP = r"(?:worth|for|costing|that costs|of|at|this|next|today|tomorrow|on|in|₹|rs|inr|\d)"


def _num(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def find_amount(text: str) -> Decimal | None:
    for m in AMOUNT.finditer(text):
        raw, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4)) if m.group(3) else (m.group(5), None)
        v = _num(raw)
        if v is None or v <= 0:
            continue
        if re.fullmatch(r"20\d\d", raw) and not unit:  # a year, not an amount
            continue
        return v * MULT.get((unit or "").lower(), 1)
    return None


def _days(text: str) -> int | None:
    m = re.search(r"(\d+|a|an|one|two|three|four)\s*(day|week|month)s?", text)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else WORD_NUM.get(m.group(1), 1)
    return n * {"day": 1, "week": 7, "month": 30}[m.group(2)]


def _percent(text: str) -> Decimal | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", text)
    return Decimal(m.group(1)) if m else None


def _label(text: str) -> str:
    m = re.search(rf"(?:buy|buying|purchase|purchasing|get|getting|afford)\s+(?:a|an|the|my|new|this)?\s*"
                  rf"(?:new\s+)?([a-z][a-z\- ]{{1,30}}?)\s+{STOP}", text)
    if m:
        word = m.group(1).strip()
        if word not in ("it", "something", "one", "them", "that"):
            return word[:1].upper() + word[1:]
    return "Purchase"


NOISE = {"what", "if", "i", "add", "a", "an", "the", "new", "my", "to", "start", "get", "join", "take", "month",
         "monthly", "per", "subscribe", "sign", "up", "for", "buy", "starting", "and", "also"}


def _subscription_label(text: str) -> str:
    """'add a ₹499/month gym membership' → 'Gym membership'; 'subscribe to youtube premium for ₹129' → 'Youtube premium'."""
    m = re.search(r"([a-z][a-z\- ]{0,40}?)\s*\b(subscription|membership|plan)\b", text)
    if m:
        words = [w for w in m.group(1).split() if w not in NOISE]
        if words:
            name = " ".join(words[-3:])
            return f"{name[:1].upper()}{name[1:]} {m.group(2)}"
    m = re.search(r"subscribe to ([a-z][a-z\- ]{1,30}?)\s+(?:for|at|worth|costing|₹|rs|inr|\d)", text)
    if m:
        return m.group(1).strip().capitalize()
    return "New subscription"


def plan_calls(question: str, subscription_names: list[str]) -> list[tuple[str, dict]]:
    t = " ".join(question.lower().split())
    amount = find_amount(t)
    changes: list[dict] = []

    if "cancel" in t and ("subscri" in t or any(n.lower() in t for n in subscription_names)):
        names = [n for n in subscription_names if n.lower() in t]
        m = re.search(r"\b(\d+|one|two|three|four|five|six|all)\b\s+(?:of\s+(?:my\s+)?)?(?:\w+\s+)?subscri", t)
        count = None
        if m:
            count = len(subscription_names) if m.group(1) == "all" else (
                int(m.group(1)) if m.group(1).isdigit() else WORD_NUM.get(m.group(1)))
        if not names and not count:
            count = 1 if re.search(r"\ba subscription\b", t) else 3
        changes.append({"type": "cancel_subscriptions", "names": names, "count": count})

    if re.search(r"(salary|income|pay ?check|payday|wage|client payment|payment from)", t) and \
            re.search(r"(delay|late|postpone|held up|pushed)", t):
        changes.append({"type": "income_delay", "days": _days(t) or 15, "all_future": "every" in t or "all" in t})

    pct = _percent(t)
    if pct and re.search(r"sav(e|ing|ings)|sip|invest", t):
        changes.append({"type": "increase_savings", "percent": float(pct)})
    elif pct and re.search(r"expense|spending|cost|bills|prices", t):
        sign = -1 if re.search(r"(cut|reduce|lower|decrease|less|drop)", t) else 1
        changes.append({"type": "expense_increase", "percent": float(pct) * sign})

    amount_used = False
    # A *new* subscription needs a start verb, so "cancel my ₹649 Netflix subscription" isn't read as one.
    if amount and re.search(r"\b(subscribe to|subscribing to|add|adding|start|starting|join|joining|sign up for|get|take)\b", t) \
            and re.search(r"\b(subscribe|subscription|membership|plan)\b", t):
        changes.append({"type": "add_subscription", "amount": float(amount), "label": _subscription_label(t)})
        amount_used = True
    elif amount and re.search(r"(unexpected|emergency|medical|hospital|surprise|repair|accident|fine\b)", t):
        label = next((w.capitalize() for w in ("medical", "repair", "emergency") if w in t), "Unexpected payment")
        changes.append({"type": "unexpected_payment", "amount": float(amount),
                        "label": label if label == "Unexpected payment" else f"{label} expense"})
        amount_used = True

    buying = re.search(r"\b(buy|buying|purchase|purchasing|get|getting|afford|spend on|pay for)\b", t)
    if changes:
        if amount and buying and not amount_used:
            changes.insert(0, {"type": "purchase", "amount": float(amount), "label": _label(t)})
        return [("simulate_scenario", {"changes": changes})]

    if re.search(r"(most|max(imum)?|how much)\b.*\b(spend|afford|buy)", t) or "spending limit" in t:
        return [("find_affordability", {"amount": float(amount)} if amount else {})]
    if amount and re.search(r"(when|earliest|which date|what date|best (time|date|day))", t):
        return [("find_affordability", {"amount": float(amount)}), ("compare_payment_options",
                                                                     {"amount": float(amount), "label": _label(t)})]
    if amount and (buying or re.search(r"(split|instal|emi|pay later|pay in 4|wait)", t)):
        return [("compare_payment_options", {"amount": float(amount), "label": _label(t)})]
    return [("get_financial_snapshot", {})]
