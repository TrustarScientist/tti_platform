# apps/people/services.py
from .models import Track, Student, Enrollment, Attempt
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal

from .models import Attempt, Cohort, Enrollment, Student, StudentGuardian, Track, TRSScore



def attach_student_profile(user, claim_code=None):
    """
    Call right after creating a TUser with role=STUDENT.
    Links to an existing unclaimed Student profile if a valid claim_code
    was supplied; otherwise creates a fresh independent profile.
    """
    if claim_code:
        student = Student.objects.filter(claim_code=claim_code, user__isnull=True).first()
        if student:
            student.user = user
            student.claim_code = None
            student.save(update_fields=['user', 'claim_code'])
            return student

    return Student.objects.create(
        user=user,
        first_name=user.first_name,
        last_name=user.last_name,
    )

# TRS related
# apps/people/services.py — add
from decimal import Decimal
from .models import Attempt, TRSScore


def verify_attempt(attempt, *, reviewer, score, notes=""):
    from django.utils import timezone
    attempt.score = score
    attempt.status = Attempt.Status.VERIFIED
    attempt.reviewed_by = reviewer
    attempt.reviewed_at = timezone.now()
    attempt.notes = notes
    attempt.save()
    recompute_trs_score(attempt.enrollment.student, attempt.assessment.dimension)
    advance_if_lesson_complete(attempt.enrollment, attempt.assessment.lesson)

# enrolment checks
def advance_if_lesson_complete(enrollment, lesson):
    """Call this whenever an Attempt is finalized. Advances the enrollment's
    lesson pointer once every assessment on the current lesson is done."""
    if lesson is None or enrollment.delivery_mode == Enrollment.DeliveryMode.COHORT:
        return False
    assessment_ids = set(lesson.assessments.values_list('id', flat=True))
    if not assessment_ids:
        return False
    finalized_ids = set(
        Attempt.objects.filter(
            enrollment=enrollment, assessment_id__in=assessment_ids,
            status__in=[Attempt.Status.VERIFIED, Attempt.Status.AUTO_PASSED],
        ).values_list('assessment_id', flat=True)
    )
    if finalized_ids >= assessment_ids:
        return enrollment.mark_current_lesson_complete()
    return False

# recompute the TRS score for a student in a given dimension, based on all verified attempts.And delivery dimension is special — it only counts the latest verified attempt, not an average of all attempts.
def recompute_trs_score(student, dimension):
    finalized = Attempt.objects.filter(
        enrollment__student=student,
        assessment__dimension=dimension,
        status__in=[Attempt.Status.VERIFIED, Attempt.Status.AUTO_PASSED],
        score__isnull=False,
    )

    if dimension.code == 'delivery':
        # Snapshot-only — the current capstone state, not a history of every attempt.
        latest = finalized.order_by('-reviewed_at', '-submitted_at').first()
        if not latest:
            return
        pct = (Decimal(latest.score) / Decimal(latest.assessment.max_score)) * 100
        TRSScore.objects.update_or_create(
            student=student, dimension=dimension,
            defaults={'score': round(pct, 2), 'attempt_count': 1},
        )
        return

    count = finalized.count()
    if count == 0:
        return
    total_pct = sum(Decimal(a.score) / Decimal(a.assessment.max_score) for a in finalized)
    avg_pct = (total_pct / count) * 100
    TRSScore.objects.update_or_create(
        student=student, dimension=dimension,
        defaults={'score': round(avg_pct, 2), 'attempt_count': count},
    )

# 
from .models import StudentGuardian


def can_manage_student(user, student):
    if not user.is_authenticated:
        return False
    return student.user_id == user.id or StudentGuardian.objects.filter(
        student=student, guardian=user
    ).exists()

#


def user_school(user):
    return getattr(user, 'school', None)  # only school partners have one


def open_cohorts_for(user, track):
    """Cohorts of this track this user may enroll into right now."""
    now = timezone.now()
    school = user_school(user)
    visible = Q(school__isnull=True)
    if school is not None:
        visible |= Q(school=school)
    return (Cohort.objects.filter(track=track, is_active=True).filter(visible)
            .filter(Q(enrollment_opens_at__isnull=True) | Q(enrollment_opens_at__lte=now))
            .filter(Q(enrollment_closes_at__isnull=True) | Q(enrollment_closes_at__gte=now)))


def tracks_for(user):
    """Tracks this user should see in the enrollment picker."""
    school = user_school(user)
    q = Q(audience=Track.Audience.PUBLIC)
    if school is not None:
        q |= Q(audience=Track.Audience.SCHOOL, cohorts__school=school, cohorts__is_active=True)
    return Track.objects.filter(is_active=True).filter(q).distinct()

LIVE_STATUSES = [Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE]
MAX_ROSTER = 60


def school_cohorts_for(user):
    """Open cohorts that belong to this school partner's school."""
    school = user_school(user)
    if school is None:
        return Cohort.objects.none()
    now = timezone.now()
    return (Cohort.objects.filter(school=school, is_active=True)
            .filter(Q(enrollment_opens_at__isnull=True) | Q(enrollment_opens_at__lte=now))
            .filter(Q(enrollment_closes_at__isnull=True) | Q(enrollment_closes_at__gte=now))
            .select_related('track'))


def seats_left(cohort):
    if not cohort.capacity:
        return None
    taken = cohort.enrollments.filter(status__in=LIVE_STATUSES).count()
    return max(cohort.capacity - taken, 0)


def parse_roster(text):
    """Turn pasted text into [{'first','last'}]. Returns (rows, errors, notes)."""
    rows, errors, notes, seen = [], [], [], set()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = " ".join(raw.replace(",", " ").split())
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) < 2:
            errors.append(f'Line {number}: "{line}" needs a first and a last name.')
            continue
        first, last = parts[0], " ".join(parts[1:])
        if len(first) > 100 or len(last) > 100:
            errors.append(f"Line {number}: that name is too long.")
            continue
        key = (first.lower(), last.lower())
        if key in seen:
            notes.append(f"{first} {last} was listed twice, so it counts once.")
            continue
        seen.add(key)
        rows.append({'first': first, 'last': last})
    if len(rows) > MAX_ROSTER:
        errors.append(f"Please add at most {MAX_ROSTER} students at a time.")
    return rows, errors, notes


def build_roster_plan(user, cohort, rows):
    """Mark each row: new student / existing (will be enrolled) / already (skip)."""
    existing = {(s.first_name.lower(), s.last_name.lower()): s
                for s in Student.objects.filter(guardianships__guardian=user)}
    live_ids = set(Enrollment.objects.filter(
        track=cohort.track, status__in=LIVE_STATUSES, student__in=list(existing.values()),
    ).values_list('student_id', flat=True))
    plan = []
    for row in rows:
        student = existing.get((row['first'].lower(), row['last'].lower()))
        if student is None:
            kind = 'new'
        elif student.pk in live_ids:
            kind = 'already'
        else:
            kind = 'existing'
        plan.append({**row, 'student': student, 'kind': kind})
    return plan


def enroll_in_school_cohort(student, cohort, enrolled_by):
    """Active, school-billed enrollment. Returns (enrollment, created)."""
    live = Enrollment.objects.filter(student=student, track=cohort.track, status__in=LIVE_STATUSES).first()
    if live:
        return live, False
    enrollment = Enrollment(
        student=student, track=cohort.track, delivery_mode=Enrollment.DeliveryMode.COHORT,
        cohort=cohort, enrolled_by=enrolled_by, school=cohort.school,
        billed_to=Enrollment.BilledTo.SCHOOL, status=Enrollment.Status.ACTIVE,
        activated_at=timezone.now(),
    )
    enrollment.full_clean()
    enrollment.save()
    return enrollment, True