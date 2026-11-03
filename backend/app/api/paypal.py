from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.money import money
from app.data.models import Account, Transaction
from app.integrations.paypal.source import PayPalApiError, PayPalNotConfigured, PayPalSource
from app.schemas.api import ImportResult, PayPalSyncRequest
from app.services import repository as repo
from app.services.import_service import store_transactions

router = APIRouter(prefix="/integrations/paypal", tags=["paypal"])


@router.get("")
def paypal_overview(db: Session = Depends(get_db)):
    """Connection status plus what PayPal currently contributes to the twin."""
    user = repo.get_primary_user(db)
    base = (select(Transaction).join(Account)
            .where(Account.user_id == user.id, Account.source == "paypal"))
    sub = base.subquery()
    count = db.scalar(select(func.count()).select_from(sub)) or 0
    inflow = db.scalar(select(func.coalesce(func.sum(sub.c.amount), 0)).where(sub.c.amount > 0)) or 0
    outflow = db.scalar(select(func.coalesce(func.sum(sub.c.amount), 0)).where(sub.c.amount < 0)) or 0
    first = db.scalar(select(func.min(sub.c.posted_on)))
    last = db.scalar(select(func.max(sub.c.posted_on)))
    merchants = db.execute(
        select(sub.c.merchant, func.count(), func.sum(sub.c.amount)).where(sub.c.amount < 0)
        .group_by(sub.c.merchant).order_by(func.sum(sub.c.amount)).limit(6)
    ).all()
    return {
        **PayPalSource(get_settings()).status(),
        "linked": count > 0,
        "transaction_count": count,
        "inflow": float(money(inflow)),
        "outflow": float(money(-outflow)),
        "first_date": first,
        "last_date": last,
        "top_merchants": [{"merchant": m, "count": c, "total": float(money(-t))} for m, c, t in merchants],
    }


@router.get("/status")
def paypal_status():
    return PayPalSource(get_settings()).status()


@router.post("/sync", response_model=ImportResult)
def paypal_sync(body: PayPalSyncRequest, db: Session = Depends(get_db)):
    src = PayPalSource(get_settings(), days=body.days, today=repo.today())
    try:
        txns = src.fetch()
    except PayPalNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except PayPalApiError as exc:
        raise HTTPException(502, str(exc))
    if not txns:
        raise HTTPException(404, f"PayPal returned no completed transactions in the last {body.days} days.")
    user = repo.get_primary_user(db)
    result = store_transactions(db, user, "paypal", txns, src.opening_balance, body.replace, "paypal_api")
    warnings = [] if src.opening_balance is not None else ["Couldn't read your PayPal balance; balances start from ₹0."]
    return ImportResult(format="paypal_api", source="paypal", warnings=warnings, **result)
