from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product_name", "size", "quantity", "unit_price_inr", "line_total")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="line total (₹)")
    def line_total(self, obj):
        return obj.line_total_inr


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "created_at", "customer_name", "city", "total_inr", "status_badge", "flag")
    list_filter = ("status", "state", "created_at")
    search_fields = ("order_number", "email", "phone", "customer_name", "razorpay_payment_id", "razorpay_order_id")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [OrderItemInline]
    actions = ["mark_packed", "mark_shipped", "mark_delivered"]
    readonly_fields = (
        "order_number", "created_at", "updated_at", "paid_at", "subtotal_inr", "shipping_inr", "total_inr",
        "razorpay_order_id", "razorpay_payment_id", "customer_name", "email", "phone",
        "address1", "address2", "city", "state", "pincode", "note",
    )
    fieldsets = (
        ("Order", {"fields": ("order_number", "status", "created_at", "paid_at", "ops_notes")}),
        ("Shipping", {"fields": ("courier", "tracking_number", "tracking_url")}),
        ("Customer", {"fields": ("customer_name", "email", "phone", "address1", "address2", "city", "state", "pincode", "note")}),
        ("Money", {"fields": ("subtotal_inr", "shipping_inr", "total_inr", "razorpay_order_id", "razorpay_payment_id")}),
    )

    class Media:
        css = {"all": ("css/admin.css",)}

    @admin.display(description="status", ordering="status")
    def status_badge(self, obj):
        return format_html('<span class="status-badge status-badge--{}">{}</span>', obj.status, obj.get_status_display())

    @admin.display(description="")
    def flag(self, obj):
        return "⚠︎ check stock" if "OVERSOLD" in (obj.ops_notes or "") else ""

    def _bulk(self, request, queryset, from_statuses, to_status, label):
        n = queryset.filter(status__in=from_statuses).update(status=to_status, updated_at=timezone.now())
        self.message_user(request, f"{n} order(s) marked {label}.")

    @admin.action(description="Mark selected as packed")
    def mark_packed(self, request, queryset):
        self._bulk(request, queryset, ["paid"], "packed", "packed")

    @admin.action(description="Mark selected as shipped")
    def mark_shipped(self, request, queryset):
        self._bulk(request, queryset, ["paid", "packed"], "shipped", "shipped")

    @admin.action(description="Mark selected as delivered")
    def mark_delivered(self, request, queryset):
        self._bulk(request, queryset, ["shipped"], "delivered", "delivered")

    def has_add_permission(self, request):
        return False
