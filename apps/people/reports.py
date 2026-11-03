# apps/people/reports.py
from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from .models import (Attempt, AttendanceRecord, ClassSession, Enrollment, ProgressReport,
                     StudentGuardian, TRSDimension, band_for)
from .services import ATTENDED, consistency_score


def month_bounds(value):
    first = value.replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return first, last


def recent_periods(today=None):
    today = today or timezone.localdate()
    this_month = today.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    return [(this_month, f"{this_month:%B %Y} (so far)"), (last_month, f"{last_month:%B %Y}")]


def parse_period(raw, today=None):
    """'2026-10' gives the first day of that month. Missing or invalid gives last month. Never the future."""
    today = today or timezone.localdate()
    this_month = today.replace(day=1)
    try:
        first = datetime.strptime(f"{raw}-01", "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return (this_month - timedelta(days=1)).replace(day=1)
    return min(first, this_month)


def cohort_enrollments(cohort, last):
    return (cohort.enrollments
            .filter(status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED])
            .filter(Q(activated_at__isnull=True) | Q(activated_at__date__lte=last))
            .select_related('student', 'track', 'cohort'))


def build_snapshot(enrollment, first, last, today=None):
    today = today or timezone.localdate()
    student, track = enrollment.student, enrollment.track

    counted = (AttendanceRecord.objects
               .filter(enrollment=enrollment, session__date__gte=first, session__date__lte=last)
               .exclude(status=AttendanceRecord.Status.EXCUSED))
    attendance = {'attended': counted.filter(status__in=ATTENDED).count(), 'total': counted.count()}

    sessions = ClassSession.objects.filter(date__gte=first, date__lte=last)
    sessions = (sessions.filter(cohort_id=enrollment.cohort_id) if enrollment.cohort_id
                else sessions.filter(enrollment=enrollment))
    covered = [s.topic for s in sessions.order_by('date') if s.topic][:8]

    finished = (Attempt.objects
                .filter(enrollment=enrollment,
                        status__in=[Attempt.Status.VERIFIED, Attempt.Status.AUTO_PASSED],
                        submitted_at__date__gte=first, submitted_at__date__lte=last)
                .select_related('assessment').order_by('submitted_at')[:8])
    completed = [{'title': a.assessment.title, 'score': a.score, 'max': a.assessment.max_score,
                  'feedback': a.feedback} for a in finished]

    lesson = next_lesson = None
    current = enrollment.effective_lesson
    if current:
        lesson = {'title': current.title, 'position': current.position, 'total': track.lessons.count()}
        following = current.next()
        next_lesson = following.title if following else None

    scores = {s.dimension_id: s.score for s in student.trs_scores.all()}
    skills = []
    for dim in TRSDimension.objects.filter(is_active=True):
        value = (consistency_score(student, today=min(last, today)) if dim.code == 'consistency'
                 else scores.get(dim.id))
        skills.append({'name': dim.name, 'band': band_for(float(value)) if value is not None else None})

    return {'child': student.first_name, 'track': track.name, 'attendance': attendance,
            'covered': covered, 'completed': completed, 'lesson': lesson,
            'next_lesson': next_lesson, 'skills': skills}


def ensure_reports(enrollments, first, last):
    """Create or refresh DRAFT reports. Published reports are never touched."""
    made = []
    for e in enrollments:
        snapshot = build_snapshot(e, first, last)
        report, created = ProgressReport.objects.get_or_create(
            enrollment=e, period_start=first,
            defaults={'student': e.student, 'period_end': last, 'snapshot': snapshot})
        if not created and report.status == ProgressReport.Status.DRAFT:
            report.snapshot, report.period_end = snapshot, last
            report.save(update_fields=['snapshot', 'period_end'])
        made.append(report)
    return made


def publish(report, user):
    report.snapshot = build_snapshot(report.enrollment, report.period_start, report.period_end)
    report.status = ProgressReport.Status.PUBLISHED
    report.published_at = timezone.now()
    report.published_by = user
    report.save(update_fields=['snapshot', 'status', 'published_at', 'published_by'])


def report_recipients(student):
    emails = set(StudentGuardian.objects
                 .filter(student=student, relationship=StudentGuardian.Relationship.PARENT)
                 .values_list('guardian__email', flat=True))
    if student.user_id:
        emails.add(student.user.email)
    return sorted(e for e in emails if e)