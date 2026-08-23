from django.shortcuts import render
from django.views.generic import CreateView
from django.contrib.auth import login
from django.urls import reverse_lazy
from .forms import SignupForm, User
from .models import User

# Create your views here.

class SignupView(CreateView):
    model = User

    form_class = SignupForm

    template_name = "auth/signup.html"

    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        """
        Save the user,
        then log them in automatically.
        """

        response = super().form_valid(form)

        login(
            self.request,
            self.object,
        )

        return response





# secret codes
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# Adjust this import to wherever LearnerProfile actually lives
from academics.models import LearnerProfile


# ── NAV CONFIG ──────────────────────────────────────────────
# url_name: None means "no page built yet" — rendered as a disabled/placeholder
# link in the template rather than {% url %}, so nothing breaks with a
# NoReverseMatch error before those pages exist. Swap to real url_names
# as each page gets built.

NAV_CONFIG = {
    "parent": [
        {"section": "My Children"},
        {"label": "Overview", "icon": "ph-house-simple", "url_name": "dashboard"},
        {"label": "Add a Child", "icon": "ph-user-plus", "url_name": None},
        {"section": "Account"},
        {"label": "Messages", "icon": "ph-chats-circle", "url_name": None},
        {"label": "Payments", "icon": "ph-credit-card", "url_name": None},
        {"label": "Settings", "icon": "ph-gear", "url_name": None},
    ],
    # Stubs for the other four roles — just enough for the shell to render
    # without error. Expand each list when that dashboard actually gets built.
    "student": [
        {"section": "Learning"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
    ],
    "instructor": [
        {"section": "Teaching"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
    ],
    "school_partner": [
        {"section": "Organisation"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
    ],
    "admin": [
        {"section": "Platform"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
    ],
}

BOTTOM_NAV_CONFIG = {
    "parent": [
        {"label": "Overview", "icon": "ph-house-simple", "url_name": "dashboard"},
        {"label": "Children", "icon": "ph-users", "url_name": None},
        {"label": "Messages", "icon": "ph-chats-circle", "url_name": None},
        {"label": "Account", "icon": "ph-user-circle", "url_name": None},
    ],
}

TEMPLATE_MAP = {
    "student": "dashboard/dashboard_student.html",
    "parent": "dashboard/dashboard_parent.html",
    "instructor": "dashboard/dashboard_instructor.html",
    "school_partner": "dashboard/dashboard_school_partner.html",
    "admin": "dashboard/dashboard_admin.html",
}


@login_required
def dashboard(request):
    role = request.user.role
    context = {
        "nav_items": NAV_CONFIG.get(role, []),
        "bottom_nav_items": BOTTOM_NAV_CONFIG.get(role, []),
    }

    if role == "parent":
        # The one real piece of data on this dashboard today.
        # Field names below (first_name, last_name, date_of_birth, track)
        # are guesses matching our earlier design discussion —
        # swap to whatever LearnerProfile actually calls them.
        context["children"] = LearnerProfile.objects.filter(guardian=request.user)

    return render(request, TEMPLATE_MAP[role], context)


"""



# student dashboard
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# Adjust this import to wherever LearnerProfile actually lives
from academics.models import LearnerProfile


# ── NAV CONFIG ──────────────────────────────────────────────
# url_name: None means "no page built yet" — rendered as a disabled/placeholder
# link in the template rather than {% url %}, so nothing breaks with a
# NoReverseMatch error before those pages exist. Swap to real url_names
# as each page gets built.

NAV_CONFIG = {
    "parent": [
        {"section": "My Children"},
        {"label": "Overview", "icon": "ph-house-simple", "url_name": "dashboard"},
        {"label": "Add a Child", "icon": "ph-user-plus", "url_name": None},
        {"section": "Account"},
        {"label": "Messages", "icon": "ph-chats-circle", "url_name": None},
        {"label": "Payments", "icon": "ph-credit-card", "url_name": None},
        {"label": "Settings", "icon": "ph-gear", "url_name": None},
    ],
    # Stubs for the other four roles — just enough for the shell to render
    # without error. Expand each list when that dashboard actually gets built.
    "student": [
        {"section": "Learning"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
        {"label": "My Program", "icon": "ph-play-circle", "url_name": None},
        {"label": "My Cohort", "icon": "ph-users", "url_name": None},
        {"label": "Resources", "icon": "ph-folder-open", "url_name": None},
        {"label": "Assignments", "icon": "ph-clipboard-text", "url_name": None},
        {"section": "Progress"},
        {"label": "My TRS Score", "icon": "ph-chart-bar", "url_name": None},
        {"label": "Certificates", "icon": "ph-seal-check", "url_name": None},
        {"section": "Account"},
        {"label": "Settings", "icon": "ph-gear", "url_name": None},
    ],
    "instructor": [
        {"section": "Teaching"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
    ],
    "school_partner": [
        {"section": "Organisation"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
    ],
    "admin": [
        {"section": "Platform"},
        {"label": "Dashboard", "icon": "ph-house-simple", "url_name": "dashboard"},
    ],
}

BOTTOM_NAV_CONFIG = {
    "parent": [
        {"label": "Overview", "icon": "ph-house-simple", "url_name": "dashboard"},
        {"label": "Children", "icon": "ph-users", "url_name": None},
        {"label": "Messages", "icon": "ph-chats-circle", "url_name": None},
        {"label": "Account", "icon": "ph-user-circle", "url_name": None},
    ],
    "student": [
        {"label": "Home", "icon": "ph-house-simple", "url_name": "dashboard"},
        {"label": "Learn", "icon": "ph-play-circle", "url_name": None},
        {"label": "Cohort", "icon": "ph-users", "url_name": None},
        {"label": "Profile", "icon": "ph-user-circle", "url_name": None},
    ],
}

TEMPLATE_MAP = {
    "student": "dashboard/dashboard_student.html",
    "parent": "dashboard/dashboard_parent.html",
    "instructor": "dashboard/dashboard_instructor.html",
    "school_partner": "dashboard/dashboard_school_partner.html",
    "admin": "dashboard/dashboard_admin.html",
}


@login_required
def dashboard(request):
    role = request.user.role
    context = {
        "nav_items": NAV_CONFIG.get(role, []),
        "bottom_nav_items": BOTTOM_NAV_CONFIG.get(role, []),
    }

    if role == "parent":
        # The one real piece of data on this dashboard today.
        # Field names below (first_name, last_name, date_of_birth, track)
        # are guesses matching our earlier design discussion —
        # swap to whatever LearnerProfile actually calls them.
        context["children"] = LearnerProfile.objects.filter(guardian=request.user)

    if role == "student":
        # Only independent-login students have a LearnerProfile linked back
        # via `user` — younger, parent-managed students won't. Handle both:
        # a student with no linked profile yet still needs a working page.
        context["student_profile"] = LearnerProfile.objects.filter(user=request.user).first()

    return render(request, TEMPLATE_MAP[role], context)
"""