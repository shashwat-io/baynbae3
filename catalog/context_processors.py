from django.conf import settings

from .models import Category


def storefront(request):
    return {
        "store": settings.STORE,
        "nav_categories": list(Category.objects.live()),
        "site_url": settings.SITE_URL,
    }
