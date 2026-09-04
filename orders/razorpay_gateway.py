"""
The only file that talks to Razorpay, and the only place paise exist.

Two modes:
  * live   — RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are set. Orders are created
             through the SDK and the customer pays in Razorpay's Standard
             Checkout modal on our own pay page; the browser then posts the
             signed result to our verify endpoint.
  * sandbox — DEBUG and no keys. A local stand-in page plays Razorpay so the
             whole checkout can be walked end to end on a laptop.
"""
import hashlib
import hmac
import secrets

from django.conf import settings

CHECKOUT_JS_URL = "https://checkout.razorpay.com/v1/checkout.js"


def to_paise(rupees):
    return int(rupees) * 100


def checkout_options(order):
    """
    The options object handed to `new Razorpay(...)` on the pay page. The
    amount is informational to the modal (Razorpay binds the charge to the
    order id created server-side) but it is still derived here, from the
    order's stored total, never from anything the browser sent.
    """
    return {
        "key": settings.RAZORPAY_KEY_ID,
        "amount": to_paise(order.total_inr),
        "currency": "INR",
        "order_id": order.razorpay_order_id,
        "name": settings.STORE["name"],
        "description": f"Order {order.order_number}",
        "prefill": {"name": order.customer_name, "email": order.email, "contact": order.phone},
        "notes": {"order_number": order.order_number},
    }


def is_sandbox():
    return settings.RAZORPAY_SANDBOX


def _client():
    import razorpay

    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_gateway_order(order):
    """Create the Razorpay order and return its id."""
    if is_sandbox():
        return f"order_sbx_{order.pk}_{secrets.token_hex(4)}"
    response = _client().order.create(
        {
            "amount": to_paise(order.total_inr),
            "currency": "INR",
            "receipt": order.order_number,
            "notes": {"order_number": order.order_number, "email": order.email},
        }
    )
    return response["id"]


def _secret():
    return settings.RAZORPAY_KEY_SECRET if not is_sandbox() else ("sandbox:" + settings.SECRET_KEY)


def sign_payment(razorpay_order_id, payment_id):
    message = f"{razorpay_order_id}|{payment_id}".encode()
    return hmac.new(_secret().encode(), message, hashlib.sha256).hexdigest()


def verify_payment_signature(razorpay_order_id, payment_id, signature):
    if not (razorpay_order_id and payment_id and signature):
        return False
    return hmac.compare_digest(sign_payment(razorpay_order_id, payment_id), signature)


def verify_webhook_signature(body_bytes, signature):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sandbox_payment_id():
    return "pay_sbx_" + secrets.token_hex(6)
