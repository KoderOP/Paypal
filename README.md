# FINORA — Personal Financial Digital Twin

> **Don't just track your money. Simulate your financial future.**

FINORA learns your financial behaviour from transactions and builds a continuously updated
*digital twin*: income cycles, recurring commitments, variable spending and upcoming
obligations. You can then project your cash flow day by day and simulate decisions before you
make them. For example: *"What happens if I buy a ₹75,000 laptop this month?"*

Built for the PayPal AI Hackathon. **PayPal is the primary data source.** You can sync through the
read-only PayPal Transaction Search API or upload a PayPal Activity report. Bank statements and plain
transaction files are also supported.

**Scope:** an upload-first onboarding flow with live analysis, the dashboard, the digital twin, a
90-day deterministic forecast, a PayPal hub, and a purchase simulator with timing optimisation. On top of that:

- **Buy now, wait, or split it?** Compares paying in full today, waiting for a safe date and PayPal Pay Later
  instalments, each as its own cash-flow line. It then checks out through the **PayPal Orders API**, with two
  explicit confirmations.
- **Goal solver** works backwards. *"What's the most I can spend this month?"* and *"When's the earliest safe date
  to buy?"* are both answered exactly, not by search.
- **Composable what-ifs:** cancel subscriptions, delayed income, more savings, spending changes, unexpected
  payments. Any combination stacks into one scenario.
- **Subscriptions** are detected from history, **added by hand** (e.g. one you just started), or linked from the
  **PayPal Subscriptions API**. A linked PayPal subscription with no history is projected from PayPal's own price
  and next billing date. Linked ones can be cancelled, suspended or re-activated, and cancelled items drop out of
  every forecast. Once real payments to an added merchant appear, the detected item takes over, so nothing is
  counted twice. *"What if I subscribe?"* can be simulated before adding.
- **AI assistant:** the language model only picks which engine tool to run. A guardrail rejects any rupee figure the
  engine didn't produce. Without an API key, a deterministic parser answers the same questions.
- **Sign in with PayPal** (OpenID Connect) is optional and open to any PayPal account. No feature requires it.
- **Compare scenarios** puts up to four what-ifs on one chart and table (e.g. *cancel subscriptions* vs *laptop on
  payday* vs *both*). The best one is the highest ending balance that never dips below the buffer. Scenarios can be
  saved, including straight from the assistant.
- **Assistant follow-ups:** *"And what if my salary is also late?"* keeps the previous scenario and adds to it.
  *"What about 20 days?"* tweaks it.
- **Cross-border freelancer mode:** multi-currency PayPal reports are converted with PayPal's own conversion rows,
  and each payment keeps its original currency, fee and applied rate. The Cross-border page shows income by client,
  PayPal fees, the average rate PayPal applied, conversion cost against a rate you enter, *"what if USD/INR drops
  3%?"* and *"what if this client pays late?"*. Withdrawals to a bank are treated as transfers, not spending.
- **Proactive alerts** on the dashboard, for example: below-buffer or overdraft ahead, a big bill due just before
  income, a Pay Later instalment due tomorrow, income that's late, or a subscription price increase. Each can be
  dismissed for that occurrence.

---

## Quick start (local, no Docker)

Prerequisites: Python 3.12+ and Node 20+.

```bash
# 1. Backend: http://localhost:8000  (docs at /docs)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. Frontend: http://localhost:5173  (second terminal)
cd frontend
npm install
npm run dev
```

On first start, the backend creates `backend/finora.db` (SQLite) with an **empty** profile. No data is
seeded. The app opens on **Get started**: enter your name, choose PayPal, a bank statement or a
transaction file, then upload your own CSV or click **Use demo file**. FINORA then analyses the data
step by step and builds every section.

The Vite dev server proxies `/api` to the backend, so no URLs or secrets live in frontend code.

Optional: `cp .env.example backend/.env` to override settings.

### With Docker (PostgreSQL)

```bash
docker compose up --build      # db (Postgres 16) + backend + frontend
```

### Tests

```bash
cd backend && .venv/bin/python -m pytest -q    # 105 tests: engine, planning, parsers, PayPal APIs (mocked), assistant, API (clock pinned to 3 Nov 2026)
cd frontend && npx tsc -b && npm run build      # type-check + production build
```

---

## Architecture

```
┌────────────────────────── Frontend (React · TS · Vite · Tailwind · Recharts) ───────────────────────────┐
│ Overview · My Financial Twin · What-if Simulator · Transactions · Settings · (Assistant, Stress: next)  │
└───────────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                                │ JSON over /api
┌───────────────────────────────────────────────▼─────────────────────────────────────────────────────────┐
│ API layer (FastAPI routers, Pydantic validation)          app/api/                                      │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Services: load DB → engine inputs, seeding, imports       app/services/                                 │
├──────────────────────────────┬──────────────────────────────────────────────────────────────────────────┤
│ Engine (PURE, Decimal-only)  │ twin.py        transactions → FinancialProfile                           │
│ app/engine/                  │ forecast.py    profile → daily 90-day projection                         │
│ no DB / network / LLM        │ simulation.py  scenario = event overlay → comparison, timing, risks       │
│                              │ health.py      ratios with explicit thresholds                            │
├──────────────────────────────┴──────────────────────────────────────────────────────────────────────────┤
│ Data layer: SQLAlchemy models + pluggable TransactionSource   app/data/                                 │
│   sources/files.py (PayPal activity · bank statement · transactions) · integrations/paypal (REST API)    │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ AI orchestration (next): LLM ⇄ tool calls ⇄ engine          Payment integration: PayPal sandbox         │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Key decisions

1. **The engine is pure and deterministic.** `app/engine` takes plain Pydantic models and returns
   results. It does no I/O, uses no randomness and never calls an LLM. All money is `Decimal`
   (`app/core/money.py` refuses floats). The same inputs always produce the same output, and a
   test asserts this. The future AI assistant will *call* these functions as tools. It can phrase
   results but cannot invent figures.
2. **Balances are always derived, never stored.** `balance = Σ account.opening_balance + Σ transactions`.
   The synthetic generator back-solves the opening balance so today's balance comes out at exactly
   ₹1,10,000. Every dashboard number traces back to transactions.
3. **Scenarios are event overlays.** A forecast is a list of dated cash events (recurring income
   and bills, obligations, estimated daily variable spend). A scenario adds or removes events and
   is projected by the same engine. New scenario types (salary delay, cancelled subscriptions…)
   only need to produce an overlay.
4. **Timing is judged fairly.** Each candidate purchase date (today plus each expected payday) is
   simulated over the full 90 days *after* that date. A late purchase therefore can't look safe just
   because the window ended.
5. **Assumptions are explicit.** Every forecast and simulation response includes its `assumptions`
   (horizon, safety buffer, look-back window, whether obligations and irregular income are counted),
   so results are reproducible.
6. **Data sources are replaceable, and PayPal comes first.** PayPal API sync, PayPal Activity CSV, bank
   statements and transaction files all normalise into `NormalizedTransaction`, so the engine never
   knows where data came from. PayPal transactions are keyed by PayPal transaction ID, which makes
   API syncs and CSV uploads de-duplicate against each other. Opening balances are inferred from
   balance columns or the PayPal balance API, so balances stay derived from transactions.
7. **SQLite is the zero-setup default and Postgres runs in Docker.** Money columns are
   `NUMERIC(14,2)`. Both databases were verified to give identical results.

### How the twin learns (deterministic rules)

| Signal | Rule |
|---|---|
| Recurring item | Same merchant and direction, ≥3 occurrences, median interval 25–35 days, ≤1 per month, amount spread ≤40%, seen in the last 45 days. Projected amount = median of the last 3. |
| Variable spending | Non-recurring debits. For each category, the median of the last three 30-day windows (robust to one-off spikes). |
| Income | Recurring credits only. Irregular income (e.g. freelance) is excluded from forecasts by default, which is conservative. |
| Savings | `Investments` (SIPs) count as savings, not spending. |

---

## Project structure

```
backend/
  app/
    main.py                 FastAPI app, CORS, startup seeding
    core/                   config (env), database, Decimal money helpers
    data/
      models.py             SQLAlchemy ORM
      categorize.py         rule-based categoriser for imports
      sources/              base protocol · files (3 formats, auto-detect) · synthetic (demo generator)
      demo_files.py         renders synthetic demo files in all 3 formats
    integrations/paypal/    PayPal REST source (OAuth, Transaction Search, balances)
    engine/                 types · twin · forecast · simulation · health
    services/               repository (DB→engine) · seed · import
    schemas/api.py          request/response models
    api/                    dashboard · data (onboarding/import) · paypal · transactions · simulations · settings
  tests/                    engine + API tests
frontend/
  src/
    lib/                    api client, types, INR formatting
    hooks/useApi.ts         loading / error / reload
    components/ui/          Card, StatCard, Badge, States, Segmented, StatusPill…
    components/charts/      CashflowChart, ScenarioChart, MonthlyBars
    components/layout/      responsive sidebar shell
    context/DataStatus.tsx  has-data gate → onboarding
    components/             DataImporter, AnalysisRun, PayPalMark, …
    pages/                  GetStarted, PayPal, Overview, Twin, Simulator, Transactions, Settings, ComingSoon
docker-compose.yml · .env.example
```

## API endpoints

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
| POST | `/checkout/orders` | `{amount, label, option_id, acknowledged: true}` → PayPal order + approval link (simulation re-run server-side and snapshotted) |
| GET | `/checkout/return` · `/checkout/cancel` | PayPal redirect targets → order `approved` / `cancelled` |
| POST | `/checkout/orders/{id}/capture` | `{confirm: true}` → capture. Records a PayPal transaction (pay in full) or one obligation per instalment (Pay Later) |
| POST | `/checkout/plan` | The "wait" option: add the purchase as a planned payment |
| GET | `/subscriptions` | Detected, added and PayPal-linked subscriptions, totals, superseded (now-detected) added entries |
| POST / PUT / DELETE | `/subscriptions/added` · `/subscriptions/added/{id}` | Add, edit or remove a subscription by hand: `{name, amount, next_billing_date}` |
| POST | `/subscriptions/link` · `/{id}/refresh` · `/{id}/cancel\|suspend\|activate` · `/mark` | Subscriptions API actions (each needs `confirm: true`) and manual cancel/restore |
| GET | `/auth/me` · `/auth/paypal/login` · `/auth/paypal/callback` · POST `/auth/logout` | Optional Sign in with PayPal |
| GET / POST | `/assistant/status` · `/assistant/chat` | AI assistant (tool calling + figure guardrail; rule-based without a key) |
| GET / PUT | `/settings` | Read settings / update `name` and/or `safety_buffer` |

Money is computed as `Decimal` and serialised as a JSON number with 2 decimal places. The client
only formats values; it never does financial arithmetic.

## Database schema

```
users          id · name · currency · preferences(JSON: data_source, safety_buffer) · created_at
accounts       id · user_id→users · name · institution · account_type · currency
               · opening_balance NUMERIC(14,2) · opening_date · source(paypal|bank_statement|csv)
transactions   id · account_id→accounts · posted_on · description · merchant · category
               · amount NUMERIC(14,2) (signed: +credit / −debit) · source · external_id · created_at
               UNIQUE(account_id, external_id)  — idempotent imports
               INDEX(account_id, posted_on)
obligations    id · user_id→users · title · category · amount NUMERIC(14,2) · due_on · notes
```

Tables are created on startup (`create_all`). Alembic migrations are a next-milestone item.

## Demo files (synthetic data)

Nothing is seeded. Demo files are generated on request (`GET /api/demo-files/{id}`) relative to today,
and the UI labels them clearly as synthetic. There is one dataset in three real-world formats:

| File | Layout |
|---|---|
| `finora-demo-paypal-activity.csv` | PayPal Activity report: Date, Time, TimeZone, Name, Type, Status, Currency, Gross, Fee, Net, Transaction ID, Balance |
| `finora-demo-bank-statement.csv` | Indian bank statement: Date, Narration, Chq./Ref.No., Value Dt, Withdrawal Amt., Deposit Amt., Closing Balance |
| `finora-demo-transactions.csv` | date, description, amount, category, merchant (the UI pre-fills the opening balance) |

The dataset covers six months:
- Salary ₹65,000/month, with the next credit always 12 days away.
- Rent ₹12,000, utilities ~₹3,000, six subscriptions totalling ₹2,500, and a ₹10,000 SIP.
- Variable spending of about ₹18k/month, plus a few one-offs.

Every format reconciles to a **₹1,10,000** current balance, and a test checks this.

**Demo storyline:** upload the PayPal demo file and watch the analysis. Then open the simulator.
Buying a ₹75,000 laptop *today* drops the projected balance to about ₹13,800 before payday, so
FINORA recommends **waiting 12 days for the salary**.

## Known limitations

- **Single data profile.** Sign in with PayPal is optional and identifies who is using the app, but
  everyone shares one financial profile. Per-user data (multi-tenancy) isn't built.
- **PayPal API features are covered by mocked-HTTP tests but not yet verified against a live sandbox
  account.** This covers Transaction Search, Orders, Subscriptions and Log in with PayPal. Activity report
  upload works fully.
- **Pay Later terms are illustrative inputs.** PayPal has no public API that returns a buyer's Pay Later
  offer, so eligibility, APR and the final schedule are decided by PayPal at checkout (the buyer picks Pay
  Later on PayPal's page). Pay Later isn't offered in every country or currency, including INR.
- **Subscriptions API limits.** PayPal lets only the *merchant's* REST app cancel a subscription through
  the API. For other merchants, FINORA links you to PayPal → Automatic payments and lets you mark the item
  cancelled.
- **Cross-border:** only foreign *income* is converted (payments received). FINORA never fetches market rates, so
  conversion cost appears only if you enter a reference rate. The freelancer demo's fees and rates are illustrative,
  not PayPal's pricing. Uploading a PayPal report *and* the bank statement it withdraws to works, because
  withdrawals are treated as transfers. A bank-side "PayPal" credit is only recognised as a transfer if its
  narration matches the transfer keywords.
- **The assistant's rule-based mode** understands the core what-if questions, not free-form chat. Add
  `OPENAI_API_KEY` for that. The Stress Testing page is still a placeholder.
- Forecasting only detects monthly recurrence (weekly or annual items count as variable spend). It
  produces a single deterministic path with no confidence bands, and irregular income is excluded.
- `as_of` is always today. A file whose history ended long ago will detect few active recurring items.
- Uploading two files that describe the same money (e.g. a bank statement and a PayPal report of the
  same account) double-counts it. The UI defaults to "replace existing data" for this reason.
- No DB migrations (`create_all` only). Light mode only.
- Charts can't be operated by keyboard yet; tooltips are hover-based. A table view exists on the
  Twin page.

## Next recommended milestones

1. **More scenarios plus side-by-side comparison**: cancel subscriptions, salary delay, +10%
   savings, unexpected payment, +20% expenses. Add `POST /simulations/compare`.
2. **AI Financial Assistant**: OpenAI tool calling (`get_profile`, `forecast`, `simulate_*`) with
   structured outputs. Answers cite the engine's figures, and a guardrail rejects numbers that
   don't come from tool results.
3. **Stress testing**: a shock library and resilience indicators (runway, liquidity risk, deficit
   probability through simple Monte Carlo on variable spend), all labelled as estimates.
4. **PayPal**: verify the live sandbox sync, add scheduled re-syncs, and offer a "pay with PayPal after
   simulation" flow that always requires an explicit confirmation step.
5. **Platform**: auth, Alembic migrations, saved scenarios, dark mode, CI.
