"""Settings for Baze Project Hub. Secrets come from environment variables or a local .env file."""
import os
import re
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Tiny .env reader so no extra package is needed. Real environment variables win."""
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env(name, default=None):
    return os.environ.get(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.academics",
    "apps.accounts",
    "apps.projects",
    "apps.supervision",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.ForcePasswordChangeMiddleware",
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
                "apps.supervision.context_processors.notifications",
                "apps.accounts.context_processors.site_switches",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

def database_settings(environ):
    """DB_NAME is the MySQL database name only. SQLite reads SQLITE_PATH, so switching to SQLite with
    the MySQL .env never creates a stray file named after the MySQL database. A relative SQLITE_PATH is
    taken from this folder, not from wherever the command was started."""
    if environ.get("DB_ENGINE", "mysql") == "sqlite":
        path = Path(environ.get("SQLITE_PATH", "db.sqlite3"))
        if not path.is_absolute():
            path = BASE_DIR / path
        return {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(path)}}
    return {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": environ.get("DB_NAME", "baze_projecthub"),
            "USER": environ.get("DB_USER", "projecthub_app"),
            "PASSWORD": environ.get("DB_PASSWORD", ""),
            "HOST": environ.get("DB_HOST", "127.0.0.1"),
            "PORT": environ.get("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }


DATABASES = database_settings(os.environ)

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# The suite creates dozens of accounts. PBKDF2 is deliberately slow and the tests assert nothing
# about hash strength, so use a fast hasher only while the test runner is active. This never
# applies to runserver or to any other management command.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"  # the welcome page, which links to Log in

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email (registration decisions). Until Baze's mail server details are in .env, messages are printed
# in the server terminal instead of being sent (the console backend).
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "True").lower() == "true"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Baze Project Hub <no-reply@bazeuniversity.edu.ng>")

# --- Project Hub product settings -------------------------------------------------------------

# Student identification number format for self-registration, from .env. The Baze identification number is BU / year and batch (A, B or C)
# / department code / number, for example BU/23B/IT/7892. Input is upper-cased before it is checked and
# stored. STUDENT_ID_HELP is the message shown when an identification number does not match, so change both together.
STUDENT_ID_REGEX = env("STUDENT_ID_REGEX", r"^BU/\d{2}[A-C]/[A-Z]{2,4}/\d{3,5}$")
STUDENT_ID_HELP = env("STUDENT_ID_HELP", "BU, your year and batch, your department code and your number, separated by slashes, like BU/23B/IT/7892")
try:
    re.compile(STUDENT_ID_REGEX)
except re.error as error:
    raise ImproperlyConfigured(f"STUDENT_ID_REGEX in .env is not a valid regular expression: {error}") from error

# How long the signed link to the registration status page keeps working.
REGISTRATION_STATUS_MAX_AGE_DAYS = int(env("REGISTRATION_STATUS_MAX_AGE_DAYS", "30"))

# Student accounts are created by an administrator or the department's coordinator (D-28), so the
# public "Create student account" page is closed unless this is switched on in .env.
STUDENT_SELF_REGISTRATION = env("STUDENT_SELF_REGISTRATION", "False").lower() == "true"

# The look of the site: "glass" (frosted surfaces over a soft crimson background) or "classic".
UI_THEME = env("UI_THEME", "glass") if env("UI_THEME", "glass") in ("glass", "classic") else "glass"
SITE_NAME = "Baze Project Hub"

# Visitors who are not logged in may browse completed projects as summaries (D-42; it replaces the
# login-only rule of D-09). Running topics, files and student identification numbers stay login-only.
# Set PUBLIC_REPOSITORY=False in .env to require a login for everything again.
PUBLIC_REPOSITORY = env("PUBLIC_REPOSITORY", "True").lower() == "true"

# Personal data (student identification number, an individual's contact) is never public, whatever the flag above says.
REPOSITORY_PAGE_SIZE = 12

# Similar-topic checker (apps/projects/services/similarity.py): archived projects whose Jaccard
# word-overlap score with a topic is at or above this value are shown as a warning, never a block.
SIMILARITY_THRESHOLD = 0.35

# Project health score (apps/projects/services/health.py), shown to supervisors and coordinators.
# risk = meeting * min(days since last held meeting / 14, 1)
#      + milestones * min(overdue milestones / 3, 1)
#      + stage * min(days at current stage / expected days for that stage, 1), scaled to 0-100.
# Heuristics chosen by hand, NOT validated against real outcomes (docs/explain/health-score.md).
HEALTH_WEIGHTS = {"meeting": 0.4, "milestones": 0.3, "stage": 0.3}
HEALTH_MEETING_LIMIT_DAYS = 14
HEALTH_OVERDUE_MILESTONE_LIMIT = 3
HEALTH_BANDS = {"watch": 30, "at_risk": 60}  # below 30 on track, 30 to 60 watch, above 60 at risk
HEALTH_EXPECTED_DAYS = {  # keyed by ProjectStage value; completed projects get no score
    "0": 14,  # Topic proposed
    "1": 14,  # Supervisor accepted
    "2": 7,   # Approved by the department
    "3": 90,  # In progress
    "4": 30,  # Submitted for examination
    "5": 21,  # Defended
}

# Automation (python manage.py run_automation, apps/supervision/automation.py). Nothing runs on its
# own: a scheduler or a --loop process must be running (docs/explain/automation.md).
AUTOMATION_PENDING_REGISTRATION_HOURS = 48
AUTOMATION_NOTICE_ACK_HOURS = 48
AUTOMATION_DEADLINE_DAYS = 3  # remind a student this many days before a milestone is due
NOTIFICATION_DEDUP_HOURS = 24  # same recipient + kind + object: at most one notification in this window
# Every in-app alert is also emailed to the person's Baze email (not to demo accounts). SITE_URL makes
# the link in the email absolute; set it to the real address of the site at launch.
EMAIL_ALERTS = env("EMAIL_ALERTS", "True").lower() == "true"
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000").rstrip("/")

# Each automation run logs a one-line summary to standard output; schedulers redirect it to a file.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"timestamped": {"format": "%(asctime)s %(levelname)s %(message)s"}},
    "handlers": {
        "automation_console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "timestamped",
        },
    },
    "loggers": {
        "projecthub.automation": {"handlers": ["automation_console"], "level": "INFO", "propagate": False},
    },
}

# Security defaults. Production deployment must also serve over HTTPS.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
