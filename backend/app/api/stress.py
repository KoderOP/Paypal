from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.engine.stress import StressReport, stress_test
from app.services import repository as repo

router = APIRouter(prefix="/stress", tags=["stress"])


@router.get("", response_model=StressReport)
def stress(db: Session = Depends(get_db)):
    user = repo.get_primary_user(db)
    a = repo.assumptions_for(user)
    return stress_test(repo.build_user_profile(db, user, a), repo.load_transactions(db, user), a)
