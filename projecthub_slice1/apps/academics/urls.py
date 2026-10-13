from django.urls import path

from . import views

urlpatterns = [
    path("", views.structure, name="academic_structure"),
    path("manage/", views.manage_structure, name="manage_structure"),
    path("manage/<str:kind>/<int:pk>/", views.edit_structure_item, name="edit_structure_item"),
    path("semesters/", views.semesters, name="semesters"),
]
