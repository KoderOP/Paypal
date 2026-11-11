# FINORA: simulate before you pay

**A PayPal + AI copilot that checks a payment against your future cash flow, then drafts the PayPal checkout. Only you can send it.**

> *"Should I buy a ₹75,000 laptop?"*
> FINORA's Groq agent runs the purchase through a deterministic 90-day model of your PayPal cash flow.
> Paying in full today takes you **below your safety buffer** before payday. Waiting is safe. **PayPal Pay in 4 is safe and
> gets you the laptop today**, so that's the recommendation. Say *"go ahead with Pay in 4"* and the agent drafts the
> PayPal checkout. You review it, approve on PayPal and confirm the capture. The four instalments then appear in your forecast.

Most finance apps tell you what you already spent. FINORA works **at the moment of decision**, before the money leaves, and
connects that decision to the PayPal rails (Orders API, Pay Later, Subscriptions, Transaction Search) that act on it.

---

## Run it (2 minutes, no keys needed)

```bash
# Backend: http://localhost:8000 (OpenAPI docs at /docs)
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend: http://localhost:5173 (second terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 and click **Launch the live demo**. This loads six months of **synthetic** PayPal activity and asks
the agent the laptop question. With no `.env`, everything works offline:

| Component | Without keys | With keys (`backend/.env`, see `.env.example`) |
|---|---|---|
| Agent | Deterministic planner, same tools, exact figures | **Groq tool calling** (`GROQ_API_KEY`), default `openai/gpt-oss-120b`, fallback `llama-3.3-70b-versatile` |
| PayPal | Built-in **PayPal demo mode**: an in-process stand-in for the REST API, clearly labelled, no money moves | **PayPal Sandbox** (`PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`): same client code |

Before a live demo, verify the key and model with `cd backend && python -m evals.check_groq`.
Docker: `docker compose up --build` (Postgres 16 + backend + frontend).

## What makes it different

1. **The model talks, the engine counts, you pay.** The LLM chooses among 7 engine tools and phrases the answer. It never
   computes. A **grounding guardrail** extracts every amount, percentage and date from the draft and checks it against the tool
   results. Ungrounded drafts are replaced with the engine's own wording, and the answer says so.
2. **Agentic, with a human gate built into the architecture.** The agent's only action tool, `prepare_paypal_checkout`,
   returns a proposal card. There is no tool that moves money. Paying needs three human steps: acknowledge (an extra tick if
   the option breaks your buffer) → approve on PayPal → confirm capture. Each step is enforced server-side (`422` without it).
3. **A transparent trace on every answer.** Each model round, tool call (with arguments), token count and guardrail verdict
   is shown under the answer in "How this answer was produced".
4. **Evaluated, not asserted.** Three reproducible evaluations (below), surfaced in-app at `/evals`.
5. **Graceful degradation.** Groq rate limits, malformed tool calls, retired models and outages are retried, swapped to the
   fallback model, or answered by the deterministic planner, and the trace shows which path ran.

## Evidence (`cd backend && python -m evals.run_all`)

| Evaluation | Result | Baseline / ablation |
|---|---|---|
| **Forecast backtest**: purchase-safety decisions, walk-forward, 60 noise-injected histories × 5 cut-offs | **95.0%** correct, **3.5%** false-safe | Seasonal-naive 92.6% / 4.6%; linear drift 76.6% / 23.4% |
| Forecast backtest: daily balance error (same data) | **15.6%** of monthly income | Seasonal-naive 20.0%; flat 35.2% |
| **Guardrail red-team**: 262 corrupted drafts, 154 faithful drafts | **97.7%** caught, **0%** false rejections | Flat 1% tolerance: 76.3% caught (digit swaps: 29.6% vs 100%) |
| **Agent benchmark**: 40 questions, deterministic planner | Tool 85% · args 77.5% · **grounded 100%** | 100% on wording it was written for, 57% on held-out paraphrases (the gap the LLM closes) |
| Agent benchmark, Groq live | `python -m evals.agent_eval --mode llm` | Not run in this build (no key available while building). Never estimated |

The backtest uses synthetic data, so it shows the method works on regular monthly cash flow, not real-world accuracy.
Run `python -m evals.forecast_backtest --file <your PayPal export.csv>` for that. Full method and caveats are in
[docs/EVALUATION.md](docs/EVALUATION.md).

The evaluations found and fixed four guardrail bugs, including a JSON-escaping bug that turned "₹12,469" into 912469
and a flat tolerance that let digit transpositions through. Regression tests cover each one.

## Architecture in one picture

```
 PayPal Transaction Search / Activity CSV / bank CSV
            │ normalise (PayPal txn id = idempotency key; FX keeps PayPal's own rate + fee)
            ▼
 ┌──────────── deterministic engine (pure, Decimal-only, no I/O, no LLM) ────────────┐
 │ twin.py  recurring detection · variable spend │ forecast.py  90-day daily path      │
 │ payment_options.py  now / wait / Pay Later    │ goals.py  max safe spend, safe date │
 │ scenarios.py  composable what-ifs             │ stress.py  shocks + Monte Carlo     │
 └───────────────────────────────▲────────────────────────────────────────────────────┘
                                 │ 7 tools (JSON schema)
 ┌──────────── agent (app/ai) ───┴────────────────────────────────────────────────────┐
 │ Groq chat completions + tool calling ⇄ tools → guardrail (₹ · % · dates) → reply    │
 │ fallback: deterministic intent planner · trace · token/latency accounting           │
 └───────────────────────────────┬────────────────────────────────────────────────────┘
                                 │ prepare_paypal_checkout = proposal only
                                 ▼
  You: acknowledge → PayPal approve (Orders API, Pay Later) → confirm capture → twin updated
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Demo script: [docs/DEMO.md](docs/DEMO.md)

## Feature map

- **Ask FINORA** (`/assistant`): the agent. Purchase decisions, affordability ("most I can spend", "earliest safe date"),
  composable what-ifs, stress tests, cross-border income, follow-ups that build on the previous answer, drafted checkouts.
- **What-if Simulator** and **Stress Test**: the same engine through forms and charts. Compare up to four scenarios;
  shock library plus a seeded Monte Carlo of your own spending variability.
- **PayPal Hub**: Transaction Search sync, Activity CSV import, Orders API checkout, Pay Later, Subscriptions API
  (link / cancel / suspend), optional Sign in with PayPal.
- **Cross-border income**: for freelancers paid via PayPal. Fees, PayPal's applied FX rate vs a reference rate, FX and
  late-client sensitivity.
- **Overview / Twin / Transactions**: the model itself, with explicit assumptions.
- **Evaluation** (`/evals`): the committed evaluation results.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q   # 186 tests: engine, parsers, PayPal (mocked + demo), Groq client, agent, guardrail, demo storyline
cd frontend && npm run build                  # type-check + production build
```

The demo storyline (pay-in-full unsafe, Pay in 4 recommended) is tested on dates across a full year, because the demo data is
generated relative to today.

## Honest limitations

- **Live Groq and PayPal Sandbox calls were not exercised while building** (no credentials were available). Both are covered by
  mocked-HTTP tests of the exact request/response shapes, and PayPal demo mode runs the full flow through the same client code.
  Run `python -m evals.check_groq` and the live agent benchmark before relying on them.
- **Pay Later terms are illustrative inputs.** PayPal decides eligibility, APR and schedule at checkout, and Pay Later isn't
  offered in every currency (including INR). Set `PAYPAL_CHECKOUT_CURRENCY=USD` for sandbox testing.
- **Value-based grounding** can't tell a corrupted figure from a coincidentally equal legitimate one (the 2.3% red-team misses).
- **One data profile per deployment.** Sign in with PayPal identifies the user but data isn't multi-tenant yet.
- Forecasts detect monthly recurrence only and produce one deterministic path (bands come from the separate stress test).
- No database migrations (`create_all`). The rate limit is in-process (use a shared store behind a load balancer).

Not financial advice. Projections are estimates from your own history.
