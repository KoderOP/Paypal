"""Minimal OpenAI Chat Completions client with tool calling (httpx, no SDK dependency).

The model decides *which* engine tool to call and phrases the answer; it never computes
figures. Injected as a FastAPI dependency so tests can supply an httpx.MockTransport.
"""
import httpx

from app.core.config import Settings, get_settings


class LlmError(RuntimeError):
    pass


class LlmClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    @property
    def model(self) -> str:
        return self.settings.openai_model

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            with httpx.Client(base_url=self.settings.openai_base_url, timeout=45, transport=self.transport) as h:
                r = h.post("/chat/completions",
                           headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                           json={"model": self.model, "messages": messages, "tools": tools,
                                 "tool_choice": "auto", "temperature": 0.2})
        except httpx.HTTPError as exc:
            raise LlmError(f"AI service unreachable: {exc.__class__.__name__}") from exc
        if r.status_code != 200:
            raise LlmError(f"AI service error {r.status_code}")
        try:
            return r.json()["choices"][0]["message"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LlmError("Unexpected AI service response") from exc


def get_llm() -> LlmClient | None:
    s = get_settings()
    return LlmClient(s) if s.openai_api_key else None
