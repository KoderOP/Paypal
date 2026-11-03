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

    # AI layer (next phase) — model configurable, key only on the server.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # PayPal integration (sandbox by default).
    paypal_client_id: str | None = None
    paypal_client_secret: str | None = None
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
