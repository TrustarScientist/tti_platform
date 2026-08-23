# academics/models.py
from django.db import models

# Create your models here.
# name, contact_person, contact_email, created_at
class School(models.Model):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255)
    contact_email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name



from django.db import models


class LearnerProfile(models.Model):
    """
    Represents anyone learning through Trustar.

    Every learner has a profile.

    Only some learners have a User account.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learner_profile",
    )

    parent = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        limit_choices_to={"role": "parent"},
    )

    first_name = models.CharField(max_length=100)

    last_name = models.CharField(max_length=100)

    date_of_birth = models.DateField(
        blank=True,
        null=True,
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

