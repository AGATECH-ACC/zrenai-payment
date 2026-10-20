"""Curlec's documented Razorpay API endpoints; secrets never reach the browser."""
import hashlib
import hmac
import re

import httpx
from django.conf import settings


class PaymentError(Exception):
    pass


class ConfigurationError(PaymentError):
    pass


def require_keys():
    if not settings.CURLEC_KEY_ID or not settings.CURLEC_KEY_SECRET:
        raise ConfigurationError("Payments are not configured yet. Please contact the store.")


def api(method, path, body=None):
    require_keys()
    try:
        response = httpx.request(
            method, f"https://api.razorpay.com/v1/{path}",
            auth=(settings.CURLEC_KEY_ID, settings.CURLEC_KEY_SECRET),
            json=body, timeout=20, follow_redirects=False,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (httpx.HTTPError, ValueError) as exc:
        # Do not expose provider bodies, credentials, or payment details in errors.
        raise PaymentError("Curlec could not confirm this request. Please try checking your purchase later.") from exc


def create_order(order):
    return api("POST", "orders", {
        "amount": order.amount, "currency": order.currency,
        "receipt": str(order.pk), "partial_payment": False,
    })


def fetch_payment(payment_id):
    if not isinstance(payment_id, str) or not re.fullmatch(r"pay_[A-Za-z0-9]{1,90}", payment_id):
        raise PaymentError("Invalid payment reference.")
    return api("GET", f"payments/{payment_id}")


def fetch_order(order_id):
    if not isinstance(order_id, str) or not re.fullmatch(r"order_[A-Za-z0-9]{1,90}", order_id):
        raise PaymentError("Invalid order reference.")
    return api("GET", f"orders/{order_id}")


def valid_signature(message, signature, secret):
    if not secret or not isinstance(signature, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", signature):
        return False
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())
