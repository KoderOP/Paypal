"""Deterministic intent parser: turns a question into engine tool calls without an LLM.

Used when no GROQ_API_KEY (or OPENAI_API_KEY) is set (and as a fallback if the LLM call fails). It understands
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
    # "a ₹75,000 laptop", "₹1.2 lakh vacation": the noun right after the amount.
    m = re.search(r"(?:₹|rs\.?|inr)\s*\d[\d,]*(?:\.\d+)?\s*(?:k|lakhs?|lac|l)?\s+(?!worth|for|on|in|at|this|next|today|"
                  r"tomorrow|per|a|an|the|and|or|using|with|via|through|by|to|from|of|now)([a-z][a-z\-]{2,20})\b", text)
    if m:
        return m.group(1).capitalize()
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


CURRENCY_WORDS = r"\b(usd|dollars?|eur|euros?|gbp|pounds?|rupee|inr|exchange rate|fx|forex|currency)\b"


def _fx_change(t: str, pct: Decimal) -> dict | None:
    """'USD/INR drops 3%' → -3 · 'dollar rises 2%' → +2 · 'rupee strengthens 3%' → -3 (rupee is the subject)."""
    if not re.search(CURRENCY_WORDS, t):
        return None
    cur = "EUR" if re.search(r"\b(eur|euros?)\b", t) else "GBP" if re.search(r"\b(gbp|pounds?)\b", t) else "USD"
    down = re.search(r"(drop|fall|fell|weaken|\bdown\b|decline|depreciat|crash|lower|dip|slide)", t)
    up = re.search(r"(rise|rose|gain|strengthen|\bup\b|appreciat|higher|jump|climb|increase)", t)
    sign = 1 if up and not down else -1
    rupee_subject = re.search(r"\b(rupee|inr)\b", t) and not re.search(r"(usd|eur|gbp)\s*/\s*inr|\bdollars?\b|\beuros?\b|\bpounds?\b", t)
    if rupee_subject:
        sign = -sign
    return {"type": "fx_change", "percent": float(pct) * sign, "currency": cur}


CHECKOUT = re.compile(r"\b(go ahead|proceed|check ?out|pay for (it|this|that)|buy it|let'?s do it|place (the|an) order|"
                      r"pay (it )?(now|with paypal|via paypal|through paypal)|confirm (the )?(purchase|payment)|"
                      r"(use|with|via|choose|pick|go with) (paypal )?(pay in 4|pay later|pay monthly))\b")


def checkout_option(t: str) -> str | None:
    if re.search(r"pay in 4|in 4|four (payments|instal)", t):
        return "pay_in_4"
    if re.search(r"monthly|12 months|pay later", t):
        return "pay_monthly_12"
    if re.search(r"in full|full amount|pay now|right now|today|at once", t):
        return "pay_now"
    return None


def _checkout_call(t: str, amount: Decimal | float, label: str) -> tuple[str, dict]:
    args: dict = {"amount": float(amount), "label": label}
    opt = checkout_option(t)
    if opt:
        args["option_id"] = opt
    return ("prepare_paypal_checkout", args)


def plan_calls(question: str, subscription_names: list[str], payer_names: list[str] | None = None) -> list[tuple[str, dict]]:
    t = " ".join(question.lower().split())
    amount = find_amount(t)
    if amount and CHECKOUT.search(t) and not re.search(r"\bwhat if\b|\bshould i\b|\bcan i\b", t):
        return [_checkout_call(t, amount, _label(t))]
    changes: list[dict] = []
    payers = [p for p in (payer_names or []) if p.lower() in t or p.split()[0].lower() in t.split()]

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

    if re.search(r"(lose|lost|losing) (my )?(job|income|salary|client)|job loss|laid off|layoff|fired|unemploy|"
                 r"pay ?cut|salary cut|income (drops|falls|cut)", t):
        months = _days(t)
        cut = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", t) if re.search(r"cut|drop|fall|less", t) else None
        change = {"type": "income_loss", "months": max(1, min(12, round((months or 30) / 30)))}
        if cut:
            change["percent"] = float(cut.group(1))
        changes.append(change)
    elif (payers or re.search(r"(salary|income|pay ?check|payday|wage|client|payment from)", t)) and \
            re.search(r"(delay|late|postpone|held up|pushed)", t):
        change = {"type": "income_delay", "days": _days(t) or 15, "all_future": "every" in t or "all" in t}
        if payers:
            change["merchant"] = payers[0]
        changes.append(change)

    pct = _percent(t)
    fx = _fx_change(t, pct) if pct else None
    if any(c["type"] == "income_loss" for c in changes):
        pass  # the percentage was a pay cut, already handled
    elif fx:
        changes.append(fx)
    elif pct and re.search(r"sav(e|ing|ings)|sip|invest", t):
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
    if re.search(r"(stress|resilien|emergency fund|runway|worst case|how long (can|could|would) (i|my money)|"
                 r"how safe|how secure|survive)", t):
        return [("run_stress_test", {})]
    if re.search(r"(withdraw|paypal fees?|\bfees?\b|conversion|exchange rate|cross.border|foreign|forex|"
                 r"usd income|dollar income|international|clients?)", t):
        return [("get_cross_border_summary", {})]
    return [("get_financial_snapshot", {})]


# ---- Follow-ups --------------------------------------------------------------------------------------
FOLLOW_UP = re.compile(r"^(and|also|plus|then|now|what about|how about|instead|but|ok|okay|what if .*\b(also|too)\b)\b"
                       r"|\b(also|too|as well|on top|instead|in addition|additionally)\b")


def _context_changes(context: dict | None) -> list[dict]:
    if not context:
        return []
    args = context.get("arguments") or {}
    if context.get("tool") == "simulate_scenario":
        return [dict(c) for c in args.get("changes", []) if isinstance(c, dict) and c.get("type")]
    if context.get("tool") in ("compare_payment_options", "prepare_paypal_checkout") and args.get("amount"):
        return [{"type": "purchase", "amount": args["amount"], "label": args.get("label") or "Purchase"}]
    return []


def _merge(prev: list[dict], new: list[dict]) -> list[dict]:
    """New changes replace earlier ones of the same kind (e.g. 15 → 20 days late); other kinds stack."""
    out = [dict(c) for c in prev]
    for c in new:
        same = next((i for i, p in enumerate(out) if p["type"] == c["type"]
                     and p.get("merchant") == c.get("merchant")), None)
        if same is None:
            out.append(c)
        else:
            out[same] = c
    return out[:8]


def describe_changes(changes: list[dict]) -> str:
    names = {"purchase": "the purchase", "cancel_subscriptions": "cancelled subscriptions",
             "income_delay": "the income delay", "increase_savings": "higher savings", "expense_increase": "the spending change",
             "unexpected_payment": "the unexpected payment", "add_subscription": "the new subscription",
             "fx_change": "the exchange-rate move", "income_loss": "the income loss"}
    parts = [c.get("label") if c["type"] in ("purchase", "add_subscription") and c.get("label") else names.get(c["type"], c["type"])
             for c in changes]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def plan_followup(question: str, context: dict | None, subscription_names: list[str],
                  payer_names: list[str] | None = None) -> tuple[list[tuple[str, dict]], str | None]:
    """Like plan_calls, but a follow-up ("and what if my salary is also late?") builds on the previous answer.

    Returns the calls plus a short description of what was carried forward (None when starting fresh).
    """
    calls = plan_calls(question, subscription_names, payer_names)
    t = " ".join(question.lower().split())
    prev = _context_changes(context)
    if context and CHECKOUT.search(t) and calls[0][0] != "prepare_paypal_checkout":
        purchase = next((c for c in prev if c["type"] == "purchase"), None)
        if purchase is None and context.get("tool") == "prepare_paypal_checkout":
            a = context.get("arguments") or {}
            purchase = {"amount": a.get("amount"), "label": a.get("label")} if a.get("amount") else None
        if purchase:
            return [_checkout_call(t, purchase["amount"], purchase.get("label") or "Purchase")], "your previous question"
    if not context or not FOLLOW_UP.search(t):
        return calls, None
    name, args = calls[0]

    if name == "simulate_scenario" and prev:
        return [("simulate_scenario", {"changes": _merge(prev, args["changes"])})], describe_changes(prev)
    if name == "compare_payment_options" and prev and context.get("tool") == "simulate_scenario":
        purchase = {"type": "purchase", "amount": args["amount"], "label": args["label"]}
        return [("simulate_scenario", {"changes": _merge(prev, [purchase])})], describe_changes(prev)
    if name != "get_financial_snapshot":
        return calls, None

    # Nothing new was named: treat it as a tweak of the previous numbers ("what about ₹50,000?", "and 20 days?").
    amount, days, pct = find_amount(t), _days(t), _percent(t)
    prev_tool, prev_args = context.get("tool"), dict(context.get("arguments") or {})
    if prev_tool in ("compare_payment_options", "find_affordability") and amount:
        return [(prev_tool, {**prev_args, "amount": float(amount)})], "your previous question"
    if prev_tool == "simulate_scenario" and prev:
        tweaked = [dict(c) for c in prev]
        hit = False
        for c in tweaked:
            if amount and not hit and c["type"] in ("purchase", "unexpected_payment", "add_subscription"):
                c["amount"], hit = float(amount), True
            elif days and c["type"] == "income_delay":
                c["days"], hit = days, True
            elif pct is not None and c["type"] in ("fx_change", "increase_savings", "expense_increase"):
                sign = -1 if c["type"] == "fx_change" and c.get("percent", 0) < 0 else 1
                c["percent"], hit = float(pct) * sign, True
        if hit:
            return [("simulate_scenario", {"changes": tweaked})], describe_changes(prev)
    return calls, None
