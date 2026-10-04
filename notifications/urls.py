from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("poll/", views.poll, name="poll"),
    path("list/", views.notification_list, name="list"),
]
