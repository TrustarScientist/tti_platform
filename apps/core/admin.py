# from django.contrib import admin

# Register your models here.
# apps/core/admin.py
from django.contrib import admin, messages

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'name', 'contact', 'child_age', 'interest', 'status')
    list_filter = ('status', 'interest')
    search_fields = ('name', 'contact', 'message')
    readonly_fields = ('created_at',)
    actions = ['mark_contacted']

    @admin.action(description="Mark selected as contacted")
    def mark_contacted(self, request, queryset):
        n = queryset.filter(status=Lead.Status.NEW).update(status=Lead.Status.CONTACTED)
        self.message_user(request, f"{n} lead(s) marked contacted.", messages.SUCCESS)