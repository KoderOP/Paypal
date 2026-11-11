"""Cross-border freelancer view: foreign income, PayPal fees, conversion cost and FX risk."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.engine.crossborder import CrossBorder
from app.schemas.api import ReferenceRate
from app.services import planning
from app.services import repository as repo

router = APIRouter(prefix="/crossborder", tags=["cross-border"])


@router.get("", response_model=CrossBorder)
def overview(db: Session = Depends(get_db)):
    return planning.cross_border_view(db, repo.get_primary_user(db))


@router.put("/reference-rate", response_model=CrossBorder)
def set_reference_rate(body: ReferenceRate, db: Session = Depends(get_db)):
    """Optional market rate the user looked up (INR per unit), used only to estimate PayPal's conversion spread."""
    user = repo.get_primary_user(db)
    prefs = dict(user.preferences or {})
    rates = dict(prefs.get("fx_reference_rates") or {})
    if body.rate is None:
        rates.pop(body.currency, None)
    else:
        rates[body.currency] = str(body.rate)
    prefs["fx_reference_rates"] = rates
    user.preferences = prefs
    db.commit()
    return planning.cross_border_view(db, user)
