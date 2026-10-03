# apps/people/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('add/', views.StudentCreateView.as_view(), name='student-add'),
    path('<int:pk>/invite/', views.GenerateClaimCodeView.as_view(), name='student-generate-claim'),
    # enrolment scope
    path('<int:pk>/enroll/', views.EnrollTrackView.as_view(), name='student-enroll'),
    path('<int:pk>/enroll/<int:track_id>/', views.EnrollDeliveryView.as_view(), name='student-enroll-delivery'),
    path('learn/<int:enrollment_id>/', views.LessonView.as_view(), name='student-lesson'),
    path('learn/<int:enrollment_id>/complete/', views.MarkLessonCompleteView.as_view(), name='student-lesson-complete'),
    # TRS related
    path('learn/<int:enrollment_id>/assess/<int:assessment_id>/', views.SubmitAssessmentView.as_view(), name='student-submit-assessment'),
    path('<int:pk>/trs/', views.TRSProfileView.as_view(), name='student-trs-profile'),
    # lesson resume
    path('learn/<int:enrollment_id>/resume/', views.ResumeEnrollmentView.as_view(), name='student-resume-enrollment'),
]