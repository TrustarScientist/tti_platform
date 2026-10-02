# tti_platform/apps/core/urls.py
from django.urls import path

from apps.core import views


urlpatterns = [
    path('', views.index, name='index'),
    # dashboard per user type
    path('dashboard/', views.dashboard, name='dashboard'),
]