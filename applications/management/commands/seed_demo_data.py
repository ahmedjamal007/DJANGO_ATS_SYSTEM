"""
Build a complete demo database: companies, jobs, candidates and applications.

    python manage.py seed_demo_data

Creates 3 companies with 15 jobs between them, 10 job seekers each with a real
resume file parsed and embedded, and applications spread across every stage of
the pipeline. The point is that the project demonstrates from a fresh clone
without anyone having to click through it first.

This is slow -- every resume and every job goes through the embedding model,
which is the honest cost of not faking the data. Expect a couple of minutes.
"""

import os
import random

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand

from accounts.models import CompanyProfile, SeekerProfile, User
from applications import services as application_services
from applications.models import Application, RecruiterNote, Resume
from jobs.models import Job, SavedJob
from jobs.services import embed_job
from sample_data import profiles

PASSWORD = "demo1234"
SAMPLE_DIR = os.path.join(settings.BASE_DIR, "sample_data")

# Where each seeded application ends up. Weighted towards the early stages,
# because a real pipeline is wide at the top and narrow at the bottom.
STAGE_PLAN = [
    Application.Stage.APPLIED,
    Application.Stage.APPLIED,
    Application.Stage.APPLIED,
    Application.Stage.SCREENING,
    Application.Stage.SCREENING,
    Application.Stage.INTERVIEW,
    Application.Stage.INTERVIEW,
    Application.Stage.OFFER,
    Application.Stage.HIRED,
    Application.Stage.REJECTED,
    Application.Stage.REJECTED,
]


class Command(BaseCommand):
    help = "Create a full demo dataset: companies, jobs, seekers, resumes and applications."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Add to the existing data instead of clearing the seeded accounts first.",
        )

    def handle(self, *args, **options):
        # A fixed seed so two runs of the demo look the same, which matters
        # when the screenshots in a report have to match what the examiner sees.
        random.seed(20260930)

        if not options["keep"]:
            self._clear()

        companies = self._create_companies()
        jobs = self._create_jobs(companies)
        seekers = self._create_seekers()
        self._create_applications(seekers, jobs)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  companies    : {len(companies)}")
        self.stdout.write(f"  jobs         : {len(jobs)}")
        self.stdout.write(f"  job seekers  : {len(seekers)}")
        self.stdout.write(f"  applications : {Application.objects.count()}")
        self.stdout.write("")
        self.stdout.write(f"  every seeded account uses the password: {PASSWORD}")
        self.stdout.write(f"  a company : {profiles.COMPANIES[0]['email']}")
        self.stdout.write(f"  a seeker  : {profiles.RESUMES[0].email}")

    # ----------------------------------------------------------------- #

    def _clear(self):
        """
        Remove previously seeded accounts, in dependency order.

        Application.resume is PROTECT, so a plain User.delete() fails as soon
        as anybody has applied -- the resume cannot go while an application
        still points at it.
        """
        emails = [c["email"] for c in profiles.COMPANIES] + [
            r.email for r in profiles.RESUMES
        ]
        stale = User.objects.filter(email__in=emails)
        if not stale.exists():
            return

        Application.objects.filter(seeker__user__in=stale).delete()
        Application.objects.filter(job__company__user__in=stale).delete()
        Resume.objects.filter(seeker__user__in=stale).delete()
        stale.delete()
        self.stdout.write("cleared previously seeded accounts")

    def _create_companies(self):
        created = []
        for spec in profiles.COMPANIES:
            user = User.objects.create_user(
                email=spec["email"], password=PASSWORD, role=User.Role.COMPANY
            )
            created.append(
                CompanyProfile.objects.create(
                    user=user,
                    name=spec["name"],
                    location=spec["location"],
                    description=spec["description"],
                    website=spec["website"],
                )
            )
        self.stdout.write(f"created {len(created)} companies")
        return created

    def _create_jobs(self, companies):
        """
        Spread the job templates across the companies by field of work, so the
        hospitality group does not end up advertising for a data scientist.
        """
        by_category = {
            profiles.HOSPITALITY: companies[2],
            profiles.FINANCE: companies[1],
        }

        created = []
        for index, spec in enumerate(profiles.JOBS):
            company = by_category.get(spec.category, companies[0])
            job = Job.objects.create(
                company=company,
                title=spec.title,
                description=spec.description,
                required_skills="\n".join(spec.skills),
                location=spec.location,
                employment_type=spec.employment_type,
                salary_min=spec.salary_min,
                salary_max=spec.salary_max,
                # Leave a couple unpublished so the draft/open distinction is
                # visible in the demo rather than theoretical.
                status=Job.Status.DRAFT if index in (5, 12) else Job.Status.OPEN,
            )
            embed_job(job)
            # Paired with its spec: the category is demo metadata used to
            # decide who applies to what, not something Job should store.
            created.append((job, spec))
            self.stdout.write(f"  embedded job {index + 1}/{len(profiles.JOBS)}: {job.title}")

        return created

    def _create_seekers(self):
        created = []
        for spec in profiles.RESUMES:
            user = User.objects.create_user(
                email=spec.email, password=PASSWORD, role=User.Role.JOB_SEEKER
            )
            seeker = SeekerProfile.objects.create(
                user=user,
                full_name=spec.full_name,
                location=spec.location,
                headline=spec.headline,
                phone="+249 9" + str(random.randint(10000000, 99999999)),
            )

            # The real file, through the real upload path: parsed, chunked and
            # embedded exactly as a candidate's own upload would be.
            path = os.path.join(SAMPLE_DIR, spec.filename)
            with open(path, "rb") as handle:
                upload = SimpleUploadedFile(spec.filename, handle.read())
            resume = application_services.create_resume(seeker, upload)

            status = "ok" if resume.is_usable else f"FAILED: {resume.parse_error}"
            self.stdout.write(f"  parsed resume for {spec.full_name}: {status}")
            created.append((seeker, spec))

        return created

    def _create_applications(self, seekers, jobs):
        """
        Have each candidate apply to jobs in their own field plus one outside it.

        The off-field application is deliberate: a pipeline where every
        candidate scores well demonstrates nothing. Having one obvious
        mismatch per person is what makes the evidence table worth looking at.
        """
        open_jobs = [(job, spec) for job, spec in jobs if job.status == Job.Status.OPEN]
        stage_cycle = iter(STAGE_PLAN * 10)

        for seeker, spec in seekers:
            matching = [job for job, js in open_jobs if js.category == spec.category]
            other = [job for job, js in open_jobs if js.category != spec.category]

            targets = random.sample(matching, min(2, len(matching)))
            if other:
                targets.append(random.choice(other))

            for job in targets:
                application = self._apply(seeker, job)
                if application is None:
                    continue
                self._advance(application, next(stage_cycle))

            # A couple of saved jobs so the dashboard section is not empty.
            for job, _ in random.sample(open_jobs, min(2, len(open_jobs))):
                SavedJob.objects.get_or_create(seeker=seeker, job=job)

        self.stdout.write(f"created {Application.objects.count()} applications")

    def _apply(self, seeker, job):
        try:
            return application_services.apply_to_job(
                seeker, job, cover_letter="I would like to be considered for this role."
            )
        except application_services.ApplicationError as exc:
            self.stdout.write(self.style.WARNING(f"  skipped: {exc}"))
            return None

    def _advance(self, application, target_stage):
        """
        Walk the application to its planned stage through the real service, so
        the seeded history is the same shape a recruiter's clicks would make.
        """
        recruiter = application.job.company.user

        if target_stage == Application.Stage.REJECTED:
            # Reject from somewhere along the path, not always from the start.
            steps = random.randint(0, 2)
            for _ in range(steps):
                try:
                    application_services.advance_stage(application, recruiter)
                except application_services.ApplicationError:
                    break
            application_services.reject_application(
                application, recruiter, note="شكرًا لاهتمامك، سنحتفظ بملفك."
            )
            return

        while application.stage != target_stage:
            try:
                application_services.advance_stage(application, recruiter)
            except application_services.ApplicationError:
                break

        if target_stage in (Application.Stage.INTERVIEW, Application.Stage.OFFER):
            RecruiterNote.objects.create(
                application=application,
                author=recruiter,
                body="خلفية قوية ومطابقة جيدة للمتطلبات.",
                rating=random.randint(3, 5),
            )
