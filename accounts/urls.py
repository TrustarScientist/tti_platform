# accounts/urls.py
# I'm  using Django's built-in authentication views, LoginView, LogoutView, PasswordChangeView, etc., 
# which are included in django.contrib.auth.urls.
from django.urls import path, include
from django.contrib.auth import views as auth_views

from .views import SignupView 

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path(
    "signup/",
    SignupView.as_view(),
    name="signup",
),

]