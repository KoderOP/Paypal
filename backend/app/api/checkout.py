"""Pay with PayPal after simulating: three human steps (two confirmations in FINORA, approval on PayPal).

1. POST /checkout/orders   requires `acknowledged: true` (the user reviewed the simulated impact).
                           The simulation is re-run server-side and snapshotted on the order.
2. The buyer approves on PayPal, and PayPal redirects to /checkout/return → the order is `approved`.
3. POST /checkout/orders/{id}/capture requires `confirm: true`. Only then is money captured.

After capture the twin is updated immediately: a full payment is recorded as a PayPal
transaction (external id = capture id, so a later Transaction Search sync de-duplicates it),
and a Pay Later plan is recorded as dated obligations, one per instalment.
"""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.data.models import Account, CheckoutOrder, Obligation, Transaction, User
from app.integrations.paypal.client import PayPalCallError, PayPalClient, get_paypal_client, new_request_id
from app.integrations.paypal.orders import capture_order, create_order, get_order
from app.integrations.paypal.source import PayPalApiError, PayPalNotConfigured
from app.schemas.api import CheckoutConfirm, CheckoutCreate, CheckoutOut, ObligationOut, PlanPurchase
from app.services import repository as repo
from app.services.import_service import account_name
from app.services.planning import payment_comparison

router = APIRouter(prefix="/checkout", tags=["checkout"])


def _out(o: CheckoutOrder) -> CheckoutOut:
    return CheckoutOut(id=o.id, paypal_order_id=o.paypal_order_id, option_id=o.option_id, funding=o.funding,
                       label=o.label, amount=o.amount, currency=o.currency, status=o.status, approve_url=o.approve_url,
                       capture_id=o.capture_id, snapshot=o.snapshot or {}, error=o.error,
                       environment=get_settings().paypal_environment)


def _get(db: Session, user: User, order_id: int) -> CheckoutOrder:
    o = db.get(CheckoutOrder, order_id)
    if not o or o.user_id != user.id:
        raise HTTPException(404, "Checkout not found")
    return o


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(f"{get_settings().frontend_url.rstrip('/')}{path}", status_code=303)


@router.post("/orders", response_model=CheckoutOut, status_code=201)
def start_checkout(body: CheckoutCreate, db: Session = Depends(get_db), pp: PayPalClient = Depends(get_paypal_client)):
    if not body.acknowledged:
        raise HTTPException(422, "Review the simulated impact and tick the confirmation before paying.")
    if not pp.configured:
        raise HTTPException(400, "PayPal checkout needs PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env.")
    user = repo.get_primary_user(db)
    cmp = payment_comparison(db, user, body.amount, body.label, body.safety_buffer, body.plans)
    option = next((o for o in cmp.options if o.id == body.option_id), None)
    if option is None or option.action != "checkout":
        raise HTTPException(422, f"'{body.option_id}' is not a payable option for this purchase.")

    snapshot = {
        "option_name": option.name, "summary": option.summary, "safe": option.safe, "recommended": option.recommended,
        "min_balance": str(option.min_balance), "min_balance_date": option.min_balance_date.isoformat(),
        "total_paid": str(option.total_paid), "extra_cost": str(option.extra_cost), "apr": str(option.apr),
        "payments": [{"on": p.on.isoformat(), "amount": str(p.amount)} for p in option.payments],
        "safety_buffer": str(cmp.assumptions.safety_buffer), "as_of": cmp.as_of.isoformat(),
        "terms_note": cmp.terms_note if option.funding == "paylater" else None,
    }
    s = get_settings()
    charge_currency, charge_amount = _charge(cmp.amount, user.currency)
    snapshot["paypal_charge"] = {"currency": charge_currency, "amount": str(charge_amount),
                                 "rate": str(s.paypal_checkout_fx_rate) if charge_currency != user.currency.upper() else None}
    # The order keeps the home-currency amount (the twin and the UI work in it); PayPal is charged `paypal_charge`.
    order = CheckoutOrder(user_id=user.id, option_id=option.id, funding=option.funding or "paypal", label=body.label,
                          amount=cmp.amount, currency=user.currency.upper(),
                          status="created", request_id=new_request_id(), snapshot=snapshot)
    db.add(order)
    db.commit()  # record the intent before calling PayPal; also releases SQLite's write lock for the call
    try:
        res = create_order(pp, amount=charge_amount, currency=charge_currency, label=order.label,
                           reference=f"finora-{order.id}", return_url=f"{s.public_api_url}/checkout/return",
                           cancel_url=f"{s.public_api_url}/checkout/cancel", request_id=order.request_id)
    except (PayPalApiError, PayPalNotConfigured) as exc:
        order.status, order.error = "failed", str(exc)[:300]
        db.commit()
        raise HTTPException(502, str(exc))
    order.paypal_order_id, order.approve_url = res["id"], res["approve_url"]
    order.status = "awaiting_approval" if res["approve_url"] else "failed"
    order.error = None if res["approve_url"] else "PayPal did not return an approval link."
    db.commit()
    return _out(order)


def _charge(amount: Decimal, home: str) -> tuple[str, Decimal]:
    """(currency, amount) to charge at PayPal. Cross-currency needs an explicit PAYPAL_CHECKOUT_FX_RATE."""
    s = get_settings()
    cur = (s.paypal_checkout_currency or home).upper()
    if cur == home.upper():
        return cur, amount
    if not s.paypal_checkout_fx_rate or s.paypal_checkout_fx_rate <= 0:
        raise HTTPException(400, f"Checkout currency is {cur} but your profile is in {home.upper()}. Set "
                                 f"PAYPAL_CHECKOUT_FX_RATE ({home.upper()} per 1 {cur}) so the amount is converted, "
                                 "or clear PAYPAL_CHECKOUT_CURRENCY.")
    return cur, (amount / s.paypal_checkout_fx_rate).quantize(Decimal("0.01"))


@router.get("/return", include_in_schema=False)
def paypal_return(token: str, db: Session = Depends(get_db), pp: PayPalClient = Depends(get_paypal_client)):
    order = db.scalars(select(CheckoutOrder).where(CheckoutOrder.paypal_order_id == token)).first()
    if order is None:
        return _redirect("/simulator?checkout=unknown")
    if order.status == "awaiting_approval":
        try:
            status = get_order(pp, token).get("status")
        except PayPalApiError as exc:
            order.error = str(exc)[:300]
            status = None
        if status == "APPROVED":
            order.status = "approved"
        db.commit()
    return _redirect(f"/checkout/{order.id}")


@router.get("/cancel", include_in_schema=False)
def paypal_cancel(token: str, db: Session = Depends(get_db)):
    order = db.scalars(select(CheckoutOrder).where(CheckoutOrder.paypal_order_id == token)).first()
    if order is None:
        return _redirect("/simulator?checkout=cancelled")
    if order.status in ("created", "awaiting_approval", "approved"):
        order.status = "cancelled"
        db.commit()
    return _redirect(f"/checkout/{order.id}")


@router.get("/orders", response_model=list[CheckoutOut])
def list_orders(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    rows = db.scalars(select(CheckoutOrder).where(CheckoutOrder.user_id == user.id).order_by(CheckoutOrder.id.desc())).all()
    return [_out(o) for o in rows]


@router.get("/orders/{order_id}", response_model=CheckoutOut)
def read_order(order_id: int, db: Session = Depends(get_db)):
    return _out(_get(db, repo.get_primary_user(db), order_id))


@router.post("/orders/{order_id}/capture", response_model=CheckoutOut)
def capture(order_id: int, body: CheckoutConfirm, db: Session = Depends(get_db),
            pp: PayPalClient = Depends(get_paypal_client)):
    user = repo.get_primary_user(db)
    order = _get(db, user, order_id)
    if not body.confirm:
        raise HTTPException(422, "Payment not confirmed.")
    if order.status == "captured":
        return _out(order)
    if order.status != "approved":
        raise HTTPException(409, f"This checkout is '{order.status}', so it can't be paid. Approve it on PayPal first.")
    try:
        res = capture_order(pp, order.paypal_order_id or "", f"{order.request_id}-capture")
    except PayPalCallError as exc:
        order.error = str(exc)[:300]
        if exc.name in ("ORDER_NOT_APPROVED", "UNPROCESSABLE_ENTITY") and exc.status == 422:
            order.status = "awaiting_approval"
        db.commit()
        raise HTTPException(502, str(exc))
    except PayPalApiError as exc:
        order.error = str(exc)[:300]
        db.commit()
        raise HTTPException(502, str(exc))
    if res["status"] != "COMPLETED" or not res["capture_id"]:
        order.status, order.error = "failed", f"PayPal returned status {res['status']} ({res.get('capture_status')})."
        db.commit()
        raise HTTPException(502, order.error)
    order.status, order.capture_id, order.error = "captured", res["capture_id"], None
    order.snapshot = {**(order.snapshot or {}), "captured_on": repo.today().isoformat(),
                      "recorded": _record_in_twin(db, user, order)}
    db.commit()
    return _out(order)


@router.post("/orders/{order_id}/cancel", response_model=CheckoutOut)
def cancel(order_id: int, db: Session = Depends(get_db)):
    order = _get(db, repo.get_primary_user(db), order_id)
    if order.status == "captured":
        raise HTTPException(409, "This payment was already captured. Refunds happen in PayPal.")
    order.status = "cancelled"
    db.commit()
    return _out(order)


@router.post("/plan", response_model=ObligationOut, status_code=201)
def plan_purchase(body: PlanPurchase, db: Session = Depends(get_db)):
    """The 'wait' option: put the purchase in the twin as a planned payment on the chosen date."""
    user = repo.get_primary_user(db)
    if body.on < repo.today():
        raise HTTPException(422, "The planned date must be today or later")
    o = Obligation(user_id=user.id, title=f"Planned: {body.label}", category="Shopping", amount=body.amount,
                   due_on=body.on, notes="Planned in the FINORA simulator (buy later)")
    db.add(o)
    db.commit()
    return ObligationOut(id=o.id, title=o.title, category=o.category, amount=o.amount, due_on=o.due_on, notes=o.notes)


def _record_in_twin(db: Session, user: User, order: CheckoutOrder) -> dict:
    """Put a captured payment into the twin, in the PayPal checkout account for this environment (never merged into
    sample or imported data), and drop any earlier "Planned:" entry for the same purchase so it isn't counted twice."""
    today = repo.today()
    env = get_settings().paypal_environment
    planned = db.scalars(select(Obligation).where(Obligation.user_id == user.id, Obligation.title == f"Planned: {order.label}",
                                                  Obligation.amount == order.amount)).all()
    for o in planned:
        db.delete(o)
    replaced = {"replaced_planned": len(planned)} if planned else {}
    if order.funding == "paylater":
        payments = (order.snapshot or {}).get("payments", [])
        n = len(payments)
        for i, p in enumerate(payments, 1):
            db.add(Obligation(user_id=user.id, title=f"{order.label} · Pay Later {i}/{n}", category="Pay Later",
                              amount=Decimal(p["amount"]), due_on=date.fromisoformat(p["on"]),
                              notes=f"Simulated schedule from FINORA's illustrative terms for PayPal order "
                                    f"{order.paypal_order_id} ({env}). PayPal sets the real terms; edit if they differ."))
        return {"kind": "obligations", "count": n, "simulated_schedule": True, **replaced}
    account = db.scalars(select(Account).where(Account.user_id == user.id, Account.origin == "paypal_checkout",
                                               Account.environment == env)).first()
    if account is None:
        account = Account(user_id=user.id, name=account_name("paypal", "paypal_checkout", env), institution="paypal",
                          opening_balance=0, opening_date=today - timedelta(days=1), source="paypal",
                          origin="paypal_checkout", environment=env)
        db.add(account)
        db.flush()
    db.add(Transaction(account_id=account.id, posted_on=today, description=f"PayPal checkout · {order.label}",
                       merchant=order.label[:120], category="Shopping", amount=-order.amount, source="paypal",
                       external_id=f"pp-{order.capture_id}"))
    return {"kind": "transaction", "external_id": f"pp-{order.capture_id}", **replaced}
