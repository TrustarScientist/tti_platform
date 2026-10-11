# apps/people/views.py
from django.views import View
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.contrib import messages

from apps.accounts.models import TUser
from .models import Student, StudentGuardian, band_for
from .forms import StudentForm
from django.conf import settings
from django.views.generic import FormView
from .forms import EnrollForm
from .models import Enrollment, Track,Cohort, Enrollment
from django.shortcuts import render, get_object_or_404, redirect
from .forms import TrackChoiceForm, DeliveryChoiceForm

from django.utils import timezone
from .forms import AttemptForm
from .models import Assessment, Attempt, TRSDimension,TRSScore
from .services import advance_if_lesson_complete, can_manage_student, recompute_trs_score, tracks_for, open_cohorts_for
from django.core.exceptions import ValidationError
from django.db import transaction
from .services import (can_manage_student, tracks_for, open_cohorts_for, parse_roster,
                       build_roster_plan, school_cohorts_for, seats_left, enroll_in_school_cohort)
from django.conf import settings
from django.utils import timezone
from .models import SchoolInvoice
import logging

logger = logging.getLogger(__name__)



class GuardianRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only parents and school partners manage Student records."""
    def test_func(self):
        return self.request.user.role in (TUser.Role.PARENT, TUser.Role.SCHOOL_PARTNER)




class StudentCreateView(GuardianRequiredMixin, CreateView):
    model = Student
    form_class = StudentForm
    template_name = 'people/student_form.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        relationship = (
            StudentGuardian.Relationship.PARENT
            if self.request.user.role == TUser.Role.PARENT
            else StudentGuardian.Relationship.SCHOOL_PARTNER
        )
        StudentGuardian.objects.create(
            student=self.object,
            guardian=self.request.user,
            relationship=relationship,
        )
        messages.success(self.request, f"{self.object.first_name} has been added.")
        return response



class EnrollTrackView(LoginRequiredMixin, FormView):
    form_class = TrackChoiceForm
    template_name = 'people/enroll_track.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()  # logged-out visitors go to login
        self.student = get_object_or_404(Student, pk=kwargs['pk'])
        if not can_manage_student(request.user, self.student):
            return HttpResponseForbidden("You don't have access to this student.")
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        return TrackChoiceForm(self.request.POST or None, student=self.student, user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['student'] = self.student
        ctx['has_tracks'] = ctx['form'].fields['track'].queryset.exists()
        return ctx

    def form_valid(self, form):
        return redirect('student-enroll-delivery', pk=self.student.pk, track_id=form.cleaned_data['track'].pk)

    


class EnrollDeliveryView(LoginRequiredMixin, FormView):
    template_name = 'people/enroll_delivery.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.student = get_object_or_404(Student, pk=kwargs['pk'])
        self.track = get_object_or_404(tracks_for(request.user), pk=kwargs['track_id'])
        if not can_manage_student(request.user, self.student):
            return HttpResponseForbidden("You don't have access to this student.")
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        return DeliveryChoiceForm(self.request.POST or None, track=self.track, user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['student'], ctx['track'] = self.student, self.track
        ctx['has_options'] = bool(ctx['form'].fields['delivery'].choices)
        return ctx

    def form_valid(self, form):
        # Already enrolled (double click, Back button, second tab)? Say so instead of erroring.
        already = Enrollment.objects.filter(
            student=self.student, track=self.track,
            status__in=[Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE],
        ).exists()
        if already:
            messages.info(self.request, f"{self.student.first_name} is already enrolled in {self.track.name}.")
            return redirect('dashboard')

        value = form.cleaned_data['delivery']
        cohort = None

        if value.startswith('cohort:'):
            delivery_mode = Enrollment.DeliveryMode.COHORT
            cohort = get_object_or_404(open_cohorts_for(self.request.user, self.track), pk=value.split(':')[1])
            taken = cohort.enrollments.filter(
                status__in=[Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE]
            ).count()
            if cohort.capacity and taken >= cohort.capacity:
                messages.error(self.request, "That batch just filled up. Please choose another option.")
                return self.form_invalid(form)
        else:
            delivery_mode = value

        school_billed = bool(cohort and cohort.school_id)
        enrollment = Enrollment(
            student=self.student, track=self.track, delivery_mode=delivery_mode, cohort=cohort,
            enrolled_by=self.request.user,
            school=(cohort.school if school_billed else getattr(self.request.user, 'school', None)),
            billed_to=Enrollment.BilledTo.SCHOOL if school_billed else Enrollment.BilledTo.FAMILY,
            status=Enrollment.Status.ACTIVE if school_billed else Enrollment.Status.PENDING_PAYMENT,
            activated_at=timezone.now() if school_billed else None,
        )
        try:
            enrollment.full_clean()
        except ValidationError as exc:
            logger.warning("Enrollment rejected: student=%s track=%s reasons=%s",
                           self.student.pk, self.track.pk, exc.messages)
            messages.error(self.request, "We couldn't complete that enrollment: " + " ".join(exc.messages))
            return redirect('dashboard')
        enrollment.save()

        if school_billed:
            messages.success(self.request, f"{self.student.first_name} is enrolled in {self.track.name} — billed to {cohort.school.name}.")
        else:
            messages.success(self.request, f"{self.student.first_name} is enrolled in {self.track.name}, pending payment confirmation.")
        return redirect('dashboard')



# lesson view
class LessonView(LoginRequiredMixin, View):
    def get(self, request, enrollment_id):
        enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
        is_owner = enrollment.student.user_id == request.user.id
        is_guardian = StudentGuardian.objects.filter(student=enrollment.student, guardian=request.user).exists()
        if not (is_owner or is_guardian):
            return HttpResponseForbidden("You don't have access to this enrollment.")

        lesson = None
        if enrollment.status in (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED):
            lesson = enrollment.effective_lesson
        assessment_rows = []
        if lesson:
            for assessment in lesson.assessments.all():
                attempt = (Attempt.objects
                           .filter(enrollment=enrollment, assessment=assessment)
                           .order_by('-submitted_at').first())
                assessment_rows.append({'assessment': assessment, 'attempt': attempt})

        return render(request, 'people/lesson.html', {
            'enrollment': enrollment, 'lesson': lesson,
            'is_owner': is_owner, 'assessment_rows': assessment_rows,
            'can_resume': enrollment.status == Enrollment.Status.COMPLETED and enrollment.has_more_lessons,
        })

# apps/people/views.py — replace MarkLessonCompleteView.post entirely
class MarkLessonCompleteView(LoginRequiredMixin, View):
    def post(self, request, enrollment_id):
        enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
        if enrollment.student.user_id != request.user.id:
            return HttpResponseForbidden("This isn't your enrollment.")
        if enrollment.status != Enrollment.Status.ACTIVE:
            messages.error(request, "This enrollment isn't active yet.")
            return redirect('dashboard')
        lesson = enrollment.effective_lesson
        if lesson and lesson.assessments.exists():
            messages.error(request, "This lesson has an assessment to complete first.")
            return redirect('student-lesson', enrollment_id=enrollment.pk)
        enrollment.mark_current_lesson_complete()
        messages.success(request, "Nice work! Moving to the next lesson.")
        return redirect('student-lesson', enrollment_id=enrollment.pk)


class GenerateClaimCodeView(GuardianRequiredMixin, View):
    """POST-only: generate/regenerate an invite code for one of *my* students."""
    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)

        # Object-level check — the role check above isn't enough on its own.
        if not StudentGuardian.objects.filter(student=student, guardian=request.user).exists():
            return HttpResponseForbidden("You don't manage this student.")

        code = student.generate_claim_code()
        messages.success(request, f"Invite code created for {student.first_name}.")
        return redirect('dashboard')

# TRS related



class SubmitAssessmentView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        self.enrollment = get_object_or_404(Enrollment, pk=kwargs['enrollment_id'])
        self.assessment = get_object_or_404(Assessment, pk=kwargs['assessment_id'], track=self.enrollment.track)
        if self.enrollment.student.user_id != request.user.id:
            return HttpResponseForbidden("This isn't your enrollment.")
        if self.enrollment.status != Enrollment.Status.ACTIVE:
            messages.error(request, "This enrollment isn't active.")
            return redirect('student-lesson', enrollment_id=self.enrollment.pk)
        already_done = Attempt.objects.filter(
            enrollment=self.enrollment, assessment=self.assessment,
            status__in=[Attempt.Status.VERIFIED, Attempt.Status.AUTO_PASSED],
        ).exists()
        if already_done:
            messages.info(request, "This has already been completed.")
            return redirect('student-lesson', enrollment_id=self.enrollment.pk)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, **kwargs):
        form = AttemptForm(assessment=self.assessment)
        return render(request, 'people/submit_assessment.html', self._ctx(form))

    def post(self, request, **kwargs):
        form = AttemptForm(request.POST, request.FILES, assessment=self.assessment)
        if not form.is_valid():
            return render(request, 'people/submit_assessment.html', self._ctx(form))

        attempt = form.save(commit=False)
        attempt.enrollment = self.enrollment
        attempt.assessment = self.assessment

        if self.assessment.requires_manual_review:
            attempt.status = Attempt.Status.NEEDS_REVIEW
            attempt.save()
            messages.success(request, "Submitted! An instructor will review it soon.")
        else:
            attempt.status = Attempt.Status.AUTO_PASSED
            attempt.score = self.assessment.max_score
            attempt.save()
            recompute_trs_score(self.enrollment.student, self.assessment.dimension)
            advance_if_lesson_complete(self.enrollment, self.assessment.lesson)
            messages.success(request, "Nice work — that's recorded.")

        return redirect('student-lesson', enrollment_id=self.enrollment.pk)

    def _ctx(self, form):
        return {'form': form, 'assessment': self.assessment, 'enrollment': self.enrollment}


class TRSProfileView(LoginRequiredMixin, View):
    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        is_self = student.user_id == request.user.id
        is_guardian = StudentGuardian.objects.filter(student=student, guardian=request.user).exists()
        if not (is_self or is_guardian):
            return HttpResponseForbidden("You don't have access to this profile.")

        dimensions = TRSDimension.objects.filter(is_active=True)
        scores = {s.dimension_id: s for s in student.trs_scores.all()}

        rows = []
        for dim in dimensions:
            score_obj = scores.get(dim.id)
            rows.append({
                'dimension': dim,
                'score': score_obj.score if score_obj else None,
                'band': band_for(float(score_obj.score)) if score_obj else None,
            })

        return render(request, 'people/trs_profile.html', {'student': student, 'rows': rows})


class ResumeEnrollmentView(LoginRequiredMixin, View):
    def post(self, request, enrollment_id):
        enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
        is_owner = enrollment.student.user_id == request.user.id
        is_guardian = StudentGuardian.objects.filter(student=enrollment.student, guardian=request.user).exists()
        if not (is_owner or is_guardian):
            return HttpResponseForbidden("You don't have access to this enrollment.")
        if enrollment.resume():
            messages.success(request, "New lessons are available — continuing where you left off.")
        else:
            messages.info(request, "No new lessons to resume yet.")
        return redirect('student-lesson', enrollment_id=enrollment.pk)



# apps/people/views.py
from .forms import LinkChildForm


class ParentRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == TUser.Role.PARENT


class GenerateGuardianInviteView(GuardianRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if not StudentGuardian.objects.filter(student=student, guardian=request.user).exists():
            return HttpResponseForbidden("You don't manage this student.")
        student.generate_guardian_invite_code()
        messages.success(request, f"Parent invite code created for {student.first_name}.")
        return redirect('dashboard')


class LinkChildView(ParentRequiredMixin, FormView):
    form_class = LinkChildForm
    template_name = 'people/link_child.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        student = form.student
        link, created = StudentGuardian.objects.get_or_create(
            student=student, guardian=self.request.user,
            defaults={'relationship': StudentGuardian.Relationship.PARENT},
        )
        if created:
            student.guardian_invite_code = None  # single use
            student.save(update_fields=['guardian_invite_code'])
            messages.success(self.request, f"{student.first_name} is now linked to your account.")
        else:
            messages.info(self.request, f"{student.first_name} is already linked to your account.")
        return super().form_valid(form)


class InvoiceView(LoginRequiredMixin, View):
    def get(self, request, pk):
        invoice = get_object_or_404(SchoolInvoice.objects.select_related('school'), pk=pk)
        user = request.user
        is_staff = user.is_staff or user.role == TUser.Role.ADMIN
        is_own_school = user.role == TUser.Role.SCHOOL_PARTNER and user.school_id == invoice.school_id
        if not (is_staff or is_own_school):
            return HttpResponseForbidden("You don't have access to this invoice.")
        return render(request, 'people/invoice.html', {
            'invoice': invoice, 'payment_instructions': settings.INVOICE_PAYMENT_INSTRUCTIONS,
        })



class SchoolPartnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        return u.role == TUser.Role.SCHOOL_PARTNER and u.school_id is not None


class BulkRosterView(SchoolPartnerRequiredMixin, View):
    template_name = 'people/bulk_roster.html'

    def _context(self, request, **extra):
        cohorts = list(school_cohorts_for(request.user))
        for c in cohorts:
            c.seats_left = seats_left(c)
        return {'cohorts': cohorts, 'school': request.user.school, **extra}

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        names = request.POST.get('names', '')
        raw_id = request.POST.get('cohort', '')
        cohort = school_cohorts_for(request.user).filter(pk=raw_id).first() if raw_id.isdigit() else None
        ctx = self._context(request, names=names, selected=raw_id)

        if cohort is None:
            return render(request, self.template_name, {**ctx, 'errors': ["Choose a cohort."]})

        rows, errors, notes = parse_roster(names)
        if not rows and not errors:
            errors.append("Add at least one student.")
        if errors:
            return render(request, self.template_name, {**ctx, 'errors': errors})

        plan = build_roster_plan(request.user, cohort, rows)
        to_enroll = [p for p in plan if p['kind'] != 'already']
        left = seats_left(cohort)
        if left is not None and len(to_enroll) > left:
            msg = f"{cohort.name} has {left} seat(s) left, but {len(to_enroll)} students need one."
            return render(request, self.template_name, {**ctx, 'errors': [msg]})

        if request.POST.get('confirm') != '1':
            return render(request, self.template_name, {
                **ctx, 'plan': plan, 'notes': notes, 'preview_cohort': cohort,
                'new_count': sum(1 for p in plan if p['kind'] == 'new'),
                'enroll_count': len(to_enroll),
            })

        created_students = enrolled = 0
        with transaction.atomic():
            locked = Cohort.objects.select_for_update().get(pk=cohort.pk)
            left = seats_left(locked)
            if left is not None and len(to_enroll) > left:
                messages.error(request, "Those seats were just taken. Please review the list again.")
                return redirect('student-bulk-roster')
            for item in plan:
                if item['kind'] == 'already':
                    continue
                student = item['student']
                if student is None:
                    student = Student.objects.create(first_name=item['first'], last_name=item['last'])
                    StudentGuardian.objects.create(
                        student=student, guardian=request.user,
                        relationship=StudentGuardian.Relationship.SCHOOL_PARTNER,
                    )
                    created_students += 1
                _, created = enroll_in_school_cohort(student, locked, request.user)
                enrolled += int(created)

        messages.success(
            request,
            f"Added {created_students} new student(s) and enrolled {enrolled} in {cohort.name}, "
            f"billed to {cohort.school.name}.",
        )
        return redirect('dashboard')