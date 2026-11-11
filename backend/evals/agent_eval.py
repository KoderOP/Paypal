"""Agent benchmark: does the agent pick the right engine tool, with the right arguments, and stay grounded?

    python -m evals.agent_eval --mode rules           # deterministic planner, offline, no key
    GROQ_API_KEY=... python -m evals.agent_eval --mode llm --tpm 8000   # live Groq, paced for the free tier

Metrics (per category and overall):
  tool_accuracy      the expected tool was called
  arg_accuracy       ...and its arguments matched (amounts within 0.5%, change types and key params)
  grounded_rate      every amount / percentage / date in the final reply came from a tool
  guardrail_replaced (llm) drafts rejected by the guardrail and rewritten from engine output
  fallback_rate      (llm) provider errors answered by the deterministic planner instead
  latency p50 / p95, mean tokens per question (llm)

Results go to evals/results/agent_<mode>.json. Nothing is invented: if a mode can't run (no key),
the script says so and writes nothing.
"""
import argparse
import json
import statistics
import time

from evals.common import RESULTS, ROOT, run_info, setup_demo

CASES = json.loads((ROOT / "agent_cases.json").read_text())["cases"]


def _num_ok(got, want) -> bool:
    try:
        return abs(float(got) - float(want)) <= max(0.5, abs(float(want)) * 0.005)
    except (TypeError, ValueError):
        return False


def _args_ok(call: dict, expect: dict) -> tuple[bool, str]:
    args = call["arguments"]
    for k, v in (expect.get("args") or {}).items():
        if isinstance(v, (int, float)):
            if not _num_ok(args.get(k), v):
                return False, f"{k}={args.get(k)!r}, expected {v}"
        elif args.get(k) != v:
            return False, f"{k}={args.get(k)!r}, expected {v!r}"
    want_changes = expect.get("changes")
    if want_changes:
        got = args.get("changes") or []
        if sorted(c.get("type") for c in got) != sorted(c["type"] for c in want_changes):
            return False, f"change types {[c.get('type') for c in got]}, expected {[c['type'] for c in want_changes]}"
        for w in want_changes:
            g = next(c for c in got if c.get("type") == w["type"])
            for k, v in w.items():
                if k == "type":
                    continue
                if not _num_ok(g.get(k), v):
                    return False, f"{w['type']}.{k}={g.get(k)!r}, expected {v}"
    return True, ""


def run_case(case: dict, db, user, llm_factory, pace_tpm: int = 0) -> dict:
    from app.ai.assistant import chat

    turns = case.get("turns") or [case["question"]]
    history: list[dict] = []
    context = None
    res = None
    t0 = time.perf_counter()
    for q in turns:
        history.append({"role": "user", "content": q})
        t0 = time.perf_counter()
        res = chat(history[-10:], db, user, llm_factory(), context)
        history.append({"role": "assistant", "content": res["reply"][:2000]})
        if pace_tpm and q is not turns[-1] and res.get("usage"):  # pace between turns of a multi-turn case too
            used = res["usage"]["prompt_tokens"] + res["usage"]["completion_tokens"]
            time.sleep(max(0.0, used / pace_tpm * 60 - (time.perf_counter() - t0)) + 1)
        context = res.get("context") or context
    ms = int((time.perf_counter() - t0) * 1000)
    exp = case["expect"]
    calls = [c for c in res["tool_calls"] if c["ok"]]
    match = next((c for c in calls if c["tool"] == exp["tool"]), None)
    args_ok, why = _args_ok(match, exp) if match else (False, f"called {[c['tool'] for c in res['tool_calls']] or 'no tool'}")
    return {
        "id": case["id"], "category": case["category"], "paraphrase": bool(case.get("paraphrase")),
        "question": turns[-1], "tool_ok": match is not None, "args_ok": args_ok, "why": why,
        "called": [c["tool"] for c in res["tool_calls"]], "grounded": bool(res["grounding"]["ok"]),
        "guardrail": res.get("guardrail"), "mode": res["mode"], "fallback": res["mode"] == "rules" and res.get("note") is not None,
        "ms": ms, "tokens": (res.get("usage") or {}).get("prompt_tokens", 0) + (res.get("usage") or {}).get("completion_tokens", 0),
        "reply": res["reply"][:600],
        # Why an answer fell back or was rewritten, so a run explains its own numbers.
        "note": res.get("note"),
        "rejected": (res.get("rejected_grounding") or {}).get("invented"),
        "provider_notes": [n for t in res.get("trace", []) if t.get("type") == "llm" for n in (t.get("detail") or {}).get("notes", [])][:6],
    }


def _rate(rows, key) -> float | None:
    return round(sum(1 for r in rows if r[key]) / len(rows), 3) if rows else None


def summarize(rows: list[dict]) -> dict:
    def block(rs):
        lat = sorted(r["ms"] for r in rs)
        return {"n": len(rs), "tool_accuracy": _rate(rs, "tool_ok"), "arg_accuracy": _rate(rs, "args_ok"),
                "grounded_rate": _rate(rs, "grounded"),
                "guardrail_replaced": round(sum(1 for r in rs if r["guardrail"] == "replaced") / len(rs), 3) if rs else None,
                "fallback_rate": _rate(rs, "fallback"),
                "latency_ms_p50": statistics.median(lat) if lat else None,
                "latency_ms_p95": lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))] if lat else None,
                "mean_tokens": round(statistics.mean(r["tokens"] for r in rs), 1) if rs else None}
    cats = sorted({r["category"] for r in rows})
    return {"overall": block(rows), "seen_wording": block([r for r in rows if not r["paraphrase"]]),
            "paraphrases": block([r for r in rows if r["paraphrase"]]),
            "by_category": {c: block([r for r in rows if r["category"] == c]) for c in cats}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rules", "llm"], default="rules")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tpm", type=int, default=0,
                    help="pace LLM runs to this tokens-per-minute budget (e.g. 8000 on Groq's free tier)")
    args = ap.parse_args()

    from app.ai.llm import LlmClient
    from app.core.config import get_settings

    s = get_settings()
    if args.mode == "llm" and not s.llm_settings:
        raise SystemExit("--mode llm needs GROQ_API_KEY (or OPENAI_API_KEY). Nothing was run or written.")
    factory = (lambda: LlmClient(s)) if args.mode == "llm" else (lambda: None)

    db, user = setup_demo()
    cases = CASES[: args.limit] if args.limit else CASES
    rows = []
    for c in cases:
        r = run_case(c, db, user, factory, args.tpm)
        rows.append(r)
        if args.tpm and r["tokens"]:
            time.sleep(max(0.0, r["tokens"] / args.tpm * 60 - r["ms"] / 1000) + 1)
        flag = "✓" if r["args_ok"] else ("~" if r["tool_ok"] else "✗")
        print(f"{flag} {r['id']:<8} {r['ms']:>6} ms  {'grounded' if r['grounded'] else 'UNGROUNDED':<10} {r['why']}")
    out = {"benchmark": "agent", "mode": args.mode,
           "provider": s.llm_settings["provider"] if args.mode == "llm" else None,
           "model": s.llm_settings["models"][0] if args.mode == "llm" else None,
           **run_info(), "paced_tpm": args.tpm or None, "summary": summarize(rows), "cases": rows}
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"agent_{args.mode}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    o = out["summary"]["overall"]
    print(f"\n{args.mode}: tool {o['tool_accuracy']:.0%} · args {o['arg_accuracy']:.0%} · grounded {o['grounded_rate']:.0%}"
          f" · p50 {o['latency_ms_p50']} ms  → {path.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
