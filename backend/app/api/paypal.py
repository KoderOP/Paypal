from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.money import money
from app.data.models import Account, CheckoutOrder, Transaction
from app.integrations.paypal.client import paypal_runtime
from app.integrations.paypal.source import PayPalApiError, PayPalNotConfigured, PayPalSource
from app.schemas.api import ImportResult, PayPalSyncRequest
from app.services import repository as repo
from app.services.import_service import MixedProvenanceError, store_transactions

router = APIRouter(prefix="/integrations/paypal", tags=["paypal"])


PAYPAL_ORIGINS = ("paypal_api", "paypal_checkout")


@router.get("")
def paypal_overview(db: Session = Depends(get_db)):
    """What PayPal really contributes, kept apart from sample and imported data.

    `transaction_count` and the stats count ONLY records that came from PayPal's APIs (Transaction Search, or payments
    captured through FINORA's checkout). Sample transactions in PayPal Activity *format* are reported separately and are
    never called PayPal records.
    """
    user = repo.get_primary_user(db)
    base = (select(Transaction).join(Account)
            .where(Account.user_id == user.id, Account.origin.in_(PAYPAL_ORIGINS)))
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
    prov = repo.provenance(db, user)
    orders = db.execute(select(CheckoutOrder.status, func.count()).where(CheckoutOrder.user_id == user.id)
                        .group_by(CheckoutOrder.status)).all()
    return {
        **PayPalSource(paypal_runtime()[0]).status(),
        "linked": count > 0,
        "transaction_count": count,
        "inflow": float(money(inflow)),
        "outflow": float(money(-outflow)),
        "first_date": first,
        "last_date": last,
        "top_merchants": [{"merchant": m, "count": c, "total": float(money(-t))} for m, c, t in merchants],
        "records_by_origin": [p for p in prov if p["origin"] in PAYPAL_ORIGINS],
        "sample_transactions": sum(p["count"] for p in prov if p["origin"] == "sample"),
        "imported_transactions": sum(p["count"] for p in prov if p["origin"] in ("user_import", "unknown")),
        "last_sync": (user.preferences or {}).get("paypal_last_sync"),
        "checkouts_by_status": {s_: n for s_, n in orders},
    }


@router.post("/check-auth")
def paypal_check_auth():
    """Ask PayPal for an OAuth token right now. Proves the credentials work; reads and changes nothing."""
    settings, transport = paypal_runtime()
    src = PayPalSource(settings, transport=transport)
    env = settings.paypal_environment
    if not src.configured:
        return {"ok": False, "environment": env, "message": "No PayPal credentials are set."}
    from app.integrations.paypal.client import PayPalClient
    try:
        PayPalClient(settings, transport).app_token()
    except (PayPalApiError, PayPalNotConfigured) as exc:
        return {"ok": False, "environment": env, "message": str(exc)[:200]}
    return {"ok": True, "environment": env,
            "message": "PayPal's simulated OAuth in demo mode returned a token." if env == "demo"
            else f"PayPal {env} returned an OAuth token for these credentials."}


@router.get("/status")
def paypal_status():
    return PayPalSource(paypal_runtime()[0]).status()


def _record_sync(db: Session, environment: str, outcome: str, records: int = 0, message: str | None = None) -> None:
    """Remember the last Transaction Search attempt, so the hub reports what actually happened."""
    from datetime import datetime, timezone
    user = repo.get_primary_user(db)
    prefs = dict(user.preferences or {})
    prefs["paypal_last_sync"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "environment": environment,
                                 "outcome": outcome, "records": records, "message": message}
    user.preferences = prefs
    db.commit()


@router.post("/sync", response_model=ImportResult)
def paypal_sync(body: PayPalSyncRequest, db: Session = Depends(get_db)):
    settings, transport = paypal_runtime()
    env = settings.paypal_environment
    user = repo.get_primary_user(db)
    src = PayPalSource(settings, days=body.days, transport=transport, today=repo.today(), home_currency=user.currency)
    try:
        txns = src.fetch()
    except PayPalNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except PayPalApiError as exc:
        _record_sync(db, env, "error", message=str(exc)[:200])
        raise HTTPException(502, str(exc))
    skipped = ", ".join(f"{n} in {c}" for c, n in src.skipped_currencies.items())
    if not txns:
        why = f"No usable transactions in the last {body.days} days" + (f" ({skipped} skipped: set PAYPAL_CHECKOUT_FX_RATE "
                                                                          "for that currency to convert them)." if skipped else ".")
        _record_sync(db, env, "empty", message=why)
        raise HTTPException(404, why)
    try:
        result = store_transactions(db, user, "paypal", txns, src.opening_balance, body.replace, "paypal_api",
                                    origin="paypal_api", environment=env)
    except MixedProvenanceError as exc:
        _record_sync(db, env, "ok", records=len(txns),
                     message=f"PayPal returned {len(txns)} record(s); not stored: {exc}")
        raise HTTPException(409, f"PayPal returned {len(txns)} record(s), not stored. {exc}")
    _record_sync(db, env, "ok", records=len(txns))
    warnings = [] if src.opening_balance is not None else ["Couldn't read your PayPal balance in a convertible currency; it starts from ₹0."]
    if src.converted:
        warnings.append(f"{src.converted} record(s) in {settings.paypal_checkout_currency} converted at your rate "
                        f"{settings.paypal_checkout_fx_rate} (not a PayPal or market rate).")
    if skipped:
        warnings.append(f"Skipped {skipped}: no conversion rate configured for that currency.")
    return ImportResult(format="paypal_api", source="paypal", warnings=warnings, **result)
