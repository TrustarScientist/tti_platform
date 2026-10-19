# apps/people/forms.py 
from datetime import date
from django import forms
from .models import Student, Track, Enrollment, Attempt
from .services import tracks_for, open_cohorts_for, price_for, region_for



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
    track = forms.ModelChoiceField(queryset=Track.objects.none(), empty_label=None,
                                   widget=forms.RadioSelect, label="Choose a track")

    def __init__(self, *args, student=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = tracks_for(user) if user is not None else Track.objects.none()
        if student is not None:
            live = Enrollment.objects.filter(
                student=student, status__in=[Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE]
            ).values_list('track_id', flat=True)
            qs = qs.exclude(id__in=live)
        self.fields['track'].queryset = qs



class DeliveryChoiceForm(forms.Form):
    delivery = forms.ChoiceField(widget=forms.RadioSelect, label="Choose how to learn")

    def __init__(self, *args, track=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = []
        if track is not None:
            def priced(label, mode):
                price = price_for(track, mode, region_for(user))
                return f"{label} · {price.label()}" if price else label

            if track.offers_cohort:
                for cohort in open_cohorts_for(user, track):
                    label = cohort.name
                    if cohort.capacity:
                        taken = cohort.enrollments.filter(
                            status__in=[Enrollment.Status.PENDING_PAYMENT, Enrollment.Status.ACTIVE]
                        ).count()
                        if taken >= cohort.capacity:
                            continue
                        label = f"{cohort.name} ({cohort.capacity - taken} seats left)"
                    if cohort.schedule_note:
                        label += f" — {cohort.schedule_note}"
                    # School cohorts are billed on the school's invoice, so they show no family price.
                    if not cohort.school_id:
                        label = priced(label, Enrollment.DeliveryMode.COHORT)
                    choices.append((f"cohort:{cohort.pk}", label))
            if track.offers_one_on_one:
                choices.append(('ONE_ON_ONE', priced("One-on-one — paced by your instructor", Enrollment.DeliveryMode.ONE_ON_ONE)))
            if track.offers_self_paced:
                choices.append(('SELF_PACED', priced("Self-paced — learn on your own schedule", Enrollment.DeliveryMode.SELF_PACED)))
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