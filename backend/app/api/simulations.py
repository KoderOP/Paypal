from fastapi import APIRouter, Depends, HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.data.models import SavedScenario
from app.engine.goals import Affordability
from app.engine.payment_options import DEFAULT_PLANS, TERMS_NOTE, PaymentComparison
from app.engine.scenarios import Change, ScenarioComparison, ScenarioResult
from app.engine.simulation import PurchaseScenario, PurchaseSimulation, simulate_purchase
from app.schemas.api import (
    AffordabilityRequest, CompareRequest, NamedScenario, PaymentOptionsRequest, PurchaseRequest, ScenarioInfo,
    ScenarioRequest,
)
from app.services import planning
from app.services import repository as repo

router = APIRouter(prefix="/simulations", tags=["simulations"])
CHANGES = TypeAdapter(list[Change])
MAX_SAVED = 20

CATALOG = [
    ScenarioInfo(type="purchase", title="Make a purchase", description="Simulate a one-time purchase and find the best date to buy.", status="available"),
    ScenarioInfo(type="payment_options", title="Buy now, wait, or split it?", description="Pay in full, wait for payday, or use PayPal Pay Later.", status="available"),
    ScenarioInfo(type="affordability", title="What can I afford?", description="The most you can spend, and the earliest safe date to buy.", status="available"),
    ScenarioInfo(type="add_subscription", title="Start a subscription", description="What if I subscribe? A new monthly charge from a start date.", status="available"),
    ScenarioInfo(type="cancel_subscriptions", title="Cancel subscriptions", description="Remove selected recurring subscriptions.", status="available"),
    ScenarioInfo(type="income_delay", title="Income delayed", description="Shift expected income by N days.", status="available"),
    ScenarioInfo(type="increase_savings", title="Increase savings", description="Raise monthly savings / SIP by a percentage.", status="available"),
    ScenarioInfo(type="unexpected_payment", title="Unexpected payment", description="An emergency outflow on a given date.", status="available"),
    ScenarioInfo(type="expense_increase", title="Expenses change", description="Scale day-to-day spending by a percentage.", status="available"),
    ScenarioInfo(type="fx_change", title="Exchange rate moves", description="What if USD/INR drops or rises by a percentage?", status="available"),
]


@router.get("/scenarios", response_model=list[ScenarioInfo])
def scenarios():
    return CATALOG


@router.post("/purchase", response_model=PurchaseSimulation)
def purchase(body: PurchaseRequest, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    a = repo.assumptions_for(user, safety_buffer=body.safety_buffer)
    profile = repo.build_user_profile(db, user, a)
    sc = PurchaseScenario(amount=body.amount, purchase_date=body.purchase_date or profile.as_of, label=body.label)
    try:
        return simulate_purchase(profile, a, sc)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/pay-later-plans")
def pay_later_plans():
    """Default (illustrative) Pay Later terms used by the comparison. Clients may send their own."""
    return {"plans": [p.model_dump(mode="json") for p in DEFAULT_PLANS], "terms_note": TERMS_NOTE}


@router.post("/payment-options", response_model=PaymentComparison)
def payment_options(body: PaymentOptionsRequest, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    return planning.payment_comparison(db, user, body.amount, body.label, body.safety_buffer, body.plans)


@router.post("/affordability", response_model=Affordability)
def affordability(body: AffordabilityRequest, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    return planning.affordability(db, user, body.amount, body.search_days, body.safety_buffer)


def _changes(raw: list[dict], where: list) -> list:
    try:
        return CHANGES.validate_python(raw)
    except ValidationError as exc:
        raise HTTPException(422, [{"loc": ["body", *where, *e["loc"]], "msg": e["msg"]} for e in exc.errors()])


@router.post("/scenario", response_model=ScenarioResult)
def scenario(body: ScenarioRequest, db: Session = Depends(get_db)):
    changes = _changes(body.changes, ["changes"])
    user = repo.get_primary_user(db)
    try:
        return planning.scenario(db, user, changes, body.title, body.safety_buffer)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/compare", response_model=ScenarioComparison)
def compare(body: CompareRequest, db: Session = Depends(get_db)):
    """Up to four scenarios on one baseline, e.g. 'cancel subscriptions' vs 'delay the laptop' vs 'both'."""
    named = [(s.name, _changes(s.changes, ["scenarios", i, "changes"])) for i, s in enumerate(body.scenarios)]
    user = repo.get_primary_user(db)
    try:
        return planning.comparison(db, user, named, body.safety_buffer)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/saved")
def saved(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    rows = db.scalars(select(SavedScenario).where(SavedScenario.user_id == user.id).order_by(SavedScenario.id.desc())).all()
    return [{"id": s.id, "name": s.name, "changes": s.changes, "created_at": s.created_at} for s in rows]


@router.post("/saved", status_code=201)
def save(body: NamedScenario, db: Session = Depends(get_db)):
    changes = _changes(body.changes, ["changes"])
    user = repo.get_primary_user(db)
    if db.scalar(select(func.count(SavedScenario.id)).where(SavedScenario.user_id == user.id)) >= MAX_SAVED:
        raise HTTPException(409, f"You can save up to {MAX_SAVED} scenarios. Delete one first.")
    s = SavedScenario(user_id=user.id, name=body.name.strip(), changes=[c.model_dump(mode="json") for c in changes])
    db.add(s)
    db.commit()
    return {"id": s.id, "name": s.name, "changes": s.changes, "created_at": s.created_at}


@router.delete("/saved/{saved_id}", status_code=204)
def delete_saved(saved_id: int, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    s = db.get(SavedScenario, saved_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Saved scenario not found")
    db.delete(s)
    db.commit()
