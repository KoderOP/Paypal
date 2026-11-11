"""Sign in with PayPal — optional, and open to any PayPal account.

Flow: /auth/paypal/login sets a signed, short-lived `state` cookie and redirects to PayPal →
PayPal redirects to /auth/paypal/callback with `code` + `state` → the state is verified, the
code is exchanged server-side, the OpenID userinfo is read, and a signed HttpOnly session
cookie carrying that person's identity is issued.

Signing in is never required: no API route checks the session, so every feature works signed
out. Anyone with a PayPal account can sign in; the identity lives in their own session cookie,
so different people can sign in and out freely.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import SESSION_COOKIE, STATE_COOKIE, new_state, sign, verify
from app.integrations.paypal.client import PayPalClient, get_paypal_client
from app.integrations.paypal.identity import authorize_url, callback_url, fetch_identity
from app.integrations.paypal.source import PayPalApiError
from app.services import repository as repo

router = APIRouter(prefix="/auth", tags=["auth"])
STATE_MAX_AGE = 600
IDENTITY_FIELDS = ("paypal_user_id", "name", "email", "verified")


def session_identity(request: Request) -> dict | None:
    """The PayPal identity in a valid (signed, unexpired) session cookie, if any."""
    payload = verify(request.cookies.get(SESSION_COOKIE))
    if not payload or not payload.get("paypal_user_id"):
        return None
    return {k: payload.get(k) for k in IDENTITY_FIELDS}


def _frontend(path: str, **query: str) -> RedirectResponse:
    url = f"{get_settings().frontend_url.rstrip('/')}{path}"
    return RedirectResponse(f"{url}?{urlencode(query)}" if query else url, status_code=303)


def _cookie_kwargs() -> dict:
    return {"httponly": True, "samesite": "lax", "secure": get_settings().frontend_url.startswith("https"), "path": "/"}


@router.get("/me")
def me(request: Request):
    s = get_settings()
    ident = session_identity(request)
    return {
        "authenticated": ident is not None,
        "login_available": s.paypal_available,
        "demo": s.paypal_environment == "demo",
        "environment": s.paypal_environment,
        "identity": ident,
        "callback_url": callback_url(s),
        "ephemeral_sessions": not s.session_secret,
    }


@router.get("/paypal/login")
def login():
    s = get_settings()
    if not s.paypal_available:
        return _frontend("/signin", error="not_configured")
    state = new_state()
    res = RedirectResponse(authorize_url(s, state), status_code=303)
    res.set_cookie(STATE_COOKIE, sign({"state": state}, STATE_MAX_AGE), max_age=STATE_MAX_AGE, **_cookie_kwargs())
    return res


@router.get("/paypal/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             db: Session = Depends(get_db), pp: PayPalClient = Depends(get_paypal_client)):
    saved = verify(request.cookies.get(STATE_COOKIE))
    if error:
        return _frontend("/signin", error="denied")
    if not code or not state or not saved or saved.get("state") != state:
        return _frontend("/signin", error="state_mismatch")
    try:
        ident = fetch_identity(pp, code)
    except PayPalApiError:
        return _frontend("/signin", error="paypal_error")
    if not ident.get("paypal_user_id"):
        return _frontend("/signin", error="paypal_error")

    # Convenience only: greet by name if the profile has none yet. Never blocks anyone.
    user = repo.get_primary_user(db)
    if not user.name.strip() and ident.get("name"):
        user.name = ident["name"][:120]
        db.commit()

    max_age = get_settings().session_max_age_days * 86400
    res = _frontend("/", signed_in="1")
    res.set_cookie(SESSION_COOKIE, sign({k: ident.get(k) for k in IDENTITY_FIELDS}, max_age), max_age=max_age,
                   **_cookie_kwargs())
    res.delete_cookie(STATE_COOKIE, path="/")
    return res


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
