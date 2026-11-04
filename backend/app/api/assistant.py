from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.assistant import chat
from app.ai.llm import LlmClient, get_llm
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.api import ChatRequest
from app.services import repository as repo

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status")
def status():
    s = get_settings()
    return {"mode": "llm" if s.openai_api_key else "rules", "model": s.openai_model if s.openai_api_key else None,
            "guardrail": "Every rupee figure in an answer must come from an engine tool result."}


@router.post("/chat")
def assistant_chat(body: ChatRequest, db: Session = Depends(get_db), llm: LlmClient | None = Depends(get_llm)):
    user = repo.get_primary_user(db)
    repo.build_user_profile(db, user, repo.assumptions_for(user))  # 404 with a clear message when there's no data
    return chat([m.model_dump() for m in body.messages], db, user, llm)
