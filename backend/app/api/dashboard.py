from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.money import total
from app.engine.forecast import forecast_baseline
from app.engine.health import health_indicators
from app.schemas.api import BalancePoint, DashboardResponse, Kpis, TwinResponse
from app.services import repository as repo

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    a = repo.assumptions_for(user)
    as_of = repo.today()
    txns = repo.load_transactions(db, user)
    profile = repo.build_user_profile(db, user, a, as_of)
    fc = forecast_baseline(profile, a)
    upcoming = [e for p in fc.points if p.on <= as_of + timedelta(days=30) for e in p.events]
    return DashboardResponse(
        as_of=as_of,
        user_name=user.name,
        data_source=(user.preferences or {}).get("data_source") or "unknown",
        kpis=Kpis(
            current_balance=profile.current_balance,
            monthly_income=profile.monthly_income,
            monthly_expenditure=profile.avg_monthly_spending,
            monthly_investments=profile.avg_monthly_investments,
            savings_rate=profile.savings_rate,
            projected_balance_30=fc.balance_on_day(30),
            projected_balance_90=fc.balance_on_day(90),
            upcoming_obligations_total=total(o.amount for o in profile.obligations if o.due_on <= as_of + timedelta(days=a.horizon_days)),
            subscriptions_monthly=profile.subscriptions_monthly,
            next_income_date=profile.next_income_date,
        ),
        health=health_indicators(profile, fc),
        history=[BalancePoint(**p) for p in repo.balance_history(db, user, txns, as_of)],
        forecast=fc,
        months=profile.months,
        categories=profile.categories,
        upcoming_events=upcoming,
        recurring=profile.recurring_income + profile.recurring_outflows,
        obligations=profile.obligations,
        assumptions=a,
    )


@router.get("/twin", response_model=TwinResponse)
def twin(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    a = repo.assumptions_for(user)
    return TwinResponse(profile=repo.build_user_profile(db, user, a), assumptions=a)


@router.get("/forecast")
def forecast(
    horizon_days: int = Query(90, ge=7, le=365),
    safety_buffer: float | None = Query(None, ge=0),
    variable_spend_multiplier: float | None = Query(None, ge=0, le=5),
    db: Session = Depends(get_db),
):
    user = repo.get_primary_user(db)
    a = repo.assumptions_for(
        user,
        horizon_days=horizon_days,
        safety_buffer=Decimal(str(safety_buffer)) if safety_buffer is not None else None,
        variable_spend_multiplier=Decimal(str(variable_spend_multiplier)) if variable_spend_multiplier is not None else None,
    )
    return forecast_baseline(repo.build_user_profile(db, user, a), a)
