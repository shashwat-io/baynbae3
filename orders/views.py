import json
import logging

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from catalog.models import Variant

from . import razorpay_gateway as gateway
from .cart import Bag
from .forms import CheckoutForm, TrackForm
from .models import Order, OrderItem

log = logging.getLogger(__name__)

PENDING_ORDER_KEY = "pending_order"
CHECKOUT_PREFILL_KEY = "checkout_prefill"


def _flash_notices(request, bag):
    for notice in bag.notices:
        messages.info(request, notice)
    bag.notices.clear()


# ------------------------------------------------------------------- bag
def bag_view(request):
    bag = Bag(request.session)
    lines = bag.lines()
    _flash_notices(request, bag)
    return render(request, "orders/bag.html", {"bag": bag, "lines": lines})


@require_POST
def bag_add(request):
    try:
        variant = Variant.objects.select_related("product").get(pk=int(request.POST.get("variant", 0)))
    except (Variant.DoesNotExist, ValueError):
        messages.error(request, "Pick a size first.")
        return redirect(request.POST.get("next") or "catalog:shop")
    bag = Bag(request.session)
    added = bag.add(variant, int(request.POST.get("quantity", 1) or 1))
    _flash_notices(request, bag)
    if added:
        messages.success(request, f"{variant.product.name} ({variant.size_label}) is in your bag.")
    return redirect("orders:bag")


@require_POST
def bag_update(request):
    bag = Bag(request.session)
    action = request.POST.get("action", "")
    variant_id = request.POST.get("variant")
    if action == "remove" and variant_id:
        bag.remove(variant_id)
    elif action in {"inc", "dec"} and variant_id:
        variant = Variant.objects.filter(pk=variant_id).select_related("product").first()
        if variant:
            current = bag.data.get(str(variant.pk), 0)
            bag.set_quantity(variant, current + (1 if action == "inc" else -1))
    _flash_notices(request, bag)
    return redirect("orders:bag")


# -------------------------------------------------------------- checkout
@require_http_methods(["GET", "POST"])
def checkout(request):
    bag = Bag(request.session)
    lines = bag.lines()
    _flash_notices(request, bag)
    if not lines:
        messages.info(request, "Your bag is empty. Let's fix that.")
        return redirect("catalog:shop")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            order = _create_order(request, bag, lines, form.cleaned_data)
            if order is None:
                return redirect("orders:bag")
            return redirect("orders:pay", token=order.token)
    else:
        form = CheckoutForm(initial=request.session.get(CHECKOUT_PREFILL_KEY, {}))
    return render(request, "orders/checkout.html", {"form": form, "bag": bag, "lines": lines})


def _create_order(request, bag, lines, data):
    # A shopper who backs out of the payment page and re-submits should not
    # leave a trail of pending orders behind them.
    previous = request.session.pop(PENDING_ORDER_KEY, None)
    if previous:
        Order.objects.filter(pk=previous, status=Order.Status.PENDING).update(status=Order.Status.ABANDONED)

    with transaction.atomic():
        order = Order.objects.create(
            status=Order.Status.PENDING,
            subtotal_inr=bag.subtotal_inr,
            shipping_inr=bag.shipping_inr,
            total_inr=bag.total_inr,
            **{k: data[k] for k in ("customer_name", "email", "phone", "address1", "address2", "city", "state", "pincode", "note")},
        )
        for line in lines:
            image = line.product.primary_image
            OrderItem.objects.create(
                order=order,
                product=line.product,
                variant=line.variant,
                product_name=line.product.name,
                product_slug=line.product.slug,
                size=line.variant.size,
                quantity=line.quantity,
                unit_price_inr=line.unit_price_inr,
                image_filename=image.filename if image else "",
            )
    try:
        order.razorpay_order_id = gateway.create_gateway_order(order)
        order.save(update_fields=["razorpay_order_id"])
    except Exception:  # network or credential trouble — never a 500 for the shopper
        log.exception("Razorpay order creation failed for %s", order.order_number)
        order.status = Order.Status.ABANDONED
        order.ops_notes = "Gateway order creation failed."
        order.save(update_fields=["status", "ops_notes"])
        messages.error(request, "Our payment partner didn't answer. Nothing was charged — please try again in a minute.")
        return None

    request.session[PENDING_ORDER_KEY] = order.pk
    request.session[CHECKOUT_PREFILL_KEY] = {k: data[k] for k in ("customer_name", "email", "phone", "address1", "address2", "city", "state", "pincode")}
    return order


def _order_from_token_or_404(token):
    order = Order.from_token(token)
    if order is None:
        raise Http404
    return order


def pay(request, token):
    """Order summary plus the form that hands the shopper to Razorpay."""
    order = _order_from_token_or_404(token)
    if order.is_paid:
        return redirect("orders:confirmation", token=order.token)
    if not order.can_retry_payment or not order.razorpay_order_id:
        messages.info(request, "That checkout expired. Your bag is still here — go again.")
        return redirect("orders:bag")
    if order.status == Order.Status.PAYMENT_FAILED:
        # Allow a retry against the same gateway order.
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PENDING)
        order.status = Order.Status.PENDING
    callback_url = settings.SITE_URL + reverse("orders:callback")
    cancel_url = settings.SITE_URL + reverse("orders:cancelled", args=[order.token])
    if gateway.is_sandbox():
        action_url = reverse("orders:sandbox_gateway", args=[order.token])
    else:
        action_url = gateway.HOSTED_CHECKOUT_URL
    return render(
        request,
        "orders/pay.html",
        {
            "order": order,
            "items": order.items.all(),
            "action_url": action_url,
            "key_id": settings.RAZORPAY_KEY_ID,
            "callback_url": callback_url,
            "cancel_url": cancel_url,
            "logo_url": settings.SITE_URL + "/static/img/social-card.png",
            "sandbox": gateway.is_sandbox(),
        },
    )


@csrf_exempt
@require_POST
def payment_callback(request):
    """
    Razorpay's hosted checkout POSTs here from razorpay.com, so the session
    cookie is not guaranteed and CSRF cannot apply. Everything is verified
    with the HMAC signature and the order is located by gateway id.
    """
    rp_order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    order = Order.objects.filter(razorpay_order_id=rp_order_id).first() if rp_order_id else None
    if order is None:
        log.warning("Callback for unknown gateway order %r", rp_order_id)
        return HttpResponseBadRequest("Unknown order.")
    if not gateway.verify_payment_signature(rp_order_id, payment_id, signature):
        log.warning("Bad payment signature for %s", order.order_number)
        order.mark_payment_failed()
        return redirect("orders:cancelled", token=order.token)
    order.mark_paid(payment_id)
    return redirect("orders:confirmation", token=order.token)


def payment_cancelled(request, token):
    order = _order_from_token_or_404(token)
    if order.is_paid:
        return redirect("orders:confirmation", token=order.token)
    if order.status == Order.Status.PENDING:
        order.mark_payment_failed()
        order.status = Order.Status.PAYMENT_FAILED
    return render(request, "orders/payment_failed.html", {"order": order})


def confirmation(request, token):
    order = _order_from_token_or_404(token)
    if not order.is_paid:
        return redirect("orders:pay", token=order.token)
    just_paid = False
    if request.session.get(PENDING_ORDER_KEY) == order.pk:
        Bag(request.session).clear()
        request.session.pop(PENDING_ORDER_KEY, None)
        just_paid = True
    return render(
        request,
        "orders/confirmation.html",
        {"order": order, "items": order.items.all(), "just_paid": just_paid},
    )


def sandbox_gateway(request, token):
    """Local stand-in for Razorpay's hosted checkout. Never mounted with real keys."""
    if not gateway.is_sandbox():
        raise Http404
    order = _order_from_token_or_404(token)
    if request.method == "POST" and request.POST.get("outcome") == "success":
        payment_id = gateway.sandbox_payment_id()
        signature = gateway.sign_payment(order.razorpay_order_id, payment_id)
        return render(
            request,
            "orders/sandbox_redirect.html",
            {
                "callback_url": reverse("orders:callback"),
                "razorpay_order_id": order.razorpay_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            },
        )
    if request.method == "POST" and request.POST.get("outcome") == "fail":
        return redirect("orders:cancelled", token=order.token)
    return render(request, "orders/sandbox_gateway.html", {"order": order})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """Belt-and-braces: if the shopper closes the tab before the callback, the webhook still lands."""
    if not gateway.verify_webhook_signature(request.body, request.headers.get("X-Razorpay-Signature", "")):
        return HttpResponse("Bad signature.", status=403)
    try:
        payload = json.loads(request.body)
        event = payload.get("event", "")
        entity = payload["payload"]["payment"]["entity"]
        rp_order_id = entity.get("order_id", "")
        payment_id = entity.get("id", "")
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("Malformed payload.")
    if event not in {"payment.captured", "order.paid"}:
        return HttpResponse("Ignored.")
    order = Order.objects.filter(razorpay_order_id=rp_order_id).first()
    if order is None:
        return HttpResponse("Unknown order.", status=200)
    order.mark_paid(payment_id)
    return HttpResponse("OK")


# ----------------------------------------------------------------- track
def track(request):
    order = None
    form = TrackForm(request.GET or None)
    searched = bool(request.GET)
    if searched and form.is_valid():
        contact = form.cleaned_data["contact"].strip().lower()
        digits = "".join(ch for ch in contact if ch.isdigit())[-10:]
        candidate = Order.objects.filter(order_number=form.cleaned_data["order_number"]).first()
        if candidate and (candidate.email.lower() == contact or (digits and candidate.phone.endswith(digits))):
            order = candidate
    return render(request, "orders/track.html", {"form": form, "order": order, "searched": searched})
