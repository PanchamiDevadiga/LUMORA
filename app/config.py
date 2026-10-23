"""LUMORA settings. All values come from the .env file or environment."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # Core
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "")
    DEBUG = _bool("FLASK_DEBUG", False)

    # Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = _int("DB_PORT", 3306)
    DB_NAME = os.getenv("DB_NAME", "lumora_db")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Login mode: "demo" or "google"
    AUTH_MODE = os.getenv("AUTH_MODE", "demo").strip().lower()
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

    # AI: "live" only when both key and model are set, else "mock"
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "")
    AI_MODE = "live" if (AI_API_KEY and AI_MODEL) else "mock"
    AI_TIMEOUT_SECONDS = _int("AI_TIMEOUT_SECONDS", 30)
    AI_MAX_RETRIES = _int("AI_MAX_RETRIES", 2)

    # Email (optional)
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "")

    # Sessions and cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    # "Remember me" keeps the user signed in this many days. Without it, the cookie ends when the browser closes.
    PERMANENT_SESSION_LIFETIME = timedelta(days=_int("REMEMBER_ME_DAYS", 7))

    # CSRF
    WTF_CSRF_ENABLED = True

    # Login protection and password reset
    LOGIN_MAX_ATTEMPTS = _int("LOGIN_MAX_ATTEMPTS", 5)
    LOGIN_WINDOW_MINUTES = _int("LOGIN_WINDOW_MINUTES", 15)
    PASSWORD_RESET_MINUTES = _int("PASSWORD_RESET_MINUTES", 30)
    RESET_MAX_REQUESTS = _int("RESET_MAX_REQUESTS", 5)

    # Password given to the fictional demo accounts by scripts/seed_demo.py
    DEMO_PASSWORD = os.getenv("DEMO_PASSWORD") or "Lumora@Demo2026"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-only-secret-key-not-for-real-use"
    DB_NAME = "lumora_test_db"
    DEBUG = False
    AUTH_MODE = "demo"
    AI_MODE = "mock"
    WTF_CSRF_ENABLED = False
    MAIL_SERVER = ""
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_WINDOW_MINUTES = 15
    PASSWORD_RESET_MINUTES = 30
    RESET_MAX_REQUESTS = 5
