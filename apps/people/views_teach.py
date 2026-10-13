from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.models import TUser
from .models import Attempt, AttendanceRecord, ClassSession, Cohort, Enrollment
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
        cohort = get_object_or_404(Cohort.objects.select_related('track', 'school', 'submitted_by'), pk=pk)
        if not can_teach_cohort(request.user, cohort):
            return HttpResponseForbidden("You don't teach this cohort.")
        roster, lesson = cohort_roster(cohort)
        queue = (Attempt.objects.filter(enrollment__cohort=cohort, status=Attempt.Status.NEEDS_REVIEW)
                 .select_related('enrollment__student', 'assessment', 'submitted_by').order_by('submitted_at'))
        recent = cohort.sessions.annotate(
            present=Count('records', filter=Q(records__status__in=['PRESENT', 'LATE'])),
            total=Count('records'),
        )[:5]
        return render(request, 'people/teach_cohort.html', {
            'cohort': cohort, 'lesson': lesson, 'roster': roster, 'queue': queue,
            'has_next': bool(lesson and lesson.next()),
            'recent_sessions': recent
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
        attempt = get_object_or_404(Attempt.objects.select_related('enrollment__cohort', 'assessment', 'submitted_by'), pk=pk)
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
    



def _parse_date(raw):
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


class AttendanceView(TeacherRequiredMixin, View):
    template_name = 'people/teach_attendance.html'

    def _load(self, request, pk):
        cohort = get_object_or_404(Cohort.objects.select_related('track', 'school', 'submitted_by'), pk=pk)
        return cohort if can_teach_cohort(request.user, cohort) else None

    def get(self, request, pk):
        cohort = self._load(request, pk)
        if cohort is None:
            return HttpResponseForbidden("You don't teach this cohort.")
        today = timezone.localdate()
        day = _parse_date(request.GET.get('date')) or today
        day = min(day, today)

        session = ClassSession.objects.filter(cohort=cohort, date=day).first()
        existing = {r.enrollment_id: r.status for r in session.records.all()} if session else {}
        enrollments = (cohort.enrollments.filter(status=Enrollment.Status.ACTIVE)
                       .select_related('student', 'submitted_by').order_by('student__first_name', 'student__last_name'))
        rows = [{'enrollment': e, 'student': e.student, 'status': existing.get(e.id, 'PRESENT')}
                for e in enrollments]
        return render(request, self.template_name, {
            'cohort': cohort, 'day': day, 'rows': rows, 'is_saved': session is not None,
            'topic': session.topic if session else '', 'statuses': AttendanceRecord.Status.choices,
        })

    def post(self, request, pk):
        cohort = self._load(request, pk)
        if cohort is None:
            return HttpResponseForbidden("You don't teach this cohort.")
        day = _parse_date(request.POST.get('date'))
        if day is None or day > timezone.localdate():
            messages.error(request, "Choose a valid date. It can't be in the future.")
            return redirect('teach-cohort', pk=cohort.pk)

        valid = {value for value, _ in AttendanceRecord.Status.choices}
        enrollments = list(cohort.enrollments.filter(status=Enrollment.Status.ACTIVE))
        attended = absent = 0
        with transaction.atomic():
            session, _ = ClassSession.objects.get_or_create(
                cohort=cohort, date=day, defaults={'taken_by': request.user})
            session.topic = request.POST.get('topic', '').strip()[:150]
            session.taken_by = request.user
            session.save(update_fields=['topic', 'taken_by'])
            for enrollment in enrollments:
                status = request.POST.get(f'status_{enrollment.pk}')
                if status not in valid:
                    continue
                AttendanceRecord.objects.update_or_create(
                    session=session, enrollment=enrollment, defaults={'status': status})
                if status in ('PRESENT', 'LATE'):
                    attended += 1
                elif status == 'ABSENT':
                    absent += 1


        messages.success(request, f"Attendance saved for {day:%A %d %B}: {attended} attended, {absent} absent.")
        return redirect('teach-cohort', pk=cohort.pk)