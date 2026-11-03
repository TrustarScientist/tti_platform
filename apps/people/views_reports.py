# apps/people/views_reports.py
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.core import notify
from . import reports as rpt
from .models import AttendanceRecord, ClassSession, Cohort, Enrollment, ProgressReport, Student
from .services import can_manage_student, can_share_report, can_teach_cohort, can_teach_enrollment
from .views_teach import TeacherRequiredMixin


def _abs(request, name, *args):
    return request.build_absolute_uri(reverse(name, args=args))


def _decorate(request, items):
    for r in items:
        r.share_url = _abs(request, 'report-shared', r.share_token) if r.share_is_live() else ''
    return items


def _teacher_back(report):
    if report.enrollment.cohort_id:
        return f"{reverse('teach-reports', args=[report.enrollment.cohort_id])}?period={report.period_start:%Y-%m}"
    return reverse('teach-enrollment', args=[report.enrollment_id])


def _parse_date(raw):
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


# ---- trainer side ----------------------------------------------------------

class CohortReportsView(TeacherRequiredMixin, View):
    def get(self, request, pk):
        cohort = get_object_or_404(Cohort.objects.select_related('track'), pk=pk)
        if not can_teach_cohort(request.user, cohort):
            return HttpResponseForbidden("You don't teach this cohort.")
        first = rpt.parse_period(request.GET.get('period'))
        items = _decorate(request, list(
            ProgressReport.objects.filter(enrollment__cohort=cohort, period_start=first)
            .select_related('student', 'enrollment').order_by('student__first_name', 'student__last_name')))
        return render(request, 'people/teach_reports.html', {
            'cohort': cohort, 'period': first, 'periods': rpt.recent_periods(), 'reports': items,
            'drafts': sum(1 for r in items if r.status == ProgressReport.Status.DRAFT),
        })


class GenerateReportsView(TeacherRequiredMixin, View):
    def post(self, request, pk):
        cohort = get_object_or_404(Cohort, pk=pk)
        if not can_teach_cohort(request.user, cohort):
            return HttpResponseForbidden("You don't teach this cohort.")
        first = rpt.parse_period(request.POST.get('period'))
        _, last = rpt.month_bounds(first)
        made = rpt.ensure_reports(rpt.cohort_enrollments(cohort, last), first, last)
        messages.success(request, f"{len(made)} draft report(s) ready for {first:%B %Y}.")
        return redirect(f"{reverse('teach-reports', args=[cohort.pk])}?period={first:%Y-%m}")


class PublishAllReportsView(TeacherRequiredMixin, View):
    def post(self, request, pk):
        cohort = get_object_or_404(Cohort, pk=pk)
        if not can_teach_cohort(request.user, cohort):
            return HttpResponseForbidden("You don't teach this cohort.")
        first = rpt.parse_period(request.POST.get('period'))
        drafts = (ProgressReport.objects
                  .filter(enrollment__cohort=cohort, period_start=first, status=ProgressReport.Status.DRAFT)
                  .select_related('student', 'enrollment__track', 'enrollment__cohort'))
        count = 0
        for report in drafts:
            rpt.publish(report, request.user)
            notify.report_published(report.pk, _abs(request, 'report-detail', report.pk))
            count += 1
        messages.success(request, f"Published {count} report(s). Linked parents were emailed.")
        return redirect(f"{reverse('teach-reports', args=[cohort.pk])}?period={first:%Y-%m}")


class ReportEditView(TeacherRequiredMixin, View):
    def post(self, request, report_id):
        report = get_object_or_404(
            ProgressReport.objects.select_related('enrollment__cohort', 'enrollment__track', 'student'), pk=report_id)
        if not can_teach_enrollment(request.user, report.enrollment):
            return HttpResponseForbidden("You can't edit this report.")
        report.trainer_note = request.POST.get('trainer_note', '').strip()[:1000]
        report.next_step = request.POST.get('next_step', '').strip()[:200]
        report.save(update_fields=['trainer_note', 'next_step'])
        if request.POST.get('action') == 'publish' and report.status == ProgressReport.Status.DRAFT:
            rpt.publish(report, request.user)
            notify.report_published(report.pk, _abs(request, 'report-detail', report.pk))
            messages.success(request, "Published. Linked parents were emailed.")
        else:
            messages.success(request, "Saved.")
        return redirect(_teacher_back(report))


class OneOnOneView(TeacherRequiredMixin, View):
    def _load(self, request, enrollment_id):
        enrollment = get_object_or_404(
            Enrollment.objects.select_related('student', 'track'),
            pk=enrollment_id, delivery_mode=Enrollment.DeliveryMode.ONE_ON_ONE)
        return enrollment if can_teach_enrollment(request.user, enrollment) else None

    def get(self, request, enrollment_id):
        enrollment = self._load(request, enrollment_id)
        if enrollment is None:
            return HttpResponseForbidden("You don't teach this student.")
        items = _decorate(request, list(
            enrollment.reports.select_related('student', 'enrollment').order_by('-period_start')))
        return render(request, 'people/teach_enrollment.html', {
            'enrollment': enrollment, 'reports': items, 'periods': rpt.recent_periods(),
            'sessions': list(enrollment.one_on_one_sessions.prefetch_related('records')[:10]),
            'statuses': AttendanceRecord.Status.choices, 'today': timezone.localdate(),
        })

    def post(self, request, enrollment_id):
        enrollment = self._load(request, enrollment_id)
        if enrollment is None:
            return HttpResponseForbidden("You don't teach this student.")
        action = request.POST.get('action')
        if action == 'log_session':
            day, status = _parse_date(request.POST.get('date')), request.POST.get('status')
            valid = {value for value, _ in AttendanceRecord.Status.choices}
            if day is None or day > timezone.localdate() or status not in valid:
                messages.error(request, "Choose a valid date (not in the future) and attendance.")
            else:
                session, _ = ClassSession.objects.get_or_create(
                    enrollment=enrollment, date=day, defaults={'taken_by': request.user})
                session.topic = request.POST.get('topic', '').strip()[:150]
                session.taken_by = request.user
                session.save(update_fields=['topic', 'taken_by'])
                AttendanceRecord.objects.update_or_create(
                    session=session, enrollment=enrollment, defaults={'status': status})
                messages.success(request, "Session logged.")
        elif action == 'generate':
            first = rpt.parse_period(request.POST.get('period'))
            _, last = rpt.month_bounds(first)
            rpt.ensure_reports([enrollment], first, last)
            messages.success(request, f"Draft ready for {first:%B %Y}.")
        return redirect('teach-enrollment', enrollment_id=enrollment.pk)


# ---- family side -----------------------------------------------------------

class ReportListView(LoginRequiredMixin, View):
    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if not can_manage_student(request.user, student):
            return HttpResponseForbidden("You don't have access to this student.")
        items = student.reports.filter(status=ProgressReport.Status.PUBLISHED).select_related('enrollment__track')
        return render(request, 'people/report_list.html', {'student': student, 'reports': items})


class ReportDetailView(LoginRequiredMixin, View):
    def get(self, request, report_id):
        report = get_object_or_404(
            ProgressReport.objects.select_related('student', 'enrollment__track', 'enrollment__cohort'),
            pk=report_id)
        if not can_manage_student(request.user, report.student):
            return HttpResponseForbidden("You don't have access to this report.")
        if report.status != ProgressReport.Status.PUBLISHED:
            raise Http404
        return render(request, 'people/report_detail.html', {
            'report': report, 'snap': report.snapshot,
            'share_url': _abs(request, 'report-shared', report.share_token) if report.share_is_live() else '',
            'can_share': can_share_report(request.user, report.student),
        })


class ReportShareView(LoginRequiredMixin, View):
    def post(self, request, report_id):
        report = get_object_or_404(
            ProgressReport.objects.select_related('enrollment__cohort', 'student'), pk=report_id)
        is_trainer = can_teach_enrollment(request.user, report.enrollment)
        if not (is_trainer or can_share_report(request.user, report.student)):
            return HttpResponseForbidden("You can't share this report.")
        if report.status != ProgressReport.Status.PUBLISHED:
            raise Http404
        if request.POST.get('action') == 'on':
            report.enable_share()
            messages.success(request, "Link created. It works without a login and expires in 60 days.")
        else:
            report.disable_share()
            messages.info(request, "Link switched off.")
        if is_trainer:
            return redirect(_teacher_back(report))
        return redirect('report-detail', report_id=report.pk)


def shared_report(request, token):
    """Public, no login. Shows a limited view and is never indexed by search engines."""
    report = (ProgressReport.objects.select_related('student', 'enrollment__track')
              .filter(share_token=token).first())
    if report is None or not report.share_is_live():
        return render(request, 'public/report_unavailable.html', status=404)
    response = render(request, 'public/report_shared.html', {'report': report, 'snap': report.snapshot})
    response['X-Robots-Tag'] = 'noindex, nofollow'
    response['Cache-Control'] = 'private, no-store'
    return response