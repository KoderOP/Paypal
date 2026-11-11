"""Environment-based configuration. Never hardcode secrets; read them from env / .env."""
from decimal import Decimal
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


DEMO_PAYPAL_HOST = "paypal-demo.finora.local"  # never resolved: the demo is served in-process


_BACKEND = Path(__file__).resolve().parents[2]
# Repo-root .env (shared with docker-compose) first, then backend/.env; later files win, real env vars win over both.
# FINORA_IGNORE_ENV_FILES=1 (set by the test suite) reads real environment variables only.
ENV_FILES = () if os.environ.get("FINORA_IGNORE_ENV_FILES") else (_BACKEND.parent / ".env", _BACKEND / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FINORA API"
    environment: str = "development"

    # SQLite is the zero-setup local fallback; use postgresql+psycopg://... in docker / prod.
    database_url: str = "sqlite:///./finora.db"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Seed used to generate the downloadable demo files (synthetic data).
    demo_seed: int = 42

    # Forecast defaults (overridable per request).
    forecast_horizon_days: int = 90
    default_safety_buffer: Decimal = Decimal("20000")

    # Public URL of the web app. PayPal redirects back here (the Vite dev server proxies /api).
    frontend_url: str = "http://localhost:5173"

    # Sessions for the optional Sign in with PayPal (open to any PayPal account; no feature needs it).
    # Set a long random SESSION_SECRET outside development so sign-ins survive restarts.
    session_secret: str | None = None
    session_max_age_days: int = 7

    # AI agent — keys only on the server. Groq is the primary provider (OpenAI-compatible Chat
    # Completions with tool calling). Without any key the agent uses a deterministic rule-based
    # planner, so the product still works offline (and in tests).
    llm_provider: str = "auto"  # auto | groq | openai | none
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    # Tried when the primary model is unavailable (decommissioned, not enabled, over capacity).
    groq_fallback_model: str | None = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_timeout_seconds: float = 30.0
    chat_rate_limit_per_minute: int = 20  # per client address; 0 disables
    # Any other OpenAI-compatible endpoint (kept for portability; Groq wins when both keys are set).
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # PayPal integration (sandbox by default).
    paypal_client_id: str | None = None
    paypal_client_secret: str | None = None
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    # Currency for Orders API checkouts. Empty = the user's profile currency (INR by default).
    paypal_checkout_currency: str | None = None
    # Needed when the checkout currency differs from the profile currency (e.g. USD sandbox, INR profile):
    # home-currency units per 1 checkout unit, e.g. 84 (INR per USD). FINORA never fetches market rates;
    # without this, a cross-currency checkout is refused rather than sending ₹75,000 as $75,000.
    paypal_checkout_fx_rate: Decimal | None = None
    # Without PayPal credentials, use FINORA's built-in PayPal demo (a local simulation of the REST
    # API: orders, sign-in, subscriptions, transaction search). Labelled as a demo everywhere.
    paypal_demo_mode: bool = True

    @property
    def llm_settings(self) -> dict | None:
        """Resolved provider config: {provider, api_key, base_url, models}, or None for rules mode."""
        p = self.llm_provider.lower()
        if p in ("auto", "groq") and self.groq_api_key:
            models = [self.groq_model] + ([self.groq_fallback_model] if self.groq_fallback_model
                                          and self.groq_fallback_model != self.groq_model else [])
            return {"provider": "groq", "api_key": self.groq_api_key, "base_url": self.groq_base_url, "models": models}
        if p in ("auto", "openai") and self.openai_api_key:
            return {"provider": "openai", "api_key": self.openai_api_key, "base_url": self.openai_base_url,
                    "models": [self.openai_model]}
        return None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def paypal_available(self) -> bool:
        """PayPal features work: real credentials, or the built-in demo."""
        return self.paypal_configured or self.paypal_demo_mode

    @property
    def paypal_environment(self) -> str:
        if DEMO_PAYPAL_HOST in self.paypal_base_url or (not self.paypal_configured and self.paypal_demo_mode):
            return "demo"
        return "sandbox" if "sandbox" in self.paypal_base_url else "live"

    @property
    def paypal_web_url(self) -> str:
        """Browser-facing PayPal site (sign-in, approval, account settings)."""
        if self.paypal_environment == "demo":
            return f"{self.frontend_url.rstrip('/')}/paypal-demo"
        return "https://www.sandbox.paypal.com" if self.paypal_environment == "sandbox" else "https://www.paypal.com"

    @property
    def public_api_url(self) -> str:
        return f"{self.frontend_url.rstrip('/')}/api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
