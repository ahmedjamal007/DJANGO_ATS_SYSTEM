from django.urls import path

# The pipeline and apply screens live under /jobs/<id>/ because that is where
# they belong in the URL structure, but their logic is about applications, so
# the views are imported from that app rather than duplicated here.
from applications import views as application_views

from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.job_list, name="list"),
    # The management routes come first so "manage" is never read as a job id.
    # With <int:pk> they could not collide, but the order documents the intent.
    path("manage/", views.my_jobs, name="my_jobs"),
    path("manage/new/", views.job_create, name="create"),
    path("manage/<int:pk>/edit/", views.job_update, name="update"),
    path("manage/<int:pk>/delete/", views.job_delete, name="delete"),
    path("<int:pk>/", views.job_detail, name="detail"),
    path("<int:pk>/save/", views.toggle_saved_job, name="toggle_saved"),
    path("<int:pk>/apply/", application_views.job_apply, name="apply"),
    path("<int:pk>/pipeline/", application_views.job_pipeline, name="pipeline"),
]
