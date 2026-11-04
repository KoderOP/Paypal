"""AI financial assistant: LLM ⇄ tool calls ⇄ deterministic engine, with a figure guardrail.

mode="llm"    the model picks tools (up to MAX_ROUNDS), then phrases an answer. The answer is
              checked by the guardrail; if it contains a rupee figure no tool produced, it is
              replaced by the deterministic answer built from the same tool results.
mode="rules"  no API key (or the LLM failed): the intent parser picks the tools and the reply is
              composed from the engine's own sentences. Figures are exact by construction.
"""
import json
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.ai import guardrail
from app.ai.llm import LlmClient, LlmError
from app.ai.rules import plan_calls
from app.ai.tools import TOOL_SPECS, ToolOutcome, run_tool
from app.data.models import User
from app.services import repository as repo

MAX_ROUNDS = 4
SYSTEM = """You are FINORA, a financial digital-twin assistant for one user, with PayPal as the main data source.
Rules:
- Every figure you mention MUST come from a tool result in this conversation. Never compute, estimate or invent amounts, dates or percentages yourself; call a tool instead.
- For purchases ("can I buy/afford X"), call compare_payment_options (buy now vs wait vs PayPal Pay Later).
- For "how much can I spend" / "when can I buy", call find_affordability.
- For what-ifs (start a new subscription, cancel subscriptions, income delayed, more savings, expenses up/down, emergencies), call simulate_scenario; combine several changes in one call when asked together.
- Amounts are Indian rupees; write them like ₹75,000. Be concise: a direct answer first, then 2-4 short supporting points.
- Pay Later terms are illustrative; PayPal decides eligibility and APR at checkout. Say so when you recommend Pay Later.
- You can't move money. Payments happen only after the user confirms in the simulator.
- This is not financial advice."""


def _subscription_names(db: Session, user: User) -> list[str]:
    a = repo.assumptions_for(user)
    p = repo.build_user_profile(db, user, a)
    return [r.merchant for r in p.recurring_outflows if r.kind == "subscription"]


def _public(o: ToolOutcome) -> dict:
    d = asdict(o)
    d.pop("lines", None)
    return d


def _rules_reply(outcomes: list[ToolOutcome]) -> str:
    parts: list[str] = []
    for o in outcomes:
        if not o.ok:
            parts.append(f"I couldn't run that calculation: {o.summary.get('error')}.")
            continue
        parts.extend(o.lines)
    return "\n".join(f"• {p}" if i else p for i, p in enumerate(parts))


def chat(messages: list[dict], db: Session, user: User, llm: LlmClient | None) -> dict:
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    note = None
    if llm is not None:
        try:
            return _chat_llm(messages, db, user, llm)
        except LlmError as exc:
            note = f"{exc}. Answered with the built-in calculator instead."

    calls = plan_calls(question, _subscription_names(db, user))
    outcomes = [run_tool(name, args, db, user) for name, args in calls]
    reply = _rules_reply(outcomes)
    if calls and calls[0][0] == "get_financial_snapshot":
        reply += ("\n\nTry asking: “What if I buy a ₹75,000 laptop?”, “What's the most I can spend this month?”, "
                  "“What if I cancel three subscriptions?” or “What if my salary is delayed by 15 days?”")
    return {"reply": reply, "mode": "rules", "model": None, "verified": True, "guardrail": None,
            "note": note, "tool_calls": [_public(o) for o in outcomes]}


def _chat_llm(messages: list[dict], db: Session, user: User, llm: LlmClient) -> dict:
    convo: list[dict] = [{"role": "system", "content": f"{SYSTEM}\nToday is {repo.today().isoformat()}."}]
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

    ok, bad = guardrail.check(draft, [o.summary for o in outcomes])
    if draft and ok:
        return {"reply": draft, "mode": "llm", "model": llm.model, "verified": True, "guardrail": "passed",
                "note": None, "tool_calls": [_public(o) for o in outcomes]}

    # Draft rejected (invented figure, empty, or ran out of rounds): answer from the engine itself.
    if not outcomes:
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        outcomes = [run_tool(n, a, db, user) for n, a in plan_calls(question, _subscription_names(db, user))]
    reason = (f"The AI draft contained figures the engine didn't produce ({', '.join(f'₹{v:,.0f}' for v in bad[:3])}), "
              "so this answer was composed directly from the computed results.") if bad else \
        "The AI didn't produce a usable answer, so this was composed directly from the computed results."
    return {"reply": _rules_reply(outcomes), "mode": "llm", "model": llm.model, "verified": True,
            "guardrail": "replaced", "note": reason, "tool_calls": [_public(o) for o in outcomes]}
