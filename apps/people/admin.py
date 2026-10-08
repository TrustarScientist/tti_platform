# apps/people/admin.py
from django.contrib import admin
from .models import Student, StudentGuardian, School
from django.contrib import messages
from .models import Track, Enrollment, Lesson, Cohort
from .models import TRSDimension, Assessment, Attempt, TRSScore
from .services import advance_if_lesson_complete, verify_attempt, recompute_trs_score


class StudentGuardianInline(admin.TabularInline):
    model = StudentGuardian
    extra = 0


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'user', 'created_at')
    search_fields = ('first_name', 'last_name', 'user__email')
    inlines = [StudentGuardianInline]



@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'referral_code', 'is_active', 'created_at')
    search_fields = ('name',)


# k

class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    ordering = ['position']


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'audience', 'age_range', 'price_naira', 'is_active')
    list_filter = ('kind', 'audience', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [LessonInline]


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    list_display = ('name', 'track', 'school', 'current_lesson', 'start_date', 'end_date', 'is_active')
    list_filter = ('track', 'school', 'is_active')
    actions = ['advance_batch']

    @admin.action(description="Advance selected cohorts to their next lesson")
    def advance_batch(self, request, queryset):
        moved = sum(1 for cohort in queryset if cohort.advance())
        self.message_user(request, f"{moved} cohort(s) advanced.", messages.SUCCESS)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'track', 'delivery_mode', 'status', 'school', 'created_at')
    list_filter = ('status', 'delivery_mode', 'track')
    actions = ['mark_active']

    @admin.action(description="Mark selected as paid (Active)")
    def mark_active(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status=Enrollment.Status.PENDING_PAYMENT).update(
            status=Enrollment.Status.ACTIVE, activated_at=timezone.now()
        )
        self.message_user(request, f"{count} enrollment(s) marked active.", messages.SUCCESS)


# TRS related


#  
@admin.register(TRSDimension)
class TRSDimensionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'order', 'is_active')
    ordering = ['order']


class AssessmentInline(admin.TabularInline):
    model = Assessment
    extra = 0


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'track', 'lesson', 'dimension', 'assessment_type', 'requires_manual_review')
    list_filter = ('track', 'dimension', 'assessment_type')


# apps/people/admin.py — replace AttemptAdmin entirely
@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'assessment', 'status', 'score', 'submitted_at')
    list_filter = ('status', 'assessment__dimension')
    actions = ['verify_as_passed']

    def save_model(self, request, obj, form, change):
        becoming_final = obj.status in (Attempt.Status.VERIFIED, Attempt.Status.AUTO_PASSED)
        if becoming_final and not obj.reviewed_by_id:
            from django.utils import timezone
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
        if becoming_final and obj.score is not None:
            recompute_trs_score(obj.enrollment.student, obj.assessment.dimension)
            advance_if_lesson_complete(obj.enrollment, obj.assessment.lesson)

    @admin.action(description="Verify selected (uses submitted score, or max score if blank)")
    def verify_as_passed(self, request, queryset):
        count = 0
        for attempt in queryset.filter(status__in=[Attempt.Status.SUBMITTED, Attempt.Status.NEEDS_REVIEW]):
            verify_attempt(
                attempt, reviewer=request.user,
                score=attempt.score if attempt.score is not None else attempt.assessment.max_score,
            )
            count += 1
        self.message_user(request, f"{count} attempt(s) verified.", messages.SUCCESS)

@admin.register(TRSScore)
class TRSScoreAdmin(admin.ModelAdmin):
    list_display = ('student', 'dimension', 'score', 'attempt_count', 'updated_at')
    list_filter = ('dimension',)