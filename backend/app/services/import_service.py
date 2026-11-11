from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.data.models import Account, CheckoutOrder, FxDetail, Obligation, Transaction, User
from app.data.sources.base import NormalizedTransaction

ORIGINS = ("sample", "user_import", "paypal_api", "paypal_checkout", "unknown")
FORMAT_NAMES = {"paypal": "PayPal Activity format", "bank_statement": "bank statement format", "csv": "transaction file"}


def account_name(source: str, origin: str, environment: str | None) -> str:
    env = {"sandbox": "Sandbox", "live": "Live", "demo": "demo mode"}.get(environment or "", "")
    if origin == "sample":
        return f"Sample data (fictional) · {FORMAT_NAMES.get(source, source)}"
    if origin == "paypal_api":
        return f"PayPal {env} · Transaction Search".replace("  ", " ")
    if origin == "paypal_checkout":
        return f"PayPal {env} · FINORA checkouts".replace("  ", " ")
    if origin == "user_import":
        return f"Imported file · {FORMAT_NAMES.get(source, source)}"
    return "Imported before source tracking"


def has_data(db: Session, user: User) -> bool:
    return bool(db.scalar(select(func.count(Transaction.id)).join(Account).where(Account.user_id == user.id)))


def clear_user_data(db: Session, user: User) -> None:
    """Empty the twin's ledger. Checkout orders stay as history (PayPal keeps them too); captured ones are marked as
    no longer reflected in the twin, so nothing shows as both completed and missing."""
    for o in db.scalars(select(CheckoutOrder).where(CheckoutOrder.user_id == user.id, CheckoutOrder.status == "captured")):
        if (o.snapshot or {}).get("recorded"):
            o.snapshot = {**o.snapshot, "recorded": {**o.snapshot["recorded"], "cleared_from_twin": True}}
    ids = select(Account.id).where(Account.user_id == user.id)
    txn_ids = select(Transaction.id).where(Transaction.account_id.in_(ids))
    db.execute(delete(FxDetail).where(FxDetail.transaction_id.in_(txn_ids)))  # SQLite doesn't cascade by default
    db.execute(delete(Transaction).where(Transaction.account_id.in_(ids)))
    db.execute(delete(Account).where(Account.user_id == user.id))
    db.execute(delete(Obligation).where(Obligation.user_id == user.id))
    prefs = dict(user.preferences or {})
    prefs.pop("data_source", None)
    user.preferences = prefs


def store_transactions(db: Session, user: User, source_name: str, txns: list[NormalizedTransaction],
                       opening_balance: Decimal | None, replace: bool, data_label: str, *, origin: str,
                       environment: str | None = None) -> dict:
    """Store normalised rows in the account for exactly this (format, origin, environment): provenance never merges."""
    if origin not in ORIGINS:
        raise ValueError(f"unknown origin {origin!r}")
    if replace:
        clear_user_data(db, user)
    had_data = has_data(db, user)
    # PayPal transaction ids are global, so a row already stored from another origin (e.g. an Activity CSV, then an API
    # sync of the same account) is skipped, not doubled. It keeps the provenance it was first stored with.
    family = db.scalars(select(Account).where(Account.user_id == user.id, Account.source == source_name)).all()
    existing = set(db.scalars(select(Transaction.external_id)
                              .where(Transaction.account_id.in_([a.id for a in family]))).all()) if family else set()
    new = [t for t in txns if t.external_id not in existing]
    account = next((a for a in family if a.origin == origin and a.environment == environment), None)
    if account is None and not new:
        # Nothing to store: don't create an empty account (its opening balance would inflate the twin's balance).
        return {"rows": len(txns), "imported": 0, "skipped_duplicates": len(txns), "account_id": family[0].id,
                "opening_balance": family[0].opening_balance, "origin": origin, "environment": environment}
    if account is None:
        # The same money seen through a second origin must not add a second opening balance.
        opening = Decimal("0") if family else (opening_balance or Decimal("0"))
        account = Account(user_id=user.id, name=account_name(source_name, origin, environment), institution=source_name,
                          opening_balance=opening, opening_date=min(t.posted_on for t in txns) - timedelta(days=1),
                          source=source_name, origin=origin, environment=environment)
        db.add(account)
        db.flush()

    rows = [Transaction(account_id=account.id, posted_on=t.posted_on, description=t.description, merchant=t.merchant,
                        category=t.category, amount=t.amount, source=source_name, external_id=t.external_id)
            for t in new]
    db.add_all(rows)
    if any(t.fx for t in new):
        db.flush()  # assign ids so foreign-currency details can reference their transaction
        db.add_all(FxDetail(transaction_id=row.id, currency=t.fx.currency, gross=t.fx.gross, fee=t.fx.fee,
                            net=t.fx.net, rate=t.fx.rate, rate_source=t.fx.rate_source)
                   for row, t in zip(rows, new) if t.fx)
    prefs = dict(user.preferences or {})
    prefs["data_source"] = data_label if not had_data or prefs.get("data_source") in (None, data_label) else "mixed"
    user.preferences = prefs
    db.commit()
    return {"rows": len(txns), "imported": len(new), "skipped_duplicates": len(txns) - len(new),
            "account_id": account.id, "opening_balance": account.opening_balance, "origin": origin,
            "environment": environment}
