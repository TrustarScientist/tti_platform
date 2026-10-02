# apps/core/views.py 
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from django.db.models import Count, Q
from apps.people.models import Student
from apps.accounts.models import TUser


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
        return render(request, template, context)

    if user.role == TUser.Role.INSTRUCTOR:
        return render(request, 'dashboard/dashboard_instructor.html')

    if user.role == TUser.Role.STUDENT:
        profile = getattr(user, 'student_profile', None)
        return render(request, 'dashboard/dashboard_student.html', {'profile': profile})

    return render(request, 'dashboard_error.html')