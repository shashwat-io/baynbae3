from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("shop/", views.shop, name="shop"),
    path("shop/<slug:category>/", views.shop, name="shop_category"),
    path("product/<slug:slug>/", views.product_detail, name="product"),
    path("about/", views.about, name="about"),
    path("size-guide/", views.size_guide, name="size_guide"),
]
