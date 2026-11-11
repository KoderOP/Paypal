from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    alerts, assistant, auth, checkout, crossborder, dashboard, data, paypal, settings, simulations, subscriptions,
    transactions,
)
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.services.seed import ensure_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_user(db)
    yield


s = get_settings()
app = FastAPI(title=s.app_name, version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=True)

# Sign in with PayPal is optional: no route requires a session, so every feature works signed out.
for r in (dashboard.router, transactions.router, simulations.router, settings.router, data.router, paypal.router,
          auth.router, checkout.router, subscriptions.router, assistant.router, alerts.router, crossborder.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "environment": s.environment}
