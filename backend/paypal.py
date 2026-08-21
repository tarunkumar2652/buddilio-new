"""PayPal REST integration — one-time orders and membership subscriptions.

Sandbox/live is picked from PAYPAL_ENV. Every call goes through _call() so token handling,
error surfacing and logging stay in one place.
"""
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("buddilio.paypal")

LIVE = "https://api-m.paypal.com"
SANDBOX = "https://api-m.sandbox.paypal.com"
CURRENCY = os.environ.get("PAYPAL_CURRENCY", "USD")

_token: dict = {"value": "", "expires": 0.0}


def base_url() -> str:
    return LIVE if os.environ.get("PAYPAL_ENV", "sandbox").lower() == "live" else SANDBOX


def creds() -> tuple[str, str]:
    """Live keys by default; sandbox keys are kept separately so tests can opt in."""
    if os.environ.get("PAYPAL_ENV", "sandbox").lower() == "live":
        return os.environ.get("PAYPAL_CLIENT_ID", ""), os.environ.get("PAYPAL_CLIENT_SECRET", "")
    return (os.environ.get("PAYPAL_SANDBOX_CLIENT_ID") or os.environ.get("PAYPAL_CLIENT_ID", ""),
            os.environ.get("PAYPAL_SANDBOX_CLIENT_SECRET") or os.environ.get("PAYPAL_CLIENT_SECRET", ""))


def enabled() -> bool:
    cid, secret = creds()
    return bool(cid and secret)


async def access_token() -> str:
    if _token["value"] and _token["expires"] > time.time() + 60:
        return _token["value"]
    cid, secret = creds()
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(f"{base_url()}/v1/oauth2/token", auth=(cid, secret),
                         data={"grant_type": "client_credentials"},
                         headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    data = r.json()
    _token.update({"value": data["access_token"], "expires": time.time() + float(data.get("expires_in", 3000))})
    return _token["value"]


async def _call(method: str, path: str, body: dict | None = None) -> dict:
    token = await access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method, f"{base_url()}{path}", headers=headers, json=body)
    if r.status_code >= 400:
        logger.warning(f"paypal {method} {path} -> {r.status_code} {r.text[:400]}")
        raise PayPalError(r.status_code, r.text)
    return r.json() if r.content else {}


class PayPalError(Exception):
    def __init__(self, status: int, body: str):
        self.status, self.body = status, body
        super().__init__(f"PayPal error {status}: {body[:300]}")


def message_of(exc: "PayPalError") -> str:
    try:
        import json
        data = json.loads(exc.body)
        det = (data.get("details") or [{}])[0]
        return det.get("description") or data.get("message") or "PayPal declined the request."
    except Exception:
        return "PayPal could not process this request."


MEMBER_ERRORS = {
    "ORDER_NOT_APPROVED": "This payment wasn't approved at PayPal, so nothing was charged.",
    "INSTRUMENT_DECLINED": "Your card was declined by the issuer. Try another card or method.",
    "PAYER_ACTION_REQUIRED": "PayPal needs one more step from you before this can be charged.",
    "ORDER_ALREADY_CAPTURED": "This payment has already been captured.",
    "PAYEE_ACCOUNT_RESTRICTED": "PayPal has restricted this account. Please contact support.",
}


def member_message(exc: "PayPalError") -> str:
    """Member-facing copy — never surface PayPal's developer instructions."""
    try:
        import json
        data = json.loads(exc.body)
        issue = ((data.get("details") or [{}])[0].get("issue") or data.get("name") or "").upper()
    except Exception:
        issue = ""
    return MEMBER_ERRORS.get(issue, "PayPal couldn't complete this payment. Nothing was charged.")


# ---------------- one-time orders ----------------
async def create_order(amount: float, reference: str, description: str,
                       return_url: str, cancel_url: str) -> dict:
    return await _call("POST", "/v2/checkout/orders", {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": reference,
            "description": description[:127],
            "custom_id": reference,
            "amount": {"currency_code": CURRENCY, "value": f"{amount:.2f}"},
        }],
        "application_context": {
            "brand_name": "Buddilio", "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
            # Card form first so buyers can pay as a guest without signing in to PayPal.
            "landing_page": "BILLING",
            "return_url": return_url, "cancel_url": cancel_url,
        },
    })


async def capture_order(paypal_order_id: str) -> dict:
    return await _call("POST", f"/v2/checkout/orders/{paypal_order_id}/capture", {})


async def get_order(paypal_order_id: str) -> dict:
    return await _call("GET", f"/v2/checkout/orders/{paypal_order_id}")


# ---------------- subscriptions ----------------
async def ensure_product(name: str, description: str) -> str:
    res = await _call("POST", "/v1/catalogs/products", {
        "name": name[:127], "description": (description or name)[:256],
        "type": "SERVICE", "category": "MEMBERSHIP_CLUBS_AND_ORGANIZATIONS"})
    return res["id"]


async def create_plan(product_id: str, name: str, price: float, interval: str,
                      interval_count: int = 1) -> str:
    """interval: MONTH or YEAR."""
    res = await _call("POST", "/v1/billing/plans", {
        "product_id": product_id, "name": name[:127],
        "description": f"Buddilio {name} membership"[:127],
        "status": "ACTIVE",
        "billing_cycles": [{
            "frequency": {"interval_unit": interval, "interval_count": interval_count},
            "tenure_type": "REGULAR", "sequence": 1, "total_cycles": 0,
            "pricing_scheme": {"fixed_price": {"value": f"{price:.2f}", "currency_code": CURRENCY}},
        }],
        "payment_preferences": {"auto_bill_outstanding": True,
                                "setup_fee_failure_action": "CONTINUE",
                                "payment_failure_threshold": 2},
    })
    return res["id"]


async def create_subscription(plan_id: str, email: str, full_name: str,
                              return_url: str, cancel_url: str, custom_id: str = "") -> dict:
    first, _, last = (full_name or "Buddilio Member").partition(" ")
    return await _call("POST", "/v1/billing/subscriptions", {
        "plan_id": plan_id, "custom_id": custom_id,
        "subscriber": {"name": {"given_name": first[:60] or "Member", "surname": last[:60] or "Buddilio"},
                       "email_address": email},
        "application_context": {"brand_name": "Buddilio", "user_action": "SUBSCRIBE_NOW",
                                "shipping_preference": "NO_SHIPPING",
                                "return_url": return_url, "cancel_url": cancel_url},
    })


async def get_subscription(subscription_id: str) -> dict:
    return await _call("GET", f"/v1/billing/subscriptions/{subscription_id}")


async def cancel_subscription(subscription_id: str, reason: str = "Cancelled by member") -> None:
    await _call("POST", f"/v1/billing/subscriptions/{subscription_id}/cancel", {"reason": reason[:127]})


def approve_link(res: dict) -> str:
    for link in res.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            return link["href"]
    return ""


# ---------------- webhooks ----------------
async def verify_webhook(headers: Any, body: dict) -> bool:
    """PayPal verifies the signature for us when a webhook id is configured."""
    webhook_id = os.environ.get("PAYPAL_WEBHOOK_ID", "")
    if not webhook_id:
        return False
    try:
        res = await _call("POST", "/v1/notifications/verify-webhook-signature", {
            "auth_algo": headers.get("paypal-auth-algo", ""),
            "cert_url": headers.get("paypal-cert-url", ""),
            "transmission_id": headers.get("paypal-transmission-id", ""),
            "transmission_sig": headers.get("paypal-transmission-sig", ""),
            "transmission_time": headers.get("paypal-transmission-time", ""),
            "webhook_id": webhook_id, "webhook_event": body})
        return res.get("verification_status") == "SUCCESS"
    except PayPalError:
        return False
