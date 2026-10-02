# apps/people/services.py
from .models import Student


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
    """The one place an Attempt becomes final. Call this from the review
    action — never set status/score directly anywhere else."""
    from django.utils import timezone

    attempt.score = score
    attempt.status = Attempt.Status.VERIFIED
    attempt.reviewed_by = reviewer
    attempt.reviewed_at = timezone.now()
    attempt.notes = notes
    attempt.save()
    recompute_trs_score(attempt.enrollment.student, attempt.assessment.dimension)


def recompute_trs_score(student, dimension):
    finalized = Attempt.objects.filter(
        enrollment__student=student,
        assessment__dimension=dimension,
        status__in=[Attempt.Status.VERIFIED, Attempt.Status.AUTO_PASSED],
        score__isnull=False,
    )
    count = finalized.count()
    if count == 0:
        return

    # Simple mean of normalized (score/max_score) attempts, as a percentage.
    # Recency- or difficulty-weighting is a real future refinement, not v1.
    total_pct = sum(Decimal(a.score) / Decimal(a.assessment.max_score) for a in finalized)
    avg_pct = (total_pct / count) * 100

    TRSScore.objects.update_or_create(
        student=student, dimension=dimension,
        defaults={'score': round(avg_pct, 2), 'attempt_count': count},
    )