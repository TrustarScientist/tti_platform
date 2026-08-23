# accounts/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin


User = get_user_model()

from .forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
)


class CustomUserAdmin(UserAdmin):

    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    
    model = User
    list_display = (
    "email",
    "first_name",
    "last_name",
    "role",
    "is_staff",
)
    search_fields = (
    "email",
    "first_name",
    "last_name",
)
    ordering = ("email",)
    fieldsets = (
    (None, {
        "fields": (
            "email",
            "password",
        ),
    }),

    ("Personal Info", {
        "fields": (
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "admin_level",
        ),
    }),

    ("Permissions", {
        "fields": (
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ),
    }),

    ("Important Dates", {
        "fields": (
            "last_login",
            "date_joined",
        ),
    }),
)
    add_fieldsets = (
    (None, {
        "classes": ("wide",),

        "fields": (
            "email",
            "role",
            "first_name",
            "last_name",
            "password1",
            "password2",
        ),
    }),
)




admin.site.register(User, CustomUserAdmin)
