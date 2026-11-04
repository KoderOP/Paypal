"""Subscriptions: what the twin detected + PayPal Subscriptions API actions.

- Detected subscriptions come from the twin's recurring-payment rules (any data source).
- A PayPal subscription (id I-…) can be linked to a detected item. FINORA then reads its live
  status, price and next billing date, and can cancel / suspend / re-activate it. Every action
  requires `confirm: true`.
- Cancelling (through PayPal, or marking an item cancelled manually) removes that item from
  every future projection: dashboard, simulator, goal solver and assistant.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.money import money, total
from app.data.models import AddedSubscription, LinkedSubscription, User
from app.integrations.paypal.client import PayPalCallError, PayPalClient, get_paypal_client
from app.integrations.paypal.source import PayPalApiError
from app.integrations.paypal.subscriptions import ACTIONS, change_status, fetch_subscription
from app.schemas.api import RecurringToggle, SubscriptionAction, SubscriptionCreate, SubscriptionLink
from app.services import repository as repo

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _autopay_url() -> str:
    return f"{get_settings().paypal_web_url}/myaccount/autopay/"


def _linked_out(s: LinkedSubscription) -> dict:
    return {"id": s.id, "paypal_subscription_id": s.paypal_subscription_id, "recurring_key": s.recurring_key,
            "name": s.name, "plan_id": s.plan_id, "status": s.status,
            "amount": float(s.amount) if s.amount is not None else None, "currency": s.currency,
            "next_billing_date": s.next_billing_date, "last_synced_at": s.last_synced_at}


def _get(db: Session, user: User, sub_id: int) -> LinkedSubscription:
    s = db.get(LinkedSubscription, sub_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Linked subscription not found")
    return s


def _apply(s: LinkedSubscription, data: dict) -> None:
    s.status, s.plan_id, s.name = data["status"], data["plan_id"], data["name"][:160]
    s.amount = money(data["amount"]) if data["amount"] is not None else s.amount
    s.currency = data["currency"] or s.currency
    # PayPal drops next_billing_time once a subscription is cancelled; keep the last known date so the
    # row can still be shown (as cancelled) instead of silently vanishing.
    s.next_billing_date = data["next_billing_date"] or s.next_billing_date
    s.last_synced_at = datetime.now()


def _twin_key(s: LinkedSubscription) -> str:
    """The recurring item this PayPal subscription drives: a detected one, or its own PayPal-only item."""
    return s.recurring_key or repo.paypal_key(s)


def _sync_cancellation(user: User, s: LinkedSubscription) -> None:
    key = _twin_key(s)
    if s.status in ("CANCELLED", "SUSPENDED", "EXPIRED"):
        repo.set_cancelled(user, key, {"via": "paypal", "status": s.status, "on": repo.today().isoformat(),
                                       "subscription_id": s.paypal_subscription_id})
    elif (((user.preferences or {}).get("cancelled_recurring") or {}).get(key) or {}).get("via") == "paypal":
        repo.set_cancelled(user, key, None)


def _added_out(s: AddedSubscription) -> dict:
    return {"id": s.id, "name": s.name, "category": s.category, "amount": float(s.amount),
            "next_billing_date": s.next_billing_date, "key": repo.added_key(s)}


@router.get("")
def overview(db: Session = Depends(get_db), pp: PayPalClient = Depends(get_paypal_client)):
    user = repo.get_primary_user(db)
    a = repo.assumptions_for(user)
    profile = repo.build_user_profile(db, user, a, include_cancelled=True)
    cancelled = (user.preferences or {}).get("cancelled_recurring") or {}
    linked = db.scalars(select(LinkedSubscription).where(LinkedSubscription.user_id == user.id)).all()
    by_key = {_twin_key(s): s for s in linked}
    added = {repo.added_key(s): s for s in
             db.scalars(select(AddedSubscription).where(AddedSubscription.user_id == user.id)).all()}
    in_twin = {r.key for r in profile.recurring_outflows}
    detected = [
        {"key": r.key, "merchant": r.merchant, "name": r.name, "category": r.category, "amount": float(r.amount),
         "annual_cost": float(money(r.amount * 12)), "day_of_month": r.day_of_month, "next_date": r.next_date,
         "occurrences": r.occurrences, "source": r.source,
         "cancelled": r.key in cancelled, "cancelled_via": (cancelled.get(r.key) or {}).get("via"),
         "linked": _linked_out(by_key[r.key]) if r.key in by_key else None,
         "added": _added_out(added[r.key]) if r.key in added else None}
        for r in sorted(profile.recurring_outflows, key=lambda r: -r.amount) if r.kind == "subscription"
    ]
    # Added items whose merchant is now detected from history: shown so the user can remove the duplicate entry.
    superseded = [_added_out(s) for k, s in added.items() if k not in in_twin]
    active = total(Decimal(str(d["amount"])) for d in detected if not d["cancelled"])
    saved = total(Decimal(str(d["amount"])) for d in detected if d["cancelled"])
    return {
        "api_available": pp.configured, "environment": get_settings().paypal_environment,
        "autopay_url": _autopay_url(), "detected": detected, "linked": [_linked_out(s) for s in linked],
        "superseded": superseded,
        "totals": {"monthly_active": float(active), "annual_active": float(money(active * 12)),
                   "monthly_cancelled": float(saved), "annual_cancelled": float(money(saved * 12)),
                   "count_active": sum(1 for d in detected if not d["cancelled"])},
    }


@router.post("/added", status_code=201)
def add_subscription(body: SubscriptionCreate, db: Session = Depends(get_db)):
    """Add a subscription by hand (e.g. one you just started). Every forecast includes it from now on."""
    if body.next_billing_date < repo.today():
        raise HTTPException(422, "The next billing date must be today or later.")
    user = repo.get_primary_user(db)
    s = AddedSubscription(user_id=user.id, name=body.name.strip(), category=body.category.strip(),
                          amount=money(body.amount), next_billing_date=body.next_billing_date)
    db.add(s)
    db.commit()
    return _added_out(s)


@router.put("/added/{added_id}")
def edit_added(added_id: int, body: SubscriptionCreate, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    s = db.get(AddedSubscription, added_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Added subscription not found")
    if body.next_billing_date < repo.today() and body.next_billing_date != s.next_billing_date:
        raise HTTPException(422, "The next billing date must be today or later.")
    s.name, s.category = body.name.strip(), body.category.strip()
    s.amount, s.next_billing_date = money(body.amount), body.next_billing_date
    db.commit()
    return _added_out(s)


@router.delete("/added/{added_id}", status_code=204)
def remove_added(added_id: int, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    s = db.get(AddedSubscription, added_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Added subscription not found")
    repo.set_cancelled(user, repo.added_key(s), None)  # drop any stale "cancelled" mark for this item
    db.delete(s)
    db.commit()


@router.post("/link", status_code=201)
def link(body: SubscriptionLink, db: Session = Depends(get_db), pp: PayPalClient = Depends(get_paypal_client)):
    if not pp.configured:
        raise HTTPException(400, "Linking a PayPal subscription needs PayPal API credentials in backend/.env.")
    user = repo.get_primary_user(db)
    try:
        data = fetch_subscription(pp, body.paypal_subscription_id)
    except PayPalCallError as exc:
        if exc.status == 404 or exc.name == "RESOURCE_NOT_FOUND":
            raise HTTPException(404, f"PayPal has no subscription {body.paypal_subscription_id} visible to this app.")
        raise HTTPException(502, str(exc))
    except PayPalApiError as exc:
        raise HTTPException(502, str(exc))

    key = body.recurring_key or _auto_match(db, user, data)
    s = db.scalars(select(LinkedSubscription).where(LinkedSubscription.user_id == user.id,
                                                    LinkedSubscription.paypal_subscription_id == data["id"])).first()
    if s is None:
        s = LinkedSubscription(user_id=user.id, paypal_subscription_id=data["id"])
        db.add(s)
    s.recurring_key = key
    _apply(s, data)
    _sync_cancellation(user, s)
    db.commit()
    return _linked_out(s)


def _auto_match(db: Session, user: User, data: dict) -> str | None:
    """Best-effort: link to a detected subscription with the same name or the same monthly price."""
    try:
        profile = repo.build_user_profile(db, user, repo.assumptions_for(user), include_cancelled=True)
    except HTTPException:
        return None
    subs = [r for r in profile.recurring_outflows if r.kind == "subscription"]
    name = data["name"].lower()
    hit = next((r for r in subs if r.merchant.lower() in name or name in r.merchant.lower()), None)
    if hit is None and data["amount"] is not None:
        hit = next((r for r in subs if abs(r.amount - money(data["amount"])) <= max(Decimal("1"), r.amount / 100)), None)
    return hit.key if hit else None


@router.post("/{sub_id}/refresh")
def refresh(sub_id: int, db: Session = Depends(get_db), pp: PayPalClient = Depends(get_paypal_client)):
    user = repo.get_primary_user(db)
    s = _get(db, user, sub_id)
    try:
        _apply(s, fetch_subscription(pp, s.paypal_subscription_id))
    except PayPalApiError as exc:
        raise HTTPException(502, str(exc))
    _sync_cancellation(user, s)
    db.commit()
    return _linked_out(s)


@router.post("/{sub_id}/{action}")
def act(sub_id: int, action: str, body: SubscriptionAction, db: Session = Depends(get_db),
        pp: PayPalClient = Depends(get_paypal_client)):
    if action not in ACTIONS:
        raise HTTPException(404, "Unknown action")
    if not body.confirm:
        raise HTTPException(422, f"Confirm that you want to {action} this subscription.")
    user = repo.get_primary_user(db)
    s = _get(db, user, sub_id)
    try:
        change_status(pp, s.paypal_subscription_id, action, body.reason)
        _apply(s, fetch_subscription(pp, s.paypal_subscription_id))
    except PayPalCallError as exc:
        if exc.status in (401, 403) or exc.name in ("NOT_AUTHORIZED", "PERMISSION_DENIED"):
            raise HTTPException(403, {
                "message": "PayPal only lets the merchant's app change this subscription. Cancel it yourself in "
                           "PayPal → Settings → Automatic payments, then mark it cancelled here.",
                "errors": [_autopay_url()]})
        if exc.status == 422:
            raise HTTPException(409, f"PayPal refused: {exc}")
        raise HTTPException(502, str(exc))
    except PayPalApiError as exc:
        raise HTTPException(502, str(exc))
    _sync_cancellation(user, s)
    db.commit()
    return _linked_out(s)


@router.delete("/{sub_id}", status_code=204)
def unlink(sub_id: int, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    s = _get(db, user, sub_id)
    db.delete(s)
    db.commit()


@router.post("/mark")
def mark(body: RecurringToggle, db: Session = Depends(get_db)):
    """Mark a detected subscription cancelled (or restore it) without the PayPal API."""
    user = repo.get_primary_user(db)
    profile = repo.build_user_profile(db, user, repo.assumptions_for(user), include_cancelled=True)
    if body.recurring_key not in {r.key for r in profile.recurring_outflows}:
        raise HTTPException(404, "That recurring payment isn't in your twin.")
    repo.set_cancelled(user, body.recurring_key,
                       {"via": "manual", "on": repo.today().isoformat()} if body.cancelled else None)
    db.commit()
    return {"recurring_key": body.recurring_key, "cancelled": body.cancelled}
