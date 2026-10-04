"""
Custom user model and the two profile models.

The user model is defined before the first migration on purpose. Django wires
AUTH_USER_MODEL into every foreign key at migration time, so swapping the user
model later means deleting the database and starting again.

Code comments are English; every string a user can see is Arabic.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """
    Manager for a user model with no username field.

    Django's default manager signature is create_user(username, email,
    password). Because we removed `username` entirely, we need our own manager
    that takes the email as the identifying argument.
    """

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        # A superuser administers /admin, it is not a participant in the job
        # board, but `role` is non-nullable so it needs some value.
        extra_fields.setdefault("role", User.Role.COMPANY)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Account identified by email address, with exactly one immutable role.

    `username` is removed rather than left unused: AbstractUser declares it as
    required and unique, which would mean carrying a second unique column that
    nothing reads and every registration has to invent a value for.
    """

    class Role(models.TextChoices):
        COMPANY = "company", "شركة"
        JOB_SEEKER = "job_seeker", "باحث عن عمل"

    username = None
    email = models.EmailField("البريد الإلكتروني", unique=True)
    role = models.CharField(
        "نوع الحساب",
        max_length=20,
        choices=Role.choices,
        help_text="يُحدَّد عند إنشاء الحساب ولا يمكن تغييره بعد ذلك.",
    )

    USERNAME_FIELD = "email"
    # Fields prompted for by createsuperuser on top of USERNAME_FIELD and
    # password. Email is already the username field, so this stays empty.
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["email"]
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        return self.email

    @property
    def is_company(self):
        return self.role == self.Role.COMPANY

    @property
    def is_job_seeker(self):
        return self.role == self.Role.JOB_SEEKER


class CompanyProfile(models.Model):
    """Employer-side details. Created at registration for every company user."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="company_profile",
        verbose_name="المستخدم",
    )
    name = models.CharField("اسم الشركة", max_length=200)
    description = models.TextField("نبذة عن الشركة", blank=True)
    website = models.URLField("الموقع الإلكتروني", blank=True)
    location = models.CharField(
        "المدينة",
        max_length=200,
        blank=True,
        help_text="مثال: الخرطوم، أم درمان، بورتسودان.",
    )
    logo = models.ImageField("الشعار", upload_to="company_logos/", blank=True, null=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "ملف شركة"
        verbose_name_plural = "ملفات الشركات"

    def __str__(self):
        return self.name


class SeekerProfile(models.Model):
    """Candidate-side details. Created at registration for every seeker user."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="seeker_profile",
        verbose_name="المستخدم",
    )
    full_name = models.CharField("الاسم الكامل", max_length=200)
    phone = models.CharField(
        "رقم الهاتف",
        max_length=40,
        blank=True,
        help_text="مثال: ‎+249 91 234 5678",
    )
    location = models.CharField(
        "المدينة",
        max_length=200,
        blank=True,
        help_text="مثال: الخرطوم، أم درمان، بورتسودان.",
    )
    headline = models.CharField(
        "نبذة مختصرة",
        max_length=200,
        blank=True,
        help_text="سطر واحد يصفك، مثال: خريج علوم حاسوب مهتم بتطوير الواجهات الخلفية.",
    )

    class Meta:
        ordering = ["full_name"]
        verbose_name = "ملف باحث عن عمل"
        verbose_name_plural = "ملفات الباحثين عن عمل"

    def __str__(self):
        return self.full_name
