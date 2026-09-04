from django.contrib import admin

from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("created_at", "email", "order_number", "category", "status")
    list_filter = ("status", "category")
    list_editable = ("status",)
    search_fields = ("email", "order_number", "message", "name")
    readonly_fields = ("created_at", "name", "email", "order_number", "category", "message")
    fields = ("created_at", "status", "name", "email", "order_number", "category", "message", "reply_notes")
