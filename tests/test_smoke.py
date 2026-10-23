
"""These tests do not need MySQL."""

import logging

import pytest

from app import RedactResetTokens, create_app
from app.config import Config, TestConfig


@pytest.fixture
def client():
    return create_app(TestConfig).test_client()


def test_health_works_even_without_database(client):
    resp = client.get("/health")
    assert resp.status_code == 200

    data = resp.get_json()
    assert data["app"] == "LUMORA"
    assert data["ai_mode"] == "mock"


def test_start_page_sends_you_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_login_page_loads_and_shows_demo_label(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"DEMO MODE" in resp.data
    assert b"Illuminate Potential" in resp.data


def test_missing_secret_key_is_refused():
    class NoSecret(TestConfig):
        SECRET_KEY = ""

    with pytest.raises(RuntimeError):
        create_app(NoSecret)


def test_bad_auth_mode_is_refused():
    class BadMode(TestConfig):
        AUTH_MODE = "anything"

    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        create_app(BadMode)


def test_bad_ai_mode_is_refused():
    class BadAIMode(TestConfig):
        AI_MODE = "anything"

    with pytest.raises(RuntimeError, match="AI_MODE"):
        create_app(BadAIMode)


def test_live_ai_requires_credentials():
    class LiveWithoutCredentials(TestConfig):
        AI_MODE = "live"
        AI_API_KEY = ""
        AI_MODEL = ""

    with pytest.raises(RuntimeError, match="AI_API_KEY or AI_MODEL"):
        create_app(LiveWithoutCredentials)


def test_session_cookie_is_httponly():
    assert Config.SESSION_COOKIE_HTTPONLY is True


def test_reset_tokens_are_hidden_in_logs():
    record = logging.LogRecord(
        "werkzeug",
        logging.INFO,
        "x",
        1,
        '"GET /reset-password/abc123_-XYZ HTTP/1.1" 200 -',
        (),
        None,
    )

    RedactResetTokens().filter(record)

    assert "abc123" not in record.getMessage()
    assert "/reset-password/<hidden>" in record.getMessage()
