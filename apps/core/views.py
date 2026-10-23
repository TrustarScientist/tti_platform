# apps/core/views.py 
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse

from django.db.models import Count, Q
from apps.people.models import Student
from apps.accounts.models import TUser

from datetime import timedelta

from django.contrib import messages
from django.core.cache import cache
from django.utils import timezone

from apps.people.models import Enrollment, Track
from apps.people.services import open_cohorts_for, price_for, region_for, seats_left

from .forms import LeadForm
from .models import Lead


def index(request):
    return render(request, 'core/home.html')


@login_required
def dashboard(request):
    user = request.user

    if user.role == TUser.Role.ADMIN:
        pending = TUser.objects.filter(
            role=TUser.Role.SCHOOL_PARTNER, status=TUser.Status.PENDING
        ).order_by('date_joined')
        totals = TUser.objects.aggregate(
            parents=Count('id', filter=Q(role=TUser.Role.PARENT)),
            schools=Count('id', filter=Q(role=TUser.Role.SCHOOL_PARTNER, status=TUser.Status.APPROVED)),
        )
        totals['students'] = Student.objects.count()
        totals['new_leads'] = Lead.objects.filter(status=Lead.Status.NEW).count()
        return render(request, 'dashboard/admin_dashboard.html', {'pending': pending, 'totals': totals})

    if user.role in (TUser.Role.PARENT, TUser.Role.SCHOOL_PARTNER):
        wards = user.wards.select_related('student').order_by(
            'student__first_name', 'student__last_name'
        )
        template = (
            'dashboard/dashboard_parent.html' if user.role == TUser.Role.PARENT
            else 'dashboard/dashboard_school_partner.html'
        )
        context = {
            'wards': wards,
            'signup_url': request.build_absolute_uri(reverse('signup')),
        }
        if user.role == TUser.Role.SCHOOL_PARTNER and user.school_id:
            context['invoices'] = user.school.invoices.exclude(status='VOID')[:6]
        return render(request, template, context)

    if user.role == TUser.Role.INSTRUCTOR:
            return redirect('teach-home')

    if user.role == TUser.Role.STUDENT:
        profile = getattr(user, 'student_profile', None)
        return render(request, 'dashboard/dashboard_student.html', {'profile': profile})

    return render(request, 'dashboard_error.html')


from django.db import connection
from django.http import HttpResponse


def healthz(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok")


# public data
FORMATS = [
    (Enrollment.DeliveryMode.COHORT, 'Live group class',
     "Learn with a small group and a live instructor, starting on set dates."),
    (Enrollment.DeliveryMode.SELF_PACED, 'Self-paced',
     "Learn on your own schedule, with lessons and projects that are checked."),
    (Enrollment.DeliveryMode.ONE_ON_ONE, 'One-on-one',
     "Private live lessons, paced for the learner."),
]
LEADS_PER_HOUR = 40


def _under_hourly_cap():
    key = f"leads:{timezone.now():%Y%m%d%H}"
    count = cache.get(key, 0)
    if count >= LEADS_PER_HOUR:
        return False
    cache.set(key, count + 1, 3600)
    return True


def _program_cards(user):
    region = region_for(user)
    cards = []
    for track in Track.objects.filter(is_active=True, audience=Track.Audience.PUBLIC).order_by('id'):
        offered = {Enrollment.DeliveryMode.COHORT: track.offers_cohort,
                   Enrollment.DeliveryMode.ONE_ON_ONE: track.offers_one_on_one,
                   Enrollment.DeliveryMode.SELF_PACED: track.offers_self_paced}
        formats = [{'title': title, 'blurb': blurb, 'price': price_for(track, mode, region)}
                   for mode, title, blurb in FORMATS if offered[mode]]
        classes = []
        if track.offers_cohort:
            for cohort in open_cohorts_for(user, track):
                left = seats_left(cohort)
                if left is None or left > 0:
                    classes.append({'cohort': cohort, 'seats_left': left})
        cards.append({'track': track, 'formats': formats, 'classes': classes})
    return cards


def programs(request):
    form = LeadForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        back = redirect(reverse('programs') + '#talk')
        if not request.POST.get('website'):  # a filled hidden field gets a normal reply and stores nothing
            if not _under_hourly_cap():
                messages.error(request, "We're getting a lot of messages right now. Please try WhatsApp instead.")
                return back
            recent = Lead.objects.filter(contact__iexact=data['contact'],
                                         created_at__gte=timezone.now() - timedelta(days=1)).exists()
            if not recent:
                Lead.objects.create(
                    name=data['name'], contact=data['contact'], child_age=data.get('child_age'),
                    interest=data.get('interest', ''), message=data.get('message', ''), source='programs')
        messages.success(request, "Thank you! We'll get back to you soon.")
        return back
    return render(request, 'public/programs.html', {'cards': _program_cards(request.user), 'form': form})