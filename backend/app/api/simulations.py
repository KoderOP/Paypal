from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.engine.simulation import PurchaseScenario, PurchaseSimulation, simulate_purchase
from app.schemas.api import PurchaseRequest, ScenarioInfo
from app.services import repository as repo

router = APIRouter(prefix="/simulations", tags=["simulations"])

CATALOG = [
    ScenarioInfo(type="purchase", title="Make a purchase", description="Simulate a one-time purchase and find the best date to buy.", status="available"),
    ScenarioInfo(type="cancel_subscriptions", title="Cancel subscriptions", description="Remove selected recurring subscriptions.", status="planned"),
    ScenarioInfo(type="salary_delay", title="Salary delayed", description="Shift expected income by N days.", status="planned"),
    ScenarioInfo(type="increase_savings", title="Increase savings", description="Raise monthly savings / SIP by a percentage.", status="planned"),
    ScenarioInfo(type="unexpected_payment", title="Unexpected payment", description="An emergency outflow on a given date.", status="planned"),
    ScenarioInfo(type="expense_increase", title="Expenses increase", description="Scale variable spending by a percentage.", status="planned"),
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
