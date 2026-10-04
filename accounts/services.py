"""
Dashboard data.

The views stay thin: they call one function here and render the result.
Keeping the aggregation out of the template is what lets the counts be tested
without going through HTML.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from applications.models import Application, Resume
from jobs.models import Job, SavedJob


def company_dashboard(company):
    """
    Headline numbers plus the company's jobs with their application counts.

    The counts come from one annotated query rather than a count per row --
    the jobs table on this page would otherwise issue a query per job.
    """
    week_ago = timezone.now() - timedelta(days=7)

    jobs = (
        Job.objects.filter(company=company)
        .annotate(
            application_count=Count("applications", distinct=True),
            new_this_week=Count(
                "applications",
                filter=Q(applications__applied_at__gte=week_ago),
                distinct=True,
            ),
        )
        .order_by("-created_at")
    )

    applications = Application.objects.filter(job__company=company)

    return {
        "jobs": jobs,
        "total_jobs": Job.objects.filter(company=company).count(),
        "open_jobs": Job.objects.filter(company=company, status=Job.Status.OPEN).count(),
        "total_applications": applications.count(),
        "new_applications": applications.filter(applied_at__gte=week_ago).count(),
        "stage_counts": _stage_counts(applications),
    }


def _stage_counts(applications):
    """
    How many candidates sit in each stage, in board order.

    One grouped query, not one per stage.
    """
    counted = dict(
        applications.values_list("stage").annotate(total=Count("id")).values_list("stage", "total")
    )
    return [
        {
            "stage": stage,
            "label": Application.Stage(stage).label,
            "total": counted.get(stage, 0),
        }
        for stage in Application.PIPELINE_STAGES
    ]


def seeker_dashboard(seeker):
    """Everything the candidate dashboard shows, except the recommendations."""
    applications = (
        Application.objects.filter(seeker=seeker)
        .select_related("job", "job__company")
        .prefetch_related("history")
    )
    resumes = Resume.objects.filter(seeker=seeker)

    active = resumes.filter(
        is_active=True, parse_status=Resume.ParseStatus.DONE
    ).first()

    return {
        "applications": applications,
        "total_applications": applications.count(),
        "active_applications": applications.exclude(
            stage__in=[Application.Stage.REJECTED, Application.Stage.HIRED]
        ).count(),
        "interview_count": applications.filter(
            stage__in=[
                Application.Stage.INTERVIEW,
                Application.Stage.OFFER,
                Application.Stage.HIRED,
            ]
        ).count(),
        "resumes": resumes,
        "active_resume": active,
        "saved_jobs": (
            SavedJob.objects.filter(seeker=seeker)
            .select_related("job", "job__company")
        ),
    }


def recommended_jobs(seeker, active_resume, limit=10):
    """
    The best open jobs for this candidate.

    Returns an empty list when there is no usable resume: a recommendation
    list built from nothing would rank every job at zero and look like the
    matching engine was broken.
    """
    if active_resume is None:
        return []

    from matching import services as matching_services

    already_applied = set(
        Application.objects.filter(seeker=seeker).values_list("job_id", flat=True)
    )
    jobs = (
        Job.objects.filter(status=Job.Status.OPEN)
        .exclude(pk__in=already_applied)
        .select_related("company")
    )

    return matching_services.recommend_jobs(active_resume, jobs, limit=limit)
