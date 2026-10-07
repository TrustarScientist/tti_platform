# apps/people/services.py
from .models import Student, Enrollment, Attempt


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

# new addition
# apps/people/services.py — add
from .models import StudentGuardian


def can_manage_student(user, student):
    if not user.is_authenticated:
        return False
    return student.user_id == user.id or StudentGuardian.objects.filter(
        student=student, guardian=user
    ).exists()