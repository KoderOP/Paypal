"""Pre-demo check: is the Groq key valid, is the configured model available, does tool calling work?

    GROQ_API_KEY=... python -m evals.check_groq

Makes one tiny tool-calling request (a few hundred tokens). Prints the key only as a length.
"""
import json
import sys

import httpx

from app.ai.llm import LlmClient, LlmError
from app.core.config import get_settings


def main() -> int:
    s = get_settings()
    cfg = s.llm_settings
    if not cfg or cfg["provider"] != "groq":
        print("GROQ_API_KEY is not set (or LLM_PROVIDER is not groq/auto).")
        return 1
    print(f"key: set ({len(cfg['api_key'])} chars) · base: {cfg['base_url']} · models: {cfg['models']}")
    try:
        r = httpx.get(f"{cfg['base_url']}/models", headers={"Authorization": f"Bearer {cfg['api_key']}"}, timeout=15)
    except httpx.HTTPError as exc:
        print(f"Could not reach Groq: {exc.__class__.__name__}")
        return 1
    if r.status_code != 200:
        print(f"/models returned {r.status_code}: the key is probably invalid.")
        return 1
    available = {m["id"] for m in r.json().get("data", [])}
    for m in cfg["models"]:
        print(f"  {m}: {'available' if m in available else 'NOT available on this key'}")
    tool = [{"type": "function", "function": {"name": "find_affordability", "description": "How much the user can spend.",
                                              "parameters": {"type": "object", "properties": {}}}}]
    client = LlmClient(s)
    try:
        msg = client.complete([{"role": "user", "content": "What's the most I can spend this month? Use a tool."}], tool)
    except LlmError as exc:
        print(f"Tool-calling request failed: {exc}")
        return 1
    calls = [c["function"]["name"] for c in msg.get("tool_calls") or []]
    c = client.calls[-1]
    print(f"tool calling via {c.model}: {'OK → ' + json.dumps(calls) if calls else 'model answered without a tool call'} "
          f"({c.ms} ms, {c.prompt_tokens}+{c.completion_tokens} tokens{', ' + '; '.join(c.notes) if c.notes else ''})")
    return 0 if calls else 2


if __name__ == "__main__":
    sys.exit(main())
