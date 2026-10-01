"""
Minimal seed data for clicking through the app by hand.

    python manage.py seed_manual_test

Creates one company with one open job, and one job seeker. Safe to re-run: it
deletes the accounts it created first, so you always get a clean slate.

The full seed_demo_data command (3 companies, 15 jobs, 10 seekers with real
sample resumes) arrives in Phase 7. This one exists so the app can be driven
by hand before that.

The passwords below are development-only fixtures for a local SQLite database.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CompanyProfile, SeekerProfile, User
from applications.models import Application, Resume
from jobs.models import Job
from jobs.services import embed_job

COMPANY_EMAIL = "company@test.local"
SEEKER_EMAIL = "seeker@test.local"
PASSWORD = "testpass123"


class Command(BaseCommand):
    help = "Create one company, one open job and one job seeker for manual testing."

    @transaction.atomic
    def handle(self, *args, **options):
        # Delete in dependency order. Application.resume is PROTECT, so a
        # plain User.delete() fails as soon as the seeker has applied to
        # anything -- the resume cannot go while an application still cites it.
        stale = User.objects.filter(email__in=[COMPANY_EMAIL, SEEKER_EMAIL])
        Application.objects.filter(seeker__user__in=stale).delete()
        Application.objects.filter(job__company__user__in=stale).delete()
        Resume.objects.filter(seeker__user__in=stale).delete()
        stale.delete()

        company_user = User.objects.create_user(
            email=COMPANY_EMAIL, password=PASSWORD, role=User.Role.COMPANY
        )
        company = CompanyProfile.objects.create(
            user=company_user,
            name="سوداتل للاتصالات",
            location="الخرطوم",
            description="شركة اتصالات سودانية.",
        )

        seeker_user = User.objects.create_user(
            email=SEEKER_EMAIL, password=PASSWORD, role=User.Role.JOB_SEEKER
        )
        SeekerProfile.objects.create(
            user=seeker_user,
            full_name="نور عبدالرحمن",
            location="الخرطوم",
            headline="مهندسة برمجيات، تطوير الواجهات الخلفية",
        )

        # Skills are phrased as work, not as credentials -- see the README
        # section on how wording changes the score.
        job = Job.objects.create(
            company=company,
            title="Senior Backend Engineer",
            description=(
                "We are looking for a backend engineer to build and maintain the "
                "server-side services behind our subscriber self-service portal. "
                "You will design HTTP APIs, model data in a relational database, "
                "and keep the deployment pipeline healthy as the system grows."
            ),
            required_skills=(
                "building REST APIs with Django and Python\n"
                "optimising slow PostgreSQL queries\n"
                "automated testing and continuous integration\n"
                "containerised deployment with Docker"
            ),
            location="الخرطوم",
            employment_type=Job.EmploymentType.FULL_TIME,
            salary_min=600000,
            salary_max=1100000,
            status=Job.Status.OPEN,
        )

        # Embed the job now so the first application does not pay for it.
        embed_job(job)

        self.stdout.write(self.style.SUCCESS("Seeded manual test data.\n"))
        self.stdout.write(f"  Company login : {COMPANY_EMAIL} / {PASSWORD}")
        self.stdout.write(f"  Seeker login  : {SEEKER_EMAIL} / {PASSWORD}")
        self.stdout.write(f"  Job           : {job.title} (open) at /jobs/{job.pk}/")
        self.stdout.write(f"  Pipeline      : /jobs/{job.pk}/pipeline/")
        self.stdout.write("")
        self.stdout.write("  As the seeker : upload sample_data/resume.pdf, then apply to the job.")
        self.stdout.write("  As the company: open the pipeline to see the score and evidence table.")
