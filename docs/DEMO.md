# FINORA: 3-minute demo script

**Setup (once):** start the backend and frontend (see README). Optional: add `GROQ_API_KEY` to `backend/.env` and run
`python -m evals.check_groq`. Without it, everything still works through the deterministic planner, and the badge says so.
To start fresh between runs: Settings → clear data, or delete `backend/finora.db`.

| Time | Do | Say |
|---|---|---|
| 0:00 | Open http://localhost:5173 (landing) | "Finance apps show what you already spent. FINORA works before you pay: it checks a payment against your future cash flow and drafts the PayPal checkout. Only you can send it." Point at the decision receipt. |
| 0:20 | Click **Launch the live demo** | "This loads six months of synthetic PayPal activity, the same format as a PayPal Activity export. The twin learns salary, bills and variable spend." |
| 0:35 | The agent answers *"Should I buy a ₹75,000 laptop?"* | "Paying in full drops me below my ₹20,000 buffer before payday. Waiting is safe. PayPal Pay in 4 is safe **and** I get it today, so that's the pick." Scroll the chart and option cards. |
| 1:05 | Open **How this answer was produced** | "The model only chose the tool. The engine computed every number, and the guardrail checked each figure. If the model had made one up, it would have been replaced and flagged." |
| 1:25 | Click **Go ahead with PayPal Pay in 4** | "The agent's only action is a proposal. Nothing is charged. Here's the instalment schedule and my lowest projected balance." |
| 1:45 | Tick the box → **Continue to PayPal** → choose **Pay Later** → **Confirm and pay** | "Three human steps, each enforced server-side: acknowledge, approve on PayPal, confirm the capture. With sandbox keys this is the real Orders API; here it's the labelled demo mode." |
| 2:15 | Open **Overview** | "The four instalments are now in the forecast. The decision updated the twin." |
| 2:30 | Ask *"And what if my salary is also 10 days late?"* | "Follow-ups build on the previous scenario." |
| 2:45 | Open **Evaluation** | "We measured it: 95% correct purchase-safety calls on noisy histories vs 92.6% for a seasonal baseline, and 97.7% of corrupted answers caught with zero false rejections. All reproducible with one command." |

**If asked "is the AI making up numbers?"** Show a trace and the red-team table. The architecture makes that impossible to
pass silently.
**If asked "what's real PayPal?"** Transaction Search, Orders v2 (with idempotency keys), Pay Later via buyer choice,
Subscriptions v1 and Log in with PayPal, all through one client. Demo mode is an in-process stand-in for those endpoints,
labelled everywhere.
