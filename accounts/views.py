"""
Account views plus the two dashboards.

The dashboards live here rather than in an app of their own: they are two
pages that read profile data, and a `dashboards` app would hold nothing else.
"""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from . import services
from .decorators import company_required, seeker_required
from .forms import RegistrationForm


def dashboard_url_for(user):
    """Return the URL name of the dashboard belonging to `user`'s role."""
    if user.is_company:
        return "accounts:company_dashboard"
    return "accounts:seeker_dashboard"


def home(request):
    """
    Landing page, and the single place role-based redirection happens.

    LOGIN_REDIRECT_URL points here, so signing in, registering and logging out
    all pass through this one view instead of each deciding where to go.
    """
    if request.user.is_authenticated:
        return redirect(dashboard_url_for(request.user))
    return render(request, "accounts/home.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "تم إنشاء حسابك بنجاح. أهلًا بك.")
            return redirect("accounts:home")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


@company_required
def company_dashboard(request):
    profile = request.user.company_profile
    context = services.company_dashboard(profile)
    context["profile"] = profile
    return render(request, "accounts/company_dashboard.html", context)


@seeker_required
def seeker_dashboard(request):
    profile = request.user.seeker_profile
    context = services.seeker_dashboard(profile)
    context["profile"] = profile
    # Scoring happens here rather than in the service so the recommendation
    # list is the only part of the page that touches the matching engine.
    context["recommendations"] = services.recommended_jobs(
        profile, context["active_resume"]
    )
    return render(request, "accounts/seeker_dashboard.html", context)
