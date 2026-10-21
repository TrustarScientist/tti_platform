# apps/people/management/commands/paystack_ping.py
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.people import payments


class Command(BaseCommand):
    help = "Ask Paystack to start a ₦100 test transaction, to check the key and the network. Charges nothing."

    def handle(self, *args, **options):
        key = settings.PAYSTACK_SECRET_KEY
        if not key:
            self.stderr.write("PAYSTACK_SECRET_KEY is not set.")
            return
        self.stdout.write(f"Key type: {key[:8]}")  # prefix only: sk_test_ or sk_live_
        started = time.monotonic()
        try:
            data = payments.initialize_transaction(
                email='ping@example.com', amount_minor=10000, currency='NGN',
                reference=payments.new_reference(),
                callback_url='https://trustartech.com.ng/payments/callback/', metadata={'ping': True})
        except payments.PaystackError as exc:
            self.stderr.write(f"FAILED after {time.monotonic() - started:.1f}s: {exc}")
            return
        self.stdout.write(f"OK in {time.monotonic() - started:.1f}s: {data.get('authorization_url')}")