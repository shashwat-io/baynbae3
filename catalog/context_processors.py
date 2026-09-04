from django.conf import settings

from .models import Category


def storefront(request):
    return {
        "store": settings.STORE,
        "nav_categories": Category.all(),
        "site_url": settings.SITE_URL,
    }
