"""Engine functions exposed to the assistant as tools.

Each tool returns:
  summary  compact JSON for the language model (all figures computed by the engine)
  card     richer payload the web UI renders (charts, option cards)
  lines    deterministic plain-language sentences, used for the rule-based reply and as the
           fallback when an LLM draft fails the figure guardrail
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.data.models import User
from app.engine.forecast import forecast_baseline
from app.engine.scenarios import Change
from app.engine.simulation import fmt_date, inr
from app.engine.stress import stress_test
from app.services import planning
from app.services import repository as repo

CHANGES = TypeAdapter(list[Change])


@dataclass
class ToolOutcome:
    tool: str
    arguments: dict
    ok: bool
    summary: dict
    card: dict | None = None
    lines: list[str] = field(default_factory=list)


def _f(v: Decimal | float | int | None) -> float | None:
    return None if v is None else float(v)


TOOL_SPECS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "get_financial_snapshot",
        "description": "Current balance, regular income, spending, subscriptions, next income date and safety buffer.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "compare_payment_options",
        "description": "Buy now, wait, or split it? Compares paying in full today, waiting for a safe date, and "
                       "PayPal Pay Later instalments for a purchase. Use for any 'can I afford / should I buy X' question.",
        "parameters": {"type": "object", "required": ["amount"], "additionalProperties": False, "properties": {
            "amount": {"type": "number", "exclusiveMinimum": 0, "description": "Purchase amount in INR"},
            "label": {"type": "string", "description": "What is being bought, e.g. 'Laptop'"}}}}},
    {"type": "function", "function": {
        "name": "find_affordability",
        "description": "Goal solver. The most the user can spend today / this month while staying above the "
                       "safety buffer, and (if amount is given) the earliest safe date to spend that amount.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {
            "amount": {"type": "number", "exclusiveMinimum": 0},
            "search_days": {"type": "integer", "minimum": 7, "maximum": 180}}}}},
    {"type": "function", "function": {
        "name": "simulate_scenario",
        "description": "What-if simulator. Combine one or more changes and project 90 days against the baseline.",
        "parameters": {"type": "object", "required": ["changes"], "additionalProperties": False, "properties": {
            "title": {"type": "string"},
            "changes": {"type": "array", "minItems": 1, "maxItems": 8, "items": {
                "type": "object", "required": ["type"], "properties": {
                    "type": {"type": "string", "enum": ["purchase", "cancel_subscriptions", "income_delay",
                                                        "increase_savings", "expense_increase", "unexpected_payment",
                                                        "add_subscription", "fx_change", "income_loss"]},
                    "months": {"type": "integer", "description": "income_loss: months without (or with less) income"},
                    "currency": {"type": "string", "description": "fx_change: foreign currency, e.g. USD"},
                    "merchant": {"type": "string", "description": "income_delay: only this payer/client is late"},
                    "amount": {"type": "number",
                               "description": "purchase / unexpected_payment amount, or add_subscription monthly price (INR)"},
                    "on": {"type": "string", "format": "date", "description": "YYYY-MM-DD, default today"},
                    "start": {"type": "string", "format": "date", "description": "add_subscription: first billing date"},
                    "label": {"type": "string"},
                    "names": {"type": "array", "items": {"type": "string"},
                              "description": "cancel_subscriptions: merchant names to cancel"},
                    "count": {"type": "integer", "description": "cancel_subscriptions: cancel the N most expensive"},
                    "days": {"type": "integer", "description": "income_delay: days late"},
                    "all_future": {"type": "boolean", "description": "income_delay: delay every payment, not just the next"},
                    "percent": {"type": "number", "description": "increase_savings / expense_increase (negative = cut); "
                                "fx_change: % move in FOREIGN/INR, e.g. -3 when USD/INR drops 3%"},
                }}}}}}},
    {"type": "function", "function": {
        "name": "get_cross_border_summary",
        "description": "For freelancers paid from abroad via PayPal: foreign income by client, PayPal fees, the rates "
                       "PayPal applied, conversion cost vs a reference rate, FX sensitivity and late-client risk.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "prepare_paypal_checkout",
        "description": "Draft a PayPal checkout for a purchase the user wants to go ahead with ('ok, pay for it', "
                       "'buy it with Pay Later'). It re-runs the simulation and returns a proposal card. It does NOT "
                       "charge anything: the user must review and confirm in the app, then approve on PayPal. Only "
                       "call it when the user asks to pay or proceed.",
        "parameters": {"type": "object", "required": ["amount"], "additionalProperties": False, "properties": {
            "amount": {"type": "number", "exclusiveMinimum": 0, "description": "Purchase amount in INR"},
            "label": {"type": "string", "description": "What is being bought"},
            "option_id": {"type": "string", "description": "Payment option id from compare_payment_options "
                          "(one of 'pay_now', 'pay_in_4', 'pay_monthly_12'). Omit to use the recommended payable option."}}}}},
    {"type": "function", "function": {
        "name": "run_stress_test",
        "description": "How resilient are the user's finances? Runs a shock library (job loss, pay cut, medical bill, "
                       "costs +30%, late income, currency drop) and a spending Monte Carlo; returns runway and risk.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
]


def run_tool(name: str, args: dict, db: Session, user: User) -> ToolOutcome:
    try:
        if name == "get_financial_snapshot":
            return _snapshot(db, user)
        if name == "compare_payment_options":
            return _payment_options(db, user, args)
        if name == "find_affordability":
            return _affordability(db, user, args)
        if name == "simulate_scenario":
            return _scenario(db, user, args)
        if name == "get_cross_border_summary":
            return _cross_border(db, user)
        if name == "run_stress_test":
            return _stress(db, user)
        if name == "prepare_paypal_checkout":
            return _checkout_proposal(db, user, args)
        return ToolOutcome(name, args, False, {"error": f"Unknown tool {name}"})
    except ValidationError as exc:
        return ToolOutcome(name, args, False, {"error": "Invalid arguments", "details": [e["msg"] for e in exc.errors()][:5]})
    except (ValueError, TypeError) as exc:
        return ToolOutcome(name, args, False, {"error": str(exc)})


def _snapshot(db: Session, user: User) -> ToolOutcome:
    a = repo.assumptions_for(user)
    p = repo.build_user_profile(db, user, a)
    fc = forecast_baseline(p, a)
    subs = [{"merchant": r.merchant, "monthly": _f(r.amount), "next_date": r.next_date.isoformat()}
            for r in sorted(p.recurring_outflows, key=lambda r: -r.amount) if r.kind == "subscription"]
    summary = {
        "as_of": p.as_of.isoformat(), "current_balance": _f(p.current_balance), "monthly_income": _f(p.monthly_income),
        "avg_monthly_spending": _f(p.avg_monthly_spending), "monthly_investments": _f(p.avg_monthly_investments),
        "subscriptions_monthly": _f(p.subscriptions_monthly), "subscriptions": subs,
        "next_income_date": p.next_income_date.isoformat() if p.next_income_date else None,
        "safety_buffer": _f(a.safety_buffer), "projected_balance_30": _f(fc.balance_on_day(30)),
        "projected_balance_90": _f(fc.balance_on_day(90)), "lowest_projected_balance": _f(fc.min_balance),
        "lowest_projected_date": fc.min_balance_date.isoformat(),
    }
    lines = [f"Your balance is {inr(p.current_balance)}. Regular income is {inr(p.monthly_income)}/month"
             + (f", next expected on {fmt_date(p.next_income_date)}." if p.next_income_date else "."),
             f"You spend about {inr(p.avg_monthly_spending)}/month, including {inr(p.subscriptions_monthly)} on "
             f"{len(subs)} subscription(s).",
             f"In 90 days your balance is projected at {inr(fc.balance_on_day(90))}; the lowest point is "
             f"{inr(fc.min_balance)} on {fmt_date(fc.min_balance_date)}."]
    return ToolOutcome("get_financial_snapshot", {}, True, summary, {"kind": "snapshot", **summary}, lines)


def _payment_options(db: Session, user: User, args: dict) -> ToolOutcome:
    amount = Decimal(str(args["amount"]))
    label = (args.get("label") or "Purchase").strip()[:80] or "Purchase"
    c = planning.payment_comparison(db, user, amount, label)
    summary = {
        "amount": _f(c.amount), "label": c.label, "safety_buffer": _f(c.assumptions.safety_buffer),
        "recommendation": {"verdict": c.recommendation.verdict, "option_id": c.recommendation.option_id,
                           "headline": c.recommendation.headline},
        "options": [{"id": o.id, "name": o.name, "safe": o.safe, "get_it_on": o.get_it_on.isoformat(),
                     "payments": len(o.payments), "first_payment": _f(o.payments[0].amount),
                     "first_payment_on": o.payments[0].on.isoformat(), "total_paid": _f(o.total_paid),
                     "extra_cost": _f(o.extra_cost), "apr": _f(o.apr), "min_balance": _f(o.min_balance),
                     "min_balance_date": o.min_balance_date.isoformat(), "days_below_buffer": o.days_below_buffer}
                    for o in c.options],
        "terms_note": c.terms_note,
    }
    card = {"kind": "payment_options", **c.model_dump(mode="json")}
    return ToolOutcome("compare_payment_options", {"amount": float(amount), "label": label}, True, summary, card,
                       [c.recommendation.headline.rstrip(".") + "."] + c.recommendation.explanation)


def _affordability(db: Session, user: User, args: dict) -> ToolOutcome:
    amount = Decimal(str(args["amount"])) if args.get("amount") else None
    days = int(args.get("search_days") or 60)
    r = planning.affordability(db, user, amount, max(7, min(180, days)))
    summary = {
        "max_safe_today": _f(r.max_safe_today), "limiting_date_today": r.limiting_date_today.isoformat(),
        "best_this_month": {"on": r.best_this_month.on.isoformat(), "max_safe_spend": _f(r.best_this_month.max_safe_spend)},
        "best_in_window": {"on": r.best_in_window.on.isoformat(), "max_safe_spend": _f(r.best_in_window.max_safe_spend)},
        "safety_buffer": _f(r.assumptions.safety_buffer), "search_days": r.search_days,
        "earliest": r.earliest.model_dump(mode="json") if r.earliest else None,
    }
    card = {"kind": "affordability", **r.model_dump(mode="json")}
    return ToolOutcome("find_affordability", {k: v for k, v in {"amount": _f(amount), "search_days": days}.items() if v},
                       True, summary, card, r.explanation)


def _stress(db: Session, user: User) -> ToolOutcome:
    a = repo.assumptions_for(user)
    r = stress_test(repo.build_user_profile(db, user, a), repo.load_transactions(db, user), a)
    summary = {
        "resilience": r.resilience, "current_balance": _f(repo.current_balance(db, user)),
        "runway_months": float(r.runway_months), "monthly_burn": _f(r.monthly_burn),
        "chance_below_buffer": float(r.chance_below_buffer), "chance_below_zero": float(r.chance_below_zero),
        "shocks": [{"name": s.name, "min_balance": _f(s.min_balance), "min_balance_date": s.min_balance_date.isoformat(),
                    "solvent": s.solvent, "above_buffer": s.above_buffer} for s in r.shocks],
        "safety_buffer": _f(a.safety_buffer),
    }
    return ToolOutcome("run_stress_test", {}, True, summary, {"kind": "stress", "resilience": r.resilience,
                                                             "summary": r.summary}, r.summary)


def _cross_border(db: Session, user: User) -> ToolOutcome:
    cb = planning.cross_border_view(db, user)
    summary = {
        "has_foreign_income": cb.has_foreign, "foreign_share_of_regular_income": float(cb.foreign_share),
        "currencies": [c.model_dump(mode="json") for c in cb.currencies],
        "clients": [c.model_dump(mode="json") for c in cb.clients],
        "fx_sensitivity": [s.model_dump(mode="json") for s in cb.sensitivity],
        "late_client": cb.late_client.model_dump(mode="json") if cb.late_client else None,
        "withdrawal_note": cb.withdrawal_note,
    }
    lines = cb.insights + [cb.withdrawal_note] if cb.has_foreign else [
        "No foreign-currency income was found. Upload a PayPal Activity report that includes your international "
        "payments and PayPal's currency conversions to see fees, rates and FX risk."]
    return ToolOutcome("get_cross_border_summary", {}, True, summary,
                       {"kind": "cross_border", **cb.model_dump(mode="json")}, lines)


def _scenario(db: Session, user: User, args: dict) -> ToolOutcome:
    raw = [{k: v for k, v in c.items() if v not in (None, "", [])} for c in args.get("changes", [])]
    changes = CHANGES.validate_python(raw)
    r = planning.scenario(db, user, changes, args.get("title"))
    summary = {
        "title": r.title, "applied": [c.model_dump(mode="json") for c in r.applied], "notes": r.notes,
        "monthly_effect": _f(r.monthly_effect),
        "impacts": [i.model_dump(mode="json") for i in r.impacts],
        "baseline_min_balance": _f(r.baseline.min_balance), "scenario_min_balance": _f(r.simulated.min_balance),
        "scenario_min_date": r.simulated.min_balance_date.isoformat(),
        "baseline_end_balance": _f(r.baseline.end_balance), "scenario_end_balance": _f(r.simulated.end_balance),
        "risks": [x.model_dump() for x in r.risks], "safety_buffer": _f(r.assumptions.safety_buffer),
    }
    card = {
        "kind": "scenario", "title": r.title, "applied": summary["applied"], "notes": r.notes, "summary": r.summary,
        "risks": summary["risks"], "impacts": summary["impacts"], "monthly_effect": summary["monthly_effect"],
        "safety_buffer": summary["safety_buffer"],
        "dates": [p.on.isoformat() for p in r.baseline.points],
        "baseline_series": [float(p.balance) for p in r.baseline.points],
        "scenario_series": [float(p.balance) for p in r.simulated.points],
    }
    return ToolOutcome("simulate_scenario", {"title": args.get("title"), "changes": raw}, True, summary, card,
                       r.summary + r.notes)


def _checkout_proposal(db: Session, user: User, args: dict) -> ToolOutcome:
    """A payment *proposal*: no order is created and nothing is charged.

    The card carries everything the UI needs for the human confirmation step, which calls
    POST /checkout/orders (acknowledged=true) and later capture (confirm=true). Unsafe options are
    still proposable when the user insists, but the card flags them and demands an extra tick.
    """
    from app.core.config import get_settings

    amount = Decimal(str(args["amount"]))
    label = (args.get("label") or "Purchase").strip()[:80] or "Purchase"
    c = planning.payment_comparison(db, user, amount, label)
    payable = [o for o in c.options if o.action == "checkout"]
    wanted = (args.get("option_id") or "").strip()
    option = next((o for o in payable if o.id == wanted), None)
    note = None
    if option is None:
        if wanted and any(o.id == wanted for o in c.options):
            note = f"'{wanted}' is not paid through PayPal checkout (it is a plan to wait), so the recommended payable option is shown."
        elif wanted:
            note = f"There is no option '{wanted}' for this purchase, so the recommended payable option is shown."
        option = next((o for o in payable if o.id == c.recommendation.option_id), None) or \
            next((o for o in payable if o.safe), None) or (payable[0] if payable else None)
    if option is None:
        return ToolOutcome("prepare_paypal_checkout", {"amount": float(amount), "label": label}, False,
                           {"error": "No PayPal payment option is available for this purchase."})
    s = get_settings()
    wait = next((o for o in c.options if o.action == "plan"), None)
    summary = {
        "status": "awaiting_user_confirmation", "charged": False, "amount": _f(amount), "label": label,
        "option_id": option.id, "option_name": option.name, "funding": option.funding, "safe": option.safe,
        "recommended": option.recommended, "payments": [{"on": p.on.isoformat(), "amount": _f(p.amount)} for p in option.payments],
        "total_paid": _f(option.total_paid), "extra_cost": _f(option.extra_cost), "min_balance": _f(option.min_balance),
        "min_balance_date": option.min_balance_date.isoformat(), "days_below_buffer": option.days_below_buffer,
        "safety_buffer": _f(c.assumptions.safety_buffer), "paypal_environment": s.paypal_environment,
        "safer_alternative": ({"option_id": wait.id, "name": wait.name, "get_it_on": wait.get_it_on.isoformat()}
                              if wait and wait.safe and not option.safe else None),
        "note": note,
    }
    lines = [f"I've prepared a PayPal checkout for {label} ({inr(amount)}) using {option.name}. Nothing has been charged."]
    if option.safe:
        lines.append(f"Your lowest projected balance would be {inr(option.min_balance)} on {fmt_date(option.min_balance_date)}, "
                     "which stays above your safety buffer.")
    else:
        lines.append(f"Warning: this takes your projected balance down to {inr(option.min_balance)} on "
                     f"{fmt_date(option.min_balance_date)}, below your {inr(c.assumptions.safety_buffer)} buffer.")
        if summary["safer_alternative"]:
            lines.append(f"Waiting until {fmt_date(wait.get_it_on)} would keep you safe.")
    lines.append("Review the details and confirm below; you'll then approve the payment on PayPal.")
    if note:
        lines.append(note)
    card = {"kind": "checkout_proposal", **summary, "terms_note": c.terms_note if option.funding == "paylater" else None}
    return ToolOutcome("prepare_paypal_checkout", {"amount": float(amount), "label": label, "option_id": option.id},
                       True, summary, card, lines)
