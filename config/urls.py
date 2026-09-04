from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import TemplateView

from config.sitemaps import sitemaps

admin.site.site_header = "Bay'n Bae — back office"
admin.site.site_title = "Bay'n Bae admin"
admin.site.index_title = "Orders, stock and support"


def robots(request):
    body = f"User-agent: *\nDisallow: /bag/\nDisallow: /checkout/\nDisallow: /admin/\nSitemap: {settings.SITE_URL}/sitemap.xml\n"
    return HttpResponse(body, content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("catalog.urls")),
    path("", include("orders.urls")),
    path("", include("support.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", robots, name="robots"),
]

handler404 = "catalog.views.not_found"
handler500 = "catalog.views.server_error"
