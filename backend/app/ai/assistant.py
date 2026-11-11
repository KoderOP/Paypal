"""FINORA agent: LLM ⇄ tool calls ⇄ deterministic engine, with a grounding guardrail and a human gate.

mode="llm"    Groq (or another OpenAI-compatible model) plans: it calls engine tools for up to
              MAX_ROUNDS rounds, then drafts an answer. The draft is checked by the guardrail
              (money, percentages and dates must all come from tool results). If any claim is
              ungrounded, the draft is replaced by the deterministic answer built from the same
              tool results, and the response says so.
mode="rules"  no API key (or the provider failed): the deterministic intent planner picks the tools
              and the reply is composed from the engine's own sentences. Exact by construction.

Actions: the agent can *prepare* a PayPal checkout (prepare_paypal_checkout) but has no tool that
moves money. Paying requires the user to confirm in the UI (POST /checkout/orders with
acknowledged=true), approve on PayPal, and confirm the capture. That boundary is architectural:
it does not depend on the model following instructions.

Every response carries a `trace` (plan → tool calls → guardrail, with timings and token usage) so
the UI can show exactly how an answer was produced.

Follow-ups: every response returns `context` (the main tool call it ran). The client sends it back
with the next question, so "and what if my salary is also late?" or "ok, pay for it" builds on it.
"""
import json
import time
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.ai import guardrail
from app.ai.llm import LlmClient, LlmError
from app.ai.rules import describe_changes, plan_followup
from app.ai.tools import TOOL_SPECS, ToolOutcome, run_tool
from app.data.models import User
from app.services import repository as repo

MAX_ROUNDS = 4
MAX_TOOL_CALLS = 8
CONTEXT_TOOLS = ("simulate_scenario", "compare_payment_options", "find_affordability", "prepare_paypal_checkout")
SYSTEM = """You are FINORA, a pre-payment financial copilot. The user's money data comes mainly from PayPal. Your job: before the user spends, show what the decision does to their future cash flow, then help them act safely.

Grounding rules (strict, checked automatically):
- Every amount, percentage and date you write MUST appear in a tool result from this conversation. Never compute, estimate, add up or invent numbers yourself. If you need a number, call a tool.
- Copy figures as the tool gives them (you may round to the nearest rupee and write ₹75,000 / ₹1.2 lakh).

Which tool:
- "Can I afford / should I buy X" → compare_payment_options (pay now vs wait vs PayPal Pay Later).
- "How much can I spend" / "when can I buy X" → find_affordability.
- What-ifs (new or cancelled subscriptions, late income or a late client, income loss, savings or spending changes, emergencies, exchange-rate moves) → simulate_scenario. Put several changes in ONE call when asked together.
- Income from abroad, PayPal fees, conversion rates → get_cross_border_summary.
- "How resilient am I", worst case, runway → run_stress_test.
- Overview questions → get_financial_snapshot.
- The user says to go ahead / pay / buy it / use Pay in 4 → prepare_paypal_checkout with the amount, label and option id from the earlier comparison. This only drafts the payment; the user confirms in the app and approves on PayPal. Never claim a payment was made.

Follow-ups ("and what if…", "also", "instead", "what about 20 days?") build on the previous calculation: keep its changes, add or replace what changed, run it as one call.

Style: amounts are Indian rupees. Lead with a direct verdict in one sentence, then 2-4 short bullet points. If an option dips below the safety buffer, say so plainly. Pay Later terms are illustrative; PayPal decides eligibility and APR at checkout. This is not financial advice."""


def _names(db: Session, user: User) -> tuple[list[str], list[str]]:
    p = repo.build_user_profile(db, user, repo.assumptions_for(user))
    return ([r.merchant for r in p.recurring_outflows if r.kind == "subscription"],
            [r.merchant for r in p.recurring_income])


def _public(o: ToolOutcome) -> dict:
    d = asdict(o)
    d.pop("lines", None)
    return d


def _context(outcomes: list[ToolOutcome]) -> dict | None:
    """The calculation a follow-up should build on: the last successful main tool call."""
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


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _run(name: str, args: dict, db: Session, user: User, trace: list[dict]) -> ToolOutcome:
    t0 = time.perf_counter()
    o = run_tool(name, args, db, user)
    trace.append({"type": "tool", "label": name, "ms": _ms(t0), "ok": o.ok,
                  "detail": {"arguments": o.arguments, **({"error": o.summary.get("error")} if not o.ok else {})}})
    return o


def _payloads(outcomes: list[ToolOutcome]) -> list[dict]:
    """What the guardrail treats as ground truth: tool results plus the arguments the tools ran with."""
    return [{"today": repo.today().isoformat()}] + [{"result": o.summary, "arguments": o.arguments} for o in outcomes]


def chat(messages: list[dict], db: Session, user: User, llm: LlmClient | None, context: dict | None = None) -> dict:
    started = time.perf_counter()
    note = None
    trace: list[dict] = []
    if llm is not None:
        try:
            res = _chat_llm(messages, db, user, llm, context, trace)
            res["latency_ms"] = _ms(started)
            return res
        except LlmError as exc:
            note = f"{exc}. Answered with the built-in deterministic planner instead."
            trace.append({"type": "fallback", "label": "Provider failed: deterministic planner", "ms": 0, "ok": False,
                          "detail": {"error": str(exc)}})

    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    t0 = time.perf_counter()
    subs, payers = _names(db, user)
    calls, built_on = plan_followup(question, context, subs, payers)
    trace.append({"type": "plan", "label": "Deterministic intent planner", "ms": _ms(t0), "ok": True,
                  "detail": {"calls": [c[0] for c in calls]}})
    outcomes = [_run(name, args, db, user, trace) for name, args in calls]
    reply = _rules_reply(outcomes)
    grounding = guardrail.check_claims(reply, _payloads(outcomes))  # suggestions below are examples, not claims
    if calls and calls[0][0] == "get_financial_snapshot":
        reply += ("\n\nTry asking: “What if I buy a ₹75,000 laptop?”, “What's the most I can spend this month?”, "
                  "“What if I cancel three subscriptions?” or “What if my salary is delayed by 15 days?”")
    trace.append({"type": "guardrail", "label": "Grounding check", "ms": 0, "ok": grounding["ok"], "detail": grounding})
    return {"reply": reply, "mode": "rules", "provider": None, "model": None, "verified": True, "guardrail": None,
            "grounding": grounding, "note": note, "built_on": built_on, "context": _context(outcomes),
            "tool_calls": [_public(o) for o in outcomes], "trace": trace, "usage": None, "latency_ms": _ms(started)}


def _chat_llm(messages: list[dict], db: Session, user: User, llm: LlmClient, context: dict | None,
              trace: list[dict]) -> dict:
    convo: list[dict] = [{"role": "system", "content": f"{SYSTEM}\nToday is {repo.today().isoformat()}."}]
    if context:
        convo.append({"role": "system", "content":
                      "The previous answer ran this calculation. If the new question builds on it, carry these changes "
                      f"forward: {json.dumps(context, default=str)[:2000]}"})
    convo += [{"role": m["role"], "content": m["content"]} for m in messages[-12:]]
    outcomes: list[ToolOutcome] = []
    draft = ""
    for round_no in range(MAX_ROUNDS):
        msg = llm.complete(convo, TOOL_SPECS)
        c = llm.calls[-1]
        calls = (msg.get("tool_calls") or [])[: max(0, MAX_TOOL_CALLS - len(outcomes))]
        trace.append({"type": "llm", "label": f"{llm.provider} · {c.model}", "ms": c.ms, "ok": True,
                      "detail": {"round": round_no + 1, "requested_tools": [k.get("function", {}).get("name") for k in calls],
                                 "prompt_tokens": c.prompt_tokens, "completion_tokens": c.completion_tokens,
                                 "retries": c.retries, "notes": c.notes}})
        if not calls:
            draft = (msg.get("content") or "").strip()
            break
        convo.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            outcome = _run(fn.get("name", ""), args if isinstance(args, dict) else {}, db, user, trace)
            outcomes.append(outcome)
            convo.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(outcome.summary, default=str)})

    usage = {"prompt_tokens": sum(c.prompt_tokens or 0 for c in llm.calls),
             "completion_tokens": sum(c.completion_tokens or 0 for c in llm.calls), "rounds": len(llm.calls)}
    built_on = _llm_built_on(context, outcomes)
    grounding = guardrail.check_claims(draft, _payloads(outcomes))
    trace.append({"type": "guardrail", "label": "Grounding check", "ms": 0, "ok": bool(draft) and grounding["ok"],
                  "detail": grounding})
    base = {"mode": "llm", "provider": llm.provider, "model": llm.model, "verified": True, "usage": usage, "trace": trace,
            "built_on": built_on}
    if draft and grounding["ok"]:
        return {**base, "reply": draft, "guardrail": "passed", "grounding": grounding, "note": None,
                "context": _context(outcomes), "tool_calls": [_public(o) for o in outcomes]}

    # Draft rejected (ungrounded claim, empty, or out of rounds): answer from the engine itself.
    if not outcomes:
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        subs, payers = _names(db, user)
        calls, built_on = plan_followup(question, context, subs, payers)
        trace.append({"type": "plan", "label": "Deterministic intent planner (fallback)", "ms": 0, "ok": True,
                      "detail": {"calls": [c[0] for c in calls]}})
        outcomes = [_run(n, a, db, user, trace) for n, a in calls]
    inv = grounding["invented"]
    bad = [f"₹{v:,.0f}" for v in inv["money"][:3]] + [f"{v:g}%" for v in inv["percent"][:2]] + inv["dates"][:2]
    reason = (f"The AI draft contained claims the engine didn't produce ({', '.join(bad)}), so this answer was "
              "composed directly from the computed results.") if bad else \
        "The AI didn't produce a usable answer, so this was composed directly from the computed results."
    reply = _rules_reply(outcomes)
    return {**base, "reply": reply, "guardrail": "replaced", "grounding": guardrail.check_claims(reply, _payloads(outcomes)),
            "rejected_grounding": grounding, "note": reason, "built_on": built_on, "context": _context(outcomes),
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
