"""All money is whole rupees. Paise only exist inside razorpay_gateway."""


def shipping_for(subtotal_inr):
    """Shipping is free across India on every prepaid order, whatever the subtotal."""
    return 0
