# apps/people/billing.py
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Enrollment, SchoolInvoice


def previous_month(today=None):
    today = today or timezone.localdate()
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def _month_window(period):
    start_d = period.replace(day=1)
    end_d = date(start_d.year + (start_d.month == 12), start_d.month % 12 + 1, 1)
    tz = timezone.get_current_timezone()
    return (start_d,
            timezone.make_aware(datetime.combine(start_d, time.min), tz),
            timezone.make_aware(datetime.combine(end_d, time.min), tz))


def issue_invoice(school, period):
    """Returns (invoice, created). (None, False) means nothing was billable that month."""
    start_d, start, end = _month_window(period)

    existing = (SchoolInvoice.objects.filter(school=school, period=start_d)
                .exclude(status=SchoolInvoice.Status.VOID).first())
    if existing:
        return existing, False

    enrollments = (Enrollment.objects
                   .filter(school=school, billed_to=Enrollment.BilledTo.SCHOOL, activated_at__lt=end)
                   .filter(Q(ended_at__isnull=True) | Q(ended_at__gte=start))
                   .select_related('student', 'track')
                   .order_by('student__last_name', 'student__first_name'))
    lines = [{'student': f"{e.student.first_name} {e.student.last_name}",
              'track': e.track.name, 'amount': e.track.price_naira} for e in enrollments]
    if not lines:
        return None, False

    invoice = SchoolInvoice.objects.create(
        school=school, period=start_d, lines=lines,
        amount_naira=sum(line['amount'] for line in lines), student_count=len(lines),
    )
    return invoice, True