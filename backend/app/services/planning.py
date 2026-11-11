"""Glue between persisted data and the planning engines (payment options, goals, scenarios).

Routers and the AI assistant both go through here, so a checkout always re-computes the
simulation server-side instead of trusting numbers sent by the browser.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import User
from app.engine.alerts import Alert, build_alerts
from app.engine.crossborder import CrossBorder, cross_border
from app.engine.forecast import forecast_baseline
from app.engine.goals import Affordability, solve_affordability
from app.engine.payment_options import PayLaterPlan, PaymentComparison, compare_payment_options
from app.engine.scenarios import ScenarioComparison, ScenarioResult, compare_scenarios, simulate_scenario
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


def comparison(db: Session, user: User, named: list[tuple[str, list]],
               safety_buffer: Decimal | None = None) -> ScenarioComparison:
    a = repo.assumptions_for(user, safety_buffer=safety_buffer)
    return compare_scenarios(repo.build_user_profile(db, user, a), a, named)


def reference_rates(user: User) -> dict[str, Decimal]:
    return {k: Decimal(v) for k, v in ((user.preferences or {}).get("fx_reference_rates") or {}).items()}


def cross_border_view(db: Session, user: User) -> CrossBorder:
    a = repo.assumptions_for(user)
    profile = repo.build_user_profile(db, user, a)
    return cross_border(profile, repo.load_transactions(db, user), a, reference_rates(user))


def all_alerts(db: Session, user: User) -> list[Alert]:
    """Every alert that applies right now, ignoring dismissals."""
    a = repo.assumptions_for(user)
    profile = repo.build_user_profile(db, user, a)
    return build_alerts(profile, forecast_baseline(profile, a), repo.load_transactions(db, user), a)


def dismissed_alerts(user: User) -> set[str]:
    return set((user.preferences or {}).get("dismissed_alerts") or [])
