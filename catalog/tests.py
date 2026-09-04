from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Product, ProductImage, Variant
from .seed_data import PRODUCTS


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
