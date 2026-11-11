"""Serves the committed evaluation results (backend/evals/results/*.json) to the web app.

Read-only: the numbers are produced by `python -m evals.run_all`, never computed here.
"""
import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/evals", tags=["evals"])
RESULTS = Path(__file__).resolve().parents[2] / "evals" / "results"


def _load(name: str) -> dict | None:
    p = RESULTS / name
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


@router.get("")
def evals():
    agent = {m: _load(f"agent_{m}.json") for m in ("rules", "llm")}
    red = _load("guardrail_redteam.json")
    if red:
        red = {k: v for k, v in red.items() if k != "misses"}
    return {"agent": agent, "guardrail": red, "backtest": _load("forecast_backtest.json"),
            "reproduce": "cd backend && python -m evals.run_all   (add --llm with GROQ_API_KEY set)"}
