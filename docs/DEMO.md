# FINORA demo script (about 4 minutes)

**Before you start**
- Start the backend and frontend (README). For live AI add `GROQ_API_KEY` and run `python -m evals.check_groq`. Without a key,
  the deterministic planner answers and the badge says so.
- For real PayPal Sandbox: set the sandbox credentials plus `PAYPAL_CHECKOUT_CURRENCY=USD` and `PAYPAL_CHECKOUT_FX_RATE=84`,
  create a **US-registered** sandbox *Personal* buyer account (India-registered buyer accounts are refused by PayPal), and
  run the checkout once beforehand. Open the PayPal approval in a private window if the browser remembers another login.
- Without PayPal credentials, checkout runs in **PayPal demo mode**: a labelled simulation where PayPal is never contacted.

**One rule for the whole demo: never imply the transactions are real.** The amber *Sample data* strip stays on every page
while the fictional profile is loaded. Say it out loud at the start.

| Time | Do | Say |
|---|---|---|
| 0:00 | Open http://localhost:5173 (landing) | "FINORA works at the moment of decision: it checks a payment against your future cash flow before you pay, then drafts a PayPal checkout that only you can confirm." |
| 0:20 | Point at the **Sample data** box, then click **Launch the live demo** | "This is a **fictional profile**: about 285 synthetic transactions we generated, in PayPal's Activity-report format. None of it is a real customer and none of it came from PayPal. We use synthetic data so anyone can run the demo without sharing financial data, and so the result is reproducible. Real users would sync PayPal's Transaction Search API or upload their own export. Every row is labelled with its source." |
| 0:45 | Agent answers *"Should I buy a ₹75,000 laptop?"* | "FINORA processed the transactions into a model: income cycles, recurring bills, variable spend, then a day-by-day 90-day projection. Paying in full today drops below the ₹20,000 safety buffer before payday. Waiting is safe. PayPal Pay in 4 is safe and gets the laptop today. The Pay in 4 terms are **illustrative**: PayPal decides eligibility and terms at checkout." |
| 1:15 | Expand **How this answer was produced** | "Two different jobs. The **engine is deterministic**: same data, same numbers, Decimal money, no randomness, fully tested, because financial figures must be reproducible and auditable. **Groq is the agent**: it understands the question, picks which engine tool to call and with what arguments, and writes the answer. It never computes. Then a **guardrail** checks every amount, percentage and date in Groq's draft against the tool results. If anything isn't from the engine, the draft is replaced and the answer says so." |
| 1:50 | Click **Go ahead with PayPal Pay in 4** (or *Pay in full now* on Sandbox) | "The agent's strongest action is a **proposal**. There's no tool that can move money. Nothing has been created at PayPal yet." |
| 2:05 | Tick **I've reviewed the simulated impact** (and the extra risk box if shown) → **Continue to PayPal** | "**Confirmation 1**, enforced on the server. Only now does FINORA call PayPal's **Orders API**. On Sandbox, ₹75,000 is charged as USD 892.86 at the rate we configured. FINORA never invents an exchange rate." |
| 2:25 | Approve on `sandbox.paypal.com` with the US buyer account (or the labelled demo page) | "**Confirmation 2**: the buyer approves on PayPal itself." |
| 2:45 | On FINORA's page, click **Confirm and pay** | "**Confirmation 3**: only this captures the money. Capturing the same order twice does nothing the second time." |
| 3:00 | Open **PayPal Hub** → *What's connected, and what's real* | "This is the honest status: API authentication (test it live), the Transaction Search result, how many records actually came from PayPal (zero from the sample!), the sample count, and each checkout with its state and real PayPal order and capture IDs." |
| 3:25 | Open **Transactions**, filter by source | "The Sandbox capture sits in its own labelled account, never mixed into the sample ledger. The balance reconciles: opening balances plus every transaction." |
| 3:40 | Open **Evaluation** | "We measured it. In a backtest on **synthetic** histories, the forecast got 95% of purchase-safety calls right vs 92.6% for a seasonal baseline. That validates the method, **not real-user accuracy**. The guardrail caught 97.7% of corrupted answers with no false rejections, and the live Groq benchmark is there with its fallback and rewrite rates. One command reproduces all of it." |

**If asked "is this real PayPal data?"** No. It's fictional sample data in PayPal's format, labelled on every page. What *is*
real: Sandbox OAuth, Orders API create/approve/capture, and (when the app has the permission) Transaction Search, all shown
with their status in the PayPal Hub.

**If asked "can the AI make up numbers?"** Show a trace and the red-team table. It can draft them, but the guardrail
rejects any figure the engine didn't produce, and the response says when that happened.

**If asked about Pay Later:** FINORA simulates Pay in 4 / Pay Monthly from illustrative terms to compare options. Real
eligibility, APR and schedule are PayPal's decision on its approval page. FINORA records the simulated schedule and
labels it as such.
