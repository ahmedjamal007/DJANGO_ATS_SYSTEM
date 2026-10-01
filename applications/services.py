"""
Resume processing. Views stay thin and call in here.

Parsing runs inline in the request, not in a background worker. It takes
roughly three to six seconds, almost all of it embedding, and for a project
of this size that is an acceptable trade against running Celery and Redis for
one task. In production this would be queued.
"""

import json
import logging

from django.urls import reverse

from django.db import IntegrityError, transaction
from django.utils import timezone

from matching import services as matching_services
from notifications import services as notifications

from .models import Application, Resume, StageHistory
from .parsing import ResumeParseError, extract_text

logger = logging.getLogger(__name__)


@transaction.atomic
def create_resume(seeker, uploaded_file, make_active=True):
    """
    Save an uploaded resume, then parse and embed it.

    The Resume row is always saved, whether or not parsing succeeds. A failure
    is recorded on the row as `parse_status='failed'` with the reason, so the
    candidate sees what went wrong and can upload a different file -- a broken
    PDF must never return a 500.
    """
    resume = Resume.objects.create(
        seeker=seeker,
        file=uploaded_file,
        original_filename=uploaded_file.name[:255],
        parse_status=Resume.ParseStatus.PENDING,
    )

    try:
        # Read from the saved file rather than the upload handle: the upload
        # may have been streamed to a temporary file that is already consumed.
        resume.file.open("rb")
        try:
            text = extract_text(resume.file, resume.original_filename)
        finally:
            resume.file.close()

        embedded = matching_services.build_resume_embeddings(text)

        resume.parsed_text = text
        resume.doc_embedding = embedded["doc_embedding"]
        resume.chunk_embeddings = embedded["chunk_embeddings"]
        resume.parse_status = Resume.ParseStatus.DONE
        resume.parse_error = ""

    except ResumeParseError as exc:
        resume.parse_status = Resume.ParseStatus.FAILED
        resume.parse_error = str(exc)

    except Exception as exc:
        # Anything the parsing layer did not anticipate -- a corrupt archive,
        # a model loading failure. Logged in full, shown to the candidate as a
        # short message, and never allowed to reach the user as a 500.
        logger.exception("Unexpected failure while processing resume %s", resume.pk)
        resume.parse_status = Resume.ParseStatus.FAILED
        resume.parse_error = f"خطأ غير متوقع أثناء المعالجة: {exc}"

    resume.save()

    # Parsing failed silently from the candidate's point of view otherwise:
    # they would see a row marked failed only if they happened to look.
    if not resume.is_usable:
        notifications.notify(
            seeker.user,
            title="تعذّرت معالجة سيرتك الذاتية",
            body=(
                f"لم نتمكن من قراءة الملف {resume.original_filename}. "
                f"{resume.parse_error}"
            ),
            link=reverse("applications:resume_list"),
        )

    # Only a successfully parsed resume is worth making active -- an unusable
    # one would leave the seeker unable to apply with no obvious reason why.
    if make_active and resume.is_usable:
        resume.activate()

    return resume


def resumes_for(seeker):
    """A seeker's resumes, newest first."""
    return Resume.objects.filter(seeker=seeker)


def active_resume_for(seeker):
    """The resume applications will be scored against, or None."""
    return Resume.objects.filter(
        seeker=seeker, is_active=True, parse_status=Resume.ParseStatus.DONE
    ).first()


# --------------------------------------------------------------------------
# Applying
# --------------------------------------------------------------------------


class ApplicationError(Exception):
    """Raised when an application cannot be made, with a message for the user."""


@transaction.atomic
def apply_to_job(seeker, job, cover_letter=""):
    """
    Create an application, scoring the seeker's active resume against the job.

    The score is computed once, here, and stored on the row. The pipeline then
    sorts hundreds of candidates without touching the model.
    """
    from jobs.models import Job
    from jobs.services import ensure_job_embeddings
    from matching import services as matching_services

    if job.status != Job.Status.OPEN:
        raise ApplicationError("هذه الوظيفة لا تستقبل طلبات حاليًا.")

    resume = active_resume_for(seeker)
    if resume is None:
        raise ApplicationError(
            "تحتاج إلى سيرة ذاتية معتمدة ومعالجة بنجاح قبل التقديم."
        )

    # Self-healing for jobs created outside the job form.
    ensure_job_embeddings(job)

    result = matching_services.score_resume_against_job(resume, job)

    try:
        application = Application.objects.create(
            job=job,
            seeker=seeker,
            resume=resume,
            cover_letter=cover_letter,
            match_score=result["score"],
            semantic_score=result["semantic"],
            coverage_score=result["coverage"],
            skill_results=json.dumps(result["skill_results"], ensure_ascii=False),
        )
    except IntegrityError as exc:
        # The unique constraint on (job, seeker). Raised rather than checked
        # beforehand so two rapid submissions cannot both pass a check and
        # then both insert.
        raise ApplicationError("لقد تقدمت لهذه الوظيفة من قبل.") from exc

    # The opening row of the timeline, so the history is complete from the
    # moment the application exists.
    StageHistory.objects.create(
        application=application,
        from_stage="",
        to_stage=Application.Stage.APPLIED,
        changed_by=seeker.user,
        note="تم تقديم الطلب.",
    )

    notifications.notify(
        job.company.user,
        title="طلب توظيف جديد",
        body=(
            f"تقدّم {seeker.full_name} لوظيفة {job.title} "
            f"بنتيجة مطابقة {result['score']:.2f}."
        ),
        link=reverse("applications:detail", args=[application.pk]),
    )

    return application


def has_applied(seeker, job):
    return Application.objects.filter(seeker=seeker, job=job).exists()


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


def applications_for_job(job):
    """
    Every application to a job, ready for the pipeline board.

    select_related is not optional here. The board renders a card per
    candidate showing their name, and without it each card costs an extra
    query -- the view the spec warns N+1s badly.
    """
    return (
        Application.objects.filter(job=job)
        .select_related("seeker", "seeker__user", "resume")
        .order_by("-match_score", "-applied_at")
    )


def pipeline_columns(job):
    """
    Applications grouped by stage, in board order.

    Built from a single queryset in Python rather than one query per column,
    so the board costs one query no matter how many stages there are.
    """
    # `can_advance` and `next_stage_label` are read straight off the model, so
    # each card knows where "accept" would send it without the view annotating
    # anything and without another query.
    grouped = {stage: [] for stage in Application.PIPELINE_STAGES}
    for application in applications_for_job(job):
        grouped.setdefault(application.stage, []).append(application)

    return [
        {
            "stage": stage,
            "label": Application.Stage(stage).label,
            "applications": grouped.get(stage, []),
        }
        for stage in Application.PIPELINE_STAGES
    ]


@transaction.atomic
def change_stage(application, new_stage, changed_by, note=""):
    """
    Move an application to a new stage and record the move.

    Returns the StageHistory row, or None when the stage did not actually
    change -- a resubmitted form should not litter the timeline with rows
    saying a candidate moved from interview to interview.
    """
    valid = {choice for choice, _ in Application.Stage.choices}
    if new_stage not in valid:
        raise ApplicationError("مرحلة غير معروفة.")

    previous = application.stage
    if previous == new_stage:
        return None

    application.stage = new_stage
    application.save(update_fields=["stage"])

    entry = StageHistory.objects.create(
        application=application,
        from_stage=previous,
        to_stage=new_stage,
        changed_by=changed_by,
        note=note,
    )

    # Every stage move funnels through here, so this is the one place the
    # candidate has to be told. Rejection gets its own wording because it
    # is the one outcome nobody should have to decode.
    _announce_stage_change(application, previous, new_stage, note)

    return entry


# --------------------------------------------------------------------------
# Moving a candidate forward
# --------------------------------------------------------------------------



# --------------------------------------------------------------------------
# Stage progression
# --------------------------------------------------------------------------

# The forward path through the pipeline. `rejected` is deliberately absent:
# it is a terminal stage reachable from anywhere, not a step in the sequence,
# so it is triggered by its own action rather than by advancing.
def next_stage_for(stage):
    """
    The stage that follows `stage`, or None when there is nowhere to go.

    Returns None for `hired` (the end of the path) and for `rejected` (not on
    the path at all), which is what the UI uses to disable its button.
    """
    if stage not in Application.FORWARD_SEQUENCE:
        return None

    position = Application.FORWARD_SEQUENCE.index(stage)
    if position + 1 >= len(Application.FORWARD_SEQUENCE):
        return None

    return Application.FORWARD_SEQUENCE[position + 1]


def advance_stage(application, changed_by, note=""):
    """
    Move a candidate one step forward.

    The caller does not choose a destination -- picking from six options on
    every card is more work than the decision actually requires. The only
    question a recruiter is answering is "does this person go through?", so
    the stage after the current one is computed here.
    """
    target = next_stage_for(application.stage)
    if target is None:
        raise ApplicationError("لا توجد مرحلة تالية لهذا المتقدم.")

    return change_stage(application, target, changed_by, note)


def reject_application(application, changed_by, note=""):
    """
    Move a candidate to `rejected` from wherever they are.

    Separate from advancing because rejection is not a step forward; it can
    happen at screening or after an offer.
    """
    if application.stage == Application.Stage.REJECTED:
        raise ApplicationError("هذا المتقدم مرفوض بالفعل.")

    return change_stage(application, Application.Stage.REJECTED, changed_by, note)


def stage_moved(application, action, changed_by, note=""):
    """
    Apply a recruiter's decision and report where the candidate ended up.

    `action` is an intent, not a destination. "accept" means "move to whatever
    stage follows the current one", and the server works out which stage that
    is; "reject" means the terminal stage. A stage name never travels over the
    wire, so a hand-edited request cannot jump somebody from applied straight
    to hired, and the caller cannot get the sequence wrong because it never
    sees it.

    Returns the payload the pipeline's JavaScript needs to update a card in
    place: where the candidate now is, and which buttons should still work.
    """
    if action == "accept":
        entry = advance_stage(application, changed_by, note)
    elif action == "reject":
        entry = reject_application(application, changed_by, note)
    else:
        raise ApplicationError("إجراء غير معروف.")

    application.refresh_from_db()
    upcoming = next_stage_for(application.stage)

    return {
        "stage": application.stage,
        "stage_label": application.get_stage_display(),
        "can_advance": upcoming is not None,
        "next_stage_label": Application.Stage(upcoming).label if upcoming else "",
        "is_rejected": application.stage == Application.Stage.REJECTED,
        "from_stage": entry.from_stage,
        "from_label": Application.Stage(entry.from_stage).label if entry.from_stage else "",
        # localtime() first: created_at is stored in UTC, and strftime would
        # otherwise render it two hours behind every timestamp the
        # templates print through the |date filter.
        "changed_at": timezone.localtime(entry.created_at).strftime("%Y/%m/%d %H:%M"),
        "changed_by": changed_by.email if changed_by else "",
    }


def _announce_stage_change(application, previous, new_stage, note=""):
    """
    Tell the candidate their application moved, in the app and by email.

    Called from `change_stage`, which every transition passes through, so
    there is no path that quietly moves someone without telling them.

    Rejection is separated out because "your application has moved to
    rejected" is a worse way to say it than simply saying it, and because the
    spec calls for it as its own trigger.
    """
    seeker_user = application.seeker.user
    job_title = application.job.title
    company_name = application.job.company.name
    link = reverse("applications:my_applications")

    if new_stage == Application.Stage.REJECTED:
        title = "لم يتم قبول طلبك"
        body = f"نأسف لإبلاغك بأن طلبك لوظيفة {job_title} لدى {company_name} لم يُقبل."
        subject = f"تحديث بخصوص طلبك لوظيفة {job_title}"
    else:
        stage_label = Application.Stage(new_stage).label
        title = "تم تحديث حالة طلبك"
        body = f"انتقل طلبك لوظيفة {job_title} لدى {company_name} إلى مرحلة: {stage_label}."
        subject = f"طلبك لوظيفة {job_title}: {stage_label}"

    if note:
        body = f"{body}\n\nملاحظة من الشركة: {note}"

    notifications.notify(seeker_user, title=title, body=body, link=link)
    notifications.send_email(seeker_user, subject=subject, message=body)
