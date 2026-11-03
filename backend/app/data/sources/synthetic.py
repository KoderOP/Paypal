"""Deterministic synthetic Indian financial history (INR).

Profile: salaried professional, ₹65,000/month salary, ~₹36,000 monthly spending and a
₹10,000 monthly SIP. Six months of transaction-level history are generated relative to
`today`; the next salary always lands 12 days after `today`.

The opening balance is *back-solved* so that opening + Σ transactions == the target
current balance (₹1,10,000). Every dashboard figure is then derived from transactions.
"""
import calendar
import random
from datetime import date, timedelta
from decimal import Decimal

from app.core.money import money
from app.data.sources.base import NormalizedTransaction

TARGET_CURRENT_BALANCE = Decimal("110000.00")
HISTORY_DAYS = 183
SALARY = Decimal("65000")
SALARY_LEAD_DAYS = 12

# (day_of_month, description, merchant, category, amount or (low, high) range)
FIXED_MONTHLY: list[tuple[int, str, str, str, int | tuple[int, int]]] = [
    (1, "Rent transfer via UPI", "Landlord - Mr. Sharma", "Rent", 12000),
    (3, "Cult.fit membership", "Cult.fit", "Subscriptions", 985),
    (5, "SIP - Index Fund Direct Growth", "Groww Mutual Fund", "Investments", 10000),
    (7, "Netflix subscription", "Netflix", "Subscriptions", 649),
    (8, "BESCOM electricity bill", "BESCOM", "Utilities", (1350, 1900)),
    (10, "Airtel postpaid bill", "Airtel", "Utilities", 599),
    (12, "Spotify Premium", "Spotify", "Subscriptions", 119),
    (14, "Salon & grooming", "Urban Company", "Personal Care", (600, 1200)),
    (18, "ACT Fibernet broadband", "ACT Fibernet", "Utilities", 799),
    (20, "Amazon Prime membership", "Amazon Prime", "Subscriptions", 299),
    (22, "YouTube Premium", "YouTube Premium", "Subscriptions", 149),
    (25, "JioHotstar subscription", "JioHotstar", "Subscriptions", 299),
]

# (probability per day or weekday filter, description, merchant, category, (low, high))
VARIABLE: list[tuple[float, int | None, str, str, str, tuple[int, int]]] = [
    (1.00, 5, "Weekly groceries", "BigBasket", "Groceries", (700, 1000)),
    (0.12, None, "Quick commerce order", "Blinkit", "Groceries", (150, 400)),
    (0.20, None, "Food order", "Swiggy", "Food Delivery", (180, 420)),
    (0.35, None, "Cab ride", "Uber", "Transport", (120, 380)),
    (0.06, None, "Online shopping", "Amazon", "Shopping", (400, 2200)),
    (0.30, 6, "Movie tickets", "BookMyShow", "Entertainment", (300, 900)),
    (0.05, None, "Pharmacy purchase", "Apollo Pharmacy", "Health", (150, 700)),
    (0.35, 4, "Dinner with friends", "Social Restaurant", "Dining Out", (500, 1200)),
    (0.10, None, "UPI payment", "Local merchant (UPI)", "Other", (100, 600)),
]
FUEL_DAYS = (4, 19)


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def next_salary_date(today: date) -> date:
    return today + timedelta(days=SALARY_LEAD_DAYS)


class SyntheticSource:
    name = "synthetic"

    def __init__(self, today: date, seed: int = 42):
        self.today = today
        self.seed = seed
        self.start = today - timedelta(days=HISTORY_DAYS)

    def fetch(self) -> list[NormalizedTransaction]:
        rng = random.Random(self.seed)
        txns: list[NormalizedTransaction] = []
        seq = 0

        def add(d: date, desc: str, merchant: str, category: str, amount: Decimal) -> None:
            nonlocal seq
            seq += 1
            txns.append(NormalizedTransaction(f"syn-{d.isoformat()}-{seq:05d}", d, desc, merchant, category, money(amount)))

        # Salary credits on the same day-of-month as the upcoming salary.
        upcoming = next_salary_date(self.today)
        for k in range(1, 8):
            pay_day = _add_months(upcoming, -k)
            if self.start <= pay_day < self.today:
                add(pay_day, "Salary credit - Acme Technologies Pvt Ltd", "Acme Technologies", "Income", SALARY)

        d = self.start
        while d < self.today:  # history up to yesterday; forecasting starts today
            for day, desc, merchant, cat, amt in FIXED_MONTHLY:
                if d.day == day:
                    value = amt if isinstance(amt, int) else rng.randint(*amt)
                    add(d, desc, merchant, cat, -Decimal(value))
            if d.day in FUEL_DAYS:
                add(d, "Fuel - HP Petrol Pump", "HP Petrol", "Transport", -Decimal(rng.randint(600, 800)))
            for prob, weekday, desc, merchant, cat, (lo, hi) in VARIABLE:
                if weekday is not None and d.weekday() != weekday:
                    continue
                if rng.random() < prob:
                    add(d, desc, merchant, cat, -Decimal(rng.randint(lo, hi)))
            d += timedelta(days=1)

        # A few realistic one-offs so the history is not perfectly regular.
        one_offs = [
            (150, "Flight tickets - Goa trip", "IndiGo", "Travel", Decimal("-9800")),
            (95, "Freelance project payment", "Upwork", "Other Income", Decimal("8000")),
            (61, "Dental treatment", "Clove Dental", "Health", Decimal("-6500")),
            (33, "Smartphone accessories", "Croma", "Shopping", Decimal("-3499")),
        ]
        for days_ago, desc, merchant, cat, amt in one_offs:
            add(self.today - timedelta(days=days_ago), desc, merchant, cat, amt)

        txns.sort(key=lambda t: (t.posted_on, t.external_id))
        return txns

    def opening_balance(self, txns: list[NormalizedTransaction]) -> Decimal:
        net = sum((t.amount for t in txns), Decimal("0"))
        return money(TARGET_CURRENT_BALANCE - net)

    def obligations(self) -> list[dict]:
        return [
            {"title": "Friend's wedding - gift", "category": "Personal", "amount": Decimal("6000"),
             "due_on": self.today + timedelta(days=26), "notes": "Planned"},
            {"title": "Car insurance renewal", "category": "Insurance", "amount": Decimal("18500"),
             "due_on": self.today + timedelta(days=75), "notes": "Annual premium"},
        ]
