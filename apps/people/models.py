# apps/people/models.py
import secrets
from django.conf import settings
from django.db import models
import secrets


class School(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    referral_code = models.CharField(max_length=12, unique=True, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.name)[:150]
            slug = base
            n = 1
            while School.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        if not self.referral_code:
            self.referral_code = secrets.token_urlsafe(6).upper().replace('_', '').replace('-', '')[:8]
        super().save(*args, **kwargs)

# Track gets a new field; add Lesson, Cohort, Enrollment below it
class Track(models.Model):
    class Kind(models.TextChoices):
        TRACK = 'TRACK', 'Long Track'
        SHORT_COURSE = 'SHORT_COURSE', 'Short Course'

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=110, unique=True, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.TRACK)
    age_range = models.CharField(max_length=30, blank=True, help_text="e.g. \"4–7\"")
    description = models.TextField(blank=True)
    price_naira = models.PositiveIntegerField(help_text="Whole naira, no kobo.")
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide from enrollment without deleting.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price_naira']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)[:110]
        super().save(*args, **kwargs)


class Lesson(models.Model):
    """Content, owned by a Track only — never by a cohort or a student."""
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=150)
    position = models.PositiveIntegerField(help_text="Order within the track. 1, 2, 3...")
    content = models.TextField(blank=True, help_text="Lesson text/instructions.")
    video_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['track', 'position']
        constraints = [
            models.UniqueConstraint(fields=['track', 'position'], name='unique_position_per_track')
        ]

    def __str__(self):
        return f"{self.track.name} — {self.position}. {self.title}"

    def next(self):
        return Lesson.objects.filter(track=self.track, position__gt=self.position).order_by('position').first()

    # markdown support for lesson content, so we can have code blocks, tables, etc.
    def rendered_content(self):
        import markdown
        return markdown.markdown(self.content, extensions=['fenced_code', 'tables'])


class Cohort(models.Model):
    """A named, dated batch. Only ever used for delivery_mode=COHORT enrollments."""
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='cohorts')
    name = models.CharField(max_length=100, help_text='e.g. "Web Dev Batch B – November"')
    enrollment_opens_at = models.DateTimeField(null=True, blank=True)
    enrollment_closes_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    current_lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text="Shared progress pointer for every student in this batch.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def clean(self):
        if self.current_lesson_id and self.current_lesson.track_id != self.track_id:
            raise ValidationError("current_lesson must belong to this cohort's track.")

    def advance(self):
        if self.current_lesson:
            nxt = self.current_lesson.next()
            if nxt:
                self.current_lesson = nxt
                self.save(update_fields=['current_lesson'])
                return True
            self.enrollments.filter(status=Enrollment.Status.ACTIVE).update(
                status=Enrollment.Status.COMPLETED
            )
            return False
        return False

    def effective_lesson(self):
        return self.current_lesson or self.track.lessons.order_by('position').first()




class Student(models.Model):
    """
    Academic profile, decoupled from login identity (TUser).
    May have no linked user at all (fully guardian-managed), or be
    linked 1:1 once the student "upgrades" to their own login.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='student_profile',
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)

    # One-time code a guardian hands to the child so they can claim
    # this profile later by creating their own login. Cleared on use.
    claim_code = models.CharField(max_length=32, unique=True, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # apps/people/models.py — inside Student, next to claim_code
    guardian_invite_code = models.CharField(max_length=32, unique=True, null=True, blank=True)

    def generate_guardian_invite_code(self):
        self.guardian_invite_code = secrets.token_urlsafe(12)
        self.save(update_fields=['guardian_invite_code'])
        return self.guardian_invite_code

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def generate_claim_code(self):
        self.claim_code = secrets.token_urlsafe(12)
        self.save(update_fields=['claim_code'])
        return self.claim_code

    @property
    def access_state(self):
        """'claimed' = has own login, 'invited' = code issued, 'managed' = neither."""
        if self.user_id:
            return 'claimed'
        if self.claim_code:
            return 'invited'
        return 'managed'


class StudentGuardian(models.Model):
    """Links a Student to whoever manages them: a parent or a school partner."""

    class Relationship(models.TextChoices):
        PARENT = 'PARENT', 'Parent'
        SCHOOL_PARTNER = 'SCHOOL_PARTNER', 'School Partner'

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='guardianships')
    guardian = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wards')
    relationship = models.CharField(max_length=20, choices=Relationship.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'guardian')

    def __str__(self):
        return f"{self.guardian} guards {self.student} ({self.relationship})"


class Enrollment(models.Model):
    class DeliveryMode(models.TextChoices):
        COHORT = 'COHORT', 'Cohort'
        ONE_ON_ONE = 'ONE_ON_ONE', 'One-on-one'
        SELF_PACED = 'SELF_PACED', 'Self-paced'

    class Status(models.TextChoices):
        PENDING_PAYMENT = 'PENDING_PAYMENT', 'Pending payment'
        ACTIVE = 'ACTIVE', 'Active'
        EXPIRED = 'EXPIRED', 'Expired'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    track = models.ForeignKey(Track, on_delete=models.PROTECT, related_name='enrollments')
    delivery_mode = models.CharField(max_length=20, choices=DeliveryMode.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)

    cohort = models.ForeignKey(Cohort, on_delete=models.SET_NULL, null=True, blank=True, related_name='enrollments')
    # Individual progress — only meaningful for ONE_ON_ONE / SELF_PACED. Cohort progress
    # lives on Cohort.current_lesson instead, shared by every student in that batch.
    current_lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )

    enrolled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='enrollments_created'
    )
    school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True, related_name='enrollments')

    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'track'],
                condition=models.Q(status__in=['PENDING_PAYMENT', 'ACTIVE']),
                name='one_live_enrollment_per_student_track',
            )
        ]

    def __str__(self):
        return f"{self.student} → {self.track} [{self.delivery_mode}] ({self.status})"

    def clean(self):
        if self.delivery_mode == self.DeliveryMode.COHORT:
            if not self.cohort_id:
                raise ValidationError("A cohort enrollment must have a cohort.")
            if self.cohort.track_id != self.track_id:
                raise ValidationError("Cohort must belong to the same track as this enrollment.")
        elif self.cohort_id:
            raise ValidationError("Only cohort enrollments may have a cohort set.")

    @property
    def effective_lesson(self):
        if self.delivery_mode == self.DeliveryMode.COHORT:
            return self.cohort.effective_lesson() if self.cohort else None
        return self.current_lesson or self.track.lessons.order_by('position').first()

    def mark_current_lesson_complete(self):
        """Self-paced (and one-on-one) progress: advance this student's own pointer.
        No-op for cohort enrollments — those move via Cohort.advance() instead."""
        if self.delivery_mode == self.DeliveryMode.COHORT:
            return False
        current = self.effective_lesson
        if not current:
            return False
        nxt = current.next()
        self.current_lesson = nxt or current
        self.save(update_fields=['current_lesson'])
        if not nxt:
            self.status = self.Status.COMPLETED
            self.save(update_fields=['status'])
        return True

    # dynamic resumption or update
    @property
    def has_more_lessons(self):
        if self.delivery_mode == self.DeliveryMode.COHORT:
            return False
        lesson = self.current_lesson or self.track.lessons.order_by('position').first()
        return bool(lesson and lesson.next())

    def resume(self):
        if self.status != self.Status.COMPLETED or self.delivery_mode == self.DeliveryMode.COHORT:
            return False
        current = self.current_lesson or self.track.lessons.order_by('position').first()
        nxt = current.next() if current else None
        if not nxt:
            return False
        self.current_lesson = nxt
        self.status = self.Status.ACTIVE
        self.save(update_fields=['current_lesson', 'status'])
        return True



# TRS related
class TRSDimension(models.Model):
    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.name

class Assessment(models.Model):
    class Type(models.TextChoices):
        QUIZ = 'QUIZ', 'Quiz'
        EXERCISE = 'EXERCISE', 'Exercise'
        PROJECT_SUBMISSION = 'PROJECT_SUBMISSION', 'Project submission'
        INSTRUCTOR_RATING = 'INSTRUCTOR_RATING', 'Instructor rating'

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='assessments')
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, null=True, blank=True, related_name='assessments',
        help_text="Leave blank for a track-level capstone assessment.",
    )
    dimension = models.ForeignKey(TRSDimension, on_delete=models.PROTECT, related_name='assessments')
    title = models.CharField(max_length=150)
    assessment_type = models.CharField(max_length=20, choices=Type.choices)
    max_score = models.PositiveIntegerField(default=100)
    # Project submissions and instructor ratings are never auto-passable — a human
    # always verifies them. Quizzes/exercises default to automated, but a specific
    # one can be flagged True to act as a periodic, manually-verified checkpoint.
    requires_manual_review = models.BooleanField(default=False)
    media_required = models.BooleanField(default=False, help_text="Submission must include a photo/video/link.")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.assessment_type in (self.Type.PROJECT_SUBMISSION, self.Type.INSTRUCTOR_RATING):
            self.requires_manual_review = True
        super().save(*args, **kwargs)

    def clean(self):
        if self.lesson_id and self.lesson.track_id != self.track_id:
            raise ValidationError("Lesson must belong to this assessment's track.")

    def __str__(self):
        return f"{self.title} ({self.dimension.name})"


class Attempt(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted'
        AUTO_PASSED = 'AUTO_PASSED', 'Auto-passed'
        NEEDS_REVIEW = 'NEEDS_REVIEW', 'Needs review'
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected — resubmit'

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='attempts')
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='attempts')
    score = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    # Local storage for now — this must move to real object storage (Cloudinary or
    # Supabase Storage) before production, since Render's disk doesn't persist deploys.
    media = models.FileField(upload_to='submissions/%Y/%m/', null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Student's own notes, or reviewer feedback.")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.enrollment.student} — {self.assessment.title} ({self.status})"


class TRSScore(models.Model):
    """One row per student per dimension — the lifetime, cross-track profile."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='trs_scores')
    dimension = models.ForeignKey(TRSDimension, on_delete=models.CASCADE, related_name='+')
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    attempt_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'dimension'], name='one_score_per_dimension')]

    def __str__(self):
        return f"{self.student} — {self.dimension.name}: {self.score}"


TRS_BANDS = [
    (0, "Emerging"), (20, "Developing"), (40, "Proficient"), (60, "Advanced"), (80, "Exceptional"),
]  # thresholds are placeholders — yours to calibrate once real scores exist


def band_for(score):
    band = TRS_BANDS[0][1]
    for threshold, name in TRS_BANDS:
        if score >= threshold:
            band = name
    return band