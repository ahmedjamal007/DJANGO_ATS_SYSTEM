"""
Django settings for the Job Board + ATS project.

SECRET_KEY and DEBUG are read from the environment so the project can be run
without a settings change; the defaults are development-only.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-change-me-in-production",
)

# Any value other than "0"/"false" counts as on, so `DJANGO_DEBUG=0` disables it.
DEBUG = os.environ.get("DJANGO_DEBUG", "1").lower() not in ("0", "false", "")

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps. applications / matching / notifications are added in
    # their own build phases.
    "accounts",
    "jobs",
    "matching",
    "applications",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "notifications.context_processors.poll_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Swaps in a fast password hasher for `manage.py test`. See the module for why.
TEST_RUNNER = "config.test_runner.FastTestRunner"

LOGIN_URL = "accounts:login"
# Both of these land on the home view, which forwards a logged-in user to the
# dashboard matching their role. Keeping that decision in one view means there
# is a single place to look when the redirect misbehaves.
LOGIN_REDIRECT_URL = "accounts:home"
LOGOUT_REDIRECT_URL = "accounts:home"


# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------

# Arabic interface, right-to-left. Setting this also gives us Django's own
# Arabic translations for form validation errors and the admin site, so
# those do not have to be translated by hand.
LANGUAGE_CODE = "ar"
# The project targets Sudan, so timestamps render in local time (UTC+2).
TIME_ZONE = "Africa/Khartoum"
USE_I18N = True
USE_TZ = True


# --------------------------------------------------------------------------
# Static and media files
# --------------------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

# Development only: messages are printed to the runserver console instead of
# being sent. Used from Phase 6 for stage-change and rejection emails.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@jobboard.local"


# --------------------------------------------------------------------------
# Matching engine
# --------------------------------------------------------------------------
# Used from Phase 3. They live here rather than in matching/ so the values can
# be changed without editing code, and so the calibrate_threshold management
# command has one authoritative place to report against.

# A required skill counts as met when its best cosine similarity against any
# resume chunk reaches this value.
#
# Chosen by `python manage.py calibrate_threshold`, which scores every sample
# resume against every sample job skill and labels each pair by field of work:
# same field should match, different field should not. Over 450 such pairs,
# 0.38 gives the best balance of recall and precision (F1 0.73).
#
# Earlier values were worse guesses on thinner evidence. 0.45 was the spec's
# default and rejected true positives; 0.32 came from only three fixtures and
# admitted too many near-misses. Re-run the command after changing the sample
# corpus.
SKILL_MATCH_THRESHOLD = 0.38

# Final score = SEMANTIC_WEIGHT * semantic + COVERAGE_WEIGHT * coverage.
# These must sum to 1.0 for the final score to stay inside 0-1.
SEMANTIC_WEIGHT = 0.5
COVERAGE_WEIGHT = 0.5

# Sentence-transformers model used for every embedding in the project.
# The interface is Arabic but resumes and job descriptions are written in
# English, so an English-only model is the right choice. If Arabic resumes
# are ever accepted, this must become a multilingual model such as
# paraphrase-multilingual-MiniLM-L12-v2 -- this one scores Arabic at noise.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


# --------------------------------------------------------------------------
# Resume uploads
# --------------------------------------------------------------------------

# Parsing runs inline in the upload view, so a very large file would hold the
# request open. Five megabytes is far more than any real resume needs.
RESUME_MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# Only formats we can extract text from. Anything else is rejected in the
# form's clean_file() with a message naming what is accepted.
RESUME_ALLOWED_EXTENSIONS = [".pdf", ".docx"]


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------

# The navbar badge polls this often, in seconds. Polling rather than
# websockets is a deliberate choice: a job board's notifications are not
# time-critical, and a setInterval costs nothing to run, deploy or explain,
# where Channels would add an ASGI server and a message broker to a project
# that otherwise runs on `manage.py runserver` alone.
NOTIFICATION_POLL_SECONDS = 20
