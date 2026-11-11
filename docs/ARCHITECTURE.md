# FINORA architecture

FINORA has three layers with hard boundaries: a **pure deterministic engine** that does all money arithmetic, an **agent**
that decides which engine function to call and how to phrase the result, and **PayPal integrations** that read data and act
on decisions only after explicit human confirmation.

```
frontend (React 19 · TS · Vite · Tailwind 4 · Recharts)
   │  JSON over /api (Vite proxy; no secrets or URLs in client code)
backend (FastAPI · Pydantic · SQLAlchemy 2 · SQLite or Postgres)
   ├── app/api/            routers: validation, HTTP errors, confirmation gates
   ├── app/ai/             agent: llm.py (Groq client) · assistant.py (loop + trace) · tools.py · guardrail.py · rules.py
   ├── app/engine/         PURE: twin · forecast · payment_options · goals · scenarios · simulation · stress · crossborder · alerts
   ├── app/services/       DB → engine adapters (repository, planning)
   ├── app/integrations/paypal/   OAuth client · Transaction Search · Orders · Subscriptions · Identity · demo-mode stand-in
   ├── app/data/           ORM models · CSV parsers (PayPal Activity, bank statement, generic) · synthetic generator
   └── evals/              agent benchmark · guardrail red-team · forecast backtest · Groq pre-flight check
```

## 1. Deterministic engine (`app/engine`)

- **Pure functions over Pydantic models.** No database, network, randomness (except the seeded Monte Carlo in `stress.py`) or LLM.
  Same inputs give the same outputs, and a test asserts it.
- **Decimal money everywhere.** `app/core/money.py` refuses floats, and money is serialised to JSON numbers only at the API edge.
- **Balances are derived, never stored:** `Σ opening balances + Σ transactions`.
- **Scenarios are event overlays.** A forecast is a list of dated cash events. A what-if adds, removes or shifts events and is
  projected by the same code, so new scenario types are cheap and comparable.
- **Fair timing.** Each payment option is simulated for the full horizon *after its last payment*, so a late option can't look
  safe just because the window ended.

How the twin learns (deterministic rules):

| Signal | Rule |
|---|---|
| Recurring item | Same merchant and direction, ≥3 occurrences, median interval 25–35 days, ≤1 per month, amount spread ≤40%, seen in the last 45 days. Projected amount = median of the last 3. |
| Variable spending | Non-recurring debits. Per category, the median of the last three 30-day windows (robust to one-off spikes). |
| Income | Recurring credits. Irregular income is excluded from forecasts by default (conservative). |
| Savings | Investments (SIPs) count as savings, not spending. |
| Transfers | Withdrawals from PayPal to a bank are transfers, not spending, so a PayPal report plus the bank statement it pays into don't double count. |

## 2. Agent (`app/ai`)

### Loop (`assistant.py`)
1. System prompt (grounding rules + tool routing) + last 12 turns + the previous answer's `context` (so follow-ups like "and if
   my salary is also late?" or "ok, pay for it" build on it).
2. Up to **4 rounds** and **8 tool calls**: the model requests tools, `run_tool` validates the arguments with Pydantic and calls
   the engine, and compact JSON results go back with matching `tool_call_id`s.
3. **Guardrail** on the final draft (below). If the draft passes it's returned. If it fails, the reply is rebuilt from the tools'
   deterministic sentences, `guardrail: "replaced"`, and `note` names the invented claims.
4. Every response carries a `trace` (LLM rounds with model, tokens, retries; tool calls with arguments and timings; guardrail
   report), `usage`, `latency_ms`, and `tool_calls[].card` for the UI's rich cards.

### Tools (`tools.py`)
| Tool | Engine call | Side effects |
|---|---|---|
| `get_financial_snapshot` | profile + baseline forecast | none |
| `compare_payment_options` | pay now vs wait vs PayPal Pay in 4 / Pay Monthly | none |
| `find_affordability` | exact max safe spend (today / this month / window) and earliest safe date | none |
| `simulate_scenario` | composable what-ifs (purchase, cancel/add subscription, income delay/loss, savings, spending, emergency, FX) | none |
| `run_stress_test` | shock library + Monte Carlo, runway, resilience | none |
| `get_cross_border_summary` | PayPal fees, applied FX rates, FX and late-client sensitivity | none |
| `prepare_paypal_checkout` | re-runs the comparison, picks the requested (or recommended) *payable* option | **none: returns a proposal** |

### Grounding guardrail (`guardrail.py`)
Ground truth is exactly what the model received: tool results + tool arguments + today's date.

- **Money** (₹, Rs, INR; lakh, K, crore): must match a tool number (or ×12 / ÷12 of one) **to the precision it was written
  with**. "₹1,68,391" must match to the rupee; "₹1.68 lakh" within ₹500; capped at 2%.
- **Percentages:** within 0.5 points of a tool number or a ratio ×100.
- **Dates** ("23 Nov", "November 23rd", "2026-11-23"): that calendar day must appear in the tool results, either as an ISO
  date or written out in an engine sentence.

### Provider client (`llm.py`)
Groq's OpenAI-compatible Chat Completions over `httpx` (no SDK). Bounded retries for 429/5xx/network errors (honours
`Retry-After`, capped at 6 s); `tool_use_failed` is retried once at temperature 0; `model_not_found` / decommissioned
switches to `GROQ_FALLBACK_MODEL`. Any other failure raises `LlmError`, and the agent answers with the deterministic planner.

### Deterministic planner (`rules.py`)
A regex intent parser that maps questions (including follow-ups and "go ahead with Pay in 4") to the same tools. It's the
offline mode and the safety net. Its accuracy on held-out paraphrases is measured, not tuned (see EVALUATION.md).

## 3. PayPal integration (`app/integrations/paypal`, `app/api/checkout.py`, `subscriptions.py`, `paypal.py`, `auth.py`)

| PayPal API | Used for |
|---|---|
| OAuth 2.0 client credentials | server-to-server token (cached) |
| Transaction Search (`/v1/reporting/transactions`) + balances | read-only sync; PayPal transaction id = idempotency key, so API syncs and CSV uploads de-duplicate |
| Orders v2 | checkout with `PayPal-Request-Id` idempotency; Pay Later via the buyer's choice on PayPal's page |
| Subscriptions v1 | link, refresh, cancel, suspend, activate (each needs `confirm: true`) |
| Log in with PayPal (OIDC) | optional identity; no feature requires it |

**Provenance of payments.** A capture is written to the `paypal_checkout` account for its environment, never into sample or
imported data. A matching "Planned:" obligation is removed so the purchase isn't counted twice. A data reset keeps checkout
orders as history and marks captured ones `cleared_from_twin`.

**The payment gate.** `POST /checkout/orders` needs `acknowledged: true`; the simulation is re-run server-side and
snapshotted on the order. The buyer approves on PayPal, which redirects to `/checkout/return`. Then
`POST /checkout/orders/{id}/capture` needs `confirm: true`. After capture, a full payment is recorded as a PayPal transaction
(capture id as external id) and Pay Later as one dated obligation per instalment, so the forecast reflects the decision.

**Demo mode.** With no credentials, `PAYPAL_DEMO_MODE=true` serves an in-process stand-in for these endpoints through the same
client code, with FINORA-hosted buyer pages labelled "PayPal demo mode · no real money".

## 4. Security
- Secrets only in server env, never in client code or logs. `check_groq` prints the key length only. Tests force all keys empty.
- Every money-moving step needs an explicit, server-validated confirmation. The agent has no money-moving tool.
- Pydantic validation on every request and tool argument (amount bounds, string lengths, enum'd change types).
- Chat rate limit (`CHAT_RATE_LIMIT_PER_MINUTE`, per client, in-process) protects LLM quota. Security headers on every API
  response (`nosniff`, `DENY` framing, `no-store`). CORS restricted to configured origins.
- PayPal calls use idempotency keys. Order intent is committed before calling PayPal, so failures are recorded, never lost.

## 5. Data model
```
users              id · name · currency · preferences(JSON)
accounts           id · user_id · name · institution · source (format family) · origin (provenance) · environment
                   · opening_balance NUMERIC(14,2) · opening_date
                   origin ∈ sample | user_import | paypal_api | paypal_checkout | unknown; environment ∈ sandbox | live | demo
                   One account per (source, origin, environment): provenance never merges. Columns added by
                   ensure_columns() at startup for older databases (old rows → origin 'unknown').
transactions       id · account_id · posted_on · description · merchant · category · amount NUMERIC(14,2) · source · external_id
                   UNIQUE(account_id, external_id)   INDEX(account_id, posted_on)
fx_details         transaction_id · currency · gross · fee · net · rate · rate_source
obligations        id · user_id · title · category · amount · due_on · notes        (planned payments, Pay Later instalments)
checkout_orders    id · user_id · paypal_order_id · option_id · funding · amount · currency · status · request_id · snapshot(JSON) · capture_id
added_subscriptions / linked_subscriptions / saved_scenarios / demo_paypal_objects
```

## 6. API endpoints

All endpoints are prefixed with `/api`. Interactive docs are at `http://localhost:8000/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/status` | `has_data`, user name, data source, transaction count |
| GET | `/demo-files` · `/demo-files/{id}` | List / download synthetic demo files (`paypal_activity`, `bank_statement`, `transactions`) |
| POST | `/data/import` | Multipart upload: `file`, `format` (`auto`/`paypal_activity`/`bank_statement`/`transactions`), `opening_balance?`, `replace` |
| DELETE | `/data` | Clear all transactions and obligations |
| GET | `/integrations/paypal` | PayPal connection status and PayPal-sourced stats (count, in/out, top payees) |
| POST | `/integrations/paypal/sync` | `{days, replace}`: read-only Transaction Search sync (needs credentials) |
| GET | `/dashboard` | KPIs, health indicators, actual balance history, 90-day forecast, months, categories, upcoming events, recurring items |
| GET | `/twin` | Full financial profile and assumptions |
| GET | `/forecast?horizon_days=&safety_buffer=&variable_spend_multiplier=` | Baseline forecast with custom assumptions |
| GET | `/transactions?search=&category=&direction=in\|out&page=&page_size=` | Paginated transactions |
| GET | `/transactions/categories` | Distinct categories |
| GET / POST | `/obligations` | List / create known future payments |
| DELETE | `/obligations/{id}` | Remove an obligation |
| GET | `/simulations/scenarios` | Scenario catalogue (available / planned) |
| POST | `/simulations/purchase` | `{amount, purchase_date?, label, safety_buffer?}` → baseline vs scenario, 30/60/90-day impact, risks, timing options, recommendation |
| POST | `/simulations/payment-options` | `{amount, label, plans?}` → pay now / wait / Pay Later options, each with a balance series, cost, low point and safe flag, plus a recommendation |
| GET | `/simulations/pay-later-plans` | Default (illustrative) Pay Later terms |
| POST | `/simulations/affordability` | `{amount?, search_days}` → most you can spend today / this month, affordability curve, earliest safe date |
| POST | `/simulations/scenario` | `{changes: [...]}` → composable what-if (`purchase`, `add_subscription`, `cancel_subscriptions`, `income_delay` (optionally one `merchant`), `increase_savings`, `expense_increase`, `unexpected_payment`, `fx_change`) |
| POST | `/simulations/compare` | `{scenarios: [{name, changes}]}` (1–4) → series, end and low balances, buffer check, best pick |
| GET / POST / DELETE | `/simulations/saved` · `/simulations/saved/{id}` | Saved scenarios for comparison |
| GET | `/alerts` · POST `/alerts/dismiss` `{id}` · POST `/alerts/restore` | Proactive alerts |
| GET | `/crossborder` · PUT `/crossborder/reference-rate` `{currency, rate}` | Foreign income, fees, applied rates, FX sensitivity, late-client risk |
| GET | `/stress` | Shock library, Monte Carlo balance bands, runway, chance under buffer, resilience |
| GET / POST | `/paypal-demo/status` · `/paypal-demo/orders/{id}` (`/approve`, `/cancel`) · `/paypal-demo/authorize` | Buyer-side steps of the built-in PayPal demo (404 when real credentials are set) |
| POST | `/checkout/orders` | `{amount, label, option_id, acknowledged: true}` → PayPal order + approval link (simulation re-run server-side and snapshotted) |
| GET | `/checkout/return` · `/checkout/cancel` | PayPal redirect targets → order `approved` / `cancelled` |
| POST | `/checkout/orders/{id}/capture` | `{confirm: true}` → capture. Records a PayPal transaction (pay in full) or one obligation per instalment (Pay Later) |
| POST | `/checkout/plan` | The "wait" option: add the purchase as a planned payment |
| GET | `/subscriptions` | Detected, added and PayPal-linked subscriptions, totals, superseded (now-detected) added entries |
| POST / PUT / DELETE | `/subscriptions/added` · `/subscriptions/added/{id}` | Add, edit or remove a subscription by hand: `{name, amount, next_billing_date}` |
| POST | `/subscriptions/link` · `/{id}/refresh` · `/{id}/cancel\|suspend\|activate` · `/mark` | Subscriptions API actions (each needs `confirm: true`) and manual cancel/restore |
| GET | `/auth/me` · `/auth/paypal/login` · `/auth/paypal/callback` · POST `/auth/logout` | Optional Sign in with PayPal |
| GET / POST | `/assistant/status` · `/assistant/chat` | AI assistant (Groq tool calling + grounding guardrail + trace; deterministic planner without a key) |
| GET / PUT | `/settings` | Read settings / update `name` and/or `safety_buffer` |
| GET | `/evals` | Committed evaluation results (read-only) |
| POST | `/data/sample` | `{file_id, replace}`: load the fictional sample profile, generated server-side, stored as `origin=sample` |
| POST | `/integrations/paypal/check-auth` | Request a PayPal OAuth token now; proves the credentials work, reads nothing |

Money is computed as `Decimal` and serialised as a JSON number with 2 decimal places. The client
only formats values; it never does financial arithmetic.


The assistant's `/assistant/chat` response also includes `provider`, `grounding`, `trace`, `usage` and `latency_ms`.
