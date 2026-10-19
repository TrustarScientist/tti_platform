# apps/people/admin.py
from django.contrib import admin
from .models import Student, StudentGuardian, School
from django.contrib import messages
from .models import Track, Enrollment, Lesson, Cohort
from .models import TRSDimension, Assessment, Attempt, TRSScore
from .services import advance_if_lesson_complete, verify_attempt, recompute_trs_score

# 
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from .billing import issue_invoice, previous_month
from .models import SchoolInvoice, Price, Payment
from .payments import PaystackError, new_reference, settle_payment, verify_transaction
from .services import price_for

#
class PriceInline(admin.TabularInline):
    model = Price
    extra = 0

    
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

    actions = ['issue_last_month_invoice']

    @admin.action(description="Issue invoice for last month")
    def issue_last_month_invoice(self, request, queryset):
        period = previous_month()
        for school in queryset:
            invoice, created = issue_invoice(school, period)
            if invoice is None:
                self.message_user(request, f"{school.name}: nothing billable for {period:%B %Y}.", messages.WARNING)
            elif created:
                self.message_user(request, f"{school.name}: issued {invoice.reference} for ₦{invoice.amount_naira:,}.", messages.SUCCESS)
            else:
                self.message_user(request, f"{school.name}: {invoice.reference} was already issued.", messages.INFO)



class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    ordering = ['position']


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'audience', 'age_range', 'price_naira', 'is_active')
    list_filter = ('kind', 'audience', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [LessonInline, PriceInline]


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    list_display = ('name', 'track', 'school', 'current_lesson', 'start_date', 'end_date', 'is_active')
    list_filter = ('track', 'school', 'is_active')
    actions = ['advance_batch']

    # 
    filter_horizontal = ('instructors',)

    @admin.action(description="Advance selected cohorts to their next lesson")
    def advance_batch(self, request, queryset):
        moved = sum(1 for cohort in queryset if cohort.advance())
        self.message_user(request, f"{moved} cohort(s) advanced.", messages.SUCCESS)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'track', 'delivery_mode', 'billed_to', 'status', 'school', 'created_at')
    list_filter = ('status', 'delivery_mode', 'billed_to', 'track')
    search_fields = ('student__first_name', 'student__last_name')
    actions = ['record_manual_payment']

    @admin.action(description="Mark selected as paid (Active)")
    def mark_active(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status=Enrollment.Status.PENDING_PAYMENT).update(
            status=Enrollment.Status.ACTIVE, activated_at=timezone.now()
        )
        self.message_user(request, f"{count} enrollment(s) marked active.", messages.SUCCESS)
        
    @admin.action(description="Record a payment received (cash/transfer): extends access")
    def record_manual_payment(self, request, queryset):
        done = 0
        live = [Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE]
        for e in queryset.filter(billed_to=Enrollment.BilledTo.FAMILY, status__in=live):
            price = price_for(e.track, e.delivery_mode)
            days = price.access_days if price else 30
            Payment.objects.create(
                enrollment=e, provider=Payment.Provider.MANUAL, reference=new_reference(),
                amount=price.amount if price else 0, currency=price.currency if price else 'NGN',
                access_days=days, status=Payment.Status.PAID, paid_at=timezone.now(),
                initiated_by=request.user)
            e.extend_access(days)
            done += 1
        self.message_user(request, f"{done} payment(s) recorded.", messages.SUCCESS)


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



@admin.register(SchoolInvoice)
class SchoolInvoiceAdmin(admin.ModelAdmin):
    list_display = ('reference', 'school', 'period', 'student_count', 'amount_naira', 'status', 'open_invoice')
    list_filter = ('status', 'school')
    readonly_fields = ('school', 'period', 'amount_naira', 'student_count', 'lines', 'issued_at', 'paid_at')
    actions = ['mark_paid', 'mark_void']

    @admin.display(description="Invoice")
    def open_invoice(self, obj):
        return format_html('<a href="{}">Open</a>', reverse('invoice-detail', args=[obj.pk]))

    @admin.action(description="Mark selected as paid")
    def mark_paid(self, request, queryset):
        n = queryset.filter(status=SchoolInvoice.Status.ISSUED).update(status=SchoolInvoice.Status.PAID, paid_at=timezone.now())
        self.message_user(request, f"{n} invoice(s) marked paid.", messages.SUCCESS)

    @admin.action(description="Void selected (then re-issue if needed)")
    def mark_void(self, request, queryset):
        n = queryset.exclude(status=SchoolInvoice.Status.VOID).update(status=SchoolInvoice.Status.VOID)
        self.message_user(request, f"{n} invoice(s) voided.", messages.SUCCESS)


    
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'enrollment', 'provider', 'amount', 'currency', 'status', 'created_at', 'paid_at')
    list_filter = ('status', 'provider')
    search_fields = ('reference', 'enrollment__student__first_name', 'enrollment__student__last_name')
    readonly_fields = ('enrollment', 'provider', 'reference', 'amount', 'currency', 'access_days',
                       'status', 'initiated_by', 'created_at', 'paid_at')
    actions = ['recheck_with_paystack']

    def has_add_permission(self, request):
        return False

    @admin.action(description="Re-check selected with Paystack")
    def recheck_with_paystack(self, request, queryset):
        settled = 0
        for payment in queryset.filter(provider=Payment.Provider.PAYSTACK).exclude(status=Payment.Status.PAID):
            try:
                data = verify_transaction(payment.reference)
            except PaystackError:
                continue
            if data.get('status') == 'success':
                result = settle_payment(payment.reference, amount_minor=data.get('amount'),
                                        currency=data.get('currency'))
                settled += int(bool(result and result.status == Payment.Status.PAID))
        self.message_user(request, f"{settled} payment(s) confirmed.", messages.SUCCESS)





    


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ('track', 'delivery_mode', 'region', 'currency', 'amount', 'access_days', 'effective_from', 'is_active')
    list_filter = ('track', 'delivery_mode', 'region', 'is_active')