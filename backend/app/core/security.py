"""Tamper-proof, expiring tokens for session and OAuth-state cookies (HMAC-SHA256, stdlib only).

Format: base64url(json payload) "." base64url(hmac). The payload carries `exp` (unix seconds).
Without SESSION_SECRET a random per-process key is used: fine for local development, but
sessions end when the server restarts.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import get_settings

SESSION_COOKIE = "finora_session"
STATE_COOKIE = "finora_oauth_state"
_EPHEMERAL_KEY = secrets.token_bytes(32)


def _key() -> bytes:
    secret = get_settings().session_secret
    return secret.encode() if secret else _EPHEMERAL_KEY


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict, max_age_seconds: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + max_age_seconds}, separators=(",", ":")).encode())
    mac = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def verify(token: str | None) -> dict | None:
    if not token or token.count(".") != 1:
        return None
    body, mac = token.split(".")
    expected = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def new_state() -> str:
    return secrets.token_urlsafe(24)
