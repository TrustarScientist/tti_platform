# apps/people/views_pay.py
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import payments as pay
from .models import Enrollment, Payment
from .services import can_manage_student, price_for, region_for

logger = logging.getLogger(__name__)


class CheckoutView(LoginRequiredMixin, View):
    def post(self, request, enrollment_id):
        enrollment = get_object_or_404(Enrollment.objects.select_related('student', 'track'), pk=enrollment_id)
        if not can_manage_student(request.user, enrollment.student):
            return HttpResponseForbidden("You can't pay for this enrollment.")
        back = redirect('student-lesson', enrollment_id=enrollment.pk)

        live = (Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE)
        if enrollment.billed_to != Enrollment.BilledTo.FAMILY or enrollment.status not in live:
            messages.info(request, "There's nothing to pay for this enrollment.")
            return back
        price = price_for(enrollment.track, enrollment.delivery_mode, region_for(request.user),
                          plan_code=enrollment.plan_code)
        if price is None:
            messages.error(request, "Online payment for this option isn't available yet. Please contact Trustar.")
            return back
        try:
            _, url = pay.start_payment(enrollment, request.user, price,
                                       request.build_absolute_uri(reverse('pay-callback')))
        except pay.PaystackError as exc:
            logger.error("Could not start a Paystack payment for enrollment %s: %s", enrollment.pk, exc)
            messages.error(request, "We couldn't start the payment. Please try again in a moment.")
            return back
        return redirect(url)


class CallbackView(LoginRequiredMixin, View):
    """Where Paystack sends the user back. Never trusts the URL: asks Paystack directly."""
    def get(self, request):
        reference = request.GET.get('reference') or request.GET.get('trxref') or ''
        payment = Payment.objects.select_related('enrollment__student').filter(reference=reference).first()
        if payment is None or not can_manage_student(request.user, payment.enrollment.student):
            messages.error(request, "We couldn't find that payment.")
            return redirect('dashboard')
        back = redirect('student-lesson', enrollment_id=payment.enrollment_id)

        if payment.status != Payment.Status.PAID:
            try:
                data = pay.verify_transaction(reference)
            except pay.PaystackError:
                messages.info(request, "We're still confirming your payment. Please check again in a minute.")
                return back
            if data.get('status') == 'success':
                pay.settle_payment(reference, amount_minor=data.get('amount'), currency=data.get('currency'))
            payment.refresh_from_db()

        if payment.status == Payment.Status.PAID:
            messages.success(request, "Payment received. Thank you!")
        elif payment.status == Payment.Status.REVIEW:
            messages.error(request, "We received a payment we need to check. Trustar will be in touch.")
        else:
            messages.info(request, "The payment wasn't completed. You can try again.")
        return back


@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(View):
    def post(self, request):
        secret = settings.PAYSTACK_SECRET_KEY
        if not secret:
            return HttpResponse(status=503)  # fail closed
        expected = hmac.new(secret.encode(), request.body, hashlib.sha512).hexdigest()
        signature = request.headers.get('x-paystack-signature', '')
        if not hmac.compare_digest(expected.encode(), signature.encode()):
            return HttpResponse(status=401)
        try:
            event = json.loads(request.body)
        except ValueError:
            return HttpResponse(status=400)
        data = event.get('data') or {}
        if event.get('event') == 'charge.success' and data.get('status') == 'success':
            pay.settle_payment(data.get('reference', ''), amount_minor=data.get('amount'),
                               currency=data.get('currency'))
        return HttpResponse(status=200)