# tti_platform/apps/core/urls.py
from django.urls import path
from apps.people.views_reports import shared_report
from apps.core import views


urlpatterns = [
    path('', views.index, name='index'),
    # dashboard per user type
    path('dashboard/', views.dashboard, name='dashboard'),
    path('healthz/', views.healthz, name='healthz'),
    path('programs/', views.programs, name='programs'),
    # 
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    # 
    
    path('r/<str:token>/', shared_report, name='report-shared'),
]