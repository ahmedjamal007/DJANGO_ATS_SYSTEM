"""
Phase 2 tests: the Job model, the listing filters, company ownership rules and
seeker bookmarks.

The ownership tests matter most. A company must not be able to reach, edit or
delete another company's posting by typing its URL.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import CompanyProfile, SeekerProfile, User

from .models import Job, SavedJob
from . import services

PASSWORD = "pw-for-tests-9931"


def make_company(email, name):
    user = User.objects.create_user(email=email, password=PASSWORD, role=User.Role.COMPANY)
    return CompanyProfile.objects.create(user=user, name=name)


def make_seeker(email, name):
    user = User.objects.create_user(email=email, password=PASSWORD, role=User.Role.JOB_SEEKER)
    return SeekerProfile.objects.create(user=user, full_name=name)


def make_job(company, **overrides):
    data = {
        "company": company,
        "title": "Backend Developer",
        "description": "Build and maintain Django services.",
        "required_skills": "3+ years of Python\nDjango ORM and migrations",
        "location": "الخرطوم",
        "employment_type": Job.EmploymentType.FULL_TIME,
        "status": Job.Status.OPEN,
    }
    data.update(overrides)
    return Job.objects.create(**data)


class JobModelTests(TestCase):
    def setUp(self):
        self.company = make_company("co@example.com", "سوداتل")

    def test_str_includes_title_and_company(self):
        job = make_job(self.company)
        self.assertIn("Backend Developer", str(job))
        self.assertIn("سوداتل", str(job))

    def test_skill_lines_splits_and_strips(self):
        job = make_job(
            self.company,
            required_skills="  3+ years of React  \n\n   \nREST API design\n",
        )
        self.assertEqual(job.skill_lines(), ["3+ years of React", "REST API design"])

    def test_embedding_fields_start_empty(self):
        """Jobs are embedded in Phase 5, not on creation."""
        job = make_job(self.company)
        self.assertEqual(job.description_embedding, "")
        self.assertEqual(job.skills_embedding, "")

    def test_salary_display_covers_every_combination(self):
        cases = [
            ({"salary_min": None, "salary_max": None}, "غير محدد"),
            ({"salary_min": 500000, "salary_max": 900000}, "500,000 – 900,000 ج.س"),
            ({"salary_min": 500000, "salary_max": None}, "من 500,000 ج.س"),
            ({"salary_min": None, "salary_max": 900000}, "حتى 900,000 ج.س"),
        ]
        for fields, expected in cases:
            with self.subTest(**fields):
                job = make_job(self.company, **fields)
                self.assertEqual(job.salary_display, expected)

    def test_salary_max_below_min_is_invalid(self):
        job = make_job(self.company, salary_min=900000, salary_max=500000)
        with self.assertRaises(ValidationError):
            job.full_clean()

    def test_default_ordering_is_newest_first(self):
        old = make_job(self.company, title="Older")
        new = make_job(self.company, title="Newer")
        self.assertEqual(list(Job.objects.all()), [new, old])


class JobListingTests(TestCase):
    def setUp(self):
        self.sudatel = make_company("co1@example.com", "سوداتل")
        self.zain = make_company("co2@example.com", "زين")

        self.open_job = make_job(
            self.sudatel, title="Backend Developer", location="الخرطوم"
        )
        self.remote_job = make_job(
            self.zain,
            title="Frontend Engineer",
            location="بورتسودان",
            employment_type=Job.EmploymentType.REMOTE,
        )
        self.draft_job = make_job(
            self.sudatel, title="Secret Role", status=Job.Status.DRAFT
        )
        self.closed_job = make_job(
            self.sudatel, title="Filled Role", status=Job.Status.CLOSED
        )

    def test_listing_shows_only_open_jobs(self):
        response = self.client.get(reverse("jobs:list"))
        self.assertEqual(response.status_code, 200)
        listed = list(response.context["jobs"])
        self.assertIn(self.open_job, listed)
        self.assertIn(self.remote_job, listed)
        self.assertNotIn(self.draft_job, listed)
        self.assertNotIn(self.closed_job, listed)

    def test_filter_by_title_text(self):
        response = self.client.get(reverse("jobs:list"), {"q": "Frontend"})
        self.assertEqual(list(response.context["jobs"]), [self.remote_job])

    def test_filter_by_company_name(self):
        response = self.client.get(reverse("jobs:list"), {"q": "زين"})
        self.assertEqual(list(response.context["jobs"]), [self.remote_job])

    def test_filter_by_location(self):
        response = self.client.get(reverse("jobs:list"), {"location": "بورتسودان"})
        self.assertEqual(list(response.context["jobs"]), [self.remote_job])

    def test_filter_by_employment_type(self):
        response = self.client.get(reverse("jobs:list"), {"employment_type": "remote"})
        self.assertEqual(list(response.context["jobs"]), [self.remote_job])

    def test_unknown_employment_type_is_ignored_not_applied(self):
        """A hand-edited query string must not silently empty the listing."""
        filtered = services.filter_jobs(services.open_jobs(), employment_type="nonsense")
        self.assertEqual(filtered.count(), 2)

    def test_filters_combine(self):
        response = self.client.get(
            reverse("jobs:list"), {"q": "Developer", "location": "الخرطوم"}
        )
        self.assertEqual(list(response.context["jobs"]), [self.open_job])


class JobDetailVisibilityTests(TestCase):
    def setUp(self):
        self.owner = make_company("owner@example.com", "سوداتل")
        self.other = make_company("other@example.com", "زين")
        self.draft = make_job(self.owner, status=Job.Status.DRAFT)
        self.open_job = make_job(self.owner, status=Job.Status.OPEN)

    def test_open_job_is_public(self):
        self.assertEqual(
            self.client.get(reverse("jobs:detail", args=[self.open_job.pk])).status_code, 200
        )

    def test_draft_job_is_hidden_from_the_public(self):
        self.assertEqual(
            self.client.get(reverse("jobs:detail", args=[self.draft.pk])).status_code, 404
        )

    def test_draft_job_is_hidden_from_another_company(self):
        self.client.force_login(self.other.user)
        self.assertEqual(
            self.client.get(reverse("jobs:detail", args=[self.draft.pk])).status_code, 404
        )

    def test_owner_can_preview_its_own_draft(self):
        self.client.force_login(self.owner.user)
        self.assertEqual(
            self.client.get(reverse("jobs:detail", args=[self.draft.pk])).status_code, 200
        )


class JobOwnershipTests(TestCase):
    """Company A must not reach company B's postings."""

    def setUp(self):
        self.owner = make_company("owner@example.com", "سوداتل")
        self.intruder = make_company("intruder@example.com", "زين")
        self.seeker = make_seeker("seeker@example.com", "محمد")
        self.job = make_job(self.owner)

    def test_company_sees_only_its_own_jobs(self):
        make_job(self.intruder, title="Other Company Role")
        self.client.force_login(self.owner.user)
        response = self.client.get(reverse("jobs:my_jobs"))
        self.assertEqual(list(response.context["jobs"]), [self.job])

    def test_other_company_cannot_open_the_edit_page(self):
        self.client.force_login(self.intruder.user)
        response = self.client.get(reverse("jobs:update", args=[self.job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_other_company_cannot_post_an_edit(self):
        self.client.force_login(self.intruder.user)
        response = self.client.post(
            reverse("jobs:update", args=[self.job.pk]),
            {
                "title": "Hijacked",
                "description": "x",
                "required_skills": "Python",
                "location": "الخرطوم",
                "employment_type": Job.EmploymentType.FULL_TIME,
                "status": Job.Status.OPEN,
            },
        )
        self.assertEqual(response.status_code, 404)
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "Backend Developer")

    def test_other_company_cannot_delete(self):
        self.client.force_login(self.intruder.user)
        response = self.client.post(reverse("jobs:delete", args=[self.job.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Job.objects.filter(pk=self.job.pk).exists())

    def test_seeker_cannot_reach_company_job_pages(self):
        self.client.force_login(self.seeker.user)
        for name, args in [
            ("jobs:my_jobs", []),
            ("jobs:create", []),
            ("jobs:update", [self.job.pk]),
            ("jobs:delete", [self.job.pk]),
        ]:
            with self.subTest(view=name):
                self.assertEqual(
                    self.client.get(reverse(name, args=args)).status_code, 403
                )

    def test_anonymous_visitor_is_redirected_to_login(self):
        response = self.client.get(reverse("jobs:create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)


class JobCrudTests(TestCase):
    def setUp(self):
        self.company = make_company("co@example.com", "سوداتل")
        self.client.force_login(self.company.user)

    def _payload(self, **overrides):
        data = {
            "title": "Data Analyst",
            "description": "Analyse operational data.",
            "required_skills": "  SQL and data modelling  \n\n  Python pandas  \n",
            "location": "أم درمان",
            "employment_type": Job.EmploymentType.FULL_TIME,
            "salary_min": "400000",
            "salary_max": "700000",
            "status": Job.Status.OPEN,
        }
        data.update(overrides)
        return data

    def test_create_assigns_the_logged_in_company(self):
        response = self.client.post(reverse("jobs:create"), self._payload())
        self.assertRedirects(response, reverse("jobs:my_jobs"))

        job = Job.objects.get(title="Data Analyst")
        self.assertEqual(job.company, self.company)

    def test_create_normalises_the_skill_lines(self):
        self.client.post(reverse("jobs:create"), self._payload())
        job = Job.objects.get(title="Data Analyst")
        self.assertEqual(
            job.required_skills, "SQL and data modelling\nPython pandas"
        )
        self.assertEqual(job.skill_lines(), ["SQL and data modelling", "Python pandas"])

    def test_blank_skills_are_rejected(self):
        response = self.client.post(
            reverse("jobs:create"), self._payload(required_skills="   \n\n  ")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Job.objects.exists())

    def test_salary_max_below_min_is_rejected_by_the_form(self):
        response = self.client.post(
            reverse("jobs:create"), self._payload(salary_min="900000", salary_max="400000")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("salary_max", response.context["form"].errors)
        self.assertFalse(Job.objects.exists())

    def test_company_field_in_post_data_is_ignored(self):
        """A crafted POST must not assign the job to another company."""
        intruder = make_company("intruder@example.com", "زين")
        self.client.post(reverse("jobs:create"), self._payload(company=intruder.pk))
        job = Job.objects.get(title="Data Analyst")
        self.assertEqual(job.company, self.company)

    def test_update_changes_the_job(self):
        job = make_job(self.company)
        self.client.post(
            reverse("jobs:update", args=[job.pk]), self._payload(title="Updated Title")
        )
        job.refresh_from_db()
        self.assertEqual(job.title, "Updated Title")

    def test_delete_requires_post(self):
        job = make_job(self.company)
        self.assertEqual(
            self.client.get(reverse("jobs:delete", args=[job.pk])).status_code, 200
        )
        self.assertTrue(Job.objects.filter(pk=job.pk).exists())

        self.client.post(reverse("jobs:delete", args=[job.pk]))
        self.assertFalse(Job.objects.filter(pk=job.pk).exists())


class SavedJobTests(TestCase):
    def setUp(self):
        self.company = make_company("co@example.com", "سوداتل")
        self.seeker = make_seeker("seeker@example.com", "محمد")
        self.job = make_job(self.company)

    def test_saving_twice_is_blocked_by_the_unique_constraint(self):
        SavedJob.objects.create(seeker=self.seeker, job=self.job)
        with self.assertRaises(Exception):
            SavedJob.objects.create(seeker=self.seeker, job=self.job)

    def test_toggle_saves_then_unsaves(self):
        self.client.force_login(self.seeker.user)
        url = reverse("jobs:toggle_saved", args=[self.job.pk])

        self.client.post(url)
        self.assertTrue(SavedJob.objects.filter(seeker=self.seeker, job=self.job).exists())

        self.client.post(url)
        self.assertFalse(SavedJob.objects.filter(seeker=self.seeker, job=self.job).exists())

    def test_toggle_requires_post(self):
        self.client.force_login(self.seeker.user)
        response = self.client.get(reverse("jobs:toggle_saved", args=[self.job.pk]))
        self.assertEqual(response.status_code, 405)

    def test_company_cannot_save_a_job(self):
        self.client.force_login(self.company.user)
        response = self.client.post(reverse("jobs:toggle_saved", args=[self.job.pk]))
        self.assertEqual(response.status_code, 403)

    def test_draft_jobs_cannot_be_saved(self):
        draft = make_job(self.company, status=Job.Status.DRAFT)
        self.client.force_login(self.seeker.user)
        response = self.client.post(reverse("jobs:toggle_saved", args=[draft.pk]))
        self.assertEqual(response.status_code, 404)

    def test_external_next_url_is_refused(self):
        """`next` is attacker-controllable, so it must not leave the site."""
        self.client.force_login(self.seeker.user)
        response = self.client.post(
            reverse("jobs:toggle_saved", args=[self.job.pk]),
            {"next": "https://evil.example.com/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.job.get_absolute_url())

    def test_internal_next_url_is_honoured(self):
        self.client.force_login(self.seeker.user)
        response = self.client.post(
            reverse("jobs:toggle_saved", args=[self.job.pk]),
            {"next": reverse("jobs:list")},
        )
        self.assertRedirects(response, reverse("jobs:list"))

    def test_saved_ids_helper_is_empty_for_anonymous_and_company(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(services.saved_job_ids_for(AnonymousUser()), set())
        self.assertEqual(services.saved_job_ids_for(self.company.user), set())

    def test_listing_marks_saved_jobs(self):
        SavedJob.objects.create(seeker=self.seeker, job=self.job)
        self.client.force_login(self.seeker.user)
        response = self.client.get(reverse("jobs:list"))
        self.assertEqual(response.context["saved_job_ids"], {self.job.pk})


class QueryCountTests(TestCase):
    """
    The listing must not issue one extra query per job.

    Without select_related("company") the template's `job.company.name` turns
    a single page render into one query per row. Asserting a fixed count is
    what stops that regression coming back unnoticed.
    """

    def setUp(self):
        self.company = make_company("co@example.com", "سوداتل")

    def test_listing_query_count_does_not_grow_with_the_number_of_jobs(self):
        for i in range(3):
            make_job(self.company, title=f"Role {i}")
        with self.assertNumQueries(1):
            list(services.open_jobs())

        for i in range(3, 12):
            make_job(self.company, title=f"Role {i}")
        with self.assertNumQueries(1):
            list(services.open_jobs())

    def test_company_name_is_reachable_without_another_query(self):
        make_job(self.company)
        jobs = list(services.open_jobs())
        with self.assertNumQueries(0):
            self.assertEqual(jobs[0].company.name, "سوداتل")
