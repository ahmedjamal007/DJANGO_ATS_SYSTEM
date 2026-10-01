from django.urls import path

from . import views

app_name = "applications"

urlpatterns = [
    # Resumes (Phase 4)
    path("resumes/", views.resume_list, name="resume_list"),
    path("resumes/upload/", views.resume_upload, name="resume_upload"),
    path("resumes/<int:pk>/activate/", views.resume_activate, name="resume_activate"),
    path("resumes/<int:pk>/delete/", views.resume_delete, name="resume_delete"),
    # Applications (Phase 5)
    path("applications/", views.my_applications, name="my_applications"),
    path("applications/<int:pk>/", views.application_detail, name="detail"),
    # Accept or reject. Answers JSON for the page's fetch() call, and
    # redirects when the form is submitted without JavaScript.
    path("applications/<int:pk>/stage/", views.stage_moved, name="stage_moved"),
    path("applications/<int:pk>/notes/", views.add_note, name="add_note"),
]
