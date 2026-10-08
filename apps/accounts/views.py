# apps/accounts/views.py (full replace)
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView

from django.core.mail import send_mail 
from django.urls import reverse



from .forms import SignupForm
from .models import TUser


class RegisterView(CreateView):
    form_class = SignupForm
    template_name = 'register.html'
    success_url = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object

        if user.role == TUser.Role.STUDENT:
            from apps.people.services import attach_student_profile
            attach_student_profile(user, form.cleaned_data.get('claim_code'))

        if user.role == TUser.Role.SCHOOL_PARTNER:
            messages.info(self.request, "Account created. It's pending admin approval before you can log in.")
        else:
            messages.info(self.request, "Registration successful! You can now log in.")

        if self.request.headers.get("HX-Request"):
            hx_response = HttpResponse()
            hx_response["HX-Redirect"] = str(self.success_url)
            return hx_response

        return response


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == TUser.Role.ADMIN


class PartnerDecisionView(AdminRequiredMixin, View):
    """POST-only. Subclasses set new_status and result_text."""
    new_status = None
    result_text = ""

    def post(self, request, pk):
        partner = get_object_or_404(TUser, pk=pk, role=TUser.Role.SCHOOL_PARTNER)
        label = partner.school_name or partner.get_full_name() or partner.email

        if partner.status != TUser.Status.PENDING:
            messages.info(request, f"{label} has already been reviewed.")
            return redirect('dashboard')

        partner.status = self.new_status
        partner.save(update_fields=['status', 'is_active'])  # save() syncs is_active from status
        messages.success(request, self.result_text.format(label=label))
        return redirect('dashboard')


class DeclinePartnerView(PartnerDecisionView):
    new_status = TUser.Status.SUSPENDED
    result_text = "{label} was declined and can't log in."


class ApprovePartnerView(PartnerDecisionView):
    new_status = TUser.Status.APPROVED
    result_text = "{label} is approved and can now log in."

    def post(self, request, pk):
        partner = get_object_or_404(TUser, pk=pk, role=TUser.Role.SCHOOL_PARTNER)

        if partner.status == TUser.Status.PENDING and partner.school_name and not partner.school_id:
            from apps.people.models import School
            name = partner.school_name.strip()
            school = School.objects.filter(name__iexact=name).first() or School.objects.create(
                name=name, contact_email=partner.email, contact_phone=partner.phone or '',
            )
            partner.school = school
            partner.save(update_fields=['school'])  # the line that was missing before

        response = super().post(request, pk)

        partner.refresh_from_db()
        if partner.status == TUser.Status.APPROVED:
            login_url = request.build_absolute_uri(reverse('login'))
            send_mail(
                subject="Your Trustar school account is approved",
                message=(f"Hi {partner.first_name or ''},\n\n"
                         f"{partner.school_name or 'Your account'} has been approved. "
                         f"You can now log in here:\n{login_url}\n\n— Trustar Tech Institute"),
                from_email=None, recipient_list=[partner.email], fail_silently=True,
            )
        return response


# 
from django.conf import settings
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required


@staff_member_required
def debug_email_settings(request):
    return HttpResponse(
        f"DEBUG={settings.DEBUG}<br>"
        f"EMAIL_BACKEND={settings.EMAIL_BACKEND}<br>"
        f"EMAIL_HOST={settings.EMAIL_HOST!r}<br>"
        f"EMAIL_PORT={settings.EMAIL_PORT}<br>"
        f"EMAIL_HOST_USER={settings.EMAIL_HOST_USER!r}<br>"
        f"EMAIL_USE_TLS={settings.EMAIL_USE_TLS}<br>"
        f"DEFAULT_FROM_EMAIL={settings.DEFAULT_FROM_EMAIL!r}<br>"
        f"EMAIL_TIMEOUT={getattr(settings, 'EMAIL_TIMEOUT', None)}"
    )


# 
from django.contrib.auth.forms import PasswordResetForm


@staff_member_required
def debug_password_reset_test(request):
    email = request.GET.get('email', 'trustartechinstitute@gmail.com')
    form = PasswordResetForm({'email': email})
    output = []

    if not form.is_valid():
        return HttpResponse(f"Form invalid: {form.errors}")

    users = list(form.get_users(email))
    output.append(f"get_users() matched {len(users)} user(s): {[u.email for u in users]}")

    if not users:
        return HttpResponse("<br>".join(output))

    try:
        form.save(
            request=request,
            use_https=True,
            email_template_name='auth/password_reset_email.txt',
            subject_template_name='auth/password_reset_subject.txt',
        )
        output.append("form.save() completed without raising.")
    except Exception as e:
        output.append(f"form.save() RAISED: {type(e).__name__}: {e}")

    return HttpResponse("<br>".join(output))