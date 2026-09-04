"""
Payment-path tests. Nothing here touches the network: the Razorpay SDK is
mocked, checkout.js is never loaded, and signatures are computed with the
same HMAC the gateway uses.
"""
import hashlib
import hmac
import importlib.util
import json
import os
import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, ProductImage, Variant

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
    category, _ = Category.objects.get_or_create(slug="dresses", defaults={"name": "Resort dresses", "short": "Dress"})
    product = Product.objects.create(
        name=slug.replace("-", " ").title(),
        slug=slug,
        category=category,
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

    def test_add_with_non_numeric_quantity_is_ignored_with_a_message(self):
        """Audit: `quantity=abc` was a bare int() and a 500."""
        r = self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk, "quantity": "abc"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "quantity didn")
        self.assertEqual(self.client.session.get(SESSION_KEY, {}), {})

    def test_add_with_zero_negative_or_fractional_quantity_is_ignored_with_a_message(self):
        for bad in ("0", "-3", "1.5"):
            with self.subTest(quantity=bad):
                r = self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk, "quantity": bad}, follow=True)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, "quantity didn")
                self.assertEqual(self.client.session.get(SESSION_KEY, {}), {})

    def test_add_with_blank_quantity_means_one(self):
        # the product form sends no quantity field at all
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk, "quantity": " "})
        self.assertEqual(self.client.session[SESSION_KEY], {str(self.s.pk): 1})

    def test_update_with_non_numeric_variant_is_ignored_with_a_message(self):
        """Audit: `variant=abc` reached the ORM as a pk and was a 500."""
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})
        for action in ("inc", "dec", "remove"):
            with self.subTest(action=action):
                r = self.client.post(reverse("orders:bag_update"), {"variant": "abc", "action": action}, follow=True)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, "isn&#x27;t in your bag")
                self.assertEqual(self.client.session[SESSION_KEY], {str(self.s.pk): 1})


class PricingTests(TestCase):
    def test_shipping_is_free_on_every_prepaid_order(self):
        """Owner decision 7b: no fee, no threshold."""
        for subtotal in (0, 100, 1998, 1999, 10000):
            self.assertEqual(shipping_for(subtotal), 0, subtotal)
        self.assertNotIn("free_shipping_over_inr", settings.STORE)
        self.assertNotIn("shipping_flat_inr", settings.STORE)

    def test_bag_totals_carry_no_shipping_for_small_or_large_carts(self):
        cheap = make_product(slug="cheap", price=100, sizes={"S": 5})
        dear = make_product(slug="dear", price=5000, sizes={"S": 5})
        bag = Bag(self.client.session)
        bag.add(cheap.variants.get(), 1)
        self.assertEqual((bag.subtotal_inr, bag.shipping_inr, bag.total_inr), (100, 0, 100))
        bag.add(dear.variants.get(), 2)
        self.assertEqual((bag.subtotal_inr, bag.shipping_inr, bag.total_inr), (10100, 0, 10100))

    def test_no_threshold_copy_survives_anywhere(self):
        product = make_product(price=1500)
        self.client.post(reverse("orders:bag_add"), {"variant": product.variants.get(size="S").pk})
        pages = [reverse(n) for n in ("catalog:home", "catalog:shop", "orders:bag", "orders:checkout", "support:shipping_returns", "support:faq")]
        pages.append(product.get_absolute_url())
        for url in pages:
            with self.subTest(url=url):
                r = self.client.get(url)
                html = r.content.decode()
                self.assertNotIn("1,999", html)
                self.assertNotIn("₹79", html)
                self.assertNotIn("shipping over", html.lower())
        self.assertContains(self.client.get(reverse("catalog:home")), "Free shipping across India")
        self.assertContains(self.client.get(reverse("orders:bag")), "Shipping's on us")


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
        self.assertRedirects(r, reverse("orders:pay", args=[order.order_number]))
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.order_number, f"BNB-{1000 + order.pk}")
        self.assertEqual(order.subtotal_inr, 1500)
        self.assertEqual(order.shipping_inr, 0)
        self.assertEqual(order.total_inr, 1500)
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
        r = self.client.get(reverse("orders:pay", args=[self.order.order_number]))
        self.assertContains(r, reverse("orders:sandbox_gateway", args=[self.order.order_number]))
        self.assertContains(r, "Sandbox mode")
        self.assertContains(r, "2,999")

    @override_settings(RAZORPAY_SANDBOX=False, RAZORPAY_KEY_ID="rzp_test_abc", RAZORPAY_KEY_SECRET="s3cret")
    def test_live_pay_page_opens_standard_checkout_and_posts_to_verify(self):
        r = self.client.get(reverse("orders:pay", args=[self.order.order_number]))
        html = r.content.decode()
        self.assertContains(r, gateway.CHECKOUT_JS_URL)
        self.assertContains(r, 'id="rzp-options"')
        options = json.loads(html.split('id="rzp-options" type="application/json">')[1].split("</script>")[0])
        self.assertEqual(options["key"], "rzp_test_abc")
        self.assertEqual(options["order_id"], self.order.razorpay_order_id)
        self.assertEqual(options["amount"], 2999 * 100)  # paise, computed in the gateway module
        self.assertEqual(options["currency"], "INR")
        self.assertEqual(options["prefill"]["email"], ADDRESS["email"])
        self.assertNotIn("s3cret", html)
        self.assertContains(r, f'action="{reverse("orders:verify_payment")}"')
        self.assertContains(r, "csrfmiddlewaretoken")
        self.assertContains(r, "new Razorpay(")
        self.assertNotContains(r, "api.razorpay.com/v1/checkout/embedded")
        self.assertNotContains(r, "Sandbox mode")
        # the sandbox stand-in must not be reachable with real keys
        self.assertEqual(self.client.get(reverse("orders:sandbox_gateway", args=[self.order.order_number])).status_code, 404)

    @override_settings(RAZORPAY_SANDBOX=False, RAZORPAY_KEY_ID="rzp_test_abc", RAZORPAY_KEY_SECRET="s3cret")
    def test_dismissing_the_modal_leaves_the_order_and_stock_untouched(self):
        r = self.client.get(reverse("orders:pay", args=[self.order.order_number]))
        html = r.content.decode()
        # the dismiss handler talks to nobody: no request, no navigation
        handler = html[html.index("ondismiss"):]
        handler = handler[: handler.index("}")]
        self.assertNotIn("fetch(", handler)
        self.assertNotIn("location", handler)
        self.assertNotIn("submit(", handler)
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
        self.assertEqual(self.s.stock, 3)
        # ...and the shopper can simply try again
        self.assertEqual(self.client.get(reverse("orders:pay", args=[self.order.order_number])).status_code, 200)

    def test_unknown_order_number_404s(self):
        self.assertEqual(self.client.get(reverse("orders:pay", args=["BNB-999999"])).status_code, 404)

    def test_pay_page_is_404_for_any_other_session(self):
        r = Client().get(reverse("orders:pay", args=[self.order.order_number]))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Client().get(reverse("orders:cancelled", args=[self.order.order_number])).status_code, 404)
        self.assertEqual(Client().get(reverse("orders:sandbox_gateway", args=[self.order.order_number])).status_code, 404)

    def test_paid_order_redirects_to_confirmation(self):
        self.order.mark_paid("pay_1")
        r = self.client.get(reverse("orders:pay", args=[self.order.order_number]))
        self.assertRedirects(r, reverse("orders:confirmation", args=[self.order.order_number]))

    def test_retry_never_knocks_a_paid_order_back_to_pending(self):
        """
        Audit HIGH: shopper cancels (payment_failed), the webhook lands (paid,
        stock taken), then the shopper reloads /pay holding a stale
        payment_failed order. The retry update must not touch the paid row,
        and a later valid callback must not decrement stock a second time.
        """
        self.client.get(reverse("orders:cancelled", args=[self.order.order_number]))
        stale = Order.objects.get(pk=self.order.pk)
        self.assertEqual(stale.status, "payment_failed")
        # the webhook wins the race
        self.assertTrue(Order.objects.get(pk=self.order.pk).mark_paid("pay_webhook"))
        self.s.refresh_from_db()
        self.assertEqual(self.s.stock, 2)
        # /pay runs against the stale object
        with mock.patch("orders.views._session_order_or_404", return_value=stale):
            r = self.client.get(reverse("orders:pay", args=[self.order.order_number]))
        self.assertRedirects(r, reverse("orders:confirmation", args=[self.order.order_number]), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        # the browser's verify post arrives afterwards: no second decrement
        sig = gateway.sign_payment(self.order.razorpay_order_id, "pay_webhook")
        self.client.post(
            reverse("orders:verify_payment"),
            {"razorpay_order_id": self.order.razorpay_order_id, "razorpay_payment_id": "pay_webhook", "razorpay_signature": sig},
        )
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(self.s.stock, 2)

    def test_retry_on_an_expired_order_sends_shopper_back_to_bag(self):
        self.client.get(reverse("orders:cancelled", args=[self.order.order_number]))
        stale = Order.objects.get(pk=self.order.pk)
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.ABANDONED)
        with mock.patch("orders.views._session_order_or_404", return_value=stale):
            r = self.client.get(reverse("orders:pay", args=[self.order.order_number]))
        self.assertRedirects(r, reverse("orders:bag"), fetch_redirect_response=False)
        self.assertEqual(Order.objects.get(pk=self.order.pk).status, "abandoned")


@override_settings(RAZORPAY_SANDBOX=True, RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
class VerifyTests(TestCase):
    """The browser posts Razorpay's signed result to /checkout/verify/; the signature is the only thing we trust."""

    def setUp(self):
        self.product = make_product(price=2000, sizes={"S": 2})
        self.s = self.product.variants.get(size="S")
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})
        self.client.post(reverse("orders:bag_add"), {"variant": self.s.pk})
        self.client.post(reverse("orders:checkout"), ADDRESS)
        self.order = Order.objects.get()

    def verify(self, payment_id="pay_ok", signature=None, client=None, ajax=True):
        client = client or self.client
        signature = signature if signature is not None else gateway.sign_payment(self.order.razorpay_order_id, payment_id)
        headers = {"X-Requested-With": "XMLHttpRequest"} if ajax else {}
        return client.post(
            reverse("orders:verify_payment"),
            {"razorpay_order_id": self.order.razorpay_order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature},
            headers=headers,
        )

    def confirmation_url(self):
        return reverse("orders:confirmation", args=[self.order.order_number])

    def test_valid_signature_marks_paid_and_decrements_stock_once(self):
        r = self.verify()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True, "redirect_url": self.confirmation_url()})
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(self.order.razorpay_payment_id, "pay_ok")
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(self.s.stock, 0)

    def test_plain_form_post_redirects_instead_of_json(self):
        r = self.verify(ajax=False)
        self.assertRedirects(r, self.confirmation_url(), fetch_redirect_response=False)
        self.assertEqual(Order.objects.get().status, "paid")

    def test_duplicate_verify_is_idempotent(self):
        self.verify()
        self.verify()
        self.s.refresh_from_db()
        self.assertEqual(self.s.stock, 0)  # not -2
        self.assertEqual(Order.objects.filter(status="paid").count(), 1)

    def test_bad_signature_marks_failed_and_leaves_stock(self):
        r = self.verify(signature="deadbeef")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])
        self.assertEqual(r.json()["redirect_url"], reverse("orders:cancelled", args=[self.order.order_number]))
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "payment_failed")
        self.assertEqual(self.s.stock, 2)
        # the plain-form flavour lands on the retry page
        r = self.verify(signature="deadbeef", ajax=False)
        self.assertRedirects(r, reverse("orders:cancelled", args=[self.order.order_number]), fetch_redirect_response=False)

    def test_signature_for_other_order_rejected(self):
        wrong = gateway.sign_payment("order_other", "pay_ok")
        self.verify(signature=wrong)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "paid")

    def test_unknown_gateway_order_400(self):
        r = self.client.post(
            reverse("orders:verify_payment"),
            {"razorpay_order_id": "order_nope", "razorpay_payment_id": "p", "razorpay_signature": "s"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])

    def test_verify_requires_a_csrf_token_and_only_the_webhook_is_exempt(self):
        """Audit 7a: verify is same-origin now, so the CSRF exemption is gone; the webhook keeps its own."""
        from . import views

        self.assertFalse(getattr(views.verify_payment, "csrf_exempt", False))
        self.assertTrue(getattr(views.razorpay_webhook, "csrf_exempt", False))
        self.assertFalse(hasattr(views, "payment_callback"))
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client.cookies  # same session, no token
        r = self.verify(client=strict)
        self.assertEqual(r.status_code, 403)
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
        self.assertEqual(self.s.stock, 2)

    def test_valid_signature_from_a_session_that_lost_its_cookie_still_pays_and_earns_the_receipt(self):
        """The signature only ever reaches the payer's browser, so it is proof enough on its own."""
        anonymous = Client()
        r = self.verify(client=anonymous)
        self.assertEqual(r.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(anonymous.get(self.confirmation_url()).status_code, 200)
        # the session that started the checkout gets it too
        self.assertEqual(self.client.get(self.confirmation_url()).status_code, 200)

    def test_confirmation_clears_bag_and_shows_order(self):
        self.verify()
        r = self.client.get(self.confirmation_url())
        self.assertContains(r, self.order.order_number)
        self.assertContains(r, "re in.")
        self.assertEqual(self.client.session.get(SESSION_KEY), {})

    def test_confirmation_for_unpaid_order_redirects_to_pay(self):
        r = self.client.get(self.confirmation_url())
        self.assertRedirects(r, reverse("orders:pay", args=[self.order.order_number]))

    def test_receipt_is_session_gated_not_a_bearer_link(self):
        """Audit MEDIUM: the old signed-token link exposed name, address, phone and email forever."""
        self.verify()
        url = self.confirmation_url()
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, ADDRESS["address1"])
        # the paying session keeps access after the pending marker is consumed
        self.assertNotIn("pending_order", self.client.session)
        self.assertEqual(self.client.get(url).status_code, 200)
        # a fresh browser holding only the order number sees nothing
        stranger = Client()
        r = stranger.get(url)
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(ADDRESS["address1"].encode(), r.content)
        self.assertNotIn(ADDRESS["phone"].encode(), r.content)
        # no token-style URL survives anywhere in the order pages
        self.assertFalse(hasattr(Order, "token"))
        self.assertFalse(hasattr(Order, "from_token"))

    def test_oversell_is_flagged_not_hidden(self):
        # someone else bought the stock while this shopper was on the gateway
        Variant.objects.filter(pk=self.s.pk).update(stock=1)
        self.verify()
        self.order.refresh_from_db()
        self.s.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertIn("OVERSOLD", self.order.ops_notes)
        self.assertEqual(self.s.stock, 0)

    def test_cancelled_page_marks_failed_and_offers_retry(self):
        r = self.client.get(reverse("orders:cancelled", args=[self.order.order_number]))
        self.assertContains(r, "Try paying again")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "payment_failed")
        # retry flips it back to pending against the same gateway order
        r = self.client.get(reverse("orders:pay", args=[self.order.order_number]))
        self.assertEqual(r.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
        # ...and a good verify after a failed attempt still completes
        self.verify()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")

    def test_sandbox_gateway_round_trip_through_verify(self):
        r = self.client.post(reverse("orders:sandbox_gateway", args=[self.order.order_number]))
        self.assertContains(r, "Payment succeeds")
        r = self.client.post(reverse("orders:sandbox_gateway", args=[self.order.order_number]), {"outcome": "success"})
        html = r.content.decode()
        self.assertContains(r, f'action="{reverse("orders:verify_payment")}"')
        self.assertContains(r, "csrfmiddlewaretoken")
        # submit the stand-in's form exactly as the browser would
        fields = dict(re.findall(r'name="(razorpay_\w+)" value="([^"]+)"', html))
        r = self.client.post(reverse("orders:verify_payment"), fields)
        self.assertRedirects(r, self.confirmation_url(), fetch_redirect_response=False)
        self.assertEqual(Order.objects.get().status, "paid")
        r = self.client.post(reverse("orders:sandbox_gateway", args=[self.order.order_number]), {"outcome": "fail"})
        self.assertRedirects(r, reverse("orders:cancelled", args=[self.order.order_number]), fetch_redirect_response=False)


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

    def test_webhook_marks_paid_and_is_idempotent_with_verify(self):
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
        # the browser's verify post arriving afterwards changes nothing
        cb_sig = gateway.sign_payment("order_LIVE123", "pay_W")
        r = self.client.post(reverse("orders:verify_payment"), {"razorpay_order_id": "order_LIVE123", "razorpay_payment_id": "pay_W", "razorpay_signature": cb_sig})
        self.assertEqual(r.status_code, 302)
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

    def track(self, order_number=None, email="ananya@example.com"):
        return self.client.get(reverse("orders:track"), {"order_number": order_number or self.order.order_number, "email": email})

    def test_track_by_order_number_and_email_only(self):
        r = self.track(order_number=self.order.order_number.lower(), email="ANANYA@example.com")
        self.assertContains(r, "DL123")
        # tracking never hands out a link to the session-gated receipt
        self.assertNotContains(r, "Full order details")
        self.assertNotContains(r, ADDRESS["address1"])
        r = self.track(email="someone@else.com")
        self.assertContains(r, "No order matches")
        self.assertNotContains(r, "DL123")
        # the phone number is no longer a credential (audit: sequential numbers + last-10-digits)
        r = self.client.get(reverse("orders:track"), {"order_number": self.order.order_number, "email": "+91 98765 43210"})
        self.assertNotContains(r, "DL123")
        r = self.client.get(reverse("orders:track"), {"order_number": self.order.order_number, "contact": "ananya@example.com"})
        self.assertNotContains(r, "DL123")

    def test_track_is_rate_limited_to_ten_lookups_an_hour_per_session(self):
        for _ in range(10):
            r = self.track(email="wrong@example.com")
            self.assertContains(r, "No order matches")
            self.assertNotContains(r, "Try again later")
        # the eleventh attempt is refused even with the right email
        r = self.track()
        self.assertContains(r, "Try again later")
        self.assertNotContains(r, "DL123")
        self.assertNotContains(r, "No order matches")
        # a different browser is unaffected
        r = Client().get(reverse("orders:track"), {"order_number": self.order.order_number, "email": "ananya@example.com"})
        self.assertContains(r, "DL123")
        # ...and the limit expires after an hour
        session = self.client.session
        session["track_attempts"] = [t - 3601 for t in session["track_attempts"]]
        session.save()
        r = self.track()
        self.assertContains(r, "DL123")

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



class AdminTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        User.objects.create_superuser("boss", "boss@example.com", "pw")
        self.client.login(username="boss", password="pw")
        self.order = Order.objects.create(status="paid", subtotal_inr=1, shipping_inr=0, total_inr=1, **ADDRESS)

    def test_order_admin_pages_render(self):
        self.assertEqual(self.client.get("/admin/orders/order/").status_code, 200)
        self.assertEqual(self.client.get(f"/admin/orders/order/{self.order.pk}/change/").status_code, 200)

    def test_status_badge_uses_a_stylesheet_class_not_inline_colour(self):
        r = self.client.get("/admin/orders/order/")
        html = r.content.decode()
        self.assertIn('class="status-badge status-badge--paid"', html)
        self.assertIn("css/admin.css", html)
        badge = html[html.index("status-badge"):]
        self.assertNotIn("style=", badge[: badge.index("</span>")])
        self.assertNotRegex(badge[: badge.index("</span>")], r"#[0-9a-fA-F]{3,6}")

    def test_bulk_actions_follow_lifecycle(self):
        self.client.post("/admin/orders/order/", {"action": "mark_delivered", "_selected_action": [self.order.pk]})
        self.assertEqual(Order.objects.get().status, "paid")  # paid -> delivered is not allowed
        self.client.post("/admin/orders/order/", {"action": "mark_packed", "_selected_action": [self.order.pk]})
        self.assertEqual(Order.objects.get().status, "packed")
