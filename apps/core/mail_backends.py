# apps/core/mail_backends.py
import json
import smtplib
import socket
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend


class IPv4SMTP(smtplib.SMTP):
    """Connects over IPv4 only, and says which address failed and why."""

    def _get_socket(self, host, port, timeout):
        addresses = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        failures = []
        for *_, sockaddr in addresses:
            try:
                return socket.create_connection((sockaddr[0], port), timeout, self.source_address)
            except OSError as exc:
                failures.append(f"{sockaddr[0]}: {exc}")
        raise OSError(f"Could not connect to {host}:{port} over IPv4 ({'; '.join(failures)})")


class IPv4SMTPBackend(DjangoSMTPBackend):
    connection_class = IPv4SMTP


class BrevoApiBackend(BaseEmailBackend):
    """Sends over HTTPS (port 443) through Brevo's API, so blocked SMTP ports don't matter.
    The sender must be a sender or domain you have verified in Brevo."""

    def send_messages(self, email_messages):
        key = getattr(settings, 'BREVO_API_KEY', '')
        if not key:
            if self.fail_silently:
                return 0
            raise RuntimeError("BREVO_API_KEY is not set.")
        sent = 0
        for message in email_messages:
            name, address = parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)
            payload = {
                'sender': {'name': name or 'Trustar Tech Institute', 'email': address},
                'to': [{'email': recipient} for recipient in message.to],
                'subject': message.subject,
                'textContent': message.body,
            }
            reply_to = message.reply_to[0] if message.reply_to else getattr(settings, 'EMAIL_REPLY_TO', '')
            if reply_to:
                payload['replyTo'] = {'email': reply_to}
            
            request = urllib.request.Request(
                'https://api.brevo.com/v3/smtp/email', data=json.dumps(payload).encode(), method='POST',
                headers={'api-key': key, 'Content-Type': 'application/json', 'Accept': 'application/json',
                         'User-Agent': 'TrustarSite/1.0 (+https://trustartech.com.ng)'})
            try:
                with urllib.request.urlopen(request, timeout=15):
                    sent += 1
            except urllib.error.HTTPError as exc:
                if not self.fail_silently:
                    detail = exc.read().decode('utf-8', 'replace')[:200]
                    raise RuntimeError(f"Brevo returned HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if not self.fail_silently:
                    raise RuntimeError("Could not reach Brevo.") from exc
        return sent