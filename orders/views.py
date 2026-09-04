import json
import logging
import time

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
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
CONFIRMED_ORDERS_KEY = "confirmed_orders"
TRACK_ATTEMPTS_KEY = "track_attempts"

# Order numbers are sequential, so the track page is rate-limited per session.
TRACK_LOOKUP_LIMIT = 10
TRACK_LOOKUP_WINDOW_SECONDS = 60 * 60


def _int_or_none(value):
    """Parse a form value as an int; anything that is not one is None, never a 500."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


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
    back = request.POST.get("next") or "catalog:shop"
    variant_id = _int_or_none(request.POST.get("variant"))
    variant = Variant.objects.select_related("product").filter(pk=variant_id).first() if variant_id else None
    if variant is None:
        messages.error(request, "Pick a size first.")
        return redirect(back)
    raw_quantity = (request.POST.get("quantity") or "").strip()
    quantity = 1 if not raw_quantity else _int_or_none(raw_quantity)
    if quantity is None or quantity < 1:
        messages.error(request, "That quantity didn't make sense, so nothing was added. Try a whole number of 1 or more.")
        return redirect(back)
    bag = Bag(request.session)
    added = bag.add(variant, quantity)
    _flash_notices(request, bag)
    if added:
        messages.success(request, f"{variant.product.name} ({variant.size_label}) is in your bag.")
    return redirect("orders:bag")


@require_POST
def bag_update(request):
    bag = Bag(request.session)
    action = request.POST.get("action", "")
    variant_id = _int_or_none(request.POST.get("variant"))
    if variant_id is None:
        messages.error(request, "That item isn't in your bag.")
    elif action == "remove":
        bag.remove(str(variant_id))
    elif action in {"inc", "dec"}:
        variant = Variant.objects.filter(pk=variant_id).select_related("product").first()
        if variant:
            current = bag.data.get(str(variant.pk), 0)
            bag.set_quantity(variant, current + (1 if action == "inc" else -1))
        else:
            messages.error(request, "That item isn't in your bag.")
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
            return redirect("orders:pay", order_number=order.order_number)
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


# Order pages carry the customer's name, address, phone and email, so they are
# never addressable by anyone who merely knows (or guesses) the order number.
# A session may see an order it is currently checking out (PENDING_ORDER_KEY)
# or one it has paid for (CONFIRMED_ORDERS_KEY, PROJECT.md S19).
def _session_owns(request, order):
    if request.session.get(PENDING_ORDER_KEY) == order.pk:
        return True
    return order.order_number in request.session.get(CONFIRMED_ORDERS_KEY, [])


def _session_order_or_404(request, order_number):
    order = Order.objects.filter(order_number=order_number).first()
    if order is None or not _session_owns(request, order):
        raise Http404
    return order


def _remember_confirmed(request, order):
    """Entitle this session to the receipt for `order` (PROJECT.md S19)."""
    confirmed = list(request.session.get(CONFIRMED_ORDERS_KEY, []))
    if order.order_number not in confirmed:
        confirmed.append(order.order_number)
        request.session[CONFIRMED_ORDERS_KEY] = confirmed


def _grant_receipt(request, order):
    """
    Record in the session that this browser paid for `order`. Returns True the
    first time the shopper lands here after paying, so the page can greet them
    and the bag can be emptied.
    """
    _remember_confirmed(request, order)
    if request.session.get(PENDING_ORDER_KEY) == order.pk:
        Bag(request.session).clear()
        request.session.pop(PENDING_ORDER_KEY, None)
        return True
    return False


def pay(request, order_number):
    """Order summary plus the button that opens Razorpay's Standard Checkout."""
    order = _session_order_or_404(request, order_number)
    if order.is_paid:
        return redirect("orders:confirmation", order_number=order.order_number)
    if not order.can_retry_payment or not order.razorpay_order_id:
        messages.info(request, "That checkout expired. Your bag is still here — go again.")
        return redirect("orders:bag")
    if order.status == Order.Status.PAYMENT_FAILED:
        # Allow a retry against the same gateway order. The status guard matters:
        # a webhook may have marked this order paid since we loaded it, and a
        # paid order must never be knocked back to pending (it would be paid
        # twice for stock and then swept to abandoned).
        moved = Order.objects.filter(pk=order.pk, status=Order.Status.PAYMENT_FAILED).update(
            status=Order.Status.PENDING
        )
        if not moved:
            order.refresh_from_db()
            if order.is_paid:
                return redirect("orders:confirmation", order_number=order.order_number)
            messages.info(request, "That checkout expired. Your bag is still here — go again.")
            return redirect("orders:bag")
        order.status = Order.Status.PENDING
    sandbox = gateway.is_sandbox()
    return render(
        request,
        "orders/pay.html",
        {
            "order": order,
            "items": order.items.all(),
            "sandbox": sandbox,
            "sandbox_url": reverse("orders:sandbox_gateway", args=[order.order_number]) if sandbox else "",
            "checkout_options": None if sandbox else gateway.checkout_options(order),
            "checkout_js_url": gateway.CHECKOUT_JS_URL,
        },
    )


def _verify_response(request, ok, redirect_to, error="", status=200):
    """JSON for the checkout script, a redirect for a plain form post (the sandbox page)."""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        body = {"ok": ok, "redirect_url": redirect_to}
        if error:
            body["error"] = error
        return JsonResponse(body, status=status)
    return redirect(redirect_to)


@require_POST
def verify_payment(request):
    """
    Razorpay's Standard Checkout hands the signed result to the shopper's
    browser, which posts it here — same origin, so the session cookie and the
    CSRF token both apply. The signature is the only thing that proves
    payment; the order is located by gateway id.
    """
    rp_order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    order = Order.objects.filter(razorpay_order_id=rp_order_id).first() if rp_order_id else None
    if order is None:
        log.warning("Verify for unknown gateway order %r", rp_order_id)
        return _verify_response(request, ok=False, redirect_to=reverse("orders:bag"), error="Unknown order.", status=400)
    if not gateway.verify_payment_signature(rp_order_id, payment_id, signature):
        log.warning("Bad payment signature for %s", order.order_number)
        order.mark_payment_failed()
        return _verify_response(
            request,
            ok=False,
            redirect_to=reverse("orders:cancelled", args=[order.order_number]),
            error="Signature verification failed.",
            status=400,
        )
    order.mark_paid(payment_id)
    # A valid signature is proof this browser completed the payment, so it is
    # entitled to the receipt even when the webhook won the race above.
    _remember_confirmed(request, order)
    return _verify_response(request, ok=True, redirect_to=reverse("orders:confirmation", args=[order.order_number]))


def payment_cancelled(request, order_number):
    order = _session_order_or_404(request, order_number)
    if order.is_paid:
        return redirect("orders:confirmation", order_number=order.order_number)
    if order.status == Order.Status.PENDING:
        order.mark_payment_failed()
        order.status = Order.Status.PAYMENT_FAILED
    return render(request, "orders/payment_failed.html", {"order": order})


def confirmation(request, order_number):
    """The receipt. 404 for any session other than the one that paid."""
    order = _session_order_or_404(request, order_number)
    if not order.is_paid:
        return redirect("orders:pay", order_number=order.order_number)
    just_paid = _grant_receipt(request, order)
    return render(
        request,
        "orders/confirmation.html",
        {"order": order, "items": order.items.all(), "just_paid": just_paid},
    )


def sandbox_gateway(request, order_number):
    """Local stand-in for Razorpay's checkout. Never mounted with real keys."""
    if not gateway.is_sandbox():
        raise Http404
    order = _session_order_or_404(request, order_number)
    if request.method == "POST" and request.POST.get("outcome") == "success":
        payment_id = gateway.sandbox_payment_id()
        signature = gateway.sign_payment(order.razorpay_order_id, payment_id)
        return render(
            request,
            "orders/sandbox_redirect.html",
            {
                "verify_url": reverse("orders:verify_payment"),
                "razorpay_order_id": order.razorpay_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            },
        )
    if request.method == "POST" and request.POST.get("outcome") == "fail":
        return redirect("orders:cancelled", order_number=order.order_number)
    return render(request, "orders/sandbox_gateway.html", {"order": order})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Belt-and-braces: if the shopper closes the tab before the browser can post
    to verify_payment, the webhook still lands. Razorpay calls this cross-site,
    so it is the one view that is CSRF-exempt; it trusts nothing but the HMAC
    over the raw body.
    """
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
def _recent_track_attempts(session):
    cutoff = time.time() - TRACK_LOOKUP_WINDOW_SECONDS
    return [t for t in session.get(TRACK_ATTEMPTS_KEY, []) if t > cutoff]


def track(request):
    """Look up one order by order number + email, at most TRACK_LOOKUP_LIMIT tries an hour per session."""
    order = None
    rate_limited = False
    form = TrackForm(request.GET or None)
    searched = bool(request.GET)
    if searched and form.is_valid():
        attempts = _recent_track_attempts(request.session)
        if len(attempts) >= TRACK_LOOKUP_LIMIT:
            rate_limited = True
        else:
            attempts.append(time.time())
            request.session[TRACK_ATTEMPTS_KEY] = attempts
            order = Order.objects.filter(
                order_number=form.cleaned_data["order_number"], email__iexact=form.cleaned_data["email"].strip()
            ).first()
    return render(
        request,
        "orders/track.html",
        {
            "form": form,
            "order": order,
            "searched": searched,
            "rate_limited": rate_limited,
            # Order pages are session-gated; only offer links this browser can open.
            "can_open": bool(order and _session_owns(request, order)),
        },
    )
