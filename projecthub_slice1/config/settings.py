"""Settings for Baze Project Hub. Secrets come from environment variables or a local .env file."""
import os
import sys
from pathlib import Path

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if env("DB_ENGINE", "mysql") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME", "baze_projecthub"),
            "USER": env("DB_USER", "projecthub_app"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }

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
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Project Hub product settings -------------------------------------------------------------
SITE_NAME = "Baze Project Hub"

# Repository access follows D-09: signed-in Baze Project Hub accounts only.
PUBLIC_REPOSITORY = False

# Personal data (student ID, an individual's contact) is never public, whatever the flag above says.
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
NOTIFICATION_DEDUP_HOURS = 24  # same recipient + kind + object: at most one notification in this window

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
