"""
Payment-path tests. Nothing here touches the network: the Razorpay SDK is
mocked, and signatures are computed with the same HMAC the gateway uses.
"""
import hashlib
import hmac
import importlib.util
import json
import os
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product, ProductImage, Variant

from . import razorpay_gateway as gateway
from .cart import MAX_PER_LINE, SESSION_KEY, Bag
from .models import Order, OrderItem
from .pricing import shipping_for

ADDRESS = {
    "customer_name": "Ananya Iyer",
    "email": "ananya@example.com",
    "phone": "9876543210",
    "address1": "Flat 4B, Sunrise Apartments",
    "address2": "Near the metro",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pincode": "560038",
    "note": "Gate shuts at 10pm",
}


def make_product(slug="tester", price=2499, sizes=None, live=True):
    product = Product.objects.create(
        name=slug.replace("-", " ").title(),
        slug=slug,
        category="dresses",
        price_inr=price,
        tagline="t",
        description="d",
        print_name="p",
        fabric="cotton",
        is_live=live,
    )
    for size, stock in (sizes or {"S": 3, "M": 0}).items():
        Variant.objects.create(product=product, size=size, stock=stock)
    ProductImage.objects.create(product=product, filename=f"{slug}-1.svg", alt="front")
    return product


def load_settings(**env):
    """
    Import config/settings.py as a throwaway module under exactly the given
    environment. The .env loader is stubbed out so the developer's local file
    cannot leak keys into the test.
    """
    path = settings.BASE_DIR / "config" / "settings.py"
    with mock.patch.dict(os.environ, {"SECRET_KEY": "test-only", **env}, clear=True), mock.patch(
        "dotenv.dotenv_values", return_value={}
    ):
        spec = importlib.util.spec_from_file_location("settings_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class SettingsTests(TestCase):
    """Sandbox payment mode must never exist outside DEBUG (audit: CRITICAL, fails open)."""

    KEYS = {"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "s", "RAZORPAY_WEBHOOK_SECRET": "w"}

    def test_production_without_razorpay_keys_refuses_to_start(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            load_settings(DEBUG="false")
        self.assertIn("RAZORPAY_KEY_ID", str(ctx.exception))

    def test_production_names_each_missing_variable(self):
        for missing in self.KEYS:
            env = {k: v for k, v in self.KEYS.items() if k != missing}
            with self.assertRaises(ImproperlyConfigured, msg=missing) as ctx:
                load_settings(DEBUG="false", **env)
            self.assertIn(missing, str(ctx.exception))

    def test_production_webhook_secret_is_required_not_optional(self):
        env = {k: v for k, v in self.KEYS.items() if k != "RAZORPAY_WEBHOOK_SECRET"}
        with self.assertRaises(ImproperlyConfigured) as ctx:
            load_settings(DEBUG="false", **env)
        self.assertIn("RAZORPAY_WEBHOOK_SECRET", str(ctx.exception))

    def test_production_with_keys_is_never_sandbox(self):
        module = load_settings(DEBUG="false", **self.KEYS)
        self.assertFalse(module.DEBUG)
        self.assertFalse(module.RAZORPAY_SANDBOX)

    def test_debug_without_keys_is_sandbox_and_with_keys_is_not(self):
        self.assertTrue(load_settings(DEBUG="true").RAZORPAY_SANDBOX)
        self.assertFalse(load_settings(DEBUG="true", **self.KEYS).RAZORPAY_SANDBOX)


class BagTests(TestCase):
    def setUp(self):
        self.product = make_product()
        self.s = self.product.variants.get(size="S")
        self.m = self.product.variants.get(size="M")

    def test_add_and_quantity_clamped_to_stock(self):
        bag = Bag(self.client.session)
        self.assertEqual(bag.add(self.s), 1)
        self.assertEqual(bag.add(self.s, 10), 2)  # stock 3, so only 2 more
        self.assertEqual(bag.add(self.s), 0)
        self.assertEqual(bag.count, 3)
        self.assertTrue(any("every S" in n for n in bag.notices))

    def test_per_line_cap(self):
        v = Variant.objects.create(product=self.product, size="L", stock=50)
        bag = Bag(self.client.session)
        bag.add(v, 99)
        self.assertEqual(bag.count, MAX_PER_LINE)

    def test_sold_out_variant_not_added(self):
        bag = Bag(self.client.session)
        self.assertEqual(bag.add(self.m), 0)
        self.assertTrue(bag.is_empty)

    def test_dead_lines_dropped_on_read(self):
        session = self.client.session
        session[SESSION_KEY] = {str(self.s.pk): 2}
        session.save()
        self.product.is_live = False
        self.product.save()
        bag = Bag(session)
        self.assertEqual(bag.lines(), [])
        self.assertTrue(bag.is_empty)

    def test_quantity_reduced_when_stock_drops(self):
        session = self.client.session
        session[SESSION_KEY] = {str(self.s.pk): 3}
        session.save()
        self.s.stock = 1
        self.s.save()
        bag = Bag(session)
        self.assertEqual(bag.lines()[0].quantity, 1)
        self.assertEqual(bag.subtotal_inr, 2499)

    def test_views_add_update_remove(self):
        r = self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})
        self.assertRedirects(r, reverse("orders:bag"))
        r = self.client.get(reverse("orders:bag"))
        self.assertContains(r, "Tester")
        self.client.post(reverse("orders:bag_update"), {"variant": self.s.pk, "action": "inc"})
        self.assertEqual(self.client.session[SESSION_KEY][str(self.s.pk)], 2)
        self.client.post(reverse("orders:bag_update"), {"variant": self.s.pk, "action": "remove"})
        self.assertEqual(self.client.session[SESSION_KEY], {})
        # removing something not in the bag is a no-op, not an error
        r = self.client.post(reverse("orders:bag_update"), {"variant": 9999, "action": "remove"})
        self.assertEqual(r.status_code, 302)

    def test_add_bad_variant_is_handled(self):
        r = self.client.post(reverse("orders:bag_add"), {"variant": "nope"})
        self.assertEqual(r.status_code, 302)


class PricingTests(TestCase):
    def test_shipping_threshold(self):
        self.assertEqual(shipping_for(0), 0)
        self.assertEqual(shipping_for(1998), 79)
        self.assertEqual(shipping_for(1999), 0)
        self.assertEqual(shipping_for(4999), 0)


@override_settings(RAZORPAY_SANDBOX=True, RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
class CheckoutTests(TestCase):
    def setUp(self):
        self.product = make_product(price=1500)
        self.s = self.product.variants.get(size="S")
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})

    def test_empty_bag_redirects(self):
        c = Client()
        r = c.get(reverse("orders:checkout"))
        self.assertRedirects(r, reverse("catalog:shop"))

    def test_invalid_form_shows_errors_and_creates_nothing(self):
        bad = dict(ADDRESS, phone="12345", pincode="00000")
        r = self.client.post(reverse("orders:checkout"), bad)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "10-digit Indian mobile number")
        self.assertContains(r, "6-digit PIN code")
        self.assertEqual(Order.objects.count(), 0)

    def test_valid_checkout_creates_pending_order_with_snapshots(self):
        r = self.client.post(reverse("orders:checkout"), ADDRESS)
        order = Order.objects.get()
        self.assertRedirects(r, reverse("orders:pay", args=[order.token]))
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.order_number, f"BNB-{1000 + order.pk}")
        self.assertEqual(order.subtotal_inr, 1500)
        self.assertEqual(order.shipping_inr, 79)
        self.assertEqual(order.total_inr, 1579)
        self.assertTrue(order.razorpay_order_id.startswith("order_sbx_"))
        item = order.items.get()
        self.assertEqual((item.product_name, item.size, item.unit_price_inr, item.quantity), ("Tester", "S", 1500, 1))
        self.assertEqual(item.image_filename, "tester-1.svg")
        # stock is NOT touched until payment
        self.s.refresh_from_db()
        self.assertEqual(self.s.stock, 3)
        # phone with +91 prefix is normalised
        self.assertEqual(order.phone, "9876543210")

    def test_phone_prefix_normalised(self):
        self.client.post(reverse("orders:checkout"), dict(ADDRESS, phone="+91 98765 43210"))
        self.assertEqual(Order.objects.get().phone, "9876543210")

    def test_resubmitting_checkout_abandons_previous_pending_order(self):
        self.client.post(reverse("orders:checkout"), ADDRESS)
        first = Order.objects.get()
        self.client.post(reverse("orders:checkout"), ADDRESS)
        first.refresh_from_db()
        self.assertEqual(first.status, "abandoned")
        self.assertEqual(Order.objects.filter(status="pending").count(), 1)

    def test_snapshot_survives_product_deletion(self):
        self.client.post(reverse("orders:checkout"), ADDRESS)
        self.product.delete()
        item = OrderItem.objects.get()
        self.assertEqual(item.product_name, "Tester")
        self.assertIsNone(item.product)

    @override_settings(RAZORPAY_SANDBOX=False, RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret")
    def test_gateway_failure_never_500s(self):
        with mock.patch("razorpay.Client") as client_cls:
            client_cls.return_value.order.create.side_effect = RuntimeError("network down")
            r = self.client.post(reverse("orders:checkout"), ADDRESS)
        self.assertRedirects(r, reverse("orders:bag"))
        self.assertEqual(Order.objects.get().status, "abandoned")


@override_settings(RAZORPAY_SANDBOX=True, RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
class PayPageTests(TestCase):
    def setUp(self):
        self.product = make_product(price=2999)
        self.s = self.product.variants.get(size="S")
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})
        self.client.post(reverse("orders:checkout"), ADDRESS)
        self.order = Order.objects.get()

    def test_sandbox_pay_page_points_at_local_gateway(self):
        r = self.client.get(reverse("orders:pay", args=[self.order.token]))
        self.assertContains(r, reverse("orders:sandbox_gateway", args=[self.order.token]))
        self.assertContains(r, "Sandbox mode")
        self.assertContains(r, "2,999")

    @override_settings(RAZORPAY_SANDBOX=False, RAZORPAY_KEY_ID="rzp_test_abc", RAZORPAY_KEY_SECRET="s3cret")
    def test_live_pay_page_posts_to_razorpay_hosted_checkout(self):
        r = self.client.get(reverse("orders:pay", args=[self.order.token]))
        self.assertContains(r, gateway.HOSTED_CHECKOUT_URL)
        self.assertContains(r, 'name="key_id" value="rzp_test_abc"')
        self.assertContains(r, 'name="callback_url" value="http://127.0.0.1:8000/checkout/callback/"')
        self.assertNotContains(r, "Sandbox mode")
        # the sandbox stand-in must not be reachable with real keys
        self.assertEqual(self.client.get(reverse("orders:sandbox_gateway", args=[self.order.token])).status_code, 404)

    def test_bad_token_404s(self):
        self.assertEqual(self.client.get(reverse("orders:pay", args=["garbage"])).status_code, 404)

    def test_paid_order_redirects_to_confirmation(self):
        self.order.mark_paid("pay_1")
        r = self.client.get(reverse("orders:pay", args=[self.order.token]))
        self.assertRedirects(r, reverse("orders:confirmation", args=[self.order.token]))


@override_settings(RAZORPAY_SANDBOX=True, RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
class CallbackTests(TestCase):
    """The hosted checkout POSTs back with a signature; that is the only thing we trust."""

    def setUp(self):
        self.product = make_product(price=2000, sizes={"S": 2})
        self.s = self.product.variants.get(size="S")
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})
        self.client.post(reverse("orders:checkout"), ADDRESS)
        self.order = Order.objects.get()

    def callback(self, payment_id="pay_ok", signature=None, client=None):
        client = client or self.client
        signature = signature if signature is not None else gateway.sign_payment(self.order.razorpay_order_id, payment_id)
        return client.post(
            reverse("orders:callback"),
            {"razorpay_order_id": self.order.razorpay_order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature},
        )

    def test_valid_signature_marks_paid_and_decrements_stock_once(self):
        r = self.callback()
        self.assertRedirects(r, reverse("orders:confirmation", args=[self.order.token]), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(self.order.razorpay_payment_id, "pay_ok")
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(self.s.stock, 0)

    def test_duplicate_callback_is_idempotent(self):
        self.callback()
        self.callback()
        self.s.refresh_from_db()
        self.assertEqual(self.s.stock, 0)  # not -2
        self.assertEqual(Order.objects.filter(status="paid").count(), 1)

    def test_bad_signature_marks_failed_and_leaves_stock(self):
        r = self.callback(signature="deadbeef")
        self.assertRedirects(r, reverse("orders:cancelled", args=[self.order.token]), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "payment_failed")
        self.assertEqual(self.s.stock, 2)

    def test_signature_for_other_order_rejected(self):
        wrong = gateway.sign_payment("order_other", "pay_ok")
        self.callback(signature=wrong)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "paid")

    def test_unknown_gateway_order_400(self):
        r = self.client.post(reverse("orders:callback"), {"razorpay_order_id": "order_nope", "razorpay_payment_id": "p", "razorpay_signature": "s"})
        self.assertEqual(r.status_code, 400)

    def test_callback_works_without_session_cookie(self):
        """Razorpay posts cross-site; SameSite=Lax means no session. Must still work."""
        anonymous = Client()
        r = self.callback(client=anonymous)
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")

    def test_confirmation_clears_bag_and_shows_order(self):
        self.callback()
        r = self.client.get(reverse("orders:confirmation", args=[self.order.token]))
        self.assertContains(r, self.order.order_number)
        self.assertContains(r, "re in.")
        self.assertEqual(self.client.session.get(SESSION_KEY), {})

    def test_confirmation_for_unpaid_order_redirects_to_pay(self):
        r = self.client.get(reverse("orders:confirmation", args=[self.order.token]))
        self.assertRedirects(r, reverse("orders:pay", args=[self.order.token]))

    def test_oversell_is_flagged_not_hidden(self):
        # someone else bought the stock while this shopper was on the gateway
        Variant.objects.filter(pk=self.s.pk).update(stock=1)
        self.callback()
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertIn("OVERSOLD", self.order.ops_notes)
        self.assertEqual(self.s.stock, 0)

    def test_cancelled_page_marks_failed_and_offers_retry(self):
        r = self.client.get(reverse("orders:cancelled", args=[self.order.token]))
        self.assertContains(r, "Try paying again")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "payment_failed")
        # retry flips it back to pending against the same gateway order
        r = self.client.get(reverse("orders:pay", args=[self.order.token]))
        self.assertEqual(r.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
        # ...and a good callback after a failed attempt still completes
        self.callback()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")

    def test_sandbox_gateway_round_trip(self):
        r = self.client.post(reverse("orders:sandbox_gateway", args=[self.order.token]))
        self.assertContains(r, "Payment succeeds")
        r = self.client.post(reverse("orders:sandbox_gateway", args=[self.order.token]), {"outcome": "success"})
        self.assertContains(r, 'name="razorpay_signature"')
        r = self.client.post(reverse("orders:sandbox_gateway", args=[self.order.token]), {"outcome": "fail"})
        self.assertRedirects(r, reverse("orders:cancelled", args=[self.order.token]), fetch_redirect_response=False)


@override_settings(RAZORPAY_SANDBOX=False, RAZORPAY_KEY_ID="rzp_test_abc", RAZORPAY_KEY_SECRET="s3cret", RAZORPAY_WEBHOOK_SECRET="whsec")
class LiveGatewayTests(TestCase):
    def setUp(self):
        self.product = make_product(price=3000, sizes={"M": 4})
        self.m = self.product.variants.get(size="M")

    def test_order_created_through_sdk_in_paise(self):
        self.client.post(reverse("orders:bag_add"), {"variant": self.m.pk})
        with mock.patch("razorpay.Client") as client_cls:
            client_cls.return_value.order.create.return_value = {"id": "order_LIVE123"}
            self.client.post(reverse("orders:checkout"), ADDRESS)
            client_cls.assert_called_once_with(auth=("rzp_test_abc", "s3cret"))
            payload = client_cls.return_value.order.create.call_args.args[0]
        order = Order.objects.get()
        self.assertEqual(order.razorpay_order_id, "order_LIVE123")
        self.assertEqual(payload["amount"], 3000 * 100)
        self.assertEqual(payload["currency"], "INR")
        self.assertEqual(payload["receipt"], order.order_number)

    def test_signature_uses_key_secret(self):
        expected = hmac.new(b"s3cret", b"order_LIVE123|pay_9", hashlib.sha256).hexdigest()
        self.assertTrue(gateway.verify_payment_signature("order_LIVE123", "pay_9", expected))
        self.assertFalse(gateway.verify_payment_signature("order_LIVE123", "pay_9", expected[:-1] + "0"))
        self.assertFalse(gateway.verify_payment_signature("", "", ""))

    def _order(self):
        return Order.objects.create(
            status="pending", subtotal_inr=3000, shipping_inr=0, total_inr=3000, razorpay_order_id="order_LIVE123",
            **{k: v for k, v in ADDRESS.items()},
        ).pk

    def test_webhook_marks_paid_and_is_idempotent_with_callback(self):
        pk = self._order()
        order = Order.objects.get(pk=pk)
        OrderItem.objects.create(order=order, product=self.product, variant=self.m, product_name="T", size="M", quantity=2, unit_price_inr=3000)
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_W", "order_id": "order_LIVE123"}}}}).encode()
        sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        r = self.client.post(reverse("orders:webhook"), body, content_type="application/json", headers={"X-Razorpay-Signature": sig})
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.m.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertEqual(self.m.stock, 2)
        # the browser callback arriving afterwards changes nothing
        cb_sig = gateway.sign_payment("order_LIVE123", "pay_W")
        self.client.post(reverse("orders:callback"), {"razorpay_order_id": "order_LIVE123", "razorpay_payment_id": "pay_W", "razorpay_signature": cb_sig})
        self.m.refresh_from_db()
        self.assertEqual(self.m.stock, 2)

    def test_webhook_rejects_bad_signature_and_ignores_other_events(self):
        self._order()
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_W", "order_id": "order_LIVE123"}}}}).encode()
        r = self.client.post(reverse("orders:webhook"), body, content_type="application/json", headers={"X-Razorpay-Signature": "nope"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Order.objects.get().status, "pending")
        other = json.dumps({"event": "refund.created", "payload": {"payment": {"entity": {"id": "pay_W", "order_id": "order_LIVE123"}}}}).encode()
        sig = hmac.new(b"whsec", other, hashlib.sha256).hexdigest()
        r = self.client.post(reverse("orders:webhook"), other, content_type="application/json", headers={"X-Razorpay-Signature": sig})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Order.objects.get().status, "pending")

    @override_settings(RAZORPAY_WEBHOOK_SECRET="")
    def test_webhook_disabled_without_secret(self):
        r = self.client.post(reverse("orders:webhook"), b"{}", content_type="application/json", headers={"X-Razorpay-Signature": "x"})
        self.assertEqual(r.status_code, 403)


class TrackAndExpiryTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(status="shipped", subtotal_inr=1, shipping_inr=0, total_inr=1, courier="Delhivery", tracking_number="DL123", **ADDRESS)

    def test_track_by_email_or_phone(self):
        r = self.client.get(reverse("orders:track"), {"order_number": self.order.order_number.lower(), "contact": "ANANYA@example.com"})
        self.assertContains(r, "DL123")
        r = self.client.get(reverse("orders:track"), {"order_number": self.order.order_number, "contact": "+91 98765 43210"})
        self.assertContains(r, "DL123")
        r = self.client.get(reverse("orders:track"), {"order_number": self.order.order_number, "contact": "someone@else.com"})
        self.assertContains(r, "No order matches")
        self.assertNotContains(r, "DL123")

    def test_expire_command(self):
        stale = Order.objects.create(status="pending", subtotal_inr=1, shipping_inr=0, total_inr=1, **ADDRESS)
        Order.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(hours=3))
        fresh = Order.objects.create(status="pending", subtotal_inr=1, shipping_inr=0, total_inr=1, **ADDRESS)
        call_command("expire_orders")
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.status, "abandoned")
        self.assertEqual(fresh.status, "pending")
        self.assertEqual(Order.objects.get(pk=self.order.pk).status, "shipped")

    def test_token_round_trip(self):
        self.assertEqual(Order.from_token(self.order.token), self.order)
        self.assertIsNone(Order.from_token(self.order.token + "x"))


class AdminTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        User.objects.create_superuser("boss", "boss@example.com", "pw")
        self.client.login(username="boss", password="pw")
        self.order = Order.objects.create(status="paid", subtotal_inr=1, shipping_inr=0, total_inr=1, **ADDRESS)

    def test_order_admin_pages_render(self):
        self.assertEqual(self.client.get("/admin/orders/order/").status_code, 200)
        self.assertEqual(self.client.get(f"/admin/orders/order/{self.order.pk}/change/").status_code, 200)

    def test_bulk_actions_follow_lifecycle(self):
        self.client.post("/admin/orders/order/", {"action": "mark_delivered", "_selected_action": [self.order.pk]})
        self.assertEqual(Order.objects.get().status, "paid")  # paid -> delivered is not allowed
        self.client.post("/admin/orders/order/", {"action": "mark_packed", "_selected_action": [self.order.pk]})
        self.assertEqual(Order.objects.get().status, "packed")
