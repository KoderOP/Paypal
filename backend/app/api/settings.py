from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.paypal.client import paypal_runtime
from app.integrations.paypal.source import PayPalSource
from app.schemas.api import SettingsOut, SettingsUpdate
from app.services import repository as repo
from app.services.import_service import has_data

router = APIRouter(tags=["settings"])


def _settings_out(db: Session) -> SettingsOut:
    user = repo.get_primary_user(db)
    s = get_settings()
    return SettingsOut(
        user_name=user.name, currency=user.currency, data_source=(user.preferences or {}).get("data_source"),
        has_data=has_data(db, user), assumptions=repo.assumptions_for(user),
        paypal=PayPalSource(paypal_runtime()[0]).status(), ai_configured=bool(s.llm_settings),
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    return _settings_out(db)


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(422, "Name cannot be empty")
        user.name = body.name.strip()
    if body.safety_buffer is not None:
        prefs = dict(user.preferences or {})
        prefs["safety_buffer"] = str(body.safety_buffer)
        user.preferences = prefs
    db.commit()
    return _settings_out(db)
