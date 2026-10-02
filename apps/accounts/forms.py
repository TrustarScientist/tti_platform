# apps/accounts/forms.py (full replace)
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import TUser

PUBLIC_ROLES = [
    (TUser.Role.STUDENT, 'Student', "I'm learning with Trustar."),
    (TUser.Role.PARENT, 'Parent', "I manage my child's learning."),
    (TUser.Role.SCHOOL_PARTNER, 'School partner',
     "I represent a school. New school accounts are reviewed before they can log in."),
]
PUBLIC_ROLE_CHOICES = [(value, label) for value, label, _hint in PUBLIC_ROLES]


class SignupForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=PUBLIC_ROLE_CHOICES,
        widget=forms.RadioSelect,
        initial=TUser.Role.STUDENT,
    )
    phone = forms.CharField(
        required=False,
        empty_value=None,  # blank must be NULL, not '', or the unique column collides
        widget=forms.TextInput(attrs={'placeholder': '+234...'}),
    )
    claim_code = forms.CharField(required=False, max_length=32)

    class Meta(UserCreationForm.Meta):
        model = TUser
        fields = ('username', 'email', 'phone', 'first_name', 'last_name', 'role', 'school_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            del self.fields['username']

        self.fields['email'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True

        self.fields['email'].label = "Email address"
        self.fields['phone'].label = "Phone number (optional)"
        self.fields['school_name'].label = "School name"
        self.fields['claim_code'].label = "Invite code (optional)"
        self.fields['claim_code'].help_text = (
            "Got a code from a parent or school? Enter it to link your existing student profile."
        )
        self.fields['password1'].label = "Password"
        self.fields['password1'].help_text = "At least 8 characters. Not too common, and not all numbers."
        self.fields['password2'].label = "Confirm password"
        self.fields['password2'].help_text = ""

        for name, ac in (('first_name', 'given-name'), ('last_name', 'family-name'),
                         ('email', 'email'), ('phone', 'tel'), ('school_name', 'organization')):
            self.fields[name].widget.attrs['autocomplete'] = ac

    @property
    def role_options(self):
        selected = self['role'].value()
        return [
            {'value': value, 'label': label, 'hint': hint, 'checked': value == selected}
            for value, label, hint in PUBLIC_ROLES
        ]

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if TUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        code = cleaned.get('claim_code')

        if code and role != TUser.Role.STUDENT:
            raise forms.ValidationError("Invite codes only apply to student sign-up.")

        if code:
            from apps.people.models import Student
            if not Student.objects.filter(claim_code=code, user__isnull=True).exists():
                self.add_error('claim_code', "This invite code is invalid or already used.")

        if role == TUser.Role.SCHOOL_PARTNER and not cleaned.get('school_name'):
            self.add_error('school_name', "Enter your school's name so we can review your account.")

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.role = self.cleaned_data['role']

        # School partners need admin review; everyone else is approved on signup.
        if user.role == TUser.Role.SCHOOL_PARTNER:
            user.status = TUser.Status.PENDING
        else:
            user.status = TUser.Status.APPROVED
            user.school_name = ''

        if commit:
            user.save()
        return user


class EmailOrPhoneAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': "That email or phone and password don't match. Check both and try again.",
        'pending': "Your account is waiting for approval. You'll be able to log in once it's approved.",
        'suspended': "This account has been deactivated. Please contact Trustar.",
    }
    username = forms.CharField(
        label="Email or phone",
        widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}),
    )

    def clean(self):
        identifier = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if identifier and password:
            user = TUser.objects.get_by_identifier(identifier)
            # Only someone who typed the right password learns the account's status.
            if user and not user.is_active and user.check_password(password):
                if user.status == TUser.Status.PENDING:
                    raise forms.ValidationError(self.error_messages['pending'], code='pending')
                if user.status == TUser.Status.SUSPENDED:
                    raise forms.ValidationError(self.error_messages['suspended'], code='suspended')

        return super().clean()