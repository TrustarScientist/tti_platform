# accounts/forms.py
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()



class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = (
            "email",
            "role",
            "first_name",
            "last_name",
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"



# public signup form for parents and learners
class SignupForm(UserCreationForm):
    """
    Public registration form.

    Only Student and Parent accounts
    can be created here.
    """

    ROLE_CHOICES = [
        ("student", "Student"),
        ("parent", "Parent"),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES
    )

    class Meta:
        model = User

        fields = (
            "email",
            "first_name",
            "last_name",
            "role",
            "password1",
            "password2",
        )