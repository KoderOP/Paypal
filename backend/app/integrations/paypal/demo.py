"""FINORA's built-in PayPal demo: an in-process stand-in for the PayPal REST API.

Used automatically when no PayPal credentials are configured (PAYPAL_DEMO_MODE, on by default),
so every PayPal feature works end to end on a laptop. It answers the same calls FINORA makes to
PayPal through the same client code (OAuth, Log in with PayPal userinfo, Orders v2, Subscriptions
v1, Transaction Search and Balances). Buyer-facing steps happen on FINORA's own clearly labelled
demo pages (/paypal-demo/...). It never contacts PayPal and moves no real money.

State lives in the `demo_paypal_objects` table, so it survives restarts.
"""
import hashlib
import json
import secrets
from datetime import date, datetime, time, timezone
from urllib.parse import parse_qs

import httpx
from sqlalchemy import select

from app.core.config import DEMO_PAYPAL_HOST, Settings, get_settings
from app.core.database import SessionLocal
from app.data.demo_files import _ref
from app.data.models import DemoPayPalObject
from app.data.sources.synthetic import TARGET_CURRENT_BALANCE, SyntheticSource
from app.engine.types import add_months

DEMO_BASE_URL = f"https://{DEMO_PAYPAL_HOST}"
APP_TOKEN = "demo-app-token"
USER_TOKEN_PREFIX = "demo-user-"

# Demo subscriptions you can link on the Subscriptions page. Netflix and Spotify match the demo
# data's detected subscriptions; the gym has no payment history (it shows the PayPal-only path).
DEMO_SUBSCRIPTIONS = [
    {"id": "I-DEMONETFLIX01", "plan_id": "P-DEMO-NETFLIX", "name": "Netflix Premium", "amount": "649.00", "day": 7},
    {"id": "I-DEMOSPOTIFY02", "plan_id": "P-DEMO-SPOTIFY", "name": "Spotify Premium", "amount": "119.00", "day": 12},
    {"id": "I-DEMOGYMPRO003", "plan_id": "P-DEMO-GYM", "name": "Cult Gym Pro", "amount": "1499.00", "day": 15},
]
TRANSITIONS = {"cancel": ({"ACTIVE", "SUSPENDED"}, "CANCELLED"), "suspend": ({"ACTIVE"}, "SUSPENDED"),
               "activate": ({"SUSPENDED"}, "ACTIVE")}


def demo_settings(base: Settings) -> Settings:
    """Settings that point the normal PayPal client at the demo."""
    return base.model_copy(update={"paypal_client_id": "demo-client", "paypal_client_secret": "demo-secret",
                                   "paypal_base_url": DEMO_BASE_URL})


def today() -> date:
    from app.services import repository  # late import: repository imports the database layer

    return repository.today()


# ---- storage --------------------------------------------------------------------------------------
def _get(kind: str, key: str) -> dict | None:
    with SessionLocal() as db:
        row = db.scalars(select(DemoPayPalObject).where(DemoPayPalObject.kind == kind, DemoPayPalObject.key == key)).first()
        return dict(row.data) if row else None


def _put(kind: str, key: str, data: dict) -> dict:
    with SessionLocal() as db:
        row = db.scalars(select(DemoPayPalObject).where(DemoPayPalObject.kind == kind, DemoPayPalObject.key == key)).first()
        if row is None:
            db.add(DemoPayPalObject(kind=kind, key=key, data=data))
        else:
            row.data = data
        db.commit()
    return data


def get_order(order_id: str) -> dict | None:
    return _get("order", order_id)


def set_order(order_id: str, data: dict) -> dict:
    return _put("order", order_id, data)


def issue_auth_code(name: str, email: str) -> str:
    code = "DEMOCODE-" + secrets.token_urlsafe(12)
    _put("auth_code", code, {"name": name, "email": email, "used": False})
    return code


def subscription(sid: str) -> dict | None:
    base = next((s for s in DEMO_SUBSCRIPTIONS if s["id"] == sid), None)
    if base is None:
        return None
    state = _get("subscription", sid) or {"status": "ACTIVE"}
    return {**base, **state}


def subscriptions() -> list[dict]:
    return [subscription(s["id"]) for s in DEMO_SUBSCRIPTIONS]


def _next_billing(day: int) -> date:
    t = today()
    d = add_months(t.replace(day=1), 0, day)
    return d if d >= t else add_months(d, 1, day)


# ---- HTTP handler -----------------------------------------------------------------------------------
def _json(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body) if body is not None else httpx.Response(status)


def _error(status: int, name: str, description: str) -> httpx.Response:
    return _json(status, {"name": name, "message": description, "details": [{"issue": name, "description": description}]})


def handle(request: httpx.Request) -> httpx.Response:
    path, method = request.url.path, request.method
    if path == "/v1/oauth2/token":
        return _token(request)
    auth = request.headers.get("Authorization", "")
    if path == "/v1/identity/openidconnect/userinfo":
        return _userinfo(auth)
    if auth != f"Bearer {APP_TOKEN}":
        return _error(401, "AUTHENTICATION_FAILURE", "Invalid access token")
    if path == "/v2/checkout/orders" and method == "POST":
        return _create_order(request)
    if path.startswith("/v2/checkout/orders/"):
        parts = path.split("/")
        if len(parts) == 6 and parts[5] == "capture" and method == "POST":
            return _capture(parts[4])
        if len(parts) == 5 and method == "GET":
            order = get_order(parts[4])
            return _json(200, _order_view(parts[4], order)) if order else _error(404, "RESOURCE_NOT_FOUND", "Order not found")
    if path.startswith("/v1/billing/plans/"):
        plan = next((s for s in DEMO_SUBSCRIPTIONS if s["plan_id"] == path.split("/")[4]), None)
        if not plan:
            return _error(404, "RESOURCE_NOT_FOUND", "Plan not found")
        return _json(200, {"id": plan["plan_id"], "name": plan["name"], "billing_cycles": [
            {"tenure_type": "REGULAR", "pricing_scheme": {"fixed_price": {"value": plan["amount"], "currency_code": "INR"}}}]})
    if path.startswith("/v1/billing/subscriptions/"):
        return _subscription(request, path.split("/"))
    if path == "/v1/reporting/transactions":
        return _transactions(request)
    if path == "/v1/reporting/balances":
        return _json(200, {"balances": [{"currency": "INR", "primary": True, "total_balance": {
            "currency_code": "INR", "value": f"{TARGET_CURRENT_BALANCE:.2f}"}}]})
    return _error(404, "NOT_FOUND", f"The PayPal demo doesn't implement {method} {path}")


def _token(request: httpx.Request) -> httpx.Response:
    form = parse_qs(request.content.decode())
    if form.get("grant_type") == ["client_credentials"]:
        return _json(200, {"access_token": APP_TOKEN, "token_type": "Bearer", "expires_in": 32400})
    if form.get("grant_type") == ["authorization_code"]:
        code = (form.get("code") or [""])[0]
        data = _get("auth_code", code)
        if not data or data.get("used"):
            return _json(400, {"error": "invalid_grant", "error_description": "Authorization code is invalid or used"})
        _put("auth_code", code, {**data, "used": True})
        return _json(200, {"access_token": USER_TOKEN_PREFIX + code, "token_type": "Bearer", "expires_in": 3600})
    return _json(400, {"error": "unsupported_grant_type"})


def _userinfo(auth: str) -> httpx.Response:
    code = auth.removeprefix("Bearer ").removeprefix(USER_TOKEN_PREFIX)
    data = _get("auth_code", code) if auth.startswith(f"Bearer {USER_TOKEN_PREFIX}") else None
    if not data:
        return _error(401, "AUTHENTICATION_FAILURE", "Invalid user token")
    uid = hashlib.sha1(data["email"].lower().encode()).hexdigest()[:16]
    return _json(200, {"user_id": f"demo:{uid}", "name": data["name"], "email": data["email"], "email_verified": True})


def _order_view(order_id: str, o: dict) -> dict:
    view = {"id": order_id, "status": o["status"], "intent": "CAPTURE",
            "purchase_units": [{"reference_id": o.get("reference"), "description": o.get("description"),
                                "amount": {"currency_code": o["currency"], "value": o["value"]}}],
            "links": [{"rel": "payer-action", "href": o["approve_url"], "method": "GET"}]}
    if o.get("capture_id"):
        view["purchase_units"][0]["payments"] = {"captures": [{"id": o["capture_id"], "status": "COMPLETED"}]}
    return view


def _create_order(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content or b"{}")
    req_id = request.headers.get("PayPal-Request-Id")
    if req_id and (prev := _get("order_request", req_id)):
        return _json(200, _order_view(prev["order_id"], get_order(prev["order_id"])))  # idempotent replay
    unit = (body.get("purchase_units") or [{}])[0]
    amount = unit.get("amount") or {}
    ctx = ((body.get("payment_source") or {}).get("paypal") or {}).get("experience_context") or {}
    if not amount.get("value") or not ctx.get("return_url"):
        return _error(422, "UNPROCESSABLE_ENTITY", "amount and return_url are required")
    order_id = "DEMO" + secrets.token_hex(6).upper()
    approve = f"{get_settings().frontend_url.rstrip('/')}/paypal-demo/checkout?token={order_id}"
    set_order(order_id, {"status": "PAYER_ACTION_REQUIRED", "value": amount["value"], "currency": amount.get("currency_code", "INR"),
                         "description": unit.get("description"), "reference": unit.get("reference_id"),
                         "return_url": ctx["return_url"], "cancel_url": ctx.get("cancel_url"), "approve_url": approve,
                         "brand": ctx.get("brand_name"), "funding": None, "capture_id": None})
    if req_id:
        _put("order_request", req_id, {"order_id": order_id})
    return _json(201, _order_view(order_id, get_order(order_id)))


def _capture(order_id: str) -> httpx.Response:
    o = get_order(order_id)
    if not o:
        return _error(404, "RESOURCE_NOT_FOUND", "Order not found")
    if o["status"] == "COMPLETED":
        return _json(201, {**_order_view(order_id, o), "status": "COMPLETED"})
    if o["status"] != "APPROVED":
        return _error(422, "ORDER_NOT_APPROVED", "Payer has not yet approved the Order for payment.")
    o.update(status="COMPLETED", capture_id="DEMOCAP" + secrets.token_hex(6).upper())
    set_order(order_id, o)
    return _json(201, _order_view(order_id, o))


def _subscription(request: httpx.Request, parts: list[str]) -> httpx.Response:
    sid = parts[4]
    sub = subscription(sid)
    if sub is None:
        return _error(404, "RESOURCE_NOT_FOUND", f"Subscription {sid} not found. Demo IDs: "
                      + ", ".join(s["id"] for s in DEMO_SUBSCRIPTIONS))
    if len(parts) == 6 and request.method == "POST":
        allowed, new = TRANSITIONS.get(parts[5], (set(), ""))
        if not new:
            return _error(404, "NOT_FOUND", "Unknown action")
        if sub["status"] not in allowed:
            return _error(422, "SUBSCRIPTION_STATUS_INVALID", f"Can't {parts[5]} a subscription that is {sub['status']}.")
        _put("subscription", sid, {"status": new, "changed_on": today().isoformat()})
        return _json(204)
    billing: dict = {"last_payment": {"amount": {"value": sub["amount"], "currency_code": "INR"}}}
    if sub["status"] == "ACTIVE":
        nxt = datetime.combine(_next_billing(sub["day"]), time(10), tzinfo=timezone.utc)
        billing["next_billing_time"] = nxt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return _json(200, {"id": sid, "status": sub["status"], "plan_id": sub["plan_id"], "billing_info": billing})


def _transactions(request: httpx.Request) -> httpx.Response:
    """Transaction Search over the same synthetic history as the demo CSV, with matching transaction ids."""
    p = request.url.params
    start = date.fromisoformat(p.get("start_date", "")[:10])
    end = date.fromisoformat(p.get("end_date", "")[:10])
    txns = SyntheticSource(today(), get_settings().demo_seed).fetch()
    details = []
    for t in txns:
        if not start <= t.posted_on <= end:
            continue
        details.append({
            "transaction_info": {
                "transaction_id": _ref(t, 17), "transaction_event_code": "T0011" if t.amount > 0 else "T0006",
                "transaction_initiation_date": f"{t.posted_on.isoformat()}T10:00:00+0000",
                "transaction_amount": {"currency_code": "INR", "value": f"{t.amount:.2f}"},
                "transaction_status": "S", "transaction_subject": t.description,
            },
            "payer_info": {"payer_name": {"alternate_full_name": t.merchant}},
        })
    return _json(200, {"transaction_details": details, "total_items": len(details), "total_pages": 1, "page": 1})


def transport() -> httpx.MockTransport:
    return httpx.MockTransport(handle)
