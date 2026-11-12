from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api import (
    alerts, assistant, auth, checkout, crossborder, dashboard, data, evals, paypal, paypal_demo, settings, simulations,
    stress, subscriptions, transactions,
)
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine, ensure_columns
from app.core.limits import SECURITY_HEADERS
from app.services.seed import ensure_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    ensure_columns(engine)
    with SessionLocal() as db:
        ensure_user(db)
    yield


s = get_settings()
app = FastAPI(title=s.app_name, version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=True)



@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


# Sign in with PayPal is optional: no route requires a session, so every feature works signed out.
for r in (dashboard.router, transactions.router, simulations.router, settings.router, data.router, paypal.router,
          auth.router, checkout.router, subscriptions.router, assistant.router, alerts.router, crossborder.router,
          paypal_demo.router, stress.router, evals.router):
    app.include_router(r, prefix="/api")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root():
    # The API lives under /api; send visitors of the bare service URL to the interactive docs.
    return RedirectResponse(url="/docs")


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "environment": s.environment}
