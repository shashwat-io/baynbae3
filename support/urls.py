from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("faq/", views.faq, name="faq"),
    path("contact/", views.contact, name="contact"),
    path("shipping-and-returns/", views.shipping_returns, name="shipping_returns"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
]
