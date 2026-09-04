from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("bag/", views.bag_view, name="bag"),
    path("bag/add/", views.bag_add, name="bag_add"),
    path("bag/update/", views.bag_update, name="bag_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/pay/<str:order_number>/", views.pay, name="pay"),
    path("checkout/verify/", views.verify_payment, name="verify_payment"),
    path("checkout/cancelled/<str:order_number>/", views.payment_cancelled, name="cancelled"),
    path("checkout/sandbox/<str:order_number>/", views.sandbox_gateway, name="sandbox_gateway"),
    path("order/<str:order_number>/", views.confirmation, name="confirmation"),
    path("track/", views.track, name="track"),
    path("webhooks/razorpay/", views.razorpay_webhook, name="webhook"),
]
