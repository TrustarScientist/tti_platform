# apps/people/teach_urls.py
from django.urls import path
from . import views_teach as v

urlpatterns = [
    path('', v.TeachHomeView.as_view(), name='teach-home'),
    path('cohorts/<int:pk>/', v.CohortConsoleView.as_view(), name='teach-cohort'),
    path('cohorts/<int:pk>/advance/', v.AdvanceCohortView.as_view(), name='teach-cohort-advance'),
    path('attempts/<int:pk>/review/', v.ReviewAttemptView.as_view(), name='teach-attempt-review'),
]