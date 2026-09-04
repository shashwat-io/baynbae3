import logging

from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product, Variant

log = logging.getLogger(__name__)

INDIAN_STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
    "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
    "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]
STATE_CHOICES = [(s, s) for s in INDIAN_STATES]


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Paid"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        ABANDONED = "abandoned", "Abandoned"
        REFUNDED = "refunded", "Refunded"

    PAID_STATUSES = {"paid", "packed", "shipped", "delivered", "refunded"}

    order_number = models.CharField(max_length=16, unique=True, blank=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    customer_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    address1 = models.CharField("address line 1", max_length=200)
    address2 = models.CharField("address line 2", max_length=200, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=60, choices=STATE_CHOICES)
    pincode = models.CharField(max_length=6)
    note = models.CharField(max_length=200, blank=True, help_text="Anything the customer told us.")

    subtotal_inr = models.PositiveIntegerField("subtotal (₹)")
    shipping_inr = models.PositiveIntegerField("shipping (₹)")
    total_inr = models.PositiveIntegerField("total (₹)")

    razorpay_order_id = models.CharField(max_length=64, blank=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True)

    courier = models.CharField(max_length=60, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True)
    tracking_url = models.URLField(blank=True)
    ops_notes = models.TextField(blank=True, help_text="Internal. Oversell flags land here.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number or f"Order #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.order_number:
            self.order_number = f"BNB-{1000 + self.pk}"
            Order.objects.filter(pk=self.pk).update(order_number=self.order_number)

    def get_absolute_url(self):
        # The receipt is session-gated (see orders.views.confirmation); this URL
        # is only useful to the browser that placed the order.
        return reverse("orders:confirmation", args=[self.order_number])

    # -- state -----------------------------------------------------------
    @property
    def is_paid(self):
        return self.status in self.PAID_STATUSES

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING

    @property
    def can_retry_payment(self):
        return self.status in {self.Status.PENDING, self.Status.PAYMENT_FAILED}

    @property
    def timeline(self):
        steps = [("paid", "Order confirmed"), ("packed", "Packed"), ("shipped", "Shipped"), ("delivered", "Delivered")]
        order = ["paid", "packed", "shipped", "delivered"]
        reached = order.index(self.status) if self.status in order else -1
        return [(label, i <= reached) for i, (_, label) in enumerate(steps)]

    def mark_paid(self, payment_id):
        """
        Transition pending -> paid exactly once and decrement stock exactly once.
        Safe to call repeatedly (verify endpoint + webhook); later calls are no-ops.
        Returns True if this call performed the transition.
        """
        with transaction.atomic():
            moved = Order.objects.filter(
                pk=self.pk, status__in=[self.Status.PENDING, self.Status.PAYMENT_FAILED]
            ).update(status=self.Status.PAID, razorpay_payment_id=payment_id, paid_at=timezone.now())
            if not moved:
                return False
            self.status = self.Status.PAID
            self.razorpay_payment_id = payment_id
            self.paid_at = timezone.now()
            oversold = []
            for item in self.items.select_related("variant"):
                if item.variant_id is None:
                    oversold.append(f"{item.product_name} {item.size}: variant deleted before payment")
                    continue
                taken = Variant.objects.filter(pk=item.variant_id, stock__gte=item.quantity).update(
                    stock=F("stock") - item.quantity
                )
                if not taken:
                    Variant.objects.filter(pk=item.variant_id).update(stock=0)
                    oversold.append(f"{item.product_name} {item.size} x{item.quantity}: stock ran out before payment")
            if oversold:
                note = "OVERSOLD — check before packing:\n" + "\n".join(oversold)
                self.ops_notes = (self.ops_notes + "\n\n" + note).strip()
                Order.objects.filter(pk=self.pk).update(ops_notes=self.ops_notes)
                log.warning("Order %s oversold: %s", self.order_number, oversold)
        log.info("Order %s paid (%s)", self.order_number, payment_id)
        return True

    def mark_payment_failed(self):
        return bool(
            Order.objects.filter(pk=self.pk, status=self.Status.PENDING).update(status=self.Status.PAYMENT_FAILED)
        )

    # -- display ---------------------------------------------------------
    @property
    def address_lines(self):
        lines = [self.address1]
        if self.address2:
            lines.append(self.address2)
        lines.append(f"{self.city}, {self.state} {self.pincode}")
        return lines

    @property
    def item_count(self):
        return sum(i.quantity for i in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    variant = models.ForeignKey(Variant, null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=120)
    product_slug = models.SlugField(max_length=140, blank=True)
    size = models.CharField(max_length=8)
    quantity = models.PositiveIntegerField(default=1)
    unit_price_inr = models.PositiveIntegerField("unit price (₹)")
    image_filename = models.CharField(max_length=160, blank=True)

    def __str__(self):
        return f"{self.product_name} ({self.size}) x{self.quantity}"

    @property
    def line_total_inr(self):
        return self.unit_price_inr * self.quantity

    @property
    def size_label(self):
        from catalog.sizes import size_label

        return size_label(self.size)

    @property
    def image_url(self):
        return static(f"img/products/{self.image_filename}") if self.image_filename else ""
