from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Category, Product, ProductImage, Variant
from catalog.seed_data import CARE_DEFAULT, CATEGORIES, IMAGE_ALTS, PRODUCTS


class Command(BaseCommand):
    help = "Load the launch catalogue. Idempotent: existing products are updated, stock is only set on first creation."

    def add_arguments(self, parser):
        parser.add_argument("--reset-stock", action="store_true", help="Also overwrite stock counts.")

    @transaction.atomic
    def handle(self, *args, **options):
        created_n = updated_n = 0
        categories = {}
        for order, cat in enumerate(CATEGORIES):
            categories[cat["slug"]], _ = Category.objects.update_or_create(
                slug=cat["slug"], defaults={**{k: v for k, v in cat.items() if k != "slug"}, "sort_order": order}
            )
        for data in PRODUCTS:
            fields = {
                k: data[k]
                for k in ("name", "price_inr", "tagline", "description", "print_name", "colourway", "fabric", "fit_note", "model_note", "batch_size", "sort_weight")
            }
            fields["category"] = categories[data["category"]]
            fields["care"] = data.get("care", CARE_DEFAULT)
            fields["is_live"] = True
            fields["is_featured"] = data.get("featured", False)
            product, created = Product.objects.update_or_create(slug=data["slug"], defaults=fields)
            created_n += created
            updated_n += not created
            for size, qty in data["stock"].items():
                variant, v_created = Variant.objects.get_or_create(
                    product=product, size=size, defaults={"stock": qty, "sku": f"BNB-{product.pk:03d}-{size}"}
                )
                if not v_created and options["reset_stock"]:
                    variant.stock = qty
                    variant.save(update_fields=["stock"])
            for n in (1, 2, 3):
                ProductImage.objects.update_or_create(
                    product=product,
                    filename=f"{data['slug']}-{n}.svg",
                    defaults={"sort_order": n, "alt": IMAGE_ALTS[n].format(**data)},
                )
        self.stdout.write(self.style.SUCCESS(f"Catalogue seeded: {created_n} created, {updated_n} updated."))
