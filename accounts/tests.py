"""
Phase 1 tests: the user model, registration, role-based redirection and the
role decorators.

The decorator tests are the important ones. Hiding a dashboard link in a
template is not authorisation -- these confirm the refusal still happens when
the URL is typed directly.
"""

from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import CompanyProfile, SeekerProfile, User

PASSWORD = "pw-for-tests-9931"


class UserModelTests(TestCase):
    def test_user_is_identified_by_email(self):
        user = User.objects.create_user(
            email="hr@example.com", password=PASSWORD, role=User.Role.COMPANY
        )
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(str(user), "hr@example.com")
        self.assertTrue(user.check_password(PASSWORD))

    def test_user_model_has_no_username_field(self):
        field_names = {f.name for f in User._meta.get_fields()}
        self.assertNotIn("username", field_names)

    def test_email_must_be_unique(self):
        User.objects.create_user(
            email="dup@example.com", password=PASSWORD, role=User.Role.COMPANY
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                email="dup@example.com", password=PASSWORD, role=User.Role.COMPANY
            )

    def test_create_user_requires_an_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=PASSWORD, role=User.Role.COMPANY)

    def test_create_superuser(self):
        admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_role_helper_properties(self):
        company = User.objects.create_user(
            email="c@example.com", password=PASSWORD, role=User.Role.COMPANY
        )
        seeker = User.objects.create_user(
            email="s@example.com", password=PASSWORD, role=User.Role.JOB_SEEKER
        )
        self.assertTrue(company.is_company)
        self.assertFalse(company.is_job_seeker)
        self.assertTrue(seeker.is_job_seeker)
        self.assertFalse(seeker.is_company)


class RegistrationTests(TestCase):
    def _register(self, role, email, **overrides):
        data = {
            "email": email,
            "display_name": "اسم للاختبار",
            "role": role,
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return self.client.post(reverse("accounts:register"), data)

    def test_company_registration_creates_a_company_profile(self):
        response = self._register(User.Role.COMPANY, "newco@example.com")
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email="newco@example.com")
        self.assertTrue(user.is_company)
        self.assertEqual(user.company_profile.name, "اسم للاختبار")
        self.assertFalse(SeekerProfile.objects.exists())

    def test_seeker_registration_creates_a_seeker_profile(self):
        response = self._register(User.Role.JOB_SEEKER, "newseeker@example.com")
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email="newseeker@example.com")
        self.assertTrue(user.is_job_seeker)
        self.assertEqual(user.seeker_profile.full_name, "اسم للاختبار")
        self.assertFalse(CompanyProfile.objects.exists())

    def test_registration_logs_the_new_user_in(self):
        self._register(User.Role.COMPANY, "autologin@example.com")
        self.assertIn("_auth_user_id", self.client.session)

    def test_registration_rejects_an_unknown_role(self):
        response = self._register("administrator", "sneaky@example.com")
        self.assertEqual(response.status_code, 200)  # redisplayed with errors
        self.assertFalse(User.objects.filter(email="sneaky@example.com").exists())

    def test_failed_registration_creates_neither_user_nor_profile(self):
        response = self._register(
            User.Role.COMPANY, "mismatch@example.com", password2="a-different-password"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="mismatch@example.com").exists())
        self.assertFalse(CompanyProfile.objects.exists())


class RoleAccessTestCase(TestCase):
    """Shared fixtures: one company account and one seeker account."""

    def setUp(self):
        self.company = User.objects.create_user(
            email="company@example.com", password=PASSWORD, role=User.Role.COMPANY
        )
        CompanyProfile.objects.create(user=self.company, name="شركة الاختبار")

        self.seeker = User.objects.create_user(
            email="seeker@example.com", password=PASSWORD, role=User.Role.JOB_SEEKER
        )
        SeekerProfile.objects.create(user=self.seeker, full_name="باحث الاختبار")


class RoleRedirectTests(RoleAccessTestCase):
    """The home view is the single place that decides where a user lands."""

    def test_anonymous_visitor_sees_the_landing_page(self):
        response = self.client.get(reverse("accounts:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/home.html")

    def test_company_is_sent_to_the_company_dashboard(self):
        self.client.force_login(self.company)
        response = self.client.get(reverse("accounts:home"))
        self.assertRedirects(response, reverse("accounts:company_dashboard"))

    def test_seeker_is_sent_to_the_seeker_dashboard(self):
        self.client.force_login(self.seeker)
        response = self.client.get(reverse("accounts:home"))
        self.assertRedirects(response, reverse("accounts:seeker_dashboard"))

    def test_login_lands_on_the_matching_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "seeker@example.com", "password": PASSWORD},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/seeker_dashboard.html")

    def test_logout_requires_post(self):
        self.client.force_login(self.company)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("accounts:logout")).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)


class RoleDecoratorTests(RoleAccessTestCase):
    def test_seeker_cannot_open_the_company_dashboard(self):
        self.client.force_login(self.seeker)
        self.assertEqual(
            self.client.get(reverse("accounts:company_dashboard")).status_code, 403
        )

    def test_company_cannot_open_the_seeker_dashboard(self):
        self.client.force_login(self.company)
        self.assertEqual(
            self.client.get(reverse("accounts:seeker_dashboard")).status_code, 403
        )

    def test_each_role_can_open_its_own_dashboard(self):
        self.client.force_login(self.company)
        self.assertEqual(
            self.client.get(reverse("accounts:company_dashboard")).status_code, 200
        )
        self.client.force_login(self.seeker)
        self.assertEqual(
            self.client.get(reverse("accounts:seeker_dashboard")).status_code, 200
        )

    def test_anonymous_user_is_redirected_to_login(self):
        for name in ("accounts:company_dashboard", "accounts:seeker_dashboard"):
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response.url)


class RtlLayoutTests(RoleAccessTestCase):
    """The interface is Arabic, so pages must declare their direction."""

    def test_pages_are_marked_right_to_left(self):
        response = self.client.get(reverse("accounts:home"))
        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, 'lang="ar"')


class TemplateHygieneTests(SimpleTestCase):
    """
    Project-wide checks over the template files themselves.

    These exist because the same bug shipped twice: Django's {# #} comment is
    matched by a regex that is not DOTALL, so a comment spanning two lines is
    never stripped and renders as visible text on the page. It is invisible in
    review and obvious to a user, which is the worst combination.
    """

    def _templates(self):
        from django.conf import settings

        root = Path(settings.BASE_DIR) / "templates"
        return sorted(root.rglob("*.html"))

    def test_no_comment_spans_more_than_one_line(self):
        offenders = []
        for path in self._templates():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "{#" in line and "#}" not in line:
                    offenders.append(f"{path.name}:{number}")

        self.assertEqual(
            offenders,
            [],
            "Multi-line {# #} comments render as visible text. "
            "Use {% comment %}...{% endcomment %} instead.",
        )

    def test_every_page_extends_the_base_template(self):
        for path in self._templates():
            if path.name == "base.html":
                continue
            with self.subTest(template=path.name):
                self.assertIn(
                    'extends "base.html"',
                    path.read_text(encoding="utf-8"),
                    f"{path.name} does not extend base.html",
                )


class DashboardStatsTestCase(TestCase):
    """Shared fixtures for the two dashboard stat suites."""

    def setUp(self):
        from applications.models import Application, Resume
        from jobs.models import Job
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.Application = Application
        self.Resume = Resume
        self.Job = Job
        self.SimpleUploadedFile = SimpleUploadedFile

        self.company = User.objects.create_user(
            email="co@example.com", password=PASSWORD, role=User.Role.COMPANY
        )
        self.company_profile = CompanyProfile.objects.create(
            user=self.company, name="سوداتل"
        )
        self.seeker = User.objects.create_user(
            email="seeker@example.com", password=PASSWORD, role=User.Role.JOB_SEEKER
        )
        self.seeker_profile = SeekerProfile.objects.create(
            user=self.seeker, full_name="محمد عثمان"
        )

    def _job(self, title="Backend Developer", status=None):
        return self.Job.objects.create(
            company=self.company_profile,
            title=title,
            description="Build services.",
            required_skills="writing Python services",
            location="الخرطوم",
            status=status or self.Job.Status.OPEN,
        )

    def _resume(self, seeker=None, active=True):
        return self.Resume.objects.create(
            seeker=seeker or self.seeker_profile,
            file=self.SimpleUploadedFile("cv.pdf", b"stub"),
            original_filename="cv.pdf",
            parse_status=self.Resume.ParseStatus.DONE,
            is_active=active,
        )

    def _application(self, job, seeker=None, stage=None, **extra):
        seeker = seeker or self.seeker_profile
        return self.Application.objects.create(
            job=job,
            seeker=seeker,
            resume=self._resume(seeker, active=False),
            stage=stage or self.Application.Stage.APPLIED,
            **extra,
        )


class CompanyDashboardTests(DashboardStatsTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.company)

    def test_headline_counts(self):
        self._job("Open One")
        self._job("Open Two")
        self._job("Hidden", status=self.Job.Status.DRAFT)

        response = self.client.get(reverse("accounts:company_dashboard"))
        self.assertEqual(response.context["total_jobs"], 3)
        self.assertEqual(response.context["open_jobs"], 2)
        self.assertEqual(response.context["total_applications"], 0)

    def test_application_counts_are_per_job(self):
        busy = self._job("Busy")
        quiet = self._job("Quiet")
        for i in range(3):
            other = SeekerProfile.objects.create(
                user=User.objects.create_user(
                    email=f"s{i}@example.com", password=PASSWORD,
                    role=User.Role.JOB_SEEKER,
                ),
                full_name=f"seeker {i}",
            )
            self._application(busy, seeker=other)

        response = self.client.get(reverse("accounts:company_dashboard"))
        counts = {job.title: job.application_count for job in response.context["jobs"]}
        self.assertEqual(counts["Busy"], 3)
        self.assertEqual(counts["Quiet"], 0)
        self.assertEqual(response.context["total_applications"], 3)

    def test_new_this_week_excludes_older_applications(self):
        from datetime import timedelta
        from django.utils import timezone

        job = self._job()
        recent = self._application(job)
        old_seeker = SeekerProfile.objects.create(
            user=User.objects.create_user(
                email="old@example.com", password=PASSWORD, role=User.Role.JOB_SEEKER
            ),
            full_name="قديم",
        )
        old = self._application(job, seeker=old_seeker)
        # auto_now_add cannot be set on create, so it is pushed back after.
        self.Application.objects.filter(pk=old.pk).update(
            applied_at=timezone.now() - timedelta(days=30)
        )

        response = self.client.get(reverse("accounts:company_dashboard"))
        self.assertEqual(response.context["total_applications"], 2)
        self.assertEqual(response.context["new_applications"], 1)

    def test_stage_counts_cover_every_stage_in_board_order(self):
        job = self._job()
        self._application(job, stage="interview")

        response = self.client.get(reverse("accounts:company_dashboard"))
        counts = response.context["stage_counts"]
        self.assertEqual(
            [c["stage"] for c in counts],
            ["applied", "screening", "interview", "offer", "hired", "rejected"],
        )
        by_stage = {c["stage"]: c["total"] for c in counts}
        self.assertEqual(by_stage["interview"], 1)
        self.assertEqual(by_stage["hired"], 0)

    def test_another_companys_jobs_are_not_counted(self):
        other = CompanyProfile.objects.create(
            user=User.objects.create_user(
                email="other@example.com", password=PASSWORD, role=User.Role.COMPANY
            ),
            name="زين",
        )
        self.Job.objects.create(
            company=other, title="Theirs", description="x",
            required_skills="y", location="الخرطوم", status=self.Job.Status.OPEN,
        )
        self._job("Mine")

        response = self.client.get(reverse("accounts:company_dashboard"))
        self.assertEqual(response.context["total_jobs"], 1)
        self.assertEqual([j.title for j in response.context["jobs"]], ["Mine"])

    def test_the_jobs_table_does_not_query_once_per_row(self):
        """
        Application counts come from one annotated query, not a count per job.

        The headline figures are a fixed handful of aggregates, so they are
        left outside the assertion; what matters is that rendering the table
        costs the same whether there are six jobs or twelve. Querysets are
        lazy, so the dict can be built first and evaluated inside the block.
        """
        from accounts import services

        for i in range(6):
            self._job(f"Job {i}")
        data = services.company_dashboard(self.company_profile)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(data["jobs"])), 6)

        for i in range(6, 12):
            self._job(f"Job {i}")
        data = services.company_dashboard(self.company_profile)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(data["jobs"])), 12)

    def test_empty_state_is_shown_with_no_jobs(self):
        response = self.client.get(reverse("accounts:company_dashboard"))
        self.assertContains(response, "لم تنشر أي وظيفة بعد")


class SeekerDashboardTests(DashboardStatsTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.seeker)

    def test_headline_counts(self):
        job_a, job_b, job_c = self._job("A"), self._job("B"), self._job("C")
        self._application(job_a, stage="applied")
        self._application(job_b, stage="interview")
        self._application(job_c, stage="rejected")

        response = self.client.get(reverse("accounts:seeker_dashboard"))
        self.assertEqual(response.context["total_applications"], 3)
        # Rejected and hired are finished, so they are not "in progress".
        self.assertEqual(response.context["active_applications"], 2)
        self.assertEqual(response.context["interview_count"], 1)

    def test_another_seekers_applications_are_not_counted(self):
        other = SeekerProfile.objects.create(
            user=User.objects.create_user(
                email="other@example.com", password=PASSWORD, role=User.Role.JOB_SEEKER
            ),
            full_name="سلمى",
        )
        self._application(self._job(), seeker=other)

        response = self.client.get(reverse("accounts:seeker_dashboard"))
        self.assertEqual(response.context["total_applications"], 0)

    def test_the_active_resume_is_surfaced(self):
        self._resume()
        response = self.client.get(reverse("accounts:seeker_dashboard"))
        self.assertIsNotNone(response.context["active_resume"])

    def test_a_failed_resume_does_not_count_as_active(self):
        resume = self._resume()
        resume.parse_status = self.Resume.ParseStatus.FAILED
        resume.save()

        response = self.client.get(reverse("accounts:seeker_dashboard"))
        self.assertIsNone(response.context["active_resume"])
        self.assertContains(response, "لا توجد سيرة ذاتية معتمدة")

    def test_saved_jobs_are_listed(self):
        from jobs.models import SavedJob

        job = self._job("Saved Role")
        SavedJob.objects.create(seeker=self.seeker_profile, job=job)

        response = self.client.get(reverse("accounts:seeker_dashboard"))
        self.assertEqual(
            [s.job.title for s in response.context["saved_jobs"]], ["Saved Role"]
        )

    def test_empty_states_are_shown(self):
        response = self.client.get(reverse("accounts:seeker_dashboard"))
        content = response.content.decode()
        self.assertIn("لم تتقدم لأي وظيفة بعد", content)
        self.assertIn("لم تحفظ أي وظيفة بعد", content)

    def test_no_recommendations_without_a_usable_resume(self):
        """A list built from no resume would rank everything at zero."""
        self._job()
        response = self.client.get(reverse("accounts:seeker_dashboard"))
        self.assertEqual(response.context["recommendations"], [])

    def test_recommendations_skip_jobs_already_applied_to(self):
        from accounts import services

        applied_to = self._job("Already Applied")
        self._application(applied_to)
        self._resume()

        # Neither job is embedded, so nothing is recommended either way; what
        # this pins is that the applied-to job is excluded from the candidates.
        recommended = services.recommended_jobs(
            self.seeker_profile, self.Resume.objects.filter(is_active=True).first()
        )
        self.assertNotIn(applied_to.pk, [job.pk for job, _ in recommended])

    def test_unembedded_jobs_are_skipped_rather_than_scored_at_zero(self):
        from matching import services as matching_services

        job = self._job()
        self.assertEqual(job.skills_embedding, "")
        resume = self._resume()
        self.assertEqual(
            matching_services.score_resume_against_jobs(resume, [job]), []
        )
