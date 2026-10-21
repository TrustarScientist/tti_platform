# apps/people/payments.py
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Payment

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    pass


def _call(method, path, payload=None):
    secret = settings.PAYSTACK_SECRET_KEY
    if not secret:
        raise PaystackError("Paystack is not configured.")
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{settings.PAYSTACK_BASE_URL}{path}", data=data, method=method,
        headers={
            'Authorization': f'Bearer {secret}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            # Python's default User-Agent ("Python-urllib/x.y") is often refused by the CDN
            # in front of API hosts, so identify ourselves plainly.
            'User-Agent': 'TrustarSite/1.0 (+https://trustartech.com.ng)',
        })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        try:
            detail = json.loads(raw).get('message', '')
        except ValueError:
            detail = ' '.join(raw.split())[:200]  # not JSON, e.g. a CDN block page: keep a short excerpt
        raise PaystackError(f"Paystack returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise PaystackError("Could not reach Paystack.") from exc
    if not body.get('status'):
        raise PaystackError(body.get('message', 'Paystack refused the request.'))
    return body['data']


def initialize_transaction(*, email, amount_minor, currency, reference, callback_url, metadata):
    return _call('POST', '/transaction/initialize', {
        'email': email, 'amount': amount_minor, 'currency': currency,
        'reference': reference, 'callback_url': callback_url, 'metadata': metadata,
    })


def verify_transaction(reference):
    return _call('GET', f"/transaction/verify/{urllib.parse.quote(reference, safe='')}")


def new_reference():
    return f"TTI-{secrets.token_hex(8).upper()}"


def start_payment(enrollment, user, price, callback_url):
    """Record what we are about to charge, then ask Paystack for a checkout link."""
    payment = Payment.objects.create(
        enrollment=enrollment, reference=new_reference(), amount=price.amount,
        currency=price.currency, access_days=price.access_days, initiated_by=user)
    try:
        data = initialize_transaction(
            email=user.email, amount_minor=price.amount_minor, currency=price.currency,
            reference=payment.reference, callback_url=callback_url,
            metadata={'payment_id': payment.pk, 'enrollment_id': enrollment.pk})
    except PaystackError:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=['status'])
        raise
    return payment, data['authorization_url']


def settle_payment(reference, *, amount_minor, currency):
    """Idempotent: marks the payment paid and extends access exactly once.
    Returns the Payment, or None if the reference is unknown."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(reference=reference).first()
        if payment is None:
            logger.warning("Paystack event for unknown reference %s", reference)
            return None
        if payment.status == Payment.Status.PAID:
            return payment
        if amount_minor != payment.amount_minor or (currency or '').upper() != payment.currency:
            logger.error("Payment %s mismatch: expected %s %s, got %s %s", reference,
                         payment.amount_minor, payment.currency, amount_minor, currency)
            payment.status = Payment.Status.REVIEW
            payment.save(update_fields=['status'])
            return payment
        payment.status = Payment.Status.PAID
        payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at'])
        payment.enrollment.extend_access(payment.access_days)
        return payment