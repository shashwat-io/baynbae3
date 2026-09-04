import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.tests import ADDRESS

from .models import Product, ProductImage, Variant
from .seed_data import PRODUCTS

# A scratch STATIC_ROOT for the production-mode render tests. Created once per
# process; the tests below clear it when they finish.
SCRATCH_STATIC_ROOT = Path(tempfile.mkdtemp(prefix="baynbae-static-"))


def make(slug, live=True, sizes=None, **kw):
    p = Product.objects.create(
        name=slug, slug=slug, category=kw.get("category", "kaftans"), price_inr=kw.get("price", 1999),
        tagline="t", description="para one\n\npara two", print_name="p", fabric="cotton", is_live=live,
    )
    for size, stock in (sizes or {"FREE": 5}).items():
        Variant.objects.create(product=p, size=size, stock=stock)
    ProductImage.objects.create(product=p, filename=f"{slug}-1.svg", alt="a", sort_order=1)
    ProductImage.objects.create(product=p, filename=f"{slug}-2.svg", alt="b", sort_order=2)
    return p


class ModelTests(TestCase):
    def test_in_stock_and_low_stock(self):
        p = make("a", sizes={"S": 0, "M": 0})
        self.assertFalse(p.in_stock)
        Variant.objects.filter(product=p, size="M").update(stock=2)
        p = Product.objects.get(pk=p.pk)
        self.assertTrue(p.in_stock)
        self.assertTrue(p.is_low_stock)

    def test_images_and_paragraphs(self):
        p = make("b")
        self.assertEqual(p.primary_image.filename, "b-1.svg")
        self.assertEqual(p.hover_image.filename, "b-2.svg")
        self.assertEqual(p.description_paragraphs, ["para one", "para two"])
        self.assertTrue(p.is_one_size)


class ViewTests(TestCase):
    def setUp(self):
        self.live = make("sun-kaftan", category="kaftans")
        self.hidden = make("secret", live=False)
        self.dress = make("gingham-dress", category="dresses", sizes={"S": 2, "M": 0, "L": 1})

    def test_home_and_shop_list_only_live(self):
        for url in (reverse("catalog:home"), reverse("catalog:shop")):
            r = self.client.get(url)
            self.assertContains(r, "sun-kaftan")
            self.assertNotContains(r, "secret")

    def test_category_filter_and_unknown_category(self):
        r = self.client.get(reverse("catalog:shop_category", args=["dresses"]))
        self.assertContains(r, "gingham-dress")
        self.assertNotContains(r, "sun-kaftan")
        self.assertEqual(self.client.get(reverse("catalog:shop_category", args=["hats"])).status_code, 404)

    def test_size_filter_uses_stock(self):
        r = self.client.get(reverse("catalog:shop"), {"size": "M"})
        self.assertNotContains(r, "gingham-dress")
        r = self.client.get(reverse("catalog:shop"), {"size": "L"})
        self.assertContains(r, "gingham-dress")

    def test_sort(self):
        r = self.client.get(reverse("catalog:shop"), {"sort": "high"})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("catalog:shop"), {"sort": "bogus"})
        self.assertEqual(r.status_code, 200)

    def test_product_page_sizes_and_404s(self):
        r = self.client.get(self.dress.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        m = Variant.objects.get(product=self.dress, size="M")
        self.assertIn(f'value="{m.pk}" aria-label="M" disabled', html)
        self.assertContains(r, "Only 1 left in L")
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse("catalog:product", args=["nope"])).status_code, 404)

    def test_sold_out_product_renders_without_form_submit(self):
        Variant.objects.filter(product=self.live).update(stock=0)
        r = self.client.get(self.live.get_absolute_url())
        self.assertContains(r, "Sold out, sorry")

    def test_empty_state(self):
        Product.objects.all().delete()
        r = self.client.get(reverse("catalog:shop"))
        self.assertContains(r, "Nothing here right now")
        self.assertEqual(self.client.get(reverse("catalog:home")).status_code, 200)

    def test_static_pages_sitemap_robots(self):
        for name in ("catalog:about", "catalog:size_guide", "sitemap", "robots"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get("/definitely-not-here/").status_code, 404)


HEX = re.compile(r"#[0-9a-fA-F]{3,6}\b")
ENCODED_HEX = re.compile(r"%23[0-9a-fA-F]{3,6}\b")


def outside_root_and_font_face(css):
    css = re.sub(r"@font-face\s*\{[^}]*\}", "", css)
    return re.sub(r":root\s*\{[^}]*\}", "", css)


class StyleSheetTests(TestCase):
    """Every colour lives in the :root block; nothing below it uses a raw hex value."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = (settings.BASE_DIR / "static" / "css" / "site.css").read_text()
        cls.admin = (settings.BASE_DIR / "static" / "css" / "admin.css").read_text()

    def test_no_raw_hex_below_root_in_site_css(self):
        body = outside_root_and_font_face(self.site)
        self.assertEqual(HEX.findall(body), [])
        self.assertEqual(ENCODED_HEX.findall(body), [], "hex hidden inside a data: URI")

    def test_no_raw_hex_below_root_in_admin_css(self):
        body = outside_root_and_font_face(self.admin)
        self.assertEqual(HEX.findall(body), [])

    def test_new_tokens_carry_the_project_values(self):
        root = re.search(r":root\s*\{[^}]*\}", self.site).group(0)
        for token in ("--blue-hover: #2E4FD6;", "--surface: #FFFFFF;", "--error: #C4342B;", "--blue: #3B63FF;", "--cream: #F6F5EA;"):
            self.assertIn(token, root)

    def test_select_caret_is_a_static_file_not_a_data_uri(self):
        self.assertNotIn("data:image", self.site)
        self.assertIn('url("../img/select-caret.svg")', self.site)
        self.assertTrue((settings.BASE_DIR / "static" / "img" / "select-caret.svg").exists())

    def test_theme_color_reads_the_cream_token(self):
        cream = re.search(r"--cream:\s*(#[0-9A-Fa-f]{6});", self.site).group(1)
        self.assertEqual(settings.STORE["theme_color"], cream)
        r = self.client.get(reverse("catalog:home"))
        self.assertContains(r, f'<meta name="theme-color" content="{cream}">')
        self.assertNotContains(r, 'content="#F6F5EA">' if cream != "#F6F5EA" else "never-present")


class SeedTests(TestCase):
    def test_seed_is_idempotent_and_images_exist(self):
        from pathlib import Path

        from django.conf import settings

        call_command("seed_catalog", verbosity=0)
        call_command("seed_catalog", verbosity=0)
        self.assertEqual(Product.objects.count(), len(PRODUCTS))
        self.assertTrue(all(p.is_live for p in Product.objects.all()))
        self.assertTrue(all(1000 <= p.price_inr <= 5000 for p in Product.objects.all()))
        products_dir = Path(settings.BASE_DIR) / "static" / "img" / "products"
        missing = [i.filename for i in ProductImage.objects.all() if not (products_dir / i.filename).exists()]
        self.assertEqual(missing, [], "run tools/render_imagery.py")
        # stock survives a re-seed unless --reset-stock is passed
        v = Variant.objects.first()
        v.stock = 0
        v.save()
        call_command("seed_catalog", verbosity=0)
        self.assertEqual(Variant.objects.get(pk=v.pk).stock, 0)
        call_command("seed_catalog", "--reset-stock", verbosity=0)
        self.assertGreater(Variant.objects.get(pk=v.pk).stock, 0)


@override_settings(
    DEBUG=False,
    STATIC_ROOT=SCRATCH_STATIC_ROOT,
    STORAGES={"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}},
    RAZORPAY_SANDBOX=True,
    RAZORPAY_KEY_ID="",
    RAZORPAY_KEY_SECRET="",
)
class ProductionRenderTests(TestCase):
    """
    Every route renders with the hashed-manifest static storage that production
    uses. A `{% static %}` on a path the manifest does not know raises, so this
    is the test that catches a DEBUG=false-only 500 (audit HIGH: home page).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("collectstatic", interactive=False, verbosity=0, clear=True)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(SCRATCH_STATIC_ROOT, ignore_errors=True)

    def setUp(self):
        # Product images must be real files: the manifest rejects anything else.
        self.product = Product.objects.create(
            name="Sundowner Kaftan", slug="sundowner-kaftan", category="kaftans", price_inr=2499,
            tagline="t", description="d", print_name="p", fabric="cotton", is_live=True, is_featured=True,
        )
        self.variant = Variant.objects.create(product=self.product, size="FREE", stock=5)
        for n in (1, 2):
            ProductImage.objects.create(product=self.product, filename=f"sundowner-kaftan-{n}.svg", alt="a", sort_order=n)

    def assert_renders(self, url, status=200):
        with self.subTest(url=url):
            r = self.client.get(url)
            self.assertEqual(r.status_code, status, url)

    def test_home_renders_with_manifest_storage(self):
        r = self.client.get(reverse("catalog:home"))
        self.assertEqual(r.status_code, 200)
        # all six tiles resolve to hashed files
        self.assertEqual(r.content.decode().count('class="ig__tile"'), 6)
        self.assertRegex(r.content.decode(), r"img/editorial/ig-1\.[0-9a-f]{12}\.svg")

    def test_home_skips_instagram_tiles_that_do_not_exist(self):
        from catalog.views import instagram_tiles

        with override_settings(STATICFILES_DIRS=[]):
            self.assertEqual(instagram_tiles(), [])

    def test_shop_product_and_error_pages_render(self):
        for url in (
            reverse("catalog:shop"),
            reverse("catalog:shop_category", args=["kaftans"]),
            reverse("catalog:shop") + "?sort=low&size=FREE",
            self.product.get_absolute_url(),
        ):
            self.assert_renders(url)
        self.assert_renders("/definitely-not-here/", status=404)

    def test_bag_checkout_pay_and_track_render(self):
        self.assert_renders(reverse("orders:bag"))
        self.client.post(reverse("orders:bag_add"), {"variant": self.variant.pk})
        self.assert_renders(reverse("orders:bag"))
        self.assert_renders(reverse("orders:checkout"))
        self.client.post(reverse("orders:checkout"), ADDRESS)
        from orders.models import Order

        order = Order.objects.get()
        self.assert_renders(reverse("orders:pay", args=[order.order_number]))
        self.assert_renders(reverse("orders:track"))
        self.assert_renders(reverse("orders:track") + f"?order_number={order.order_number}&email={ADDRESS['email']}")

    def test_every_footer_page_renders(self):
        for name in (
            "catalog:about", "catalog:size_guide", "support:faq", "support:contact",
            "support:shipping_returns", "support:privacy", "support:terms", "orders:track",
        ):
            self.assert_renders(reverse(name))
