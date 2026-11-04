"""Loads persisted data and adapts it into pure engine inputs."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.money import ZERO, money
from app.data.models import AddedSubscription, Account, LinkedSubscription, Obligation, Transaction, User
from app.engine.twin import FinancialProfile, RecurringItem, build_profile, with_added, without_cancelled
from app.engine.types import Assumptions, ObligationIn, Txn


def today() -> date:
    return date.today()


def get_primary_user(db: Session) -> User:
    from app.services.seed import ensure_user

    return ensure_user(db)


NO_DATA = {"code": "no_data", "message": "No financial data yet. Connect PayPal or upload a statement to build your twin."}


def load_transactions(db: Session, user: User) -> list[Txn]:
    rows = db.scalars(
        select(Transaction).join(Account).where(Account.user_id == user.id).order_by(Transaction.posted_on, Transaction.id)
    ).all()
    return [Txn(posted_on=r.posted_on, description=r.description, merchant=r.merchant, category=r.category, amount=r.amount) for r in rows]


def opening_total(db: Session, user: User) -> Decimal:
    return money(db.scalar(select(func.coalesce(func.sum(Account.opening_balance), 0)).where(Account.user_id == user.id)) or 0)


def current_balance(db: Session, user: User) -> Decimal:
    """Balance is always derived: Σ opening balances + Σ transactions."""
    txn_sum = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).join(Account).where(Account.user_id == user.id)
    )
    return money(opening_total(db, user) + Decimal(str(txn_sum or 0)))


def load_obligations(db: Session, user: User) -> list[ObligationIn]:
    rows = db.scalars(select(Obligation).where(Obligation.user_id == user.id).order_by(Obligation.due_on)).all()
    return [ObligationIn(title=o.title, category=o.category, amount=o.amount, due_on=o.due_on) for o in rows]


def assumptions_for(user: User, **overrides) -> Assumptions:
    prefs = user.preferences or {}
    base = {
        "horizon_days": get_settings().forecast_horizon_days,
        "safety_buffer": Decimal(str(prefs.get("safety_buffer", get_settings().default_safety_buffer))),
    }
    base.update({k: v for k, v in overrides.items() if v is not None})
    return Assumptions(**base)


def cancelled_keys(user: User) -> set[str]:
    """Recurring items the user cancelled (through the PayPal Subscriptions API or marked manually)."""
    return set(((user.preferences or {}).get("cancelled_recurring") or {}).keys())


def set_cancelled(user: User, key: str, info: dict | None) -> None:
    prefs = dict(user.preferences or {})
    cancelled = dict(prefs.get("cancelled_recurring") or {})
    if info is None:
        cancelled.pop(key, None)
    else:
        cancelled[key] = info
    prefs["cancelled_recurring"] = cancelled
    user.preferences = prefs


def added_key(sub: AddedSubscription) -> str:
    return f"manual:{sub.id}"


def paypal_key(sub: LinkedSubscription) -> str:
    return f"paypal:{sub.paypal_subscription_id}"


def added_items(db: Session, user: User) -> list[RecurringItem]:
    """Subscriptions not learned from history: added by hand, or linked from PayPal without a match."""
    items: list[RecurringItem] = []
    for s in db.scalars(select(AddedSubscription).where(AddedSubscription.user_id == user.id)).all():
        items.append(RecurringItem(
            key=added_key(s), name=s.name, merchant=s.name, category=s.category, kind="subscription", direction="out",
            amount=money(s.amount), day_of_month=s.next_billing_date.day, occurrences=0, last_date=None,
            next_date=s.next_billing_date, source="manual"))
    linked = db.scalars(select(LinkedSubscription).where(LinkedSubscription.user_id == user.id,
                                                         LinkedSubscription.recurring_key.is_(None))).all()
    for s in linked:
        # Only project what PayPal told us, in the profile currency; never guess a price or a date.
        if s.amount is None or s.next_billing_date is None or (s.currency and s.currency != user.currency):
            continue
        items.append(RecurringItem(
            key=paypal_key(s), name=s.name, merchant=s.name, category="Subscriptions", kind="subscription",
            direction="out", amount=money(s.amount), day_of_month=s.next_billing_date.day, occurrences=0,
            last_date=None, next_date=s.next_billing_date, source="paypal"))
    return items


def build_user_profile(db: Session, user: User, a: Assumptions, as_of: date | None = None,
                       include_cancelled: bool = False) -> FinancialProfile:
    txns = load_transactions(db, user)
    if not txns:
        raise HTTPException(status_code=404, detail=NO_DATA)
    profile = build_profile(txns, current_balance(db, user), as_of or today(), load_obligations(db, user), a)
    profile = with_added(profile, added_items(db, user))
    return profile if include_cancelled else without_cancelled(profile, cancelled_keys(user))


def balance_history(db: Session, user: User, txns: list[Txn], as_of: date) -> list[dict]:
    """Actual end-of-day balances reconstructed from transactions (history up to yesterday)."""
    if not txns:
        return []
    by_day: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for t in txns:
        by_day[t.posted_on] += t.amount
    balance = opening_total(db, user)
    d, end = txns[0].posted_on, max(as_of - timedelta(days=1), txns[-1].posted_on)
    out = []
    while d <= end:
        balance += by_day.get(d, ZERO)
        out.append({"on": d, "balance": money(balance)})
        d += timedelta(days=1)
    return out
