"""
Categories move from a hardcoded list in catalog/models.py to a Category row
the owner manages in the admin.

``Product.category`` (a slug CharField) is renamed to ``category_text`` for
the length of this migration so the data step can read it; a Category row is
created for each of the previously hardcoded entries (and for any unknown
slug a product happens to carry), every product is pointed at its row, and
0003 drops the text column and makes the FK non-nullable.
"""
import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify

# The list that used to live in catalog/models.py, verbatim.
HARDCODED = [
    ("kaftans", "Kaftans", "Kaftan", "One size, zero effort. Throw it on over anything, or nothing.", "cat-kaftans.svg"),
    ("cover-ups", "Cover-ups", "Cover-up", "Sheer, breezy, and doing the absolute minimum amount of covering.", "cat-cover-ups.svg"),
    ("dresses", "Resort dresses", "Dress", "From breakfast buffet to sunset bar without a costume change.", "cat-dresses.svg"),
    ("co-ord-sets", "Co-ord sets", "Co-ord", "Two pieces, one decision. Wear them together, or split them up.", "cat-co-ord-sets.svg"),
    ("shorts-sets", "Shorts sets", "Shorts set", "Shirt and shorts that look like you planned it. You didn't.", "cat-shorts-sets.svg"),
]


def create_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    by_slug = {}
    for order, (slug, name, short, blurb, image) in enumerate(HARDCODED):
        by_slug[slug], _ = Category.objects.get_or_create(
            slug=slug, defaults={"name": name, "short": short, "blurb": blurb, "image": image, "sort_order": order}
        )
    for product in Product.objects.all().order_by("pk"):
        text = (product.category_text or "").strip()
        slug = slugify(text) or "uncategorised"
        category = by_slug.get(slug)
        if category is None:
            category, _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": text.replace("-", " ").title() or "Uncategorised", "sort_order": len(by_slug)}
            )
            by_slug[slug] = category
        product.category = category
        product.save(update_fields=["category"])


def restore_category_text(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    for product in Product.objects.select_related("category").all():
        product.category_text = product.category.slug if product.category_id else ""
        product.save(update_fields=["category_text"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("sort_order", models.PositiveIntegerField(default=0, help_text="Lower comes first in the nav.")),
                ("short", models.CharField(blank=True, help_text='Singular, for product cards: "Kaftan".', max_length=40)),
                ("blurb", models.CharField(blank=True, help_text="One line under the heading on the shop page.", max_length=200)),
                ("image", models.CharField(blank=True, help_text="File in static/img/editorial/, for the home-page tile.", max_length=120)),
            ],
            options={"ordering": ["sort_order", "name"], "verbose_name_plural": "categories"},
        ),
        migrations.RenameField(model_name="product", old_name="category", new_name="category_text"),
        migrations.AlterField(
            model_name="product",
            name="category_text",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, related_name="products", to="catalog.category"
            ),
        ),
        migrations.RunPython(create_categories, restore_category_text),
    ]
