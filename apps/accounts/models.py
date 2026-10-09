# tti_platform/apps/accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser

from .managers import TUserManager

# Create your models here.
"""
independent students can register themselves but 'child' students can't hence their parents' access
and the need for a separate Student model that can optionally connect to a user account

Also, school partners can create their students

a 'child' student or student under a school partner (who may not have user account)
can 'upgrade' explicitly. 

students can ,potentially, be associated with several school partners and parents, but must be approved
"""

class TUser(AbstractUser):
    email = models.EmailField(
        max_length=128, 
        unique=True,
        help_text='required email'
        )
    phone = models.CharField(
        max_length=15, 
        unique=True, 
        blank=True, 
        null=True, 
        help_text="optional phone you can also use to login"
        )

    USERNAME_FIELD = 'email'
    # no default email appearing here since it's already the username field
    REQUIRED_FIELDS = []

    school_name = models.CharField(
        max_length=150, blank=True,
        help_text="School partners only: the school this account represents.",
    )
    # for proper refinement
    school = models.ForeignKey(
        'people.School', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='partners',
    )
    # custom manager
    objects = TUserManager()

    class Role(models.TextChoices):
        STUDENT = 'STUDENT', 'Student'
        INSTRUCTOR = 'INSTRUCTOR', 'Instructor'
        PARENT = 'PARENT', 'Parent'
        ADMIN = 'ADMIN', 'Admin'
        SCHOOL_PARTNER = 'SCHOOL_PARTNER', 'School Partner'

    role = models.CharField(
        max_length=25,
        choices=Role.choices,
        default=Role.STUDENT,
        help_text="primary role"
    )

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        SUSPENDED = 'SUSPENDED', 'Suspended'

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING
    )

    def save(self, *args, **kwargs):
        # status drives is_active (unchanged)
        if self.status in (self.Status.PENDING, self.Status.SUSPENDED):
            self.is_active = False
        elif self.status == self.Status.APPROVED:
            self.is_active = True

        # An approved school partner always ends up attached to a School,
        # whichever route approved them (queue button, Django admin, shell).
        if (self.role == self.Role.SCHOOL_PARTNER and self.status == self.Status.APPROVED
                and self.school_name and not self.school_id):
            from apps.people.models import School
            name = self.school_name.strip()
            self.school = School.objects.filter(name__iexact=name).first() or School.objects.create(
                name=name, contact_email=self.email, contact_phone=self.phone or '',
            )
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:  # the approve view saves with a restricted field list
                kwargs['update_fields'] = set(update_fields) | {'school'}

        super().save(*args, **kwargs)


    def __str__(self) -> str:
        return f"{self.email} as {self.role}"
    

    