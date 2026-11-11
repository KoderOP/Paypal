"""Walk-forward backtest of the cash-flow twin against simple baselines.

    python -m evals.forecast_backtest                       # synthetic histories (default 30 seeds)
    python -m evals.forecast_backtest --file my_paypal.csv  # your own PayPal / bank export

Protocol. For each history and each cut-off date, the model sees only transactions BEFORE the
cut-off, forecasts the next 30 days, and is scored against what actually happened.

Forecasters
  twin            FINORA's engine (build_profile → forecast_baseline), unmodified.
  flat            balance stays where it is.
  linear_drift    average daily net flow of the last 90 days, applied every day.
  seasonal_naive  replays the daily net flows of the last 30 days (a strong baseline for monthly
                  cash-flow patterns).

Metrics
  path_mae        mean absolute error of the daily balance over the 30 days (₹), also shown as a
                  share of monthly income so different histories are comparable.
  low_point_mae   error in the lowest balance over the 30 days: the number the product's
                  "is it safe?" answers depend on.
  decision        for purchase sizes from 10% to 150% of monthly income, made on the cut-off day:
                  is the balance predicted to stay above the ₹20,000 buffer? We report accuracy
                  and the FALSE-SAFE rate (predicted safe, actually breached), the costly error.

Data. Synthetic histories come from the same generator as the demo file, with two conditions:
  clean      the generator as-is (regular salary, fixed bills): favours any model that finds
             monthly structure, so treat it as an upper bound.
  perturbed  income dates jittered by −3..+4 days, 10% of bills skipped, random one-off expenses
             (~2% of days, ₹2k–15k), and variable spend scaled ±25% per month.
Results on synthetic data are NOT evidence about real users. Run --file on a real export for that.
"""
import argparse
import json
import random
import statistics
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from evals.common import RESULTS, run_info

HORIZON = 30
BUFFER = Decimal("20000")
SIZES = [Decimal(x) / 10 for x in range(1, 16)]  # purchase = 10% … 150% of monthly income


def _to_txns(normalized):
    from app.engine.types import Txn
    return [Txn(posted_on=t.posted_on, description=t.description, merchant=t.merchant, category=t.category,
                amount=t.amount) for t in normalized]


def perturb(txns, seed: int, today: date):
    rng = random.Random(f"perturb-{seed}")
    out = []
    month_scale: dict[tuple[int, int], float] = {}
    for t in txns:
        if t.category in ("Income",):
            t = replace(t, posted_on=t.posted_on + timedelta(days=rng.randint(-3, 4)))
        elif t.category in ("Subscriptions", "Utilities") and rng.random() < 0.10:
            continue
        elif t.amount < 0 and t.category not in ("Rent", "Investments", "Subscriptions", "Utilities"):
            k = (t.posted_on.year, t.posted_on.month)
            month_scale.setdefault(k, rng.uniform(0.75, 1.25))
            t = replace(t, amount=(t.amount * Decimal(str(round(month_scale[k], 3)))).quantize(Decimal("0.01")))
        if t.posted_on < today:
            out.append(t)
    start = min(t.posted_on for t in txns)
    d, n = start, 0
    while d < today:
        if rng.random() < 0.02:
            n += 1
            out.append(replace(txns[0], external_id=f"oneoff-{seed}-{n}", posted_on=d, description="One-off expense",
                               merchant=f"One-off {n}", category="Shopping", amount=-Decimal(rng.randint(2000, 15000))))
        d += timedelta(days=1)
    return sorted(out, key=lambda t: (t.posted_on, t.external_id))


def actual_path(txns, start_balance: Decimal, cutoff: date) -> list[Decimal]:
    by_day: dict[date, Decimal] = {}
    for t in txns:
        by_day[t.posted_on] = by_day.get(t.posted_on, Decimal(0)) + t.amount
    bal, out = start_balance, []
    for i in range(HORIZON + 1):
        bal += by_day.get(cutoff + timedelta(days=i), Decimal(0))
        out.append(bal)
    return out


def forecasts(history, balance: Decimal, cutoff: date) -> tuple[dict[str, list[Decimal]], Decimal]:
    from app.engine.forecast import forecast_baseline
    from app.engine.twin import build_profile
    from app.engine.types import Assumptions

    a = Assumptions(horizon_days=HORIZON, safety_buffer=BUFFER)
    profile = build_profile(history, balance, cutoff, None, a)
    twin = [p.balance for p in forecast_baseline(profile, a).points]

    def net_by_day(days: int) -> list[Decimal]:
        out = []
        for k in range(days, 0, -1):
            d = cutoff - timedelta(days=k)
            out.append(sum((t.amount for t in history if t.posted_on == d), Decimal(0)))
        return out

    last90 = net_by_day(90)
    drift = sum(last90, Decimal(0)) / 90
    last30 = net_by_day(30)
    seasonal, bal = [], balance
    for i in range(HORIZON + 1):
        bal += last30[i % 30]
        seasonal.append(bal)
    return ({"twin": twin, "flat": [balance] * (HORIZON + 1),
             "linear_drift": [balance + drift * (i + 1) for i in range(HORIZON + 1)],
             "seasonal_naive": seasonal}, profile.monthly_income or Decimal(1))


def score(pred: list[Decimal], act: list[Decimal], income: Decimal) -> dict:
    path_mae = sum(abs(p - a) for p, a in zip(pred, act)) / len(act)
    low_err = abs(min(pred) - min(act))
    correct = false_safe = actually_unsafe = 0
    for s in SIZES:
        amt = income * s
        p_safe, a_safe = min(pred) - amt >= BUFFER, min(act) - amt >= BUFFER
        correct += p_safe == a_safe
        false_safe += p_safe and not a_safe
        actually_unsafe += not a_safe
    return {"path_mae": float(path_mae), "path_mae_pct_income": float(path_mae / income * 100),
            "low_point_mae": float(low_err), "decisions": len(SIZES), "correct": correct, "false_safe": false_safe,
            "actually_unsafe": actually_unsafe}


def backtest_history(txns, opening: Decimal, cutoffs: list[date], label: str) -> list[dict]:
    rows = []
    for c in cutoffs:
        history = [t for t in txns if t.posted_on < c]
        future = [t for t in txns if c <= t.posted_on <= c + timedelta(days=HORIZON)]
        if len(history) < 30:
            continue
        balance = opening + sum((t.amount for t in history), Decimal(0))
        act = actual_path(future, balance, c)
        preds, income = forecasts(history, balance, c)
        for name, pred in preds.items():
            rows.append({"history": label, "cutoff": c.isoformat(), "model": name, **score(pred, act, income)})
    return rows


def aggregate(rows: list[dict]) -> dict:
    out = {}
    for m in sorted({r["model"] for r in rows}):
        rs = [r for r in rows if r["model"] == m]
        dec = sum(r["decisions"] for r in rs)
        unsafe = sum(r["actually_unsafe"] for r in rs)
        out[m] = {"n_forecasts": len(rs),
                  "path_mae": round(statistics.mean(r["path_mae"] for r in rs)),
                  "path_mae_pct_income": round(statistics.mean(r["path_mae_pct_income"] for r in rs), 2),
                  "low_point_mae": round(statistics.mean(r["low_point_mae"] for r in rs)),
                  "decision_accuracy": round(sum(r["correct"] for r in rs) / dec, 4),
                  "false_safe_rate": round(sum(r["false_safe"] for r in rs) / dec, 4),
                  "false_safe_share_of_unsafe": round(sum(r["false_safe"] for r in rs) / unsafe, 4) if unsafe else None}
    return out


def synthetic(seeds: int) -> dict:
    from app.data.sources.synthetic import SyntheticSource

    today = date(2026, 11, 3)
    results = {}
    for condition in ("clean", "perturbed"):
        rows = []
        for persona in ("salaried", "freelancer"):
            for seed in range(1, seeds + 1):
                src = SyntheticSource(today, seed, persona)
                norm = src.fetch()
                if condition == "perturbed":
                    norm = perturb(norm, seed, today)
                opening = Decimal(0)
                start = min(t.posted_on for t in norm)
                cutoffs = [start + timedelta(days=d) for d in (95, 110, 125, 140, 152)]
                rows += backtest_history(_to_txns(norm), opening, cutoffs, f"{persona}-{seed}")
        results[condition] = {"aggregate": aggregate(rows), "n_histories": seeds * 2, "cutoffs_per_history": 5}
    return results


def from_file(path: Path) -> dict:
    from app.data.sources.files import parse_file

    parsed = parse_file(path.read_text(encoding="utf-8-sig"), "auto")
    norm = parsed.transactions
    start, end = min(t.posted_on for t in norm), max(t.posted_on for t in norm)
    cutoffs, c = [], start + timedelta(days=90)
    while c + timedelta(days=HORIZON) <= end:
        cutoffs.append(c)
        c += timedelta(days=14)
    if not cutoffs:
        raise SystemExit("Need at least 120 days of history for a 90-day lookback + 30-day horizon.")
    rows = backtest_history(_to_txns(norm), parsed.opening_balance or Decimal(0), cutoffs, path.name)
    return {"file": {"aggregate": aggregate(rows), "cutoffs": len(cutoffs), "format": parsed.format}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--file", type=Path)
    args = ap.parse_args()
    res = from_file(args.file) if args.file else synthetic(args.seeds)
    out = {"benchmark": "forecast_backtest", **run_info(), "horizon_days": HORIZON, "buffer": float(BUFFER),
           "purchase_sizes_pct_income": [float(s * 100) for s in SIZES], "results": res}
    if not args.file:  # never overwrite the committed synthetic report with someone's private file
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / "forecast_backtest.json").write_text(json.dumps(out, indent=2))
    for cond, r in res.items():
        print(f"\n== {cond} ==")
        print(f"{'model':<16}{'path MAE':>12}{'% income':>10}{'low-pt MAE':>12}{'decision acc':>14}{'false-safe':>12}")
        for m, a in r["aggregate"].items():
            print(f"{m:<16}{a['path_mae']:>12,}{a['path_mae_pct_income']:>9}%{a['low_point_mae']:>12,}"
                  f"{a['decision_accuracy']:>13.1%}{a['false_safe_rate']:>12.1%}")


if __name__ == "__main__":
    main()
