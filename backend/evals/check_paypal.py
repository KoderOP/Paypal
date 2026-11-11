"""PayPal Sandbox verification: real OAuth, a real Orders v2 order, and (after you approve it) a real capture.

    python -m evals.check_paypal                 # 1. token + create a USD 1.00 sandbox order, prints the approval link
    #   open the link, log in with a SANDBOX *personal* (buyer) account, approve
    python -m evals.check_paypal --capture ID    # 2. capture that order, prints the capture id and status

Uses the app's own PayPal client code (app/integrations/paypal). Refuses to run against live PayPal.
To verify the full product path instead, run the app and pay from Ask FINORA (see docs/DEMO.md).
"""
import argparse
import sys
from decimal import Decimal

from app.core.config import get_settings
from app.integrations.paypal.client import PayPalClient, new_request_id
from app.integrations.paypal.orders import capture_order, create_order, get_order
from app.integrations.paypal.source import PayPalApiError


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", metavar="ORDER_ID")
    ap.add_argument("--amount", default="1.00")
    ap.add_argument("--currency", default="USD")
    args = ap.parse_args()
    s = get_settings()
    if not s.paypal_configured:
        print("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not set (sandbox app: developer.paypal.com → Apps & Credentials).")
        return 1
    if "sandbox" not in s.paypal_base_url:
        print(f"Refusing: PAYPAL_BASE_URL is {s.paypal_base_url}, not the sandbox.")
        return 1
    pp = PayPalClient(s)
    try:
        pp.app_token()
        print(f"OAuth: OK ({s.paypal_base_url})")
        if args.capture:
            o = get_order(pp, args.capture)
            print(f"order {args.capture}: {o.get('status')}")
            res = capture_order(pp, args.capture, new_request_id())
            print(f"capture: {res['status']} · capture id {res['capture_id']} · {res['capture_status']}")
            return 0 if res["status"] == "COMPLETED" else 2
        res = create_order(pp, amount=Decimal(args.amount), currency=args.currency, label="FINORA sandbox check",
                           reference="finora-check", return_url=f"{s.public_api_url}/checkout/return",
                           cancel_url=f"{s.public_api_url}/checkout/cancel", request_id=new_request_id())
        print(f"order created: {res['id']} ({res['status']}) for {args.currency} {args.amount}")
        print(f"approve (sandbox buyer account): {res['approve_url']}")
        print(f"then: python -m evals.check_paypal --capture {res['id']}")
        print("(After approval PayPal redirects to FINORA's /checkout/return; it's fine if the app isn't running.)")
        return 0
    except PayPalApiError as exc:
        print(f"PayPal error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
