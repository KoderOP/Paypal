"""Environment-based configuration. Never hardcode secrets; read them from env / .env."""
from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # AI assistant — key only on the server. Without a key the assistant uses a deterministic
    # rule-based intent parser, so it still works offline (and in tests).
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # PayPal integration (sandbox by default).
    paypal_client_id: str | None = None
    paypal_client_secret: str | None = None
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    # Currency for Orders API checkouts. Empty = the user's profile currency (INR by default).
    paypal_checkout_currency: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def paypal_environment(self) -> str:
        return "sandbox" if "sandbox" in self.paypal_base_url else "live"

    @property
    def paypal_web_url(self) -> str:
        """Browser-facing PayPal site (sign-in, approval, account settings)."""
        return "https://www.sandbox.paypal.com" if self.paypal_environment == "sandbox" else "https://www.paypal.com"

    @property
    def public_api_url(self) -> str:
        return f"{self.frontend_url.rstrip('/')}/api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
