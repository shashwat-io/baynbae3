from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from catalog.models import Category, Product


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.live()

    def lastmod(self, obj):
        return obj.updated_at


class StaticSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return [
            "catalog:home",
            "catalog:shop",
            "catalog:about",
            "catalog:size_guide",
            "support:faq",
            "support:contact",
            "support:shipping_returns",
            "support:privacy",
            "support:terms",
        ]

    def location(self, item):
        return reverse(item)


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Category.objects.live()


sitemaps = {"products": ProductSitemap, "categories": CategorySitemap, "pages": StaticSitemap}
