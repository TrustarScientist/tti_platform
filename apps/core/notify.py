# apps/core/notify.py
import logging
import threading

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _deliver(subject, body, to):
    try:
        send_mail(subject, body, None, [to], fail_silently=False)
    except Exception:
        # The log names the mail server, never the recipient.
        logger.exception("Email failed via %s:%s: %s",
                         settings.EMAIL_HOST or settings.EMAIL_BACKEND, settings.EMAIL_PORT, subject)


def _send(subject, body, to):
    """Send in the background, so an unreachable mail server never holds up a page."""
    if getattr(settings, 'EMAIL_ASYNC', True):
        threading.Thread(target=_deliver, args=(subject, body, to), daemon=True).start()
    else:
        _deliver(subject, body, to)


def notify_new_lead(lead):
    if settings.ADMIN_NOTIFY_EMAIL:
        _send(f"New enquiry: {lead.name}",
              f"Name: {lead.name}\nContact: {lead.contact}\nAge: {lead.child_age or '-'}\n"
              f"Interested in: {lead.interest or '-'}\n\n{lead.message or ''}",
              settings.ADMIN_NOTIFY_EMAIL)
    if '@' in lead.contact:
        _send("We got your message",
              f"Hi {lead.name.split()[0]},\n\nThanks for getting in touch with Trustar. "
              "We'll reply soon, usually within a day.\n\n— Trustar Tech Institute",
              lead.contact)


def payment_receipt(payment_id):
    from apps.people.models import Payment
    payment = (Payment.objects.select_related('enrollment__student', 'enrollment__track', 'initiated_by')
               .filter(pk=payment_id).first())
    payer = payment.initiated_by if payment else None
    if payer is None or not payer.email:
        return
    e = payment.enrollment
    paid_through = f"{e.paid_through:%d %B %Y}" if e.paid_through else "the end of your paid period"
    _send(f"Payment received: {e.track.name}",
          f"Hi {payer.first_name or ''},\n\nThank you. We received {payment.currency} {payment.amount:,.0f} "
          f"for {e.student.first_name}'s place in {e.track.name}.\n\nReference: {payment.reference}\n"
          f"Access is paid through {paid_through}.\n\n— Trustar Tech Institute",
          payer.email)


def report_published(report_id, url):
    from apps.people.models import ProgressReport
    from apps.people.reports import report_recipients
    report = ProgressReport.objects.select_related('student', 'enrollment__track').filter(pk=report_id).first()
    if report is None:
        return
    first = report.student.first_name
    for to in report_recipients(report.student):
        _send(f"{first}'s progress report for {report.period_label}",
              f"Hello,\n\n{first}'s {report.enrollment.track.name} progress report for {report.period_label} "
              f"is ready.\n\nOpen it here (you'll be asked to log in):\n{url}\n\n— Trustar Tech Institute", to)