"""
Tests for the two management commands.

`seed_demo_data` is slow -- it embeds fifteen jobs and ten resumes through the
real model -- so it runs once for the whole class and the assertions inspect
what it produced.
"""

import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import CompanyProfile, SeekerProfile, User
from applications.models import Application, Resume, StageHistory
from jobs.models import Job, SavedJob
from sample_data import profiles

TEMP_MEDIA = tempfile.mkdtemp(prefix="ats-seed-media-")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class SeedDemoDataTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.output = StringIO()
        call_command("seed_demo_data", stdout=cls.output)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def test_it_creates_the_counts_the_spec_asks_for(self):
        self.assertEqual(CompanyProfile.objects.count(), 3)
        self.assertEqual(Job.objects.count(), 15)
        self.assertEqual(SeekerProfile.objects.count(), 10)
        self.assertTrue(Application.objects.exists())

    def test_every_resume_parsed_and_embedded(self):
        """A seeded resume that failed to parse would be a broken demo."""
        self.assertEqual(Resume.objects.count(), 10)
        for resume in Resume.objects.all():
            with self.subTest(resume=resume.original_filename):
                self.assertEqual(resume.parse_status, Resume.ParseStatus.DONE)
                self.assertTrue(resume.parsed_text)
                self.assertTrue(resume.doc_embedding)
                self.assertTrue(resume.chunk_embeddings)

    def test_every_job_is_embedded(self):
        for job in Job.objects.all():
            with self.subTest(job=job.title):
                self.assertTrue(job.description_embedding)
                self.assertTrue(job.skills_embedding)

    def test_both_draft_and_open_jobs_exist(self):
        self.assertTrue(Job.objects.filter(status=Job.Status.OPEN).exists())
        self.assertTrue(Job.objects.filter(status=Job.Status.DRAFT).exists())

    def test_applications_are_spread_across_every_stage(self):
        """
        The demo has to show a populated pipeline, not a column of new
        applications.
        """
        stages = set(Application.objects.values_list("stage", flat=True))
        for stage in Application.PIPELINE_STAGES:
            with self.subTest(stage=stage):
                self.assertIn(stage, stages)

    def test_every_application_is_scored(self):
        for application in Application.objects.all():
            with self.subTest(application=application.pk):
                self.assertGreater(application.match_score, 0)
                self.assertTrue(application.skill_breakdown)

    def test_every_application_has_a_timeline(self):
        for application in Application.objects.all():
            with self.subTest(application=application.pk):
                history = list(application.history.all())
                self.assertTrue(history)
                self.assertEqual(history[0].from_stage, "")
                self.assertEqual(history[-1].to_stage, application.stage)

    def test_candidates_outscore_themselves_on_their_own_field(self):
        """
        Each seeker applies inside their field and once outside it. The
        in-field application should score higher, or the engine is not working.
        """
        by_category = {r.email: r.category for r in profiles.RESUMES}
        job_category = {j.title: j.category for j in profiles.JOBS}

        compared = 0
        for seeker in SeekerProfile.objects.all():
            category = by_category[seeker.user.email]
            applications = list(Application.objects.filter(seeker=seeker))

            in_field = [a for a in applications if job_category.get(a.job.title) == category]
            out_field = [a for a in applications if job_category.get(a.job.title) != category]
            if not in_field or not out_field:
                continue

            compared += 1
            self.assertGreater(
                max(a.match_score for a in in_field),
                min(a.match_score for a in out_field),
                f"{seeker.full_name} scored better outside their field",
            )

        self.assertGreater(compared, 5, "not enough seekers had both kinds of application")

    def test_saved_jobs_are_created(self):
        self.assertTrue(SavedJob.objects.exists())

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_demo_data", stdout=StringIO())
        self.assertEqual(CompanyProfile.objects.count(), 3)
        self.assertEqual(SeekerProfile.objects.count(), 10)
        self.assertEqual(Job.objects.count(), 15)


class CalibrateThresholdTests(TestCase):
    def test_it_reports_both_distributions_and_a_verdict(self):
        output = StringIO()
        call_command("calibrate_threshold", stdout=output)
        text = output.getvalue()

        for expected in [
            "Similarity distributions",
            "same field",
            "different",
            "Threshold sweep",
            "recall",
            "precision",
            "Verdict",
            "SKILL_MATCH_THRESHOLD now",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_it_writes_nothing_to_the_database(self):
        """The command reports; a human edits settings.py."""
        call_command("calibrate_threshold", stdout=StringIO())
        self.assertFalse(Job.objects.exists())
        self.assertFalse(Resume.objects.exists())
        self.assertFalse(User.objects.exists())
