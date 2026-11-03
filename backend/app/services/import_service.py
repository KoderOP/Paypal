from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.data.models import Account, Obligation, Transaction, User
from app.data.sources.base import NormalizedTransaction

ACCOUNT_NAMES = {"paypal": "PayPal account", "bank_statement": "Bank account", "csv": "Imported transactions"}


def has_data(db: Session, user: User) -> bool:
    return bool(db.scalar(select(func.count(Transaction.id)).join(Account).where(Account.user_id == user.id)))


def clear_user_data(db: Session, user: User) -> None:
    ids = select(Account.id).where(Account.user_id == user.id)
    db.execute(delete(Transaction).where(Transaction.account_id.in_(ids)))
    db.execute(delete(Account).where(Account.user_id == user.id))
    db.execute(delete(Obligation).where(Obligation.user_id == user.id))
    prefs = dict(user.preferences or {})
    prefs.pop("data_source", None)
    user.preferences = prefs


def store_transactions(db: Session, user: User, source_name: str, txns: list[NormalizedTransaction],
                       opening_balance: Decimal | None, replace: bool, data_label: str) -> dict:
    if replace:
        clear_user_data(db, user)
    had_data = has_data(db, user)
    account = db.scalars(select(Account).where(Account.user_id == user.id, Account.source == source_name)).first()
    if account is None:
        account = Account(user_id=user.id, name=ACCOUNT_NAMES.get(source_name, "Imported"), institution=source_name,
                          opening_balance=opening_balance or Decimal("0"),
                          opening_date=min(t.posted_on for t in txns) - timedelta(days=1), source=source_name)
        db.add(account)
        db.flush()

    existing = set(db.scalars(select(Transaction.external_id).where(Transaction.account_id == account.id)).all())
    new = [t for t in txns if t.external_id not in existing]
    db.add_all(
        Transaction(account_id=account.id, posted_on=t.posted_on, description=t.description, merchant=t.merchant,
                    category=t.category, amount=t.amount, source=source_name, external_id=t.external_id)
        for t in new
    )
    prefs = dict(user.preferences or {})
    prefs["data_source"] = data_label if not had_data or prefs.get("data_source") in (None, data_label) else "mixed"
    user.preferences = prefs
    db.commit()
    return {"rows": len(txns), "imported": len(new), "skipped_duplicates": len(txns) - len(new),
            "account_id": account.id, "opening_balance": account.opening_balance}
