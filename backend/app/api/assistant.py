from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.assistant import chat
from app.ai.llm import LlmClient, get_llm
from app.core.config import get_settings
from app.core.database import get_db
from app.core.limits import RateLimit
from app.schemas.api import ChatRequest
from app.services import repository as repo

router = APIRouter(prefix="/assistant", tags=["assistant"])
chat_limit = RateLimit(get_settings().chat_rate_limit_per_minute, 60)


@router.get("/status")
def status():
    cfg = get_settings().llm_settings
    return {"mode": "llm" if cfg else "rules", "provider": cfg["provider"] if cfg else None,
            "model": cfg["models"][0] if cfg else None, "fallback_models": cfg["models"][1:] if cfg else [],
            "guardrail": "Every amount, percentage and date in an answer must come from an engine tool result.",
            "actions": "The agent can prepare a PayPal checkout; only the user can confirm and approve it."}


@router.post("/chat", dependencies=[Depends(chat_limit)])
def assistant_chat(body: ChatRequest, db: Session = Depends(get_db), llm: LlmClient | None = Depends(get_llm)):
    user = repo.get_primary_user(db)
    repo.build_user_profile(db, user, repo.assumptions_for(user))  # 404 with a clear message when there's no data
    return chat([m.model_dump() for m in body.messages], db, user, llm,
                body.context.model_dump() if body.context else None)
