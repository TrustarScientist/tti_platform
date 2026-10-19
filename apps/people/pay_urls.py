# apps/people/pay_urls.py
from django.urls import path

from . import views_pay as v

urlpatterns = [
    path('checkout/<int:enrollment_id>/', v.CheckoutView.as_view(), name='pay-checkout'),
    path('callback/', v.CallbackView.as_view(), name='pay-callback'),
    path('paystack/webhook/', v.PaystackWebhookView.as_view(), name='pay-webhook'),
]