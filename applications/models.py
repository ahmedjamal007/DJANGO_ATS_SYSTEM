"""
The Resume model.

A resume is stored separately from any application on purpose: a candidate
uploads once and reuses the file across every job they apply to, which is how
real ATS software works and which means parsing and embedding are paid for
once per file rather than once per application.

The Application model, stage history and recruiter notes arrive in Phase 5.
"""

import json

from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property

from accounts.models import SeekerProfile


class Resume(models.Model):
    class ParseStatus(models.TextChoices):
        PENDING = "pending", "قيد المعالجة"
        DONE = "done", "تمت المعالجة"
        FAILED = "failed", "فشلت المعالجة"

    seeker = models.ForeignKey(
        SeekerProfile,
        on_delete=models.CASCADE,
        related_name="resumes",
        verbose_name="الباحث عن عمل",
    )
    file = models.FileField("الملف", upload_to="resumes/")
    original_filename = models.CharField("اسم الملف", max_length=255, blank=True)

    parsed_text = models.TextField("النص المستخرج", blank=True, default="")

    # JSON in text columns. See matching/embeddings.py for why SQLite holding
    # vectors as JSON is sufficient here.
    doc_embedding = models.TextField(blank=True, default="")
    chunk_embeddings = models.TextField(blank=True, default="")

    parse_status = models.CharField(
        "حالة المعالجة",
        max_length=10,
        choices=ParseStatus.choices,
        default=ParseStatus.PENDING,
    )
    parse_error = models.TextField("سبب الفشل", blank=True, default="")

    # Which resume is used when the seeker applies. Exactly one per seeker is
    # active; activate() enforces that.
    is_active = models.BooleanField("السيرة المعتمدة", default=False)
    uploaded_at = models.DateTimeField("تاريخ الرفع", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "سيرة ذاتية"
        verbose_name_plural = "السير الذاتية"

    def __str__(self):
        return f"{self.original_filename or self.file.name} — {self.seeker.full_name}"

    @property
    def is_usable(self):
        """Only a parsed resume can be scored, so only it can be applied with."""
        return self.parse_status == self.ParseStatus.DONE

    def activate(self):
        """
        Make this the seeker's active resume, clearing any previous one.

        Done as a single UPDATE over the other rows rather than a loop, and
        only for this seeker's resumes.
        """
        Resume.objects.filter(seeker=self.seeker).exclude(pk=self.pk).update(
            is_active=False
        )
        if not self.is_active:
            self.is_active = True
            self.save(update_fields=["is_active"])


class Application(models.Model):
    """
    One candidate's application to one job.

    The scores are computed once, when the application is created, and stored.
    They are not recalculated on every page view: a score is a record of how
    this resume compared to this job at the moment of applying, and freezing it
    means the pipeline can sort hundreds of candidates without running the
    model at all.
    """

    class Stage(models.TextChoices):
        APPLIED = "applied", "تم التقديم"
        SCREENING = "screening", "الفرز المبدئي"
        INTERVIEW = "interview", "المقابلة"
        OFFER = "offer", "عرض وظيفي"
        HIRED = "hired", "تم التوظيف"
        REJECTED = "rejected", "مرفوض"

    # Column order for the pipeline board. `rejected` is last because it is a
    # terminal stage reachable from any of the others, not a step in sequence.
    PIPELINE_STAGES = [
        Stage.APPLIED,
        Stage.SCREENING,
        Stage.INTERVIEW,
        Stage.OFFER,
        Stage.HIRED,
        Stage.REJECTED,
    ]

    # The forward path only. `rejected` is deliberately absent: it is a
    # terminal stage reachable from anywhere, not a step in the sequence, so
    # it is triggered by its own action rather than by advancing.
    FORWARD_SEQUENCE = [
        Stage.APPLIED,
        Stage.SCREENING,
        Stage.INTERVIEW,
        Stage.OFFER,
        Stage.HIRED,
    ]

    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name="الوظيفة",
    )
    seeker = models.ForeignKey(
        SeekerProfile,
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name="المتقدم",
    )
    # PROTECT, not CASCADE: deleting a resume must not silently erase the
    # applications made with it, and the recruiter still needs the evidence.
    resume = models.ForeignKey(
        Resume,
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name="السيرة الذاتية",
    )

    stage = models.CharField(
        "المرحلة", max_length=20, choices=Stage.choices, default=Stage.APPLIED
    )

    match_score = models.FloatField("النتيجة النهائية", default=0.0)
    semantic_score = models.FloatField("التشابه العام", default=0.0)
    coverage_score = models.FloatField("تغطية المهارات", default=0.0)

    # JSON list of {"skill", "similarity", "matched", "evidence"}. This is what
    # makes the score defensible rather than opaque, so it is stored with the
    # application rather than recomputed.
    skill_results = models.TextField(blank=True, default="")

    cover_letter = models.TextField("رسالة التقديم", blank=True)
    applied_at = models.DateTimeField("تاريخ التقديم", auto_now_add=True)

    class Meta:
        ordering = ["-match_score", "-applied_at"]
        constraints = [
            # A candidate applies to a job once. The apply view catches the
            # IntegrityError this raises and shows a readable message.
            models.UniqueConstraint(fields=["job", "seeker"], name="unique_application")
        ]
        verbose_name = "طلب توظيف"
        verbose_name_plural = "طلبات التوظيف"

    def __str__(self):
        return f"{self.seeker.full_name} → {self.job.title}"

    def get_absolute_url(self):
        return reverse("applications:detail", args=[self.pk])

    @cached_property
    def skill_breakdown(self):
        """
        The per-skill results, parsed once.

        Cached because the pipeline card reads the matched count and the total
        for every application on the page; parsing the JSON three times per
        card would be wasted work.
        """
        if not self.skill_results:
            return []
        try:
            return json.loads(self.skill_results)
        except json.JSONDecodeError:
            return []

    @property
    def matched_skill_count(self):
        return sum(1 for entry in self.skill_breakdown if entry.get("matched"))

    @property
    def total_skill_count(self):
        return len(self.skill_breakdown)

    @property
    def next_stage(self):
        """
        The stage that follows this one, or None when there is nowhere to go.

        None for `hired` (end of the path) and for `rejected` (not on the path
        at all). The template uses this to decide whether to draw an accept
        button at all.
        """
        if self.stage not in self.FORWARD_SEQUENCE:
            return None
        position = self.FORWARD_SEQUENCE.index(self.stage)
        if position + 1 >= len(self.FORWARD_SEQUENCE):
            return None
        return self.FORWARD_SEQUENCE[position + 1]

    @property
    def can_advance(self):
        return self.next_stage is not None

    @property
    def next_stage_label(self):
        upcoming = self.next_stage
        return self.Stage(upcoming).label if upcoming else ""

    @property
    def is_rejected(self):
        return self.stage == self.Stage.REJECTED

    @property
    def score_percent(self):
        """The final score as a whole number, for display."""
        return round(self.match_score * 100)


class StageHistory(models.Model):
    """
    One recorded move through the pipeline.

    Kept alongside `Application.stage` rather than derived from it: the stage
    field is where the candidate is now, this table is how they got there.
    Both dashboards render their timeline from these rows.
    """

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="الطلب",
    )
    # Blank on the first row, which records the application being created.
    from_stage = models.CharField(
        "من مرحلة", max_length=20, choices=Application.Stage.choices, blank=True
    )
    to_stage = models.CharField(
        "إلى مرحلة", max_length=20, choices=Application.Stage.choices
    )
    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stage_changes",
        verbose_name="بواسطة",
    )
    note = models.TextField("ملاحظة", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "سجل المراحل"
        verbose_name_plural = "سجل المراحل"

    def __str__(self):
        return f"{self.application_id}: {self.from_stage or '—'} → {self.to_stage}"


class RecruiterNote(models.Model):
    """A comment left on a candidate by the hiring company."""

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name="الطلب",
    )
    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="recruiter_notes",
        verbose_name="الكاتب",
    )
    body = models.TextField("الملاحظة")
    rating = models.PositiveSmallIntegerField(
        "التقييم",
        null=True,
        blank=True,
        choices=[(n, str(n)) for n in range(1, 6)],
        help_text="اختياري، من 1 إلى 5.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ملاحظة"
        verbose_name_plural = "الملاحظات"

    def __str__(self):
        return f"ملاحظة على {self.application_id}"
