# apps/people/views_teach.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.accounts.models import TUser
from .models import Attempt, Cohort, Enrollment
from .services import can_teach_cohort, teachable_cohorts, cohort_roster, verify_attempt, reject_attempt


class TeacherRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        return u.is_staff or u.role in (TUser.Role.ADMIN, TUser.Role.INSTRUCTOR)


class TeachHomeView(TeacherRequiredMixin, View):
    def get(self, request):
        cohorts = teachable_cohorts(request.user).annotate(
            students=Count('enrollments', filter=Q(enrollments__status=Enrollment.Status.ACTIVE), distinct=True),
            waiting=Count('enrollments__attempts',
                          filter=Q(enrollments__attempts__status=Attempt.Status.NEEDS_REVIEW), distinct=True),
        ).order_by('name')
        return render(request, 'people/teach_home.html', {'cohorts': cohorts})


class CohortConsoleView(TeacherRequiredMixin, View):
    def get(self, request, pk):
        cohort = get_object_or_404(Cohort.objects.select_related('track', 'school'), pk=pk)
        if not can_teach_cohort(request.user, cohort):
            return HttpResponseForbidden("You don't teach this cohort.")
        roster, lesson = cohort_roster(cohort)
        queue = (Attempt.objects.filter(enrollment__cohort=cohort, status=Attempt.Status.NEEDS_REVIEW)
                 .select_related('enrollment__student', 'assessment').order_by('submitted_at'))
        return render(request, 'people/teach_cohort.html', {
            'cohort': cohort, 'lesson': lesson, 'roster': roster, 'queue': queue,
            'has_next': bool(lesson and lesson.next()),
        })


class AdvanceCohortView(TeacherRequiredMixin, View):
    def post(self, request, pk):
        cohort = get_object_or_404(Cohort, pk=pk)
        if not can_teach_cohort(request.user, cohort):
            return HttpResponseForbidden("You don't teach this cohort.")
        if cohort.advance():
            messages.success(request, f"{cohort.name} moved to the next lesson.")
        else:
            messages.success(request, f"That was the last lesson. {cohort.name} is now complete.")
        return redirect('teach-cohort', pk=cohort.pk)


class ReviewAttemptView(TeacherRequiredMixin, View):
    def post(self, request, pk):
        attempt = get_object_or_404(Attempt.objects.select_related('enrollment__cohort', 'assessment'), pk=pk)
        cohort = attempt.enrollment.cohort
        if cohort is None or not can_teach_cohort(request.user, cohort):
            return HttpResponseForbidden("You can't review this submission.")
        if attempt.status != Attempt.Status.NEEDS_REVIEW:
            messages.info(request, "That submission was already reviewed.")
            return redirect('teach-cohort', pk=cohort.pk)

        feedback = request.POST.get('feedback', '').strip()[:1000]
        if request.POST.get('action') == 'reject':
            reject_attempt(attempt, reviewer=request.user, feedback=feedback)
            messages.success(request, "Sent back to the student to redo.")
        else:
            max_score = attempt.assessment.max_score
            raw = request.POST.get('score', '').strip()
            try:
                score = int(raw) if raw else max_score
            except ValueError:
                score = -1
            if not 0 <= score <= max_score:
                messages.error(request, f"Score must be a whole number from 0 to {max_score}.")
                return redirect('teach-cohort', pk=cohort.pk)
            verify_attempt(attempt, reviewer=request.user, score=score, feedback=feedback)
            messages.success(request, "Verified.")
        return redirect('teach-cohort', pk=cohort.pk)