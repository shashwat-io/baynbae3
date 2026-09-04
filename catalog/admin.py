from django.contrib import admin
from django.db.models import Count, Q, Sum

from .models import Category, Product, ProductImage, Variant


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0
    fields = ("size", "stock", "sku")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("filename", "alt", "sort_order")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Add a row here and it appears in the nav as soon as it has a live product."""

    list_display = ("name", "slug", "sort_order", "live_products")
    list_editable = ("sort_order",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_live=Count("products", filter=Q(products__is_live=True)))

    @admin.display(description="live products", ordering="_live")
    def live_products(self, obj):
        return obj._live


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price_inr", "stock_total", "is_live", "is_featured", "sort_weight")
    list_filter = ("is_live", "is_featured", "category")
    list_editable = ("is_live", "is_featured", "sort_weight")
    search_fields = ("name", "slug", "print_name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [VariantInline, ProductImageInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "category", "price_inr", "is_live", "is_featured", "sort_weight")}),
        ("Copy", {"fields": ("tagline", "description", "fit_note", "model_note")}),
        ("Make", {"fields": ("print_name", "colourway", "fabric", "care", "batch_size")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_stock=Sum("variants__stock"))

    @admin.display(description="stock", ordering="_stock")
    def stock_total(self, obj):
        return obj._stock or 0


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    """Flat stock sheet: correct counts across every product without opening each one."""

    list_display = ("product", "size", "stock", "sku")
    list_editable = ("stock",)
    list_filter = ("size", "product__category", "product__is_live")
    search_fields = ("product__name", "sku")
    list_per_page = 100
    ordering = ("product__name", "id")
