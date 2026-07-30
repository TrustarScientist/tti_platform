# urls for the core app
from django.urls import path

from core import views


urlpatterns = [
    path('', views.index, name='index'),
]