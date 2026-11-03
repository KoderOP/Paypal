"""Startup bootstrap. FINORA never seeds financial data: users bring their own via upload,
PayPal sync, or by choosing one of the clearly-labelled demo files."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.data.models import User


def ensure_user(db: Session) -> User:
    user = db.scalars(select(User).order_by(User.id).limit(1)).first()
    if user is None:
        user = User(name="", currency="INR", preferences={"safety_buffer": str(get_settings().default_safety_buffer)})
        db.add(user)
        db.commit()
    return user
