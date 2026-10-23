"""Password, reset-token, rate-limit and email helpers."""
import hashlib
import re
import secrets
import smtplib
from email.message import EmailMessage

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import repositories as repo

# Used when the email is unknown, so the response time looks the same.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored_hash, password):
    if not stored_hash:
        check_password_hash(_DUMMY_HASH, password)
        return False
    return check_password_hash(stored_hash, password)


def validate_new_password(password, confirm):
    """Return an error message, or None if the password is fine."""
    if password != confirm:
        return "The two passwords do not match."
    if len(password) < 8:
        return "Use at least 8 characters."
    if len(password) > 128:
        return "Use at most 128 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Use at least one letter and one number."
    return None


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(user_id, minutes=None):
    """Make a single-use token. Returns the raw token; only its hash is saved."""
    if minutes is None:
        minutes = current_app.config["PASSWORD_RESET_MINUTES"]
    repo.invalidate_reset_tokens(user_id)
    raw = secrets.token_urlsafe(32)
    repo.insert_reset_token(user_id, hash_token(raw), minutes)
    return raw


def is_login_blocked(email, ip):
    cfg = current_app.config
    window, limit = cfg["LOGIN_WINDOW_MINUTES"], cfg["LOGIN_MAX_ATTEMPTS"]
    if repo.count_failed_logins(email, window) >= limit:
        return True
    if ip and repo.count_failed_logins_by_ip(ip, window) >= limit * 4:
        return True
    return False


def mail_is_configured():
    cfg = current_app.config
    return bool(cfg["MAIL_SERVER"] and cfg["MAIL_DEFAULT_SENDER"])


def send_email(to_address, subject, body):
    """Send a plain email. Returns True/False. Never logs the body (it may hold a link)."""
    if not mail_is_configured():
        return False
    cfg = current_app.config
    msg = EmailMessage()
    msg["From"] = cfg["MAIL_DEFAULT_SENDER"]
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as smtp:
            smtp.starttls()
            if cfg["MAIL_USERNAME"]:
                smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        current_app.logger.warning("Could not send an email (SMTP problem).")
        return False
