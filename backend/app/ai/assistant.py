"""AI financial assistant: LLM ⇄ tool calls ⇄ deterministic engine, with a figure guardrail.

mode="llm"    the model picks tools (up to MAX_ROUNDS), then phrases an answer. The answer is
              checked by the guardrail; if it contains a rupee figure no tool produced, it is
              replaced by the deterministic answer built from the same tool results.
mode="rules"  no API key (or the LLM failed): the intent parser picks the tools and the reply is
              composed from the engine's own sentences. Figures are exact by construction.

Follow-ups: every response returns `context` (the main tool call it ran). The client sends it back
with the next question, so "and what if my salary is also late?" builds on the previous scenario
instead of starting fresh. In rules mode the parser merges the changes; in LLM mode the model is
told what was computed last and asked to carry it forward.
"""
import json
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.ai import guardrail
from app.ai.llm import LlmClient, LlmError
from app.ai.rules import describe_changes, plan_followup
from app.ai.tools import TOOL_SPECS, ToolOutcome, run_tool
from app.data.models import User
from app.services import repository as repo

MAX_ROUNDS = 4
CONTEXT_TOOLS = ("simulate_scenario", "compare_payment_options", "find_affordability")
SYSTEM = """You are FINORA, a financial digital-twin assistant for one user, with PayPal as the main data source.
Rules:
- Every figure you mention MUST come from a tool result in this conversation. Never compute, estimate or invent amounts, dates or percentages yourself; call a tool instead.
- For purchases ("can I buy/afford X"), call compare_payment_options (buy now vs wait vs PayPal Pay Later).
- For "how much can I spend" / "when can I buy", call find_affordability.
- For what-ifs (start a new subscription, cancel subscriptions, income or a client's payment delayed, more savings, expenses up/down, emergencies, exchange-rate moves), call simulate_scenario; combine several changes in one call when asked together.
- For questions about income from abroad, PayPal fees, conversion rates or withdrawing, call get_cross_border_summary.
- For "how resilient am I", "worst case", "how long would my money last", call run_stress_test. For job loss or a pay cut, use simulate_scenario with income_loss.
- Follow-up questions ("and what if…", "also", "instead", "what about 20 days?") build on the previous calculation: keep its changes, add or replace what the user changed, and run it as one call.
- Amounts are Indian rupees; write them like ₹75,000. Be concise: a direct answer first, then 2-4 short supporting points.
- Pay Later terms are illustrative; PayPal decides eligibility and APR at checkout. Say so when you recommend Pay Later.
- You can't move money. Payments happen only after the user confirms in the simulator.
- This is not financial advice."""


def _names(db: Session, user: User) -> tuple[list[str], list[str]]:
    p = repo.build_user_profile(db, user, repo.assumptions_for(user))
    return ([r.merchant for r in p.recurring_outflows if r.kind == "subscription"],
            [r.merchant for r in p.recurring_income])


def _public(o: ToolOutcome) -> dict:
    d = asdict(o)
    d.pop("lines", None)
    return d


def _context(outcomes: list[ToolOutcome]) -> dict | None:
    """The calculation a follow-up should build on: the last successful scenario / purchase / affordability call."""
    main = next((o for o in reversed(outcomes) if o.ok and o.tool in CONTEXT_TOOLS), None)
    return {"tool": main.tool, "arguments": main.arguments} if main else None


def _rules_reply(outcomes: list[ToolOutcome]) -> str:
    parts: list[str] = []
    for o in outcomes:
        if not o.ok:
            parts.append(f"I couldn't run that calculation: {o.summary.get('error')}.")
            continue
        parts.extend(o.lines)
    return "\n".join(f"• {p}" if i else p for i, p in enumerate(parts))


def chat(messages: list[dict], db: Session, user: User, llm: LlmClient | None, context: dict | None = None) -> dict:
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    note = None
    if llm is not None:
        try:
            return _chat_llm(messages, db, user, llm, context)
        except LlmError as exc:
            note = f"{exc}. Answered with the built-in calculator instead."

    subs, payers = _names(db, user)
    calls, built_on = plan_followup(question, context, subs, payers)
    outcomes = [run_tool(name, args, db, user) for name, args in calls]
    reply = _rules_reply(outcomes)
    if calls and calls[0][0] == "get_financial_snapshot":
        reply += ("\n\nTry asking: “What if I buy a ₹75,000 laptop?”, “What's the most I can spend this month?”, "
                  "“What if I cancel three subscriptions?” or “What if my salary is delayed by 15 days?”")
    return {"reply": reply, "mode": "rules", "model": None, "verified": True, "guardrail": None, "note": note,
            "built_on": built_on, "context": _context(outcomes), "tool_calls": [_public(o) for o in outcomes]}


def _chat_llm(messages: list[dict], db: Session, user: User, llm: LlmClient, context: dict | None) -> dict:
    convo: list[dict] = [{"role": "system", "content": f"{SYSTEM}\nToday is {repo.today().isoformat()}."}]
    if context:
        convo.append({"role": "system", "content":
                      "The previous answer ran this calculation. If the new question builds on it, carry these changes "
                      f"forward: {json.dumps(context, default=str)[:2000]}"})
    convo += [{"role": m["role"], "content": m["content"]} for m in messages[-12:]]
    outcomes: list[ToolOutcome] = []
    draft = ""
    for _ in range(MAX_ROUNDS):
        msg = llm.complete(convo, TOOL_SPECS)
        calls = msg.get("tool_calls") or []
        if not calls:
            draft = (msg.get("content") or "").strip()
            break
        convo.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
        for call in calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            outcome = run_tool(fn.get("name", ""), args if isinstance(args, dict) else {}, db, user)
            outcomes.append(outcome)
            convo.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(outcome.summary, default=str)})

    built_on = _llm_built_on(context, outcomes)
    ok, bad = guardrail.check(draft, [o.summary for o in outcomes])
    if draft and ok:
        return {"reply": draft, "mode": "llm", "model": llm.model, "verified": True, "guardrail": "passed", "note": None,
                "built_on": built_on, "context": _context(outcomes), "tool_calls": [_public(o) for o in outcomes]}

    # Draft rejected (invented figure, empty, or ran out of rounds): answer from the engine itself.
    if not outcomes:
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        subs, payers = _names(db, user)
        calls, built_on = plan_followup(question, context, subs, payers)
        outcomes = [run_tool(n, a, db, user) for n, a in calls]
    reason = (f"The AI draft contained figures the engine didn't produce ({', '.join(f'₹{v:,.0f}' for v in bad[:3])}), "
              "so this answer was composed directly from the computed results.") if bad else \
        "The AI didn't produce a usable answer, so this was composed directly from the computed results."
    return {"reply": _rules_reply(outcomes), "mode": "llm", "model": llm.model, "verified": True,
            "guardrail": "replaced", "note": reason, "built_on": built_on, "context": _context(outcomes),
            "tool_calls": [_public(o) for o in outcomes]}


def _llm_built_on(context: dict | None, outcomes: list[ToolOutcome]) -> str | None:
    """Say what carried over when the model's scenario kept changes from the previous one."""
    if not context or context.get("tool") != "simulate_scenario":
        return None
    prev = {json.dumps(c, sort_keys=True, default=str) for c in (context.get("arguments") or {}).get("changes", [])}
    for o in outcomes:
        if o.tool == "simulate_scenario":
            kept = [c for c in o.arguments.get("changes", []) if json.dumps(c, sort_keys=True, default=str) in prev]
            if kept and len(o.arguments.get("changes", [])) > len(kept):
                return describe_changes(kept)
    return None
