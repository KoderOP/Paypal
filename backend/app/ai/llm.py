"""LLM client for the FINORA agent: Groq first, any OpenAI-compatible endpoint second.

Groq serves an OpenAI-compatible Chat Completions API with tool calling, so one small httpx
client covers both (no SDK dependency). The model only *chooses* engine tools and phrases the
answer; it never computes figures (see app/ai/assistant.py and app/ai/guardrail.py).

Reliability behaviour, all covered by tests with httpx.MockTransport:
- 429 / 5xx / network errors  → bounded retries with backoff (honours Retry-After, capped).
- 400 `tool_use_failed`        → Groq rejected a malformed tool call; retried once at temperature 0.
- 404 / model decommissioned   → the next configured model is tried (GROQ_FALLBACK_MODEL).
- anything else                → LlmError; the agent then answers with the deterministic planner.

Each call records which model answered, token usage and latency so the UI can show an honest trace.
"""
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import Settings, get_settings

MAX_RETRIES = 2
MAX_BACKOFF_SECONDS = 6.0


class LlmError(RuntimeError):
    pass


@dataclass
class LlmCall:
    model: str
    ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    retries: int = 0
    notes: list[str] = field(default_factory=list)


class LlmClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        cfg = settings.llm_settings
        if cfg is None:
            raise ValueError("No LLM provider configured")
        self.settings = settings
        self.provider: str = cfg["provider"]
        self.base_url: str = cfg["base_url"]
        self._key: str = cfg["api_key"]
        self.models: list[str] = cfg["models"]
        self.transport = transport
        self._sleep = sleep
        self.calls: list[LlmCall] = []

    @property
    def model(self) -> str:
        """The model currently in use (moves to the fallback after the primary is found unavailable)."""
        return self.models[0]

    def _post(self, payload: dict) -> httpx.Response:
        with httpx.Client(base_url=self.base_url, timeout=self.settings.llm_timeout_seconds,
                          transport=self.transport) as h:
            return h.post("/chat/completions", headers={"Authorization": f"Bearer {self._key}"}, json=payload)

    def complete(self, messages: list[dict], tools: list[dict], temperature: float = 0.1) -> dict:
        """One chat completion round. Returns the assistant message dict (content and/or tool_calls)."""
        start = time.perf_counter()
        call = LlmCall(model=self.model, ms=0)
        temp = temperature
        attempt = 0
        while True:
            payload = {"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto",
                       "temperature": temp, "max_tokens": 1200}
            try:
                r = self._post(payload)
            except httpx.HTTPError as exc:
                if attempt < MAX_RETRIES:
                    attempt += 1
                    call.notes.append(f"network error ({exc.__class__.__name__}), retrying")
                    self._sleep(min(MAX_BACKOFF_SECONDS, 0.5 * 2 ** attempt))
                    continue
                raise LlmError(f"AI service unreachable: {exc.__class__.__name__}") from exc

            if r.status_code == 200:
                break
            code = _error_code(r)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < MAX_RETRIES:
                    attempt += 1
                    wait = _retry_after(r) or 0.5 * 2 ** attempt
                    call.notes.append(f"{r.status_code} from provider, retrying in {min(wait, MAX_BACKOFF_SECONDS):.1f}s")
                    self._sleep(min(MAX_BACKOFF_SECONDS, wait))
                    continue
                raise LlmError("AI service is rate-limited" if r.status_code == 429 else f"AI service error {r.status_code}")
            if r.status_code == 400 and code == "tool_use_failed" and attempt < MAX_RETRIES:
                attempt += 1
                temp = 0.0
                call.notes.append("model produced a malformed tool call, retrying at temperature 0")
                continue
            if (r.status_code == 404 or code in ("model_not_found", "model_decommissioned")) and len(self.models) > 1:
                gone = self.models.pop(0)
                call.notes.append(f"model {gone} unavailable, switched to {self.model}")
                call.model = self.model
                continue
            raise LlmError(f"AI service error {r.status_code}{f' ({code})' if code else ''}")

        try:
            body = r.json()
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LlmError("Unexpected AI service response") from exc
        usage = body.get("usage") or {}
        call.prompt_tokens = usage.get("prompt_tokens")
        call.completion_tokens = usage.get("completion_tokens")
        call.retries = attempt
        call.ms = int((time.perf_counter() - start) * 1000)
        self.calls.append(call)
        return msg


def _error_code(r: httpx.Response) -> str | None:
    try:
        err = r.json().get("error") or {}
        return err.get("code") or err.get("type")
    except (ValueError, AttributeError):
        return None


def _retry_after(r: httpx.Response) -> float | None:
    try:
        return float(r.headers.get("retry-after", ""))
    except ValueError:
        return None


def get_llm() -> LlmClient | None:
    s = get_settings()
    return LlmClient(s) if s.llm_settings else None
