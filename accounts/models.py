# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from .managers import UserManager

class User(AbstractUser):
    """
    Represents someone who can log into the application.
    Not every learner has a User account.
    """

    username = None

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("instructor", "Instructor"),
        ("student", "Student"),
        ("parent", "Parent"),
        ("school_partner", "School Partner"),
    ]

    ADMIN_LEVEL_CHOICES = [
        ("super", "Super Admin"),
        ("school", "School Admin"),
        ("coordinator", "Coordinator"),
    ]

    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
    )

    admin_level = models.CharField(
        max_length=20,
        choices=ADMIN_LEVEL_CHOICES,
        null=True,
        blank=True
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["role"]

    objects = UserManager()      # my custom manager

    def __str__(self):
        return f"{self.email} ({self.role})"

