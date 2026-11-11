"""PayPal Orders API v2 — checkout with an explicit confirmation step.

`user_action=CONTINUE` makes PayPal's button read "Continue" rather than "Pay now": the buyer
approves on PayPal, comes back to FINORA, reviews the simulated impact again and only then
confirms, which triggers the capture. Pay Later is offered by PayPal on its approval page
(the buyer chooses it there); FINORA cannot force or pre-approve credit.
"""
from decimal import Decimal

from app.integrations.paypal.client import PayPalClient


def create_order(pp: PayPalClient, *, amount: Decimal, currency: str, label: str, reference: str,
                 return_url: str, cancel_url: str, request_id: str) -> dict:
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": reference,
            "description": label[:127],
            "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
        }],
        "payment_source": {"paypal": {"experience_context": {
            "brand_name": "FINORA",
            "user_action": "CONTINUE",
            "shipping_preference": "NO_SHIPPING",
            "return_url": return_url,
            "cancel_url": cancel_url,
        }}},
    }
    res = pp.call("POST", "/v2/checkout/orders", json=body, idempotency_key=request_id)
    approve = next((l["href"] for l in res.get("links", []) if l.get("rel") in ("payer-action", "approve")), None)
    return {"id": res["id"], "status": res.get("status"), "approve_url": approve}


def get_order(pp: PayPalClient, order_id: str) -> dict:
    return pp.call("GET", f"/v2/checkout/orders/{order_id}")


def capture_order(pp: PayPalClient, order_id: str, request_id: str) -> dict:
    res = pp.call("POST", f"/v2/checkout/orders/{order_id}/capture", json={}, idempotency_key=request_id)
    captures = [c for pu in res.get("purchase_units", []) for c in (pu.get("payments") or {}).get("captures", [])]
    cap = captures[0] if captures else {}
    return {"status": res.get("status"), "capture_id": cap.get("id"), "capture_status": cap.get("status")}
