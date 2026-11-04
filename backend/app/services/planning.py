"""Glue between persisted data and the planning engines (payment options, goals, scenarios).

Routers and the AI assistant both go through here, so a checkout always re-computes the
simulation server-side instead of trusting numbers sent by the browser.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import User
from app.engine.goals import Affordability, solve_affordability
from app.engine.payment_options import PayLaterPlan, PaymentComparison, compare_payment_options
from app.engine.scenarios import ScenarioResult, simulate_scenario
from app.services import repository as repo


def payment_comparison(db: Session, user: User, amount: Decimal, label: str, safety_buffer: Decimal | None = None,
                       plans: list | None = None) -> PaymentComparison:
    a = repo.assumptions_for(user, safety_buffer=safety_buffer)
    profile = repo.build_user_profile(db, user, a)
    parsed = [PayLaterPlan(**(p.model_dump() if hasattr(p, "model_dump") else p)) for p in plans] if plans else None
    return compare_payment_options(profile, a, amount, label, parsed)


def affordability(db: Session, user: User, amount: Decimal | None = None, search_days: int = 60,
                  safety_buffer: Decimal | None = None) -> Affordability:
    a = repo.assumptions_for(user, safety_buffer=safety_buffer)
    return solve_affordability(repo.build_user_profile(db, user, a), a, search_days, amount)


def scenario(db: Session, user: User, changes: list, title: str | None = None,
             safety_buffer: Decimal | None = None) -> ScenarioResult:
    a = repo.assumptions_for(user, safety_buffer=safety_buffer)
    return simulate_scenario(repo.build_user_profile(db, user, a), a, changes, title)
