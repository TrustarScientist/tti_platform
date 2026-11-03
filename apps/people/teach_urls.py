# apps/people/teach_urls.py
from django.urls import path
from . import views_teach as v
from . import views_reports as r

urlpatterns = [
    path('', v.TeachHomeView.as_view(), name='teach-home'),
    path('cohorts/<int:pk>/', v.CohortConsoleView.as_view(), name='teach-cohort'),
    path('cohorts/<int:pk>/advance/', v.AdvanceCohortView.as_view(), name='teach-cohort-advance'),
    path('attempts/<int:pk>/review/', v.ReviewAttemptView.as_view(), name='teach-attempt-review'),
    # 
    path('cohorts/<int:pk>/attendance/', v.AttendanceView.as_view(), name='teach-attendance'),
    # 
    path('cohorts/<int:pk>/reports/', r.CohortReportsView.as_view(), name='teach-reports'),
    path('cohorts/<int:pk>/reports/generate/', r.GenerateReportsView.as_view(), name='teach-reports-generate'),
    path('cohorts/<int:pk>/reports/publish-all/', r.PublishAllReportsView.as_view(), name='teach-reports-publish-all'),
    path('reports/<int:report_id>/save/', r.ReportEditView.as_view(), name='teach-report-save'),
    path('one-on-one/<int:enrollment_id>/', r.OneOnOneView.as_view(), name='teach-enrollment'),
]