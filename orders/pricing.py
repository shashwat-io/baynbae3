"""All money is whole rupees. Paise only exist inside razorpay_gateway."""
from django.conf import settings


def shipping_for(subtotal_inr):
    if subtotal_inr <= 0:
        return 0
    if subtotal_inr >= settings.STORE["free_shipping_over_inr"]:
        return 0
    return settings.STORE["shipping_flat_inr"]


def free_shipping_gap(subtotal_inr):
    """Rupees left to unlock free shipping, or 0."""
    return max(0, settings.STORE["free_shipping_over_inr"] - subtotal_inr)
