"""PayPal Subscriptions API v1 — read, cancel, suspend and re-activate a billing subscription.

Important limit: PayPal lets only the *merchant's* REST app manage a subscription through the
API. For a subscription with another merchant (e.g. Netflix billed via PayPal), the API returns
NOT_AUTHORIZED and the subscriber must cancel it in PayPal → Settings → Automatic payments.
FINORA reports that case honestly with a direct link instead of pretending it worked.
"""
from datetime import datetime
from decimal import Decimal

from app.integrations.paypal.client import PayPalCallError, PayPalClient

ACTIONS = {"cancel", "suspend", "activate"}


def _amount(sub: dict, plan: dict | None) -> tuple[Decimal | None, str | None]:
    last = (sub.get("billing_info") or {}).get("last_payment", {}).get("amount")
    if plan:
        for cycle in plan.get("billing_cycles", []):
            if cycle.get("tenure_type") == "REGULAR":
                price = (cycle.get("pricing_scheme") or {}).get("fixed_price")
                if price:
                    return Decimal(price["value"]), price.get("currency_code")
    if last:
        return Decimal(last["value"]), last.get("currency_code")
    return None, None


def fetch_subscription(pp: PayPalClient, subscription_id: str) -> dict:
    sub = pp.call("GET", f"/v1/billing/subscriptions/{subscription_id}")
    plan = None
    if sub.get("plan_id"):
        try:
            plan = pp.call("GET", f"/v1/billing/plans/{sub['plan_id']}")
        except PayPalCallError:
            plan = None  # plan details are optional; the subscription itself is what matters
    amount, currency = _amount(sub, plan)
    nxt = (sub.get("billing_info") or {}).get("next_billing_time")
    return {
        "id": sub["id"],
        "status": sub.get("status", "UNKNOWN"),
        "plan_id": sub.get("plan_id"),
        "name": (plan or {}).get("name") or f"PayPal subscription {sub['id']}",
        "amount": amount,
        "currency": currency,
        "next_billing_date": datetime.fromisoformat(nxt.replace("Z", "+00:00")).date() if nxt else None,
    }


def change_status(pp: PayPalClient, subscription_id: str, action: str, reason: str) -> None:
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {sorted(ACTIONS)}")
    pp.call("POST", f"/v1/billing/subscriptions/{subscription_id}/{action}", json={"reason": reason[:128]}, ok=(204, 200))
