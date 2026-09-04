from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Category, Product, ProductImage, Variant
from catalog.seed_data import CARE_DEFAULT, CATEGORIES, IMAGE_ALTS, PRODUCTS


class Command(BaseCommand):
    help = (
        "Load the sample catalogue for development. Idempotent: existing products are updated, "
        "stock and published state are only set on first creation."
    )

    def add_arguments(self, parser):
        parser.add_argument("--reset-stock", action="store_true", help="Also overwrite stock counts.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run outside DEBUG. The seed catalogue is sample data, not real products — see README.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # PRODUCTS is invented sample data: names, prints, prices and fabric
        # compositions nobody has verified. Loading it into a real database
        # would publish sixteen products making claims about garments that do
        # not exist, so outside development it takes an explicit --force.
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_catalog loads sample data and DEBUG is false. Re-run with --force if you "
                "really mean to write the sample catalogue to this database."
            )
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
            fields["is_featured"] = data.get("featured", False)
            # is_live is set on creation only. Re-seeding must never republish a
            # product someone deliberately took off the storefront in the admin.
            product, created = Product.objects.update_or_create(
                slug=data["slug"], defaults=fields, create_defaults={**fields, "is_live": True}
            )
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
