"""PayPal REST integration (Transaction Search API).

Flow: OAuth2 client-credentials → GET /v1/reporting/transactions in ≤31-day windows
(paged) → normalise each `transaction_info` into a `NormalizedTransaction`.
The current balance comes from GET /v1/reporting/balances so the opening balance can be
back-solved — balances stay derived from transactions, as everywhere else in FINORA.

Notes
- Requires the REST app to have *Transaction Search* enabled; PayPal may delay new
  transactions by up to ~3 hours in this API.
- Read-only. FINORA never initiates a PayPal payment without explicit user confirmation.
- We never fabricate PayPal data: without credentials this source refuses to run.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from app.core.config import Settings
from app.core.money import money
from app.data.categorize import categorize
from app.data.sources.base import NormalizedTransaction

EVENT_LABELS = {
    "T00": "PayPal payment", "T01": "Non-payment fee", "T02": "Currency conversion", "T03": "Bank deposit",
    "T04": "Bank withdrawal", "T05": "Debit card", "T06": "Credit card withdrawal", "T07": "Credit card deposit",
    "T11": "Reversal", "T12": "Adjustment", "T15": "Hold", "T17": "Bank deposit", "T22": "Bank transfer",
}
WINDOW_DAYS = 31


class PayPalNotConfigured(RuntimeError):
    pass


class PayPalApiError(RuntimeError):
    pass


class PayPalSource:
    name = "paypal"

    def __init__(self, settings: Settings, days: int = 180, transport: httpx.BaseTransport | None = None,
                 today: date | None = None):
        self.settings = settings
        self.days = days
        self.transport = transport
        self.today = today or date.today()
        self.opening_balance: Decimal | None = None
        self.currency: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.paypal_client_id and self.settings.paypal_client_secret)

    @property
    def environment(self) -> str:
        return self.settings.paypal_environment

    def status(self) -> dict:
        demo = self.environment == "demo"
        if demo:
            message = ("PayPal demo mode: no PayPal credentials are set, so FINORA uses its built-in PayPal simulation. "
                       "Sync, checkout, Pay Later, subscriptions and sign-in all work with synthetic data and no real "
                       "money. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to backend/.env to use your real PayPal.")
        elif self.configured:
            message = (f"PayPal {self.environment} credentials are set. Use “Test connection” to verify them with PayPal; "
                       "Transaction Search also needs that feature enabled on the REST app.")
        else:
            message = ("Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to the backend .env to enable live API sync. "
                       "You can import a PayPal Activity report (CSV) right now.")
        return {"configured": self.configured, "environment": self.environment, "demo": demo,
                "api_sync_available": self.configured, "message": message}

    # -- HTTP -------------------------------------------------------------------------
    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.settings.paypal_base_url, timeout=30, transport=self.transport)

    def _token(self, client: httpx.Client) -> str:
        r = client.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                        auth=(self.settings.paypal_client_id or "", self.settings.paypal_client_secret or ""))
        if r.status_code != 200:
            raise PayPalApiError(f"PayPal authentication failed ({r.status_code}). Check your client ID and secret.")
        return r.json()["access_token"]

    def _get(self, client: httpx.Client, token: str, path: str, params: dict) -> dict:
        r = client.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 403:
            raise PayPalApiError("PayPal denied access. Enable 'Transaction Search' for this REST app in the developer dashboard.")
        if r.status_code != 200:
            raise PayPalApiError(f"PayPal API error {r.status_code}: {r.text[:200]}")
        return r.json()

    # -- Source -------------------------------------------------------------------------
    def fetch(self) -> list[NormalizedTransaction]:
        if not self.configured:
            raise PayPalNotConfigured(self.status()["message"])
        start = self.today - timedelta(days=self.days)
        details: list[dict] = []
        with self._client() as client:
            token = self._token(client)
            w_start = start
            while w_start <= self.today:
                w_end = min(w_start + timedelta(days=WINDOW_DAYS - 1), self.today)
                page, total_pages = 1, 1
                while page <= total_pages:
                    body = self._get(client, token, "/v1/reporting/transactions", {
                        "start_date": f"{w_start.isoformat()}T00:00:00-0000",
                        "end_date": f"{w_end.isoformat()}T23:59:59-0000",
                        "fields": "transaction_info,payer_info,cart_info",
                        "page_size": 500, "page": page,
                    })
                    details.extend(body.get("transaction_details", []))
                    total_pages = int(body.get("total_pages", 1) or 1)
                    page += 1
                w_start = w_end + timedelta(days=1)
            txns = [t for t in (self._normalise(d) for d in details) if t is not None]
            txns.sort(key=lambda t: (t.posted_on, t.external_id))
            try:
                balances = self._get(client, token, "/v1/reporting/balances",
                                     {"as_of_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
                primary = next((b for b in balances.get("balances", []) if b.get("primary")), None) or (balances.get("balances") or [None])[0]
                if primary:
                    current = Decimal(primary["total_balance"]["value"])
                    self.currency = primary["total_balance"].get("currency_code")
                    self.opening_balance = money(current - sum((t.amount for t in txns), Decimal("0")))
            except (PayPalApiError, KeyError, ValueError):
                self.opening_balance = None
        return txns

    @staticmethod
    def _normalise(detail: dict) -> NormalizedTransaction | None:
        info = detail.get("transaction_info", {})
        if info.get("transaction_status") not in ("S", None):
            return None
        amount = info.get("transaction_amount", {}).get("value")
        txn_id = info.get("transaction_id")
        if amount is None or not txn_id:
            return None
        value = money(Decimal(amount))
        if value == 0:
            return None
        posted = datetime.fromisoformat(info["transaction_initiation_date"].replace("Z", "+00:00")).date()
        payer = detail.get("payer_info", {}).get("payer_name", {}).get("alternate_full_name")
        items = detail.get("cart_info", {}).get("item_details") or []
        item = items[0].get("item_name") if items else None
        label = EVENT_LABELS.get((info.get("transaction_event_code") or "")[:3], "PayPal transaction")
        name = payer or info.get("transaction_subject") or item or label
        desc = f"{label} · {item or info.get('transaction_note') or name}"
        return NormalizedTransaction(f"pp-{txn_id}", posted, desc[:255], name[:120], categorize(f"{name} {desc}", value > 0), value)
