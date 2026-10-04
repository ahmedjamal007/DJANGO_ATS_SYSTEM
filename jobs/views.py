"""
Job views: a public listing and detail page, plus company-only CRUD.

Ownership is checked on every company view. `get_object_or_404` is filtered by
the logged-in company rather than fetching by primary key and comparing
afterwards, so another company's job is simply not found.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import company_required, seeker_required

from . import services
from .forms import JobFilterForm, JobForm
from .models import Job, SavedJob


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------


def job_list(request):
    """Open jobs, narrowed by the filter form."""
    form = JobFilterForm(request.GET or None)

    jobs = services.open_jobs()
    if form.is_valid():
        jobs = services.filter_jobs(
            jobs,
            query=form.cleaned_data["q"],
            location=form.cleaned_data["location"],
            employment_type=form.cleaned_data["employment_type"],
        )

    return render(
        request,
        "jobs/job_list.html",
        {
            "form": form,
            "jobs": jobs,
            "saved_job_ids": services.saved_job_ids_for(request.user),
        },
    )


def job_detail(request, pk):
    """
    A job page.

    Open jobs are public. A draft or closed job is visible only to the company
    that owns it, so a company can preview a posting before opening it.
    """
    job = get_object_or_404(Job.objects.select_related("company"), pk=pk)

    if not job.is_open:
        user = request.user
        owns_it = (
            user.is_authenticated
            and user.is_company
            and job.company_id == user.company_profile.pk
        )
        if not owns_it:
            raise Http404("هذه الوظيفة غير متاحة.")

    return render(
        request,
        "jobs/job_detail.html",
        {
            "job": job,
            "skills": job.skill_lines(),
            "is_saved": job.pk in services.saved_job_ids_for(request.user),
        },
    )


# --------------------------------------------------------------------------
# Company CRUD
# --------------------------------------------------------------------------


@company_required
def my_jobs(request):
    jobs = services.jobs_owned_by(request.user.company_profile).select_related("company")
    return render(request, "jobs/my_jobs.html", {"jobs": jobs})


@company_required
def job_create(request):
    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            # Taken from the session, never from the submitted data.
            job.company = request.user.company_profile
            job.save()
            # Embedding happens here rather than in Job.save(); see the note on
            # embed_job for why.
            services.embed_job(job)
            messages.success(request, "تم حفظ الوظيفة.")
            return redirect("jobs:my_jobs")
    else:
        form = JobForm()

    return render(request, "jobs/job_form.html", {"form": form, "job": None})


@company_required
def job_update(request, pk):
    job = get_object_or_404(Job, pk=pk, company=request.user.company_profile)

    if request.method == "POST":
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            job = form.save()
            # The description or the skill lines may have changed, so the
            # stored vectors are stale until they are rebuilt.
            services.embed_job(job)
            messages.success(request, "تم تحديث الوظيفة.")
            return redirect("jobs:my_jobs")
    else:
        form = JobForm(instance=job)

    return render(request, "jobs/job_form.html", {"form": form, "job": job})


@company_required
def job_delete(request, pk):
    job = get_object_or_404(Job, pk=pk, company=request.user.company_profile)

    if request.method == "POST":
        job.delete()
        messages.success(request, "تم حذف الوظيفة.")
        return redirect("jobs:my_jobs")

    return render(request, "jobs/job_confirm_delete.html", {"job": job})


# --------------------------------------------------------------------------
# Seeker bookmarks
# --------------------------------------------------------------------------


@require_POST
@seeker_required
def toggle_saved_job(request, pk):
    """Save or unsave a job. POST only -- it changes stored state."""
    job = get_object_or_404(Job, pk=pk, status=Job.Status.OPEN)
    seeker = request.user.seeker_profile

    saved, created = SavedJob.objects.get_or_create(seeker=seeker, job=job)
    if created:
        messages.success(request, "تمت إضافة الوظيفة إلى المحفوظات.")
    else:
        saved.delete()
        messages.success(request, "تمت إزالة الوظيفة من المحفوظات.")

    # `next` comes from the request, so it is validated before being used as a
    # redirect target. Without this check a crafted form could bounce the user
    # to an external site that looks like this one.
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect(job.get_absolute_url())
