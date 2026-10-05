from django.urls import path

from . import views

urlpatterns = [path("", views.structure, name="academic_structure")]
