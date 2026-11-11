"""Shared PayPal REST client (OAuth2 + JSON calls) for Orders, Subscriptions and Identity.

Used as a FastAPI dependency (`get_paypal_client`) so tests can inject an `httpx.MockTransport`.
Secrets never leave the server; the browser only ever sees PayPal approval / sign-in URLs.
"""
import uuid

import httpx

from app.core.config import Settings, get_settings
from app.integrations.paypal.source import PayPalApiError, PayPalNotConfigured

NOT_CONFIGURED = ("PayPal isn't configured. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox app) to "
                  "backend/.env and restart the backend.")


class PayPalClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self._token: str | None = None

    @property
    def configured(self) -> bool:
        return self.settings.paypal_configured

    def _http(self) -> httpx.Client:
        return httpx.Client(base_url=self.settings.paypal_base_url, timeout=30, transport=self.transport)

    def _require(self) -> None:
        if not self.configured:
            raise PayPalNotConfigured(NOT_CONFIGURED)

    def app_token(self) -> str:
        """Client-credentials token for calls made as the FINORA app."""
        self._require()
        if self._token is None:
            with self._http() as h:
                r = h.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                           auth=(self.settings.paypal_client_id or "", self.settings.paypal_client_secret or ""))
            if r.status_code != 200:
                raise PayPalApiError(f"PayPal authentication failed ({r.status_code}). Check your client ID and secret.")
            self._token = r.json()["access_token"]
        return self._token

    def exchange_code(self, code: str) -> dict:
        """Authorization-code grant for Log in with PayPal."""
        self._require()
        with self._http() as h:
            r = h.post("/v1/oauth2/token", data={"grant_type": "authorization_code", "code": code},
                       auth=(self.settings.paypal_client_id or "", self.settings.paypal_client_secret or ""))
        if r.status_code != 200:
            raise PayPalApiError(f"PayPal sign-in failed ({r.status_code}): {_reason(r)}")
        return r.json()

    def call(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None,
             token: str | None = None, idempotency_key: str | None = None, ok: tuple[int, ...] = (200, 201)) -> dict:
        headers = {"Authorization": f"Bearer {token or self.app_token()}", "Content-Type": "application/json"}
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key
        with self._http() as h:
            r = h.request(method, path, json=json, params=params, headers=headers)
        if r.status_code not in ok:
            raise PayPalCallError(r.status_code, _name(r), f"PayPal API error {r.status_code}: {_reason(r)}")
        return r.json() if r.content else {}


class PayPalCallError(PayPalApiError):
    def __init__(self, status: int, name: str, message: str):
        super().__init__(message)
        self.status = status
        self.name = name


def _name(r: httpx.Response) -> str:
    try:
        return r.json().get("name") or r.json().get("error") or ""
    except ValueError:
        return ""


def _reason(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return r.text[:200]
    detail = (body.get("details") or [{}])[0]
    return (detail.get("description") or body.get("message") or body.get("error_description")
            or body.get("name") or str(body))[:300]


def new_request_id() -> str:
    return str(uuid.uuid4())


def paypal_runtime() -> tuple[Settings, httpx.BaseTransport | None]:
    """Effective PayPal settings + transport: real PayPal when credentials exist, otherwise the built-in demo."""
    s = get_settings()
    if s.paypal_configured or not s.paypal_demo_mode:
        return s, None
    from app.integrations.paypal import demo  # late import: demo uses the database layer

    return demo.demo_settings(s), demo.transport()


def get_paypal_client() -> PayPalClient:
    settings, transport = paypal_runtime()
    return PayPalClient(settings, transport)
