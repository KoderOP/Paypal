# FINORA evaluation

Three questions decide whether FINORA's advice can be trusted:

1. **Is the forecast good enough to make a purchase decision?** → walk-forward backtest
2. **Does the guardrail stop an LLM from stating wrong numbers, without blocking right ones?** → red-team with ablation
3. **Does the agent call the right tool with the right arguments?** → benchmark

Everything is reproducible and seeded:

```bash
cd backend
python -m evals.run_all              # offline: ~10 s, writes evals/results/*.json and REPORT.md
GROQ_API_KEY=... python -m evals.run_all --llm   # adds the live Groq agent benchmark
python -m evals.forecast_backtest --file ~/Downloads/paypal_activity.csv   # backtest on your own export (not saved)
```

The numbers below come from `evals/results/` at the commit recorded in each JSON file. The web app shows the same files at
`/evals`.

---

## 1. Forecast backtest (`evals/forecast_backtest.py`)

**Protocol.** For each history and each of 5 cut-off dates, the forecaster sees only transactions *before* the cut-off,
predicts the next 30 days of daily balances, and is scored against what actually happened.

**Forecasters.** `twin` is FINORA's engine, unmodified. Baselines: `flat` (balance stays put), `linear_drift` (average
daily net flow over 90 days), and `seasonal_naive` (replay the last 30 days' daily flows). Seasonal-naive is a deliberately
strong baseline for monthly cash flow.

**Metrics.**
- *Path MAE*: mean absolute daily balance error, also as % of monthly income.
- *Low-point MAE*: error in the minimum balance, the number "is it safe?" depends on.
- *Decision accuracy*: for purchases of 10%–150% of monthly income made on the cut-off day, is "stays above the ₹20,000
  buffer" predicted correctly? *False-safe*: predicted safe but actually breached. That's the costly error.

**Data.** 30 seeds × 2 personas (salaried, USD freelancer paid via PayPal) = 60 histories per condition.
- *Clean*: the demo generator as-is.
- *Perturbed*: income dates jittered −3…+4 days, 10% of bills skipped, one-off expenses on ~2% of days (₹2k–15k), and
  variable spending scaled ±25% per month.

**Results** (60 histories × 5 cut-offs = 300 forecasts per model and condition)

| Condition | Model | Path MAE | % income | Low-point MAE | Decision acc. | False-safe |
|---|---|---|---|---|---|---|
| clean | **twin** | ₹2,736 | **4.2%** | ₹3,039 | **96.8%** | **2.6%** |
| clean | seasonal naive | ₹7,016 | 10.7% | ₹6,630 | 93.2% | 3.9% |
| clean | linear drift | ₹20,034 | 30.6% | ₹22,571 | 77.3% | 22.7% |
| clean | flat | ₹23,803 | 36.3% | ₹21,863 | 78.0% | 22.0% |
| perturbed | **twin** | ₹10,003 | **15.6%** | ₹6,143 | **95.0%** | **3.5%** |
| perturbed | seasonal naive | ₹12,974 | 20.0% | ₹9,087 | 92.6% | 4.6% |
| perturbed | linear drift | ₹20,875 | 32.3% | ₹24,605 | 76.6% | 23.4% |
| perturbed | flat | ₹22,789 | 35.2% | ₹24,034 | 77.2% | 22.8% |

**Reading it.**
- The twin beats every baseline on every metric in both conditions. Its advantage shrinks under noise (path error 4.2% →
  15.6% of income), which is expected: it models structure, and the noise removes some.
- Decisions degrade far less than path error (96.8% → 95.0%). Low-point accuracy matters more than day-by-day accuracy.
- **A 3.5% false-safe rate is not zero.** This is why the product presents a buffer, shows the low point and date, and offers
  a stress test with Monte Carlo bands. A natural next step is calibrating a margin from these residuals.

**What this does and doesn't show.** It shows the forecasting *method* beats standard baselines on cash flow with monthly
structure, with and without noise. It does **not** show accuracy on real users: no real histories were available. The 95.0%
figure should always be quoted with "synthetic backtest" and the baseline next to it.

**Caveat.** The histories come from the same generator family as the demo. That favours any model that finds monthly
structure, so read these as evidence the method works, not as real-world accuracy. The `--file` mode exists so anyone can
measure it on a real PayPal export.

## 2. Guardrail red-team (`evals/guardrail_redteam.py`)

**Protocol.** For each of the 40 benchmark questions, run the real tools and take the engine's deterministic reply as a
known-correct answer. Ground truth is exactly what an LLM would receive (tool results + arguments + today).

- *Faithful* variants (must pass): verbatim; amounts in lakh/K notation; amounts rounded to the rupee; dates as "November 15".
- *Corrupted* variants (must be caught): one amount ×1.005 / ×1.05 / ×1.2 / ×0.5; two digits transposed; a fabricated extra
  sentence with a new amount; a date moved 3 days; a percentage +5 points.

**Ablation.** Every draft is also checked with the earlier flat 1% money tolerance.

| Variant | n | Shipped (precision-aware) | Flat 1% |
|---|---|---|---|
| Faithful (all four kinds) | 154 | **100% accepted** | 100% accepted |
| Digits transposed | 27 | **100% caught** | 29.6% |
| Amount ×1.005 | 38 | **100%** | 0% |
| Amount ×1.05 | 38 | 100% | 100% |
| Amount ×1.2 | 38 | 97.4% | 100% |
| Amount ×0.5 | 38 | 92.1% | 92.1% |
| Fabricated sentence | 40 | 95.0% | 95.0% |
| Date +3 days | 38 | 100% | 100% |
| Percentage +5 | 5 | 100% | 100% |
| **All corruptions** | 262 | **97.7%** | 76.3% |

**Reading it.** Precision-aware tolerance (a full-digit figure must match to the rupee; a rounded one within half its last
unit, capped at 2%) removes the blind spot for small errors at no cost in false rejections. The remaining 2.3% of misses are
coincidences: the corrupted value equals another figure the tools legitimately returned. Value-based grounding can't
separate those, so fixing it would need claim-to-source binding (e.g. having the model cite tool fields), which is future work.

### Bugs this evaluation found (now fixed, with regression tests in `tests/test_agent.py`)
1. `json.dumps` escaped "₹" as `₹`, and its trailing "9" merged into the next number ("₹12,469" became 912469), so real
   figures inside engine sentences looked invented.
2. Dates written out in engine sentences ("15 Nov 2026") weren't recognised, only ISO dates.
3. Today's date wasn't treated as known.
4. A flat 1% tolerance let digit transpositions through (29.6% detection).

Before fixes 1–3, **45% of the engine's own correct replies were flagged as ungrounded**, which would have made the LLM
path rewrite most good answers.

## 3. Agent benchmark (`evals/agent_eval.py`, cases in `evals/agent_cases.json`)

40 cases across purchases, affordability, what-ifs, stress, cross-border, snapshot, drafted checkouts and multi-turn
follow-ups. 14 are **held-out paraphrases** (e.g. *"Thinking of getting a PS5 for 55k. Split it or pay outright?"*,
*"Sounds good, let's split it into four"*) that the deterministic planner was not written for, and that it was deliberately
not tuned on afterwards.

Scored per case: the expected tool was called; its arguments matched (amounts within 0.5%, change types and key parameters);
the final reply passed the grounding check.

**Deterministic planner (offline, measured):**

| Slice | n | Tool | Arguments | Grounded |
|---|---|---|---|---|
| Overall | 40 | 85.0% | 77.5% | 100% |
| Wording it was written for | 26 | 100% | 100% | 100% |
| Held-out paraphrases | 14 | 57.1% | 35.7% | 100% |

The planner is exact on the wording it knows and brittle beyond it, while staying grounded either way. That gap is the reason
for the LLM path.

**Groq (live, `openai/gpt-oss-120b`):**

Final run, commit `c4cd1f2` (agent code identical to `fced06e`, where the run started), paced to 8,000 tokens/minute:

| Slice | n | Tool | Arguments | Grounded | Guardrail rewrites | Fallback to planner | p50 / p95 latency |
|---|---|---|---|---|---|---|---|
| Overall | 40 | 92.5% | 90.0% | 100% | 17.5% | 15.0% | 1.7 s / 12.3 s |
| Wording the planner was written for | 26 | 100% | 100% | 100% | 15.4% | 15.4% | 1.7 s / 12.3 s |
| Held-out paraphrases | 14 | 78.6% | 71.4% | 100% | 21.4% | 14.3% | 1.7 s / 12.3 s |

**Reading it honestly.**
- On paraphrases Groq beats the offline planner (71.4% vs 35.7% correct arguments), which is what the LLM is for.
  On wording the planner knows, both score 100%.
- **Every final answer was grounded (100%).** That holds by design: a rejected draft is replaced by engine output.
- **Fallbacks (15%)** were provider errors during the run (6 cases, clustered at the end, all multi-turn or late). The client
  had switched to the fallback model (`openai/gpt-oss-20b` shows usage), which also failed for those cases, so the offline
  planner answered (still correctly, where its wording allowed). Both models were healthy right after the run. This run did not
  record the exact error per case. `agent_eval.py` now saves `note`, `rejected` and `provider_notes` for each case.
- **Rewrites vary a lot between runs: 20%, 7.5% and 17.5%** over three full runs on the same questions. We therefore don't
  claim the change below reliably lowered the rate. What we did verify is *why* drafts are rejected (next section).
- p95 latency of about 12 s reflects rate-limit retries on the free tier, not model speed (p50 is 1.7 s).


Run with `python -m evals.agent_eval --mode llm --tpm 8000`. `--tpm` paces requests to Groq's free-tier limit of 8,000 tokens per
minute, so the results measure the agent, not the rate limiter. One question costs about 4,800 tokens (two model rounds,
each carrying the tool schemas).

### Why some Groq drafts are rewritten
In the first live run, 8 of 40 drafts (20%) failed the guardrail and were replaced with engine wording. To find out whether
the guardrail was too strict, we re-ran those 8 questions and recorded the rejected drafts. 6 passed on the rerun (the model's
output varies between runs). Both rejections that reproduced were **Groq doing its own arithmetic**:

- *"Earliest date I could drop ₹60,000 on a sofa?"* Groq subtracted ₹68,800 − ₹60,000 and wrote "you'll still have a buffer of
  about ₹8,800". The subtraction was right, but the meaning was wrong: ₹8,800 is the room *above* the ₹20,000 buffer, and the
  low point would be ₹28,800.
- *"What about 20 days?"* (income delay). Groq stated the drop in the lowest balance as ₹25,302; the right figure is
  ₹88,800 − ₹62,498 = **₹26,302**.

So the rewrites were true catches, not false alarms. The fix was on the tool side: results now include the differences people
ask about, computed by the engine (`min_balance_change`, `end_balance_change`, `room_above_buffer_if_bought_today`,
`lowest_projected_balance_if_bought_today`), and the prompt says to quote them rather than compute. Both questions then
passed with correct figures when re-asked. The table above is from a later full run. Its rewrite rate (17.5%) is within the run-to-run range, so the effect on the overall rate is not established.

## Test suite

`pytest` (207 tests) covers the engine, parsers, PayPal flows (mocked HTTP and demo mode), the Groq client's retry/fallback
behaviour, the agent loop and trace, the guardrail (accept/reject cases plus regressions), the checkout-proposal tool (creates
no order, flags unsafe options), the rate limit, and the landing demo storyline on dates across a full year.
