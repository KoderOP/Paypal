"""Log in with PayPal (OAuth 2.0 authorization code + OpenID Connect userinfo).

Setup in the PayPal developer dashboard (sandbox app): enable "Log in with PayPal", add the
return URL `<FRONTEND_URL>/api/auth/paypal/callback`, and tick the "Full name" and "Email" scopes.
"""
from urllib.parse import urlencode

from app.core.config import Settings
from app.integrations.paypal.client import PayPalClient

SCOPES = "openid profile email"


def callback_url(settings: Settings) -> str:
    return f"{settings.public_api_url}/auth/paypal/callback"


def authorize_url(settings: Settings, state: str) -> str:
    query = urlencode({
        "flowEntry": "static",
        "client_id": settings.paypal_client_id or "",
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": callback_url(settings),
        "state": state,
    })
    return f"{settings.paypal_web_url}/signin/authorize?{query}"


def fetch_identity(pp: PayPalClient, code: str) -> dict:
    token = pp.exchange_code(code)["access_token"]
    info = pp.call("GET", "/v1/identity/openidconnect/userinfo", params={"schema": "openid"}, token=token)
    email = info.get("email") or next((e.get("value") for e in info.get("emails", []) if e.get("primary")), None)
    return {
        "paypal_user_id": info.get("user_id") or info.get("sub") or info.get("payer_id"),
        "name": info.get("name") or " ".join(p for p in (info.get("given_name"), info.get("family_name")) if p),
        "email": email,
        "verified": bool(info.get("email_verified") or info.get("verified_account")),
    }
