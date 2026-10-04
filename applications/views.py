"""
Resume management for the job seeker.

Every view is scoped to `request.user.seeker_profile`, so one candidate can
never reach another's resume by guessing an id.
"""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import company_required, seeker_required
from jobs.models import Job

from . import services
from .forms import ApplyForm, RecruiterNoteForm, ResumeUploadForm
from .models import Application, Resume


@seeker_required
def resume_list(request):
    seeker = request.user.seeker_profile
    return render(
        request,
        "applications/resume_list.html",
        {
            "resumes": services.resumes_for(seeker),
            "form": ResumeUploadForm(),
            "active_resume": services.active_resume_for(seeker),
        },
    )


@seeker_required
def resume_upload(request):
    """
    Handle the upload, parse it inline, then redirect.

    The parse takes a few seconds. The template disables the submit button and
    shows a waiting message so the candidate does not submit twice.
    """
    seeker = request.user.seeker_profile

    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resume = services.create_resume(seeker, form.cleaned_data["file"])

            if resume.is_usable:
                messages.success(request, "تم رفع السيرة الذاتية ومعالجتها بنجاح.")
            else:
                messages.warning(
                    request,
                    f"تم رفع الملف لكن تعذّرت معالجته: {resume.parse_error}",
                )
            return redirect("applications:resume_list")
    else:
        form = ResumeUploadForm()

    return render(
        request,
        "applications/resume_list.html",
        {
            "resumes": services.resumes_for(seeker),
            "form": form,
            "active_resume": services.active_resume_for(seeker),
        },
    )


@require_POST
@seeker_required
def resume_activate(request, pk):
    resume = get_object_or_404(Resume, pk=pk, seeker=request.user.seeker_profile)

    if not resume.is_usable:
        messages.error(request, "لا يمكن اعتماد سيرة لم تتم معالجتها بنجاح.")
    else:
        resume.activate()
        messages.success(request, "تم اعتماد هذه السيرة الذاتية.")

    return redirect("applications:resume_list")


@require_POST
@seeker_required
def resume_delete(request, pk):
    resume = get_object_or_404(Resume, pk=pk, seeker=request.user.seeker_profile)
    resume.delete()
    messages.success(request, "تم حذف السيرة الذاتية.")
    return redirect("applications:resume_list")


# --------------------------------------------------------------------------
# Applying (job seeker)
# --------------------------------------------------------------------------


@seeker_required
def job_apply(request, pk):
    """
    Apply to an open job with the seeker's active resume.

    The score is computed inside `apply_to_job`, which takes a few seconds
    only if the job still needs embedding; normally the vectors already exist
    on both sides and the comparison is pure arithmetic.
    """
    job = get_object_or_404(Job.objects.select_related("company"), pk=pk)
    seeker = request.user.seeker_profile

    if services.has_applied(seeker, job):
        messages.info(request, "لقد تقدمت لهذه الوظيفة من قبل.")
        return redirect(job.get_absolute_url())

    if request.method == "POST":
        form = ApplyForm(request.POST)
        if form.is_valid():
            try:
                services.apply_to_job(seeker, job, form.cleaned_data["cover_letter"])
            except services.ApplicationError as exc:
                messages.error(request, str(exc))
                return redirect(job.get_absolute_url())

            messages.success(request, "تم إرسال طلبك بنجاح.")
            return redirect("applications:my_applications")
    else:
        form = ApplyForm()

    return render(
        request,
        "applications/apply.html",
        {
            "job": job,
            "form": form,
            "active_resume": services.active_resume_for(seeker),
        },
    )


@seeker_required
def my_applications(request):
    """The seeker's own applications, with their current stage."""
    applications = (
        Application.objects.filter(seeker=request.user.seeker_profile)
        .select_related("job", "job__company")
        .prefetch_related("history")
    )
    return render(
        request, "applications/my_applications.html", {"applications": applications}
    )


# --------------------------------------------------------------------------
# Pipeline and candidate review (company)
# --------------------------------------------------------------------------


def _company_application(request, pk):
    """
    Fetch an application, but only if it belongs to one of this company's jobs.

    Filtering in the query rather than fetching and comparing afterwards means
    another company's candidate is simply not found.
    """
    return get_object_or_404(
        Application.objects.select_related(
            "job", "job__company", "seeker", "seeker__user", "resume"
        ),
        pk=pk,
        job__company=request.user.company_profile,
    )


@company_required
def job_pipeline(request, pk):
    job = get_object_or_404(
        Job.objects.select_related("company"),
        pk=pk,
        company=request.user.company_profile,
    )
    columns = services.pipeline_columns(job)

    return render(
        request,
        "applications/pipeline.html",
        {
            "job": job,
            "columns": columns,
            "total": sum(len(column["applications"]) for column in columns),
        },
    )


@company_required
def application_detail(request, pk):
    """
    The candidate review screen.

    The per-skill evidence table rendered here is what turns an opaque number
    into something a recruiter can act on and a viva can defend.
    """
    application = _company_application(request, pk)

    # Where "accept" would send this candidate is read off the model, so the
    # template needs no stage logic and the view stays a fetch-and-render.
    return render(
        request,
        "applications/detail.html",
        {
            "application": application,
            "skill_results": application.skill_breakdown,
            "history": application.history.select_related("changed_by"),
            "notes": application.notes.select_related("author"),
            "note_form": RecruiterNoteForm(),
        },
    )


@require_POST
@company_required
def add_note(request, pk):
    application = _company_application(request, pk)
    form = RecruiterNoteForm(request.POST)

    if form.is_valid():
        note = form.save(commit=False)
        note.application = application
        note.author = request.user
        note.save()
        messages.success(request, "تمت إضافة الملاحظة.")
    else:
        messages.error(request, "لا يمكن حفظ ملاحظة فارغة.")

    return redirect(application.get_absolute_url())


def _wants_json(request):
    """
    True when the caller is the page's JavaScript rather than a browser
    navigation.

    Checked so one view can serve both: the fetch() call gets JSON, and a
    form submitted with JavaScript disabled still gets a redirect. Keeping
    them in one view means the permission and ownership rules cannot drift
    apart between an AJAX path and a non-AJAX one.
    """
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )


@require_POST
@company_required
def stage_moved(request, pk):
    """
    Accept or reject a candidate. The server decides which stage that means.

    The client sends only an intent -- "accept" or "reject" -- and never a
    stage name, so a hand-edited request cannot jump someone straight from
    applied to hired.
    """
    application = _company_application(request, pk)
    action = request.POST.get("action", "")
    note = request.POST.get("note", "")[:500]

    try:
        result = services.stage_moved(
            application, action, changed_by=request.user, note=note
        )
    except services.ApplicationError as exc:
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect(application.get_absolute_url())

    if _wants_json(request):
        return JsonResponse({"ok": True, "application_id": application.pk, **result})

    messages.success(request, f"تم نقل المتقدم إلى: {result['stage_label']}")
    return redirect(application.get_absolute_url())
