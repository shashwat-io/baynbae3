import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from orders.tests import ADDRESS

from .models import Category, Product, ProductImage, Variant
from .seed_data import CATEGORIES, PRODUCTS
from .templatetags.money import rupees

# A scratch STATIC_ROOT for the production-mode render tests. Created once per
# process; the tests below clear it when they finish.
SCRATCH_STATIC_ROOT = Path(tempfile.mkdtemp(prefix="baynbae-static-"))


CATEGORY_NAMES = {"kaftans": "Kaftans", "dresses": "Resort dresses", "cover-ups": "Cover-ups"}


def category(slug, **kw):
    """Fetch or create a category. The launch five already exist (migration 0002), so given fields are applied to them."""
    obj, _ = Category.objects.get_or_create(slug=slug, defaults={"name": CATEGORY_NAMES.get(slug, slug.title())})
    if kw:
        for field, value in kw.items():
            setattr(obj, field, value)
        obj.save()
    return obj


def make(slug, live=True, sizes=None, **kw):
    p = Product.objects.create(
        name=slug, slug=slug, category=category(kw.get("category", "kaftans")), price_inr=kw.get("price", 1999),
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
        for token in (
            "--color-blue: #3B63FF;", "--color-cream: #F6F5EA;", "--color-muted: #6E6E68;",
            "--color-border: #DEDCCE;", "--color-surface: #FFFFFF;", "--color-error: #C4342B;",
            "--color-blue-hover: #2E4FD6;",
        ):
            self.assertIn(token, root)

    def test_select_caret_is_a_static_file_not_a_data_uri(self):
        self.assertNotIn("data:image", self.site)
        self.assertIn('url("../img/select-caret.svg")', self.site)
        self.assertTrue((settings.BASE_DIR / "static" / "img" / "select-caret.svg").exists())

    def test_theme_color_reads_the_cream_token(self):
        cream = re.search(r"--color-cream:\s*(#[0-9A-Fa-f]{6});", self.site).group(1)
        self.assertEqual(settings.STORE["theme_color"], cream)
        r = self.client.get(reverse("catalog:home"))
        self.assertContains(r, f'<meta name="theme-color" content="{cream}">')
        self.assertNotContains(r, 'content="#F6F5EA">' if cream != "#F6F5EA" else "never-present")


class SeedTests(TestCase):
    def test_seed_is_idempotent_and_images_exist(self):
        call_command("seed_catalog", "--force", verbosity=0)
        call_command("seed_catalog", "--force", verbosity=0)
        self.assertEqual(Product.objects.count(), len(PRODUCTS))
        self.assertEqual(list(Category.objects.values_list("slug", flat=True)), [c["slug"] for c in CATEGORIES])
        self.assertTrue(all(p.category.slug == d["category"] for p, d in zip(Product.objects.order_by("pk"), PRODUCTS)))
        editorial = Path(settings.BASE_DIR) / "static" / "img" / "editorial"
        self.assertTrue(all((editorial / c.image).exists() for c in Category.objects.all()))
        self.assertTrue(all(p.is_live for p in Product.objects.all()))
        self.assertTrue(all(1000 <= p.price_inr <= 5000 for p in Product.objects.all()))
        products_dir = Path(settings.BASE_DIR) / "static" / "img" / "products"
        missing = [i.filename for i in ProductImage.objects.all() if not (products_dir / i.filename).exists()]
        self.assertEqual(missing, [], "run tools/render_imagery.py")
        # stock survives a re-seed unless --reset-stock is passed
        v = Variant.objects.first()
        v.stock = 0
        v.save()
        call_command("seed_catalog", "--force", verbosity=0)
        self.assertEqual(Variant.objects.get(pk=v.pk).stock, 0)
        call_command("seed_catalog", "--reset-stock", "--force", verbosity=0)
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
            name="Sundowner Kaftan", slug="sundowner-kaftan", category=category("kaftans", image="cat-kaftans.svg"), price_inr=2499,
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

    def test_missing_image_files_fall_back_to_the_placeholder(self):
        """A typo in an admin-typed filename must never 500 a page (audit HIGH)."""
        ProductImage.objects.filter(product=self.product).update(filename="typo-that-does-not-exist.svg")
        Category.objects.filter(slug="kaftans").update(image="typo-that-does-not-exist.svg")
        placeholder = re.compile(r"img/placeholder\.[0-9a-f]{12}\.svg")
        for url in (reverse("catalog:home"), reverse("catalog:shop"), self.product.get_absolute_url()):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200, url)
                html = r.content.decode()
                self.assertRegex(html, placeholder)
                self.assertNotIn("typo-that-does-not-exist", html)

    def test_order_item_with_missing_image_file_renders_the_placeholder(self):
        from orders.models import Order, OrderItem

        self.client.post(reverse("orders:bag_add"), {"variant": self.variant.pk})
        self.client.post(reverse("orders:checkout"), ADDRESS)
        order = Order.objects.get()
        OrderItem.objects.filter(order=order).update(image_filename="typo-that-does-not-exist.svg")
        r = self.client.get(reverse("orders:pay", args=[order.order_number]))
        self.assertEqual(r.status_code, 200)
        self.assertRegex(r.content.decode(), r"img/placeholder\.[0-9a-f]{12}\.svg")


class ImageUrlTests(TestCase):
    """`image_url` in development: finders decide, the placeholder covers a miss."""

    @override_settings(DEBUG=True)
    def test_existing_file_resolves_and_missing_file_falls_back(self):
        from catalog.images import image_url

        self.assertEqual(image_url("img/editorial/hero.svg"), "/static/img/editorial/hero.svg")
        self.assertEqual(image_url("img/products/nope.svg"), "/static/img/placeholder.svg")
        self.assertEqual(image_url(""), "/static/img/placeholder.svg")


# ---------------------------------------------------------------- 7c: categories
class CategoryMigrationTests(TransactionTestCase):
    """0002 creates a Category per hardcoded entry and points every product at one; 0003 tightens the FK."""

    before = [("catalog", "0001_initial")]
    after = [("catalog", "0003_product_category_required")]

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.before)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _product(self, apps, slug, category):
        Product = apps.get_model("catalog", "Product")
        return Product.objects.create(
            name=slug, slug=slug, category=category, price_inr=1000, tagline="t", description="d", print_name="p", fabric="f"
        )

    def test_migration_creates_the_five_categories_and_links_products(self):
        old_apps = self.executor.loader.project_state(self.before).apps
        self._product(old_apps, "a-kaftan", "kaftans")
        self._product(old_apps, "a-dress", "dresses")
        self._product(old_apps, "a-hat", "hats")  # a slug the hardcoded list never had

        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.after)
        new_apps = self.executor.loader.project_state(self.after).apps
        NewCategory = new_apps.get_model("catalog", "Category")
        NewProduct = new_apps.get_model("catalog", "Product")

        expected = ["kaftans", "cover-ups", "dresses", "co-ord-sets", "shorts-sets", "hats"]
        self.assertEqual(list(NewCategory.objects.order_by("sort_order").values_list("slug", flat=True)), expected)
        kaftans = NewCategory.objects.get(slug="kaftans")
        self.assertEqual((kaftans.name, kaftans.short, kaftans.image, kaftans.sort_order), ("Kaftans", "Kaftan", "cat-kaftans.svg", 0))
        self.assertEqual(NewProduct.objects.get(slug="a-kaftan").category.slug, "kaftans")
        self.assertEqual(NewProduct.objects.get(slug="a-dress").category.slug, "dresses")
        self.assertEqual(NewProduct.objects.get(slug="a-hat").category.name, "Hats")
        # the FK is non-nullable after 0003
        field = NewProduct._meta.get_field("category")
        self.assertFalse(field.null)
        self.assertFalse(any(f.name == "category_text" for f in NewProduct._meta.get_fields()))


class CategoryNavTests(TestCase):
    def setUp(self):
        self.kaftans = category("kaftans", sort_order=2)
        self.dresses = category("dresses", sort_order=1)
        self.empty = category("hats", sort_order=0)
        self.draft_only = category("scarves", sort_order=0)
        make("k1", category="kaftans")
        make("d1", category="dresses")
        make("s1", category="scarves", live=False)

    def nav(self, response):
        return [c.slug for c in response.context["nav_categories"]]

    def test_nav_lists_only_categories_with_a_live_product_in_sort_order(self):
        r = self.client.get(reverse("catalog:home"))
        self.assertEqual(self.nav(r), ["dresses", "kaftans"])
        self.assertContains(r, self.kaftans.url)
        self.assertNotContains(r, self.empty.url)
        self.assertNotContains(r, self.draft_only.url)
        # shop chips and the home tiles use the same list
        self.assertEqual([c.slug for c in r.context["categories"]], ["dresses", "kaftans"])
        r = self.client.get(reverse("catalog:shop"))
        self.assertEqual([c.slug for c in r.context["categories"]], ["dresses", "kaftans"])

    def test_going_live_and_reordering_change_the_nav_without_code(self):
        Product.objects.filter(slug="s1").update(is_live=True)
        self.assertEqual(self.nav(self.client.get("/")), ["scarves", "dresses", "kaftans"])
        Category.objects.filter(slug="scarves").update(sort_order=9)
        self.assertEqual(self.nav(self.client.get("/")), ["dresses", "kaftans", "scarves"])

    def test_sitemap_lists_live_categories_only(self):
        body = self.client.get(reverse("sitemap")).content.decode()
        self.assertIn(self.kaftans.url, body)
        self.assertIn(self.dresses.url, body)
        self.assertNotIn(self.empty.url, body)

    def test_category_page_and_product_page_read_from_the_model(self):
        Category.objects.filter(slug="kaftans").update(blurb="Loose and lovely.", short="Kaftan")
        r = self.client.get(self.kaftans.url)
        self.assertContains(r, "Loose and lovely.")
        self.assertContains(r, "k1")
        self.assertNotContains(r, "d1")
        r = self.client.get(Product.objects.get(slug="k1").get_absolute_url())
        self.assertContains(r, f'<a href="{self.kaftans.url}">Kaftans</a>')
        self.assertEqual(self.client.get(reverse("catalog:shop_category", args=["hats"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("catalog:shop_category", args=["nope"])).status_code, 404)

    def test_home_hero_link_follows_the_kaftan_category(self):
        self.assertContains(self.client.get("/"), "Start with a kaftan")
        Category.objects.filter(slug="kaftans").update(slug="caftans")
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Start with a kaftan")


class CategoryAdminTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("boss", "boss@example.com", "pw")
        self.client.login(username="boss", password="pw")

    def test_category_added_in_the_admin_appears_in_nav_once_it_has_a_live_product(self):
        r = self.client.post(
            "/admin/catalog/category/add/",
            {"name": "Sarongs", "slug": "sarongs", "sort_order": 0, "short": "Sarong", "blurb": "Tie it, tuck it.", "image": ""},
        )
        self.assertEqual(r.status_code, 302, r.content[:300])
        sarongs = Category.objects.get(slug="sarongs")
        self.assertNotIn("sarongs", [c.slug for c in self.client.get("/").context["nav_categories"]])
        make("wave-sarong", category="sarongs")
        r = self.client.get("/")
        self.assertIn("sarongs", [c.slug for c in r.context["nav_categories"]])
        self.assertContains(r, f'<a href="{sarongs.url}"')
        self.assertContains(r, "Sarongs")
        # the list page renders with the live-product count
        self.assertContains(self.client.get("/admin/catalog/category/"), "Sarongs")
        self.assertEqual(self.client.get("/admin/catalog/product/").status_code, 200)

    def test_duplicate_slug_is_refused(self):
        category("kaftans")
        r = self.client.post("/admin/catalog/category/add/", {"name": "Other", "slug": "kaftans", "sort_order": 0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Category.objects.filter(slug="kaftans").count(), 1)


# ---------------------------------------------------------------- 7d: Indian digit grouping
class RupeesFilterTests(TestCase):
    def test_indian_grouping(self):
        for amount, expected in ((0, "₹ 0"), (999, "₹ 999"), (1000, "₹ 1,000"), (12500, "₹ 12,500"), (125000, "₹ 1,25,000"), (1234567, "₹ 12,34,567")):
            with self.subTest(amount=amount):
                self.assertEqual(rupees(amount), expected)
        self.assertEqual(rupees("2400"), "₹ 2,400")
        self.assertEqual(rupees(-1500), "-₹ 1,500")
        self.assertEqual(rupees("free"), "free")
        self.assertIsNone(rupees(None))

    def test_every_price_on_the_storefront_uses_the_filter(self):
        p = make("big-ticket", price=125000, sizes={"S": 2})
        r = self.client.get(p.get_absolute_url())
        self.assertContains(r, "₹ 1,25,000")
        self.assertNotContains(r, "125,000")
        self.client.post(reverse("orders:bag_add"), {"variant": p.variants.get().pk})
        for name in ("catalog:shop", "orders:bag", "orders:checkout"):
            with self.subTest(page=name):
                r = self.client.get(reverse(name))
                self.assertContains(r, "₹ 1,25,000")
                self.assertNotContains(r, "125,000")
        # humanize is gone for good
        self.assertNotIn("django.contrib.humanize", settings.INSTALLED_APPS)
        for path in (settings.BASE_DIR / "templates").rglob("*.html"):
            self.assertNotIn("intcomma", path.read_text(), path)
            self.assertNotIn("humanize", path.read_text(), path)


class SizeGuideTests(TestCase):
    """
    PROJECT.md S17: the chart is cm only, XS-XL, and every measurement cell is
    an owner placeholder until the owner supplies numbers. The figures that
    were there before were invented, and in inches.
    """

    def setUp(self):
        self.html = self.client.get(reverse("catalog:size_guide")).content.decode()
        self.table = self.html.split("<table")[1].split("</table>")[0]

    def test_every_measurement_cell_is_an_owner_placeholder(self):
        from catalog.sizes import FITTED_SIZES, SIZE_GUIDE_COLUMNS

        for size in FITTED_SIZES:
            for column in SIZE_GUIDE_COLUMNS:
                with self.subTest(size=size, column=column):
                    self.assertIn(f'<mark class="todo">[OWNER: {size} {column.lower()} in cm]</mark>', self.table)
        # No measurement survives as a number anywhere in the table.
        self.assertNotRegex(self.table.replace("todo", ""), r"\d")

    def test_chart_is_centimetres_and_has_no_invented_uk_column(self):
        for column in ("Bust", "Waist", "Hip", "Length"):
            self.assertIn(f"<th>{column} (cm)</th>", self.table)
        self.assertNotIn("(in)", self.table)
        self.assertNotIn("<th>UK</th>", self.table)
        self.assertNotIn("UK 6", self.html)

    def test_one_size_fit_claims_are_placeholders_not_invented_measurements(self):
        self.assertIn('[OWNER: one-size kaftan measurements in cm]', self.html)
        self.assertIn('[OWNER: cover-up lengths in cm]', self.html)
        self.assertNotIn("60 inches", self.html)
        self.assertNotIn("120 to 124", self.html)


class SeedGuardTests(TestCase):
    """
    seed_data.py is sample data: invented names, prints, prices and fabric
    compositions. The command must not be able to publish it to a real
    database by accident, and must not republish what an owner unpublished.
    """

    def test_refuses_to_run_outside_debug_without_force(self):
        from django.core.management.base import CommandError

        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_catalog", verbosity=0)
        self.assertIn("sample data", str(ctx.exception))
        self.assertEqual(Product.objects.count(), 0)

    def test_runs_outside_debug_when_forced(self):
        with override_settings(DEBUG=False):
            call_command("seed_catalog", "--force", verbosity=0)
        self.assertGreater(Product.objects.count(), 0)

    def test_runs_in_debug_without_force(self):
        with override_settings(DEBUG=True):
            call_command("seed_catalog", verbosity=0)
        self.assertGreater(Product.objects.live().count(), 0)

    def test_reseeding_does_not_republish_an_unpublished_product(self):
        call_command("seed_catalog", "--force", verbosity=0)
        product = Product.objects.live().first()
        Product.objects.filter(pk=product.pk).update(is_live=False)

        call_command("seed_catalog", "--force", verbosity=0)

        self.assertFalse(Product.objects.get(pk=product.pk).is_live, "re-seeding republished a product the owner took down")
        # Other products are still updated by the re-seed.
        self.assertGreater(Product.objects.live().count(), 0)


class TokenNamingTests(TestCase):
    """PROJECT.md S14 names every colour token --color-*. Both stylesheets follow it."""

    def setUp(self):
        self.site = (settings.BASE_DIR / "static" / "css" / "site.css").read_text()
        self.admin = (settings.BASE_DIR / "static" / "css" / "admin.css").read_text()

    def test_every_colour_token_uses_the_color_prefix(self):
        for name, css in (("site.css", self.site), ("admin.css", self.admin)):
            with self.subTest(file=name):
                root = re.search(r":root\s*\{[^}]*\}", css).group(0)
                declared = re.findall(r"(--[\w-]+)\s*:", root)
                # A colour token's whole value is one colour. --shadow carries
                # offsets around an rgba() and is not a colour token.
                colours = [
                    t for t in declared
                    if re.fullmatch(r"#[0-9A-Fa-f]{3,8}|rgba?\([^)]*\)", root.split(t + ":")[1].split(";")[0].split("/*")[0].strip())
                ]
                self.assertTrue(colours)
                for token in colours:
                    self.assertTrue(token.startswith("--color-"), f"{token} in {name} is a colour without the --color- prefix")

    def test_no_var_reference_uses_an_old_token_name(self):
        for name, css in (("site.css", self.site), ("admin.css", self.admin)):
            with self.subTest(file=name):
                for ref in set(re.findall(r"var\((--[\w-]+)\)", css)):
                    self.assertIn(f"{ref}:", self.site + self.admin, f"{ref} is referenced but never declared")

    def test_the_two_stylesheets_agree_on_shared_token_values(self):
        site_root = re.search(r":root\s*\{[^}]*\}", self.site).group(0)
        admin_root = re.search(r":root\s*\{[^}]*\}", self.admin).group(0)
        for token in ("--color-blue", "--color-cream", "--color-ink", "--color-error", "--color-muted"):
            in_site = re.search(rf"{token}:\s*([^;]+);", site_root)
            in_admin = re.search(rf"{token}:\s*([^;]+);", admin_root)
            if in_site and in_admin:
                self.assertEqual(in_site.group(1).split("/*")[0].strip(), in_admin.group(1).strip(), token)
