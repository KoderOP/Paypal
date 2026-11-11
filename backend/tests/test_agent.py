"""Agent tests: Groq client reliability, grounding guardrail, the checkout action tool and the trace.

The LLM provider is replaced by httpx.MockTransport, so no network or API key is needed.
"""
import json

import httpx
import pytest

from app.ai import guardrail
from app.ai.llm import LlmClient, LlmError, get_llm
from app.core.config import Settings
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def demo_data(client):
    content = client.get("/api/demo-files/paypal_activity").content
    r = client.post("/api/data/import", files={"file": ("pp.csv", content, "text/csv")}, data={"replace": "true"})
    assert r.status_code == 200, r.text
    yield


def groq(**kw) -> Settings:
    return Settings(groq_api_key="gsk-test", openai_api_key=None, _env_file=None, **kw)


def ok(message: dict, usage: dict | None = None) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": message}], "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5}})


def tool_call(name: str, args: dict, cid: str = "c1") -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def scripted(responses: list):
    """A provider that returns the given responses in order and records each request body."""
    seen: list[dict] = []
    it = iter(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        nxt = next(it)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt if isinstance(nxt, httpx.Response) else ok(nxt)
    return handler, seen


def use_llm(handler, settings: Settings | None = None):
    s = settings or groq()
    app.dependency_overrides[get_llm] = lambda: LlmClient(s, httpx.MockTransport(handler), sleep=lambda _: None)


def ask(client, q: str, context: dict | None = None) -> dict:
    try:
        r = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": q}], "context": context})
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert r.status_code == 200, r.text
    return r.json()


# ---- Provider configuration ---------------------------------------------------------------------------
def test_groq_is_preferred_and_has_fallback_model():
    cfg = Settings(groq_api_key="g", openai_api_key="o", _env_file=None).llm_settings
    assert cfg["provider"] == "groq" and cfg["base_url"].startswith("https://api.groq.com/openai/v1")
    assert len(cfg["models"]) == 2
    assert Settings(groq_api_key=None, openai_api_key="o", _env_file=None).llm_settings["provider"] == "openai"
    assert Settings(groq_api_key=None, openai_api_key=None, _env_file=None).llm_settings is None
    assert Settings(groq_api_key="g", llm_provider="none", _env_file=None).llm_settings is None


def test_client_sends_groq_request_shape():
    handler, seen = scripted([{"role": "assistant", "content": "hi"}])
    c = LlmClient(groq(groq_model="m-primary"), httpx.MockTransport(handler))
    assert c.complete([{"role": "user", "content": "x"}], [{"type": "function"}])["content"] == "hi"
    assert seen[0]["model"] == "m-primary" and seen[0]["tool_choice"] == "auto" and seen[0]["tools"]
    assert c.calls[0].prompt_tokens == 10


def test_client_retries_rate_limit_then_succeeds():
    handler, seen = scripted([httpx.Response(429, headers={"retry-after": "1"}, json={"error": {"code": "rate_limit_exceeded"}}),
                              {"role": "assistant", "content": "ok"}])
    slept: list[float] = []
    c = LlmClient(groq(), httpx.MockTransport(handler), sleep=slept.append)
    assert c.complete([], [])["content"] == "ok"
    assert slept == [1.0] and c.calls[0].retries == 1 and len(seen) == 2


def test_client_retries_malformed_tool_call_at_temperature_zero():
    handler, seen = scripted([httpx.Response(400, json={"error": {"code": "tool_use_failed", "message": "bad"}}),
                              {"role": "assistant", "content": "ok"}])
    LlmClient(groq(), httpx.MockTransport(handler), sleep=lambda _: None).complete([], [])
    assert seen[0]["temperature"] > 0 and seen[1]["temperature"] == 0


def test_client_falls_back_to_second_model_when_primary_is_gone():
    handler, seen = scripted([httpx.Response(404, json={"error": {"code": "model_not_found"}}),
                              {"role": "assistant", "content": "ok"}])
    c = LlmClient(groq(groq_model="gone", groq_fallback_model="backup"), httpx.MockTransport(handler))
    c.complete([], [])
    assert [s["model"] for s in seen] == ["gone", "backup"] and c.model == "backup"


def test_client_gives_up_after_bounded_retries():
    handler, seen = scripted([httpx.Response(503)] * 9)
    with pytest.raises(LlmError):
        LlmClient(groq(), httpx.MockTransport(handler), sleep=lambda _: None).complete([], [])
    assert len(seen) == 6  # (first try + MAX_RETRIES) on the primary, then the same on the fallback model


def test_short_rate_limits_exhausted_on_primary_move_to_fallback():
    handler, seen = scripted([httpx.Response(429, headers={"retry-after": "2"})] * 3 + [{"role": "assistant", "content": "ok"}])
    c = LlmClient(groq(groq_model="big", groq_fallback_model="small"), httpx.MockTransport(handler), sleep=lambda _: None)
    assert c.complete([], [])["content"] == "ok"
    assert [s["model"] for s in seen] == ["big", "big", "big", "small"]


# ---- Guardrail -------------------------------------------------------------------------------------------
PAYLOAD = [{"result": {"min_balance": 13812.5, "savings_rate": 0.424, "min_balance_date": "2026-11-22",
                       "options": [{"first_payment": 18750.0}]}, "arguments": {"amount": 75000, "percent": 3}}]


@pytest.mark.parametrize("text", [
    "Your low point is ₹13,813 on 22 Nov.", "Pay ₹18,750 today; the laptop costs ₹75k.", "Savings rate is 42.4%.",
    "On November 22nd you'd be at Rs. 13,812.", "A 3% drop.", "Lowest balance on 2026-11-22.", "That's ₹0.75 lakh."])
def test_guardrail_accepts_grounded_claims(text):
    assert guardrail.check_claims(text, PAYLOAD)["ok"], text


@pytest.mark.parametrize("text,kind", [
    ("You'd still have ₹91,234 left.", "money"), ("Your savings rate is 55%.", "percent"),
    ("Your balance bottoms out on 14 Dec.", "dates"), ("Pay ₹19,500 today.", "money")])
def test_guardrail_rejects_invented_claims(text, kind):
    r = guardrail.check_claims(text, PAYLOAD)
    assert not r["ok"] and r["invented"][kind], text


# ---- Agent (LLM mode) ------------------------------------------------------------------------------------
def test_llm_answer_with_trace_and_usage(client):
    handler, seen = scripted([tool_call("compare_payment_options", {"amount": 75000, "label": "Laptop"}),
                              {"role": "assistant", "content": "Use PayPal Pay in 4: ₹18,750 today."}])
    use_llm(handler)
    body = ask(client, "Can I buy a ₹75k laptop?")
    assert body["mode"] == "llm" and body["provider"] == "groq" and body["guardrail"] == "passed"
    kinds = [t["type"] for t in body["trace"]]
    assert kinds == ["llm", "tool", "llm", "guardrail"]
    assert body["usage"]["prompt_tokens"] == 20 and body["usage"]["rounds"] == 2
    assert body["grounding"]["checked"]["money"] == 1
    # The tool result is sent back to the model with the matching call id.
    assert seen[1]["messages"][-1]["role"] == "tool" and seen[1]["messages"][-1]["tool_call_id"] == "c1"


def test_llm_invented_date_is_replaced(client):
    handler, _ = scripted([tool_call("compare_payment_options", {"amount": 75000, "label": "Laptop"}),
                           {"role": "assistant", "content": "Buy it on 30 Dec and you'll be fine."}])
    use_llm(handler)
    body = ask(client, "Can I buy a ₹75k laptop?")
    assert body["guardrail"] == "replaced" and "30 Dec" not in body["reply"]
    assert body["rejected_grounding"]["invented"]["dates"] and body["grounding"]["ok"]


def test_provider_outage_falls_back_to_deterministic_planner(client):
    handler, _ = scripted([httpx.ConnectError("down")] * 3)
    use_llm(handler)
    body = ask(client, "What if I buy a laptop worth ₹75,000 this month?")
    assert body["mode"] == "rules" and "unreachable" in body["note"]
    assert body["trace"][0]["type"] == "fallback" and body["tool_calls"][0]["tool"] == "compare_payment_options"


# ---- Checkout action tool: proposes, never pays ------------------------------------------------------
def test_checkout_proposal_creates_no_order(client):
    before = client.get("/api/checkout/orders").json()
    handler, _ = scripted([tool_call("prepare_paypal_checkout", {"amount": 75000, "label": "Laptop", "option_id": "pay_in_4"}),
                           {"role": "assistant", "content": "I've drafted the PayPal Pay in 4 checkout. Confirm it below."}])
    use_llm(handler)
    body = ask(client, "Go ahead with Pay in 4 for the laptop")
    card = body["tool_calls"][0]["card"]
    assert card["kind"] == "checkout_proposal" and card["status"] == "awaiting_user_confirmation" and card["charged"] is False
    assert card["option_id"] == "pay_in_4" and card["funding"] == "paylater" and len(card["payments"]) == 4
    assert client.get("/api/checkout/orders").json() == before  # nothing was created at PayPal or in the DB
    assert body["context"]["tool"] == "prepare_paypal_checkout"


def test_unsafe_proposal_is_flagged_with_safer_alternative(client):
    handler, _ = scripted([tool_call("prepare_paypal_checkout", {"amount": 75000, "label": "Laptop", "option_id": "pay_now"}),
                           {"role": "assistant", "content": "Drafted."}])
    use_llm(handler)
    card = ask(client, "Just pay the full ₹75,000 now")["tool_calls"][0]["card"]
    assert card["safe"] is False and card["safer_alternative"]["option_id"] == "wait"


def test_proposal_for_non_payable_option_uses_recommended(client):
    handler, _ = scripted([tool_call("prepare_paypal_checkout", {"amount": 75000, "option_id": "wait"}),
                           {"role": "assistant", "content": "Drafted."}])
    use_llm(handler)
    card = ask(client, "pay for it")["tool_calls"][0]["card"]
    assert card["option_id"] != "wait" and "not paid through PayPal checkout" in card["note"]


def test_rules_mode_compare_then_go_ahead(client):
    first = ask(client, "Should I buy a ₹75,000 laptop?")
    assert first["tool_calls"][0]["tool"] == "compare_payment_options"
    second = ask(client, "OK, go ahead with Pay in 4", first["context"])
    call = second["tool_calls"][0]
    assert call["tool"] == "prepare_paypal_checkout" and call["arguments"] == {"amount": 75000.0, "label": "Laptop", "option_id": "pay_in_4"}
    assert second["grounding"]["ok"] and "Nothing has been charged" in second["reply"]


def test_status_reports_provider(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "groq_api_key", "gsk-x")
    s = client.get("/api/assistant/status").json()
    assert s["mode"] == "llm" and s["provider"] == "groq" and s["model"]


# ---- Regressions found by evals/agent_eval.py -------------------------------------------------------
def test_guardrail_reads_rupee_figures_inside_engine_sentences():
    # json.dumps used to escape ₹ as ₹, gluing its "9" onto the amount (₹12,469 → 912469).
    payload = [{"result": {"explanation": "₹1,07,531 on 15 Dec 2026, ₹12,469 short."}}]
    assert guardrail.check_claims("You'd be ₹12,469 short.", payload)["ok"]


def test_guardrail_accepts_dates_written_out_by_the_engine():
    payload = [{"result": {"applied": [{"description": "Delay income due 15 Nov 2026 by 15 days"}], "on": "2026-12-01"}}]
    assert guardrail.check_claims("The income due on 15 Nov arrives later.", payload)["ok"]
    assert not guardrail.check_claims("The income due on 16 Nov arrives later.", payload)["ok"]


def test_evals_endpoint_serves_committed_results(client):
    body = client.get("/api/evals").json()
    assert "reproduce" in body
    if body["agent"]["rules"]:
        assert body["agent"]["rules"]["summary"]["overall"]["n"] >= 30


def test_security_headers_and_chat_rate_limit(client):
    from app.api.assistant import chat_limit
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    old, chat_limit.limit = chat_limit.limit, 2
    chat_limit.hits.clear()
    try:
        codes = [client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "How am I doing?"}]}).status_code
                 for _ in range(3)]
    finally:
        chat_limit.limit = old
        chat_limit.hits.clear()
    assert codes == [200, 200, 429]


def test_long_rate_limit_switches_to_fallback_model_immediately():
    handler, seen = scripted([httpx.Response(429, headers={"retry-after": "38"}, json={"error": {"code": "rate_limit_exceeded"}}),
                              {"role": "assistant", "content": "ok"}])
    slept: list[float] = []
    c = LlmClient(groq(groq_model="big", groq_fallback_model="small"), httpx.MockTransport(handler), sleep=slept.append)
    c.complete([], [])
    assert [s["model"] for s in seen] == ["big", "small"] and slept == [] and "rate-limited" in c.calls[0].notes[0]


@pytest.mark.parametrize("chip,option", [("Go ahead with PayPal Pay in 4", "pay_in_4"), ("Pay in full now with PayPal", "pay_now")])
def test_ui_follow_up_chips_draft_a_checkout_without_an_llm(client, chip, option):
    # These exact strings are the one-tap buttons in frontend/src/pages/Assistant.tsx (PAY_FOLLOWUPS).
    ctx = {"tool": "compare_payment_options", "arguments": {"amount": 75000, "label": "Laptop"}}
    call = ask(client, chip, ctx)["tool_calls"][0]
    assert call["tool"] == "prepare_paypal_checkout" and call["arguments"]["option_id"] == option
