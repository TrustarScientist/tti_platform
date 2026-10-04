# apps/accounts/urls.py — replace the whole file
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

from .forms import EmailOrPhoneAuthenticationForm
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('signup/', views.RegisterView.as_view(), name='signup'),
    path('login/', auth_views.LoginView.as_view(
        template_name='auth/login.html',
        authentication_form=EmailOrPhoneAuthenticationForm,
        redirect_authenticated_user=True,
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('partners/<int:pk>/approve/', views.ApprovePartnerView.as_view(), name='partner-approve'),
    path('partners/<int:pk>/decline/', views.DeclinePartnerView.as_view(), name='partner-decline'),


    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='auth/password_reset_form.html',
        email_template_name='auth/password_reset_email.txt',
        subject_template_name='auth/password_reset_subject.txt',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='auth/password_reset_complete.html'
    ), name='password_reset_complete'),
    # 
    path('debug-email-settings/', views.debug_email_settings, name='debug-email-settings'),
]