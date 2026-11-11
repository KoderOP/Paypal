"""Buyer-facing steps of the built-in PayPal demo (approve a checkout, sign in).

These stand in for the pages a buyer would see on paypal.com. They exist only in demo mode
(no PayPal credentials configured) and return 404 otherwise. FINORA's frontend renders them as
clearly labelled demo pages; no real money moves and PayPal is never contacted.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.integrations.paypal import demo
from app.integrations.paypal.identity import callback_url

router = APIRouter(prefix="/paypal-demo", tags=["paypal-demo"])


class Approve(BaseModel):
    funding: str = Field("paypal", pattern="^(paypal|paylater)$")


class Authorize(BaseModel):
    state: str = Field(min_length=1, max_length=200)
    redirect_uri: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_demo() -> None:
    if get_settings().paypal_environment != "demo":
        raise HTTPException(404, "The PayPal demo is only available when no PayPal credentials are configured.")


def _with(url: str, **params: str) -> str:
    return f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"


@router.get("/status")
def status():
    s = get_settings()
    demo_on = s.paypal_environment == "demo"
    return {"demo": demo_on, "environment": s.paypal_environment,
            "subscriptions": [{"id": x["id"], "name": x["name"], "amount": float(x["amount"]), "status": x["status"]}
                              for x in demo.subscriptions()] if demo_on else []}


@router.get("/orders/{order_id}")
def order(order_id: str):
    _require_demo()
    o = demo.get_order(order_id)
    if not o:
        raise HTTPException(404, "Demo order not found")
    return {"id": order_id, "status": o["status"], "amount": float(o["value"]), "currency": o["currency"],
            "description": o.get("description"), "merchant": o.get("brand") or "FINORA", "funding": o.get("funding")}


@router.post("/orders/{order_id}/approve")
def approve(order_id: str, body: Approve):
    _require_demo()
    o = demo.get_order(order_id)
    if not o:
        raise HTTPException(404, "Demo order not found")
    if o["status"] == "PAYER_ACTION_REQUIRED":
        o.update(status="APPROVED", funding=body.funding)
        demo.set_order(order_id, o)
    elif o["status"] != "APPROVED":
        raise HTTPException(409, f"This order is {o['status'].lower()} and can't be approved.")
    return {"redirect": _with(o["return_url"], token=order_id, PayerID="DEMOPAYER")}


@router.post("/orders/{order_id}/cancel")
def cancel(order_id: str):
    _require_demo()
    o = demo.get_order(order_id)
    if not o:
        raise HTTPException(404, "Demo order not found")
    if o["status"] in ("PAYER_ACTION_REQUIRED", "APPROVED"):
        o["status"] = "VOIDED"
        demo.set_order(order_id, o)
    return {"redirect": _with(o.get("cancel_url") or o["return_url"], token=order_id)}


@router.post("/authorize")
def authorize(body: Authorize):
    """Demo 'Log in with PayPal': issue an authorization code for the identity the user typed in."""
    _require_demo()
    if body.redirect_uri != callback_url(get_settings()):
        raise HTTPException(400, "redirect_uri doesn't match FINORA's sign-in callback")  # no open redirects
    code = demo.issue_auth_code(body.name.strip(), body.email.strip())
    return {"redirect": _with(body.redirect_uri, code=code, state=body.state)}
