from django.core.validators import MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse

from .sizes import SIZE_CHOICES, SIZE_ORDER, size_label


class CategoryQuerySet(models.QuerySet):
    def live(self):
        """Categories that have at least one live product — the only ones worth a nav link."""
        return self.filter(products__is_live=True).distinct()


class Category(models.Model):
    """Managed in the admin. Adding one here puts it in the nav, the shop chips and the sitemap."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower comes first in the nav.")
    short = models.CharField(max_length=40, blank=True, help_text='Singular, for product cards: "Kaftan".')
    blurb = models.CharField(max_length=200, blank=True, help_text="One line under the heading on the shop page.")
    image = models.CharField(max_length=120, blank=True, help_text="File in static/img/editorial/, for the home-page tile.")

    objects = CategoryQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:shop_category", args=[self.slug])

    @property
    def url(self):
        return self.get_absolute_url()

    @property
    def image_url(self):
        return static(f"img/editorial/{self.image}") if self.image else ""

    @property
    def short_name(self):
        return self.short or self.name


class ProductQuerySet(models.QuerySet):
    def live(self):
        return self.filter(is_live=True)

    def with_stock(self):
        return self.annotate(total_stock=models.Sum("variants__stock"))


class Product(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    price_inr = models.PositiveIntegerField(
        "price (₹)", validators=[MinValueValidator(1)], help_text="Whole rupees."
    )
    tagline = models.CharField(max_length=140, help_text="One line under the name.")
    description = models.TextField(help_text="Plain paragraphs; blank line between them.")
    print_name = models.CharField(max_length=80, help_text='e.g. "Tide Stripe"')
    colourway = models.CharField(max_length=80, default="Bay blue on cream")
    fabric = models.CharField(max_length=200)
    care = models.CharField(max_length=200, default="Gentle machine wash cold. Line dry in the shade. Cool iron if you must.")
    fit_note = models.CharField(max_length=200, blank=True)
    model_note = models.CharField(max_length=120, blank=True, help_text='e.g. "Model is 5\'5" and wears S"')
    batch_size = models.PositiveSmallIntegerField(default=20, help_text="Pieces cut in this run — shown on the page.")
    is_live = models.BooleanField(default=False, help_text="Only live products appear on the storefront.")
    is_featured = models.BooleanField(default=False, help_text="Featured on the home page.")
    sort_weight = models.SmallIntegerField(default=0, help_text="Higher floats to the top of listings.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-sort_weight", "-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:product", args=[self.slug])

    # -- stock -----------------------------------------------------------
    def sized_variants(self):
        return sorted(self.variants.all(), key=lambda v: SIZE_ORDER.get(v.size, 99))

    @property
    def in_stock(self):
        return any(v.stock > 0 for v in self.variants.all())

    @property
    def total_stock(self):
        return sum(v.stock for v in self.variants.all())

    @property
    def is_low_stock(self):
        total = self.total_stock
        return 0 < total <= 5

    @property
    def is_one_size(self):
        variants = list(self.variants.all())
        return len(variants) == 1 and variants[0].size == "FREE"

    # -- images ----------------------------------------------------------
    def ordered_images(self):
        return sorted(self.images.all(), key=lambda i: i.sort_order)

    @property
    def primary_image(self):
        images = self.ordered_images()
        return images[0] if images else None

    @property
    def hover_image(self):
        images = self.ordered_images()
        return images[1] if len(images) > 1 else None

    @property
    def description_paragraphs(self):
        return [p.strip() for p in self.description.split("\n\n") if p.strip()]

    @property
    def is_new(self):
        from django.utils import timezone

        return (timezone.now() - self.created_at).days <= 30


class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=8, choices=SIZE_CHOICES)
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=40, unique=True, null=True, blank=True)

    class Meta:
        unique_together = [("product", "size")]
        ordering = ["product", "id"]

    def __str__(self):
        return f"{self.product.name} · {self.size_label}"

    @property
    def size_label(self):
        return size_label(self.size)

    @property
    def is_available(self):
        return self.stock > 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    filename = models.CharField(max_length=160, help_text="File in static/img/products/")
    alt = models.CharField(max_length=200)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.filename

    @property
    def url(self):
        return static(f"img/products/{self.filename}")
