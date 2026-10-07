# apps/people/forms.py (full replace)
from datetime import date
from django import forms
from .models import Student,Track,Cohort, Enrollment
from django.db.models import Q
from django.utils import timezone
from .models import Assessment, Attempt


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ('first_name', 'last_name', 'date_of_birth')
        widgets = {'date_of_birth': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].label = "First name"
        self.fields['last_name'].label = "Last name"
        self.fields['date_of_birth'].label = "Date of birth (optional)"

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob and dob > date.today():
            raise forms.ValidationError("Date of birth can't be in the future.")
        return dob

# enrol
class EnrollForm(forms.Form):
    track = forms.ModelChoiceField(
        queryset=Track.objects.filter(is_active=True), empty_label=None,
        widget=forms.RadioSelect, label="Choose a track",
    )

# delivery



class TrackChoiceForm(forms.Form):
    track = forms.ModelChoiceField(
        queryset=Track.objects.filter(is_active=True),
        empty_label=None, widget=forms.RadioSelect, label="Choose a track",
    )

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student is not None:
            live_track_ids = Enrollment.objects.filter(
                student=student, status__in=[Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE]
            ).values_list('track_id', flat=True)
            self.fields['track'].queryset = self.fields['track'].queryset.exclude(id__in=live_track_ids)


class DeliveryChoiceForm(forms.Form):
    delivery = forms.ChoiceField(widget=forms.RadioSelect, label="Choose how to learn")

    def __init__(self, *args, track=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = []
        if track is not None:
            now = timezone.now()
            open_cohorts = Cohort.objects.filter(track=track, is_active=True).filter(
                Q(enrollment_opens_at__isnull=True) | Q(enrollment_opens_at__lte=now)
            ).filter(
                Q(enrollment_closes_at__isnull=True) | Q(enrollment_closes_at__gte=now)
            )
            for cohort in open_cohorts:
                if cohort.capacity:
                    taken = cohort.enrollments.filter(
                        status__in=[Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE]
                    ).count()
                    if taken >= cohort.capacity:
                        continue
                    label = f"{cohort.name} ({cohort.capacity - taken} seats left)"
                else:
                    label = cohort.name
                choices.append((f"cohort:{cohort.pk}", label))
        choices.append(('ONE_ON_ONE', "One-on-one — paced by your instructor"))
        choices.append(('SELF_PACED', "Self-paced — learn on your own schedule"))
        self.fields['delivery'].choices = choices



# TRS related
class AttemptForm(forms.ModelForm):
    class Meta:
        model = Attempt
        fields = ('notes', 'media')

    def __init__(self, *args, assessment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.assessment = assessment
        self.fields['notes'].label = "Tell us about it"
        self.fields['notes'].widget.attrs['rows'] = 4
        self.fields['media'].label = "Photo, video, or screenshot"
        self.fields['media'].required = bool(assessment and assessment.media_required)



# lc
class LinkChildForm(forms.Form):
    code = forms.CharField(max_length=32, label="Parent invite code")

    def clean_code(self):
        code = self.cleaned_data['code'].strip()
        student = Student.objects.filter(guardian_invite_code=code).first()
        if not student:
            raise forms.ValidationError("This code is invalid or has already been used.")
        self.student = student
        return code