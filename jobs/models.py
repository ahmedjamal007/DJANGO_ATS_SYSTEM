"""
Job postings and the seeker's saved-job bookmarks.

The two embedding fields are declared here but stay empty until Phase 5, when
jobs are embedded on save. They are text columns holding JSON lists of floats:
SQLite has no vector type, and with job counts in the hundreds a brute-force
cosine similarity in NumPy is fast enough that it does not need one.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from accounts.models import CompanyProfile, SeekerProfile


class Job(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        OPEN = "open", "مفتوحة"
        CLOSED = "closed", "مغلقة"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "دوام كامل"
        PART_TIME = "part_time", "دوام جزئي"
        CONTRACT = "contract", "عقد مؤقت"
        INTERNSHIP = "internship", "تدريب"
        REMOTE = "remote", "عمل عن بعد"

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="jobs",
        verbose_name="الشركة",
    )
    title = models.CharField("المسمى الوظيفي", max_length=200)
    description = models.TextField("وصف الوظيفة")
    required_skills = models.TextField(
        "المهارات المطلوبة",
        help_text=(
            "مهارة واحدة في كل سطر، وتُكتب بالإنجليزية. "
            "صِف العمل نفسه لا سنوات الخبرة: عبارة مثل "
            "«building REST APIs with Django and Python» تعطي تطابقًا أدق بكثير من "
            "«Python» وحدها، بينما «3+ years of Python» تُطابق سطور المؤهلات "
            "الدراسية بدلًا من سطور الخبرة العملية."
        ),
    )
    location = models.CharField(
        "المدينة",
        max_length=200,
        help_text="مثال: الخرطوم، أم درمان، بورتسودان.",
    )
    employment_type = models.CharField(
        "نوع التوظيف",
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    salary_min = models.PositiveIntegerField(
        "أقل راتب (ج.س)", null=True, blank=True
    )
    salary_max = models.PositiveIntegerField(
        "أعلى راتب (ج.س)", null=True, blank=True
    )
    status = models.CharField(
        "الحالة",
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    # Populated in Phase 5 by the matching engine. JSON lists of floats.
    description_embedding = models.TextField(blank=True, default="")
    skills_embedding = models.TextField(blank=True, default="")

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "وظيفة"
        verbose_name_plural = "الوظائف"

    def __str__(self):
        return f"{self.title} — {self.company.name}"

    def get_absolute_url(self):
        return reverse("jobs:detail", args=[self.pk])

    def clean(self):
        """A maximum below the minimum is a data-entry slip, not a valid range."""
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValidationError(
                {"salary_max": "أعلى راتب يجب أن يكون مساويًا لأقل راتب أو أكبر منه."}
            )

    def skill_lines(self):
        """
        The required skills as a clean list, one phrase per line.

        This is the only place the field is split. Phase 5 embeds exactly this
        list, so the skills shown on the detail page and the skills that get
        scored can never drift apart.
        """
        return [line.strip() for line in self.required_skills.splitlines() if line.strip()]

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    @property
    def salary_display(self):
        """Salary range in Sudanese Pounds, or a dash when unspecified."""
        if self.salary_min is None and self.salary_max is None:
            return "غير محدد"
        if self.salary_min is not None and self.salary_max is not None:
            return f"{self.salary_min:,} – {self.salary_max:,} ج.س"
        if self.salary_min is not None:
            return f"من {self.salary_min:,} ج.س"
        return f"حتى {self.salary_max:,} ج.س"


class SavedJob(models.Model):
    """A seeker's bookmark. Listed on the seeker dashboard in Phase 7."""

    seeker = models.ForeignKey(
        SeekerProfile,
        on_delete=models.CASCADE,
        related_name="saved_jobs",
        verbose_name="الباحث عن عمل",
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="saved_by",
        verbose_name="الوظيفة",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        # One bookmark per seeker per job. Saving twice is a no-op, not a
        # second row.
        constraints = [
            models.UniqueConstraint(fields=["seeker", "job"], name="unique_saved_job")
        ]
        verbose_name = "وظيفة محفوظة"
        verbose_name_plural = "الوظائف المحفوظة"

    def __str__(self):
        return f"{self.seeker.full_name} → {self.job.title}"
