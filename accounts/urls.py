from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    # LogoutView only accepts POST from Django 5, so the navbar uses a form.
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/company/", views.company_dashboard, name="company_dashboard"),
    path("dashboard/seeker/", views.seeker_dashboard, name="seeker_dashboard"),
]
