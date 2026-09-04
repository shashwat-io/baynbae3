from django.test import TestCase
from django.urls import reverse

from .models import SupportTicket


class SupportTests(TestCase):
    def test_pages_render(self):
        for name in ("support:faq", "support:contact", "support:shipping_returns", "support:privacy", "support:terms"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_contact_creates_ticket(self):
        r = self.client.post(
            reverse("support:contact"),
            {"name": "A", "email": "a@example.com", "order_number": "bnb-1001", "category": "sizing", "message": "Between S and M for the slip dress?"},
        )
        self.assertRedirects(r, reverse("support:contact"))
        t = SupportTicket.objects.get()
        self.assertEqual((t.order_number, t.category, t.status), ("BNB-1001", "sizing", "open"))

    def test_validation_and_honeypot(self):
        r = self.client.post(reverse("support:contact"), {"email": "a@example.com", "category": "other", "message": "hi"})
        self.assertContains(r, "little more detail")
        r = self.client.post(reverse("support:contact"), {"email": "a@example.com", "category": "other", "message": "spam spam spam spam", "website": "http://x"})
        self.assertEqual(SupportTicket.objects.count(), 0)
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------- brand facts
from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import override_settings  # noqa: E402

from catalog.models import Product  # noqa: E402
from orders.models import Order  # noqa: E402
from orders.tests import ADDRESS, load_settings  # noqa: E402

# Phrases that must not reappear anywhere. "over ₹" catches a shipping threshold
# in any form, spaced or not, which a bare "1,999" does not: a product may
# legitimately cost that much.
FORBIDDEN = ("Bengaluru", "Erode", "Bhiwandi", "over ₹", "7 days")
SHIPPING = "Free shipping across India on all prepaid orders."
PLACEHOLDER = '<mark class="todo">[OWNER: {}]</mark>'


# Sandbox is pinned exactly as every other checkout test pins it: these tests
# post a real checkout, and without this a developer's .env keys would send the
# suite to the live Razorpay API (CLAUDE.md: tests never make network calls).
@override_settings(RAZORPAY_SANDBOX=True, RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
class BrandFactTests(TestCase):
    """
    Every brand fact on the site is either a locked owner decision or a visible
    [OWNER: …] placeholder. Nothing is invented: no city, no timeline, no story.
    """

    def setUp(self):
        call_command("seed_catalog", "--force", verbosity=0)
        self.product = Product.objects.live().first()

    def every_page(self):
        """Every public page, including a filled bag, checkout, and a pay page for a real order."""
        self.client.post(reverse("orders:bag_add"), {"variant": self.product.variants.first().pk})
        urls = [
            reverse(n)
            for n in (
                "catalog:home", "catalog:shop", "catalog:about", "catalog:size_guide", "orders:bag", "orders:checkout",
                "orders:track", "support:faq", "support:contact", "support:shipping_returns", "support:privacy", "support:terms",
            )
        ]
        urls += [p.get_absolute_url() for p in Product.objects.live()]
        # The test address must not itself contain a forbidden word.
        self.client.post(reverse("orders:checkout"), {**ADDRESS, "city": "Panaji", "state": "Goa", "pincode": "403001"})
        urls.append(reverse("orders:pay", args=[Order.objects.get().order_number]))
        return urls

    def test_the_named_invented_facts_stay_gone(self):
        """
        A denylist of the specific claims this pass removed — it is a
        regression guard, not proof that every fact on the site is verified.
        Unverified copy the owner still has to confirm (fabric compositions and
        GSM on product pages, the size chart, batch numbers, studio hours) is
        NOT covered here.
        """
        for url in self.every_page():
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                html = r.content.decode()
                for word in FORBIDDEN:
                    self.assertNotIn(word, html)

    def test_locked_shipping_copy_on_every_surface(self):
        self.client.post(reverse("orders:bag_add"), {"variant": self.product.variants.first().pk})
        for name in ("catalog:home", "orders:bag", "orders:checkout", "support:shipping_returns", "support:faq"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn(SHIPPING, html)
                self.assertNotIn("on all orders", html)
        product_html = self.client.get(self.product.get_absolute_url()).content.decode()
        # The ticker alone would satisfy assertIn; the product page must carry the sentence itself too.
        self.assertGreaterEqual(product_html.count(SHIPPING), 3)
        bag_html = self.client.get(reverse("orders:bag")).content.decode()
        self.assertGreaterEqual(bag_html.count(SHIPPING), 3)

    def test_locked_returns_copy_on_every_surface(self):
        for url in (reverse("catalog:home"), reverse("support:faq"), reverse("support:shipping_returns"), self.product.get_absolute_url()):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertIn("defects only", html)
                self.assertIn("3–5 days", html)
                self.assertNotIn("within 7 days", html)
                self.assertNotIn("Exchanges within", html)
        policy = self.client.get(reverse("support:shipping_returns")).content.decode()
        self.assertIn("Returns are for defects only", policy)
        self.assertIn("within 3–5 days of delivery", policy)
        self.assertNotIn("Exchanges within", policy)
        self.assertIn("Returns for defects only, within 3–5 days", self.client.get(reverse("catalog:home")).content.decode())

    def test_blank_facts_render_as_owner_placeholders(self):
        expected = {
            "catalog:home": ("dispatch city", "dispatch window", "sourcing story — real fabric origin and process"),
            "catalog:about": ("sourcing story — real fabric origin and process", "city where the label started"),
            "support:shipping_returns": ("dispatch city", "dispatch window", "delivery window"),
            "support:faq": ("dispatch city", "dispatch window", "delivery window"),
            "support:contact": ("phone/WhatsApp number", "business address"),
            "support:terms": ("registered business address", "jurisdiction city", "print process"),
        }
        for name, facts in expected.items():
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                for fact in facts:
                    self.assertIn(PLACEHOLDER.format(fact), html)
        self.assertIn(PLACEHOLDER.format("dispatch window"), self.client.get(self.product.get_absolute_url()).content.decode())

    def test_blank_support_email_renders_placeholder_not_env_fallback(self):
        # settings: no default address is baked in
        self.assertEqual(load_settings(DEBUG="true").STORE["support_email"], "")
        self.assertEqual(load_settings(DEBUG="true", SUPPORT_EMAIL="x@example.in").STORE["support_email"], "x@example.in")

        with override_settings(STORE={**settings.STORE, "support_email": ""}):
            for name in ("support:contact", "support:terms", "support:privacy", "catalog:home"):
                with self.subTest(page=name):
                    html = self.client.get(reverse(name)).content.decode()
                    self.assertIn(PLACEHOLDER.format("support email"), html)
                    self.assertNotIn("hello@baynbae.in", html)
                    self.assertNotIn("mailto:", html)

        with override_settings(STORE={**settings.STORE, "support_email": "x@example.in", "support_whatsapp": "919999999999"}):
            html = self.client.get(reverse("support:contact")).content.decode()
            self.assertIn('href="mailto:x@example.in"', html)
            self.assertIn("wa.me/919999999999", html)
            self.assertNotIn("[OWNER: support email]", html)
            self.assertNotIn("[OWNER: phone/WhatsApp number]", html)
