"""Proactive alerts for the dashboard.

Dismissing hides one occurrence: alert ids carry the date they refer to, so the same situation
next month shows up again. Dismissals for alerts that no longer apply are pruned on every write.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.data.models import User
from app.schemas.api import AlertDismiss
from app.services import planning
from app.services import repository as repo

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _view(db: Session, user: User) -> dict:
    found = planning.all_alerts(db, user)
    hidden = planning.dismissed_alerts(user)
    return {"alerts": [a.model_dump(mode="json") for a in found if a.id not in hidden],
            "dismissed": sum(1 for a in found if a.id in hidden)}


def _save(db: Session, user: User, ids: set[str]) -> None:
    prefs = dict(user.preferences or {})
    prefs["dismissed_alerts"] = sorted(ids)
    user.preferences = prefs
    db.commit()


@router.get("")
def list_alerts(db: Session = Depends(get_db)) -> dict:
    return _view(db, repo.get_primary_user(db))


@router.post("/dismiss")
def dismiss(body: AlertDismiss, db: Session = Depends(get_db)) -> dict:
    user = repo.get_primary_user(db)
    live = {a.id for a in planning.all_alerts(db, user)}
    # Keep dismissals that still refer to a live alert; ignore ids that don't exist.
    _save(db, user, (planning.dismissed_alerts(user) | {body.id}) & live)
    return _view(db, user)


@router.post("/restore")
def restore(db: Session = Depends(get_db)) -> dict:
    user = repo.get_primary_user(db)
    _save(db, user, set())
    return _view(db, user)
