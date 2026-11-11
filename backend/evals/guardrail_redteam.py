"""Guardrail red-team: how often does the grounding check catch a wrong figure, and how often does it
wrongly reject a correct answer?

    python -m evals.guardrail_redteam

For every benchmark question we run the real engine tools and take the deterministic reply as a
known-correct answer. From it we build:

  faithful variants (must PASS)   the reply itself; amounts re-written in lakh / K notation or
                                   rounded to the rupee; dates re-written as "November 15".
  corrupted variants (must FAIL)  one amount scaled by ×1.05, ×1.2, ×0.5; two digits transposed;
                                   a fabricated extra sentence with a new amount; a date moved by
                                   3 days; a percentage moved by 5 points.
                                   Also one amount scaled by ×1.005 (a small but real error).

Ablation: every draft is checked twice, with the shipped precision-aware money tolerance and with
the earlier flat 1% tolerance, so the effect of that design change is measured, not asserted.

Ground truth for each draft is exactly what an LLM would have received: tool results + arguments +
today's date. All randomness is seeded, so the report is reproducible.
"""
import json
import random
import re
from decimal import Decimal

from evals.common import RESULTS, ROOT, run_info, setup_demo

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
SHORT = [m[:3] for m in MONTH_NAMES]
MONEY_RE = re.compile(r"₹(\d[\d,]*(?:\.\d+)?)")
DATE_RE = re.compile(r"\b(\d{1,2}) (" + "|".join(SHORT) + r")(?: (20\d\d))?\b")
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)%")


def inr(v: Decimal) -> str:
    """Indian digit grouping, like the engine: 1,07,531."""
    n = int(v.quantize(Decimal("1")))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        s = f"{head},{tail}"
    return ("-" if n < 0 else "") + s


def _val(m: re.Match) -> Decimal:
    return Decimal(m.group(1).replace(",", ""))


def _replace_nth(text: str, regex: re.Pattern, idx: int, fn) -> str:
    ms = list(regex.finditer(text))
    m = ms[idx]
    return text[:m.start()] + fn(m) + text[m.end():]


def faithful_variants(reply: str) -> dict[str, str]:
    out = {"engine_reply": reply}
    if MONEY_RE.search(reply):
        def lakh(m):
            v = _val(m)
            return f"₹{(v / 100000):.2f} lakh" if v >= 100000 else f"₹{(v / 1000):.1f}K" if v >= 10000 else m.group(0)
        out["lakh_k_notation"] = MONEY_RE.sub(lakh, reply)
        out["rounded_to_rupee"] = MONEY_RE.sub(lambda m: f"₹{inr(_val(m))}", reply)
    if DATE_RE.search(reply):
        out["long_month_dates"] = DATE_RE.sub(lambda m: f"{MONTH_NAMES[SHORT.index(m.group(2))]} {int(m.group(1))}", reply)
    return out


def corrupted_variants(reply: str, rng: random.Random) -> dict[str, str]:
    out: dict[str, str] = {}
    money = [m for m in MONEY_RE.finditer(reply) if _val(m) >= 100]
    if money:
        i = rng.randrange(len(money))
        idx = [m.start() for m in MONEY_RE.finditer(reply)].index(money[i].start())
        for name, f in (("scale_x1.05", Decimal("1.05")), ("scale_x1.2", Decimal("1.2")), ("scale_x0.5", Decimal("0.5"))):
            out[name] = _replace_nth(reply, MONEY_RE, idx, lambda m, f=f: f"₹{inr(_val(m) * f)}")
        digits = inr(_val(money[i])).replace(",", "")
        if len(digits) >= 3 and len(set(digits[-3:-1])) == 2:
            swapped = digits[:-3] + digits[-2] + digits[-3] + digits[-1]
            out["digit_transposition"] = _replace_nth(reply, MONEY_RE, idx, lambda m: f"₹{inr(Decimal(swapped))}")
        out["small_error_x1.005"] = _replace_nth(reply, MONEY_RE, idx, lambda m: f"₹{inr(_val(m) * Decimal('1.005'))}")
    fabricated = rng.choice([3_450, 12_900, 27_350, 41_800, 66_600, 93_250, 1_48_700])
    out["fabricated_sentence"] = reply + f"\nYou'd also save about ₹{inr(Decimal(fabricated))} a year by switching."
    if DATE_RE.search(reply):
        def shift(m):
            d = (int(m.group(1)) + 3 - 1) % 28 + 1
            return f"{d} {m.group(2)}" + (f" {m.group(3)}" if m.group(3) else "")
        out["date_shift_3d"] = _replace_nth(reply, DATE_RE, 0, shift)
    if PCT_RE.search(reply):
        out["percent_plus_5"] = _replace_nth(reply, PCT_RE, 0, lambda m: f"{Decimal(m.group(1)) + 5}%")
    return out


def main():
    from app.ai import guardrail
    from app.ai.assistant import _payloads, _rules_reply
    from app.ai.rules import plan_followup
    from app.ai.tools import run_tool
    from evals.agent_eval import CASES

    db, user = setup_demo()
    rng = random.Random(20261111)
    rows = []
    for case in CASES:
        context = None
        for q in case.get("turns") or [case["question"]]:
            calls, _ = plan_followup(q, context, [], [])
            outcomes = [run_tool(n, a, db, user) for n, a in calls]
            main_call = next((o for o in reversed(outcomes) if o.ok), None)
            context = {"tool": main_call.tool, "arguments": main_call.arguments} if main_call else context
        if not any(o.ok for o in outcomes):
            continue
        reply = _rules_reply(outcomes)
        truth = _payloads(outcomes)
        variants = [(n, t, "pass") for n, t in faithful_variants(reply).items()] + \
                   [(n, t, "fail") for n, t in corrupted_variants(reply, rng).items()]
        for name, text, expect in variants:
            r = guardrail.check_claims(text, truth)
            flat = guardrail.check_claims(text, truth, flat_tolerance=Decimal("0.01"))
            rows.append({"case": case["id"], "variant": name, "expect": expect, "passed": r["ok"],
                         "passed_flat_1pct": flat["ok"], "text": text[-240:] if r["ok"] != (expect == "pass") else None})

    def summarize(key: str) -> dict:
        faithful = [r for r in rows if r["expect"] == "pass"]
        corrupt = [r for r in rows if r["expect"] == "fail"]
        by_variant = {}
        for v in sorted({r["variant"] for r in rows}):
            sel = [r for r in rows if r["variant"] == v]
            ok = sum(r[key] for r in sel) / len(sel)
            by_variant[v] = ({"n": len(sel), "acceptance_rate": round(ok, 3)} if sel[0]["expect"] == "pass"
                             else {"n": len(sel), "detection_rate": round(1 - ok, 3)})
        acc = sum(r[key] for r in faithful) / len(faithful)
        return {"faithful_n": len(faithful), "faithful_acceptance_rate": round(acc, 3),
                "false_rejection_rate": round(1 - acc, 3), "corrupted_n": len(corrupt),
                "corruption_detection_rate": round(1 - sum(r[key] for r in corrupt) / len(corrupt), 3),
                "by_variant": by_variant}

    summary = summarize("passed")
    ablation = summarize("passed_flat_1pct")
    out = {"benchmark": "guardrail_redteam", **run_info(), "summary": summary,
           "ablation_flat_1pct_tolerance": ablation,
           "misses": [r for r in rows if (r["expect"] == "fail") == r["passed"]][:50]}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "guardrail_redteam.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"{'variant':<22} {'shipped':>8} {'flat 1%':>8}")
    for v, d in summary["by_variant"].items():
        k = "detection_rate" if "detection_rate" in d else "acceptance_rate"
        print(f"{v:<22} {d[k]:>8.1%} {ablation['by_variant'][v][k]:>8.1%}  ({k.split('_')[0]}, n={d['n']})")
    print(f"\nfaithful accepted {summary['faithful_acceptance_rate']:.1%} (flat {ablation['faithful_acceptance_rate']:.1%}) · "
          f"corruptions caught {summary['corruption_detection_rate']:.1%} (flat {ablation['corruption_detection_rate']:.1%})")
    for m in out["misses"][:12]:
        print("MISS", m["case"], m["variant"], "|", (m["text"] or "")[-160:].replace("\n", " / "))


if __name__ == "__main__":
    main()
