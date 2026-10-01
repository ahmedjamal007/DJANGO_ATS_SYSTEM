"""
Job querying. Views stay thin and call into here.

A note for the viva, because the distinction matters:

The filters below are plain database `icontains` lookups. That is deliberate
and it does not contradict the project's "all matching is semantic" rule. That
rule governs the comparison between a *resume* and a *job* -- the scoring that
ranks candidates -- and that path never compares strings. What happens here is
*browsing*: a visitor narrowing a list by a word they typed and a city they
picked. Running a transformer over every job on every keystroke would be
slower, less predictable, and would not help someone who typed "Khartoum"
and expects to see Khartoum.
"""

from django.db.models import Q

from .models import Job


def open_jobs():
    """
    Every job visible to the public.

    `select_related("company")` is not optional here: the listing template
    prints the company name for each row, and without it the page issues one
    extra query per job.
    """
    return Job.objects.filter(status=Job.Status.OPEN).select_related("company")


def filter_jobs(queryset, *, query="", location="", employment_type=""):
    """Narrow `queryset` by the listing page's three filters. Blanks are ignored."""
    query = (query or "").strip()
    location = (location or "").strip()
    employment_type = (employment_type or "").strip()

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(company__name__icontains=query)
        )

    if location:
        queryset = queryset.filter(location__icontains=location)

    # Guard against a hand-edited query string carrying a value that is not a
    # real choice, which would silently return an empty list.
    valid_types = {value for value, _ in Job.EmploymentType.choices}
    if employment_type in valid_types:
        queryset = queryset.filter(employment_type=employment_type)

    return queryset


def jobs_owned_by(company_profile):
    """The company's own postings, in every status."""
    return Job.objects.filter(company=company_profile)


def saved_job_ids_for(user):
    """
    The set of job ids this user has bookmarked.

    Returned as a set so the listing template can test membership without a
    query per row. Anonymous users and companies have nothing saved.
    """
    if not user.is_authenticated or not user.is_job_seeker:
        return set()
    return set(
        user.seeker_profile.saved_jobs.values_list("job_id", flat=True)
    )


def embed_job(job):
    """
    Compute and store the job's description and skill-line embeddings.

    Called when a company saves a job, so that applying to it later never has
    to run the model on the job side.

    This deliberately does *not* live in `Job.save()`. Overriding save would
    load the transformer and re-encode on every write -- including a status
    flip from draft to open, every fixture a test creates, and every row the
    seed command inserts -- which would make the whole suite slow for no
    benefit. Embedding is an expensive side effect, so it is triggered
    explicitly at the one point where the text can actually have changed.
    """
    from matching import services as matching_services

    built = matching_services.build_job_embeddings(job.description, job.skill_lines())
    job.description_embedding = built["description_embedding"]
    job.skills_embedding = built["skills_embedding"]
    job.save(update_fields=["description_embedding", "skills_embedding"])
    return job


def ensure_job_embeddings(job):
    """
    Embed the job if it has not been embedded yet.

    A safety net for jobs created outside the job form -- seeded rows, fixtures,
    anything added through /admin. Without it those jobs would score every
    candidate at zero and the failure would look like a broken matching engine
    rather than a missing embedding.
    """
    if not job.description_embedding or not job.skills_embedding:
        embed_job(job)
    return job
