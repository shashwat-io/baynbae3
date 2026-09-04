"""Drop the interim category_text column and make Product.category non-nullable."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_category_and_product_fk"),
    ]

    operations = [
        migrations.RemoveField(model_name="product", name="category_text"),
        migrations.AlterField(
            model_name="product",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="products", to="catalog.category"
            ),
        ),
    ]
