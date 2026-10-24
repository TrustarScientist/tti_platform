# apps/core/management/commands/send_test_email.py
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send one test email and show the real error if it fails."

    def add_arguments(self, parser):
        parser.add_argument('to')

    def handle(self, *args, to, **options):
        self.stdout.write(f"Backend: {settings.EMAIL_BACKEND} · host: {settings.EMAIL_HOST or '(none)'}")
        sent = send_mail("Trustar test email", "If you can read this, email works.", None, [to], fail_silently=False)
        self.stdout.write(f"Sent: {sent}")