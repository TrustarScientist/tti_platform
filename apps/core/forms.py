# apps/core/forms.py
from django import forms

from apps.people.models import Track
from .models import Lead


class LeadForm(forms.ModelForm):
    interest = forms.ChoiceField(required=False)

    class Meta:
        model = Lead
        fields = ('name', 'contact', 'child_age', 'interest', 'message')
        widgets = {'message': forms.Textarea(attrs={'rows': 3})}
        labels = {
            'name': 'Your name', 'contact': 'Phone or email', 'child_age': "Learner's age (optional)",
            'message': 'Anything we should know? (optional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['interest'].label = 'What are you interested in?'
        self.fields['interest'].choices = [('', 'Not sure yet')] + [
            (t.name, t.name) for t in Track.objects.filter(is_active=True, audience=Track.Audience.PUBLIC)
        ]

    def clean_contact(self):
        value = self.cleaned_data['contact'].strip()
        digits = sum(ch.isdigit() for ch in value)
        looks_like_email = '@' in value and '.' in value.split('@')[-1]
        if looks_like_email or digits >= 7:
            return value
        raise forms.ValidationError("Enter a phone number or an email we can reach you on.")

    def clean_child_age(self):
        age = self.cleaned_data.get('child_age')
        if age is not None and not 2 <= age <= 99:
            raise forms.ValidationError("Enter an age between 2 and 99.")
        return age