from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order


class Command(BaseCommand):
    help = "Mark unpaid checkouts older than ORDER_EXPIRY_MINUTES as abandoned. Run from cron."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=settings.ORDER_EXPIRY_MINUTES)
        n = Order.objects.filter(
            status__in=[Order.Status.PENDING, Order.Status.PAYMENT_FAILED], created_at__lt=cutoff
        ).update(status=Order.Status.ABANDONED)
        self.stdout.write(f"{n} order(s) marked abandoned.")
