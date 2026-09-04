from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("bag/", views.bag_view, name="bag"),
    path("bag/add/", views.bag_add, name="bag_add"),
    path("bag/update/", views.bag_update, name="bag_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/pay/<str:token>/", views.pay, name="pay"),
    path("checkout/callback/", views.payment_callback, name="callback"),
    path("checkout/cancelled/<str:token>/", views.payment_cancelled, name="cancelled"),
    path("checkout/sandbox/<str:token>/", views.sandbox_gateway, name="sandbox_gateway"),
    path("order/<str:token>/", views.confirmation, name="confirmation"),
    path("track/", views.track, name="track"),
    path("webhooks/razorpay/", views.razorpay_webhook, name="webhook"),
]
