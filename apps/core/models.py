# from django.db import models

# Create your models here.
# apps/core/models.py
from django.db import models


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = 'NEW', 'New'
        CONTACTED = 'CONTACTED', 'Contacted'
        CLOSED = 'CLOSED', 'Closed'

    name = models.CharField(max_length=120)
    contact = models.CharField(max_length=120, help_text="Phone number or email.")
    child_age = models.PositiveSmallIntegerField(null=True, blank=True)
    interest = models.CharField(max_length=100, blank=True)
    message = models.TextField(max_length=1000, blank=True)
    source = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    notes = models.TextField(blank=True, help_text="Internal notes. Never shown publicly.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.contact})"