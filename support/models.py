from django.db import models


class SupportTicket(models.Model):
    class Category(models.TextChoices):
        ORDER = "order", "Where's my order?"
        RETURN = "return", "Exchange or defect"
        SIZING = "sizing", "Sizing help"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    order_number = models.CharField(max_length=16, blank=True)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    message = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    reply_notes = models.TextField(blank=True, help_text="Internal notes / what was replied.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.get_category_display()} — {self.email}"
