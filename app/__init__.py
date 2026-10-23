
"""LUMORA app factory."""
import logging
import re

from flask import Flask, g, render_template, request
from flask_wtf.csrf import CSRFError

from app.config import Config
from app.extensions import csrf

_TOKEN_RE = re.compile(r"(/reset-password/)[A-Za-z0-9_\-]+")


class RedactResetTokens(logging.Filter):
    """Hide password-reset tokens from the web server's request log."""

    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = _TOKEN_RE.sub(r"\1<hidden>", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _TOKEN_RE.sub(r"\1<hidden>", arg)
                if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validate essential application configuration.
    if not app.config["SECRET_KEY"]:
        raise RuntimeError(
            "FLASK_SECRET_KEY is empty. Open your .env file and set it. "
            'Make one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    if app.config["AUTH_MODE"] not in ("demo", "google"):
        raise RuntimeError("AUTH_MODE must be 'demo' or 'google'.")

    # Explicitly validate the selected AI mode.
    if app.config["AI_MODE"] not in ("mock", "live"):
        raise RuntimeError("AI_MODE must be 'mock' or 'live'.")

    # Live AI must never silently fall back to mock mode.
    if app.config["AI_MODE"] == "live":
        if not app.config["AI_API_KEY"] or not app.config["AI_MODEL"]:
            raise RuntimeError(
                "AI_MODE is 'live', but AI_API_KEY or AI_MODEL is missing. "
                "Set both in your .env file, or use AI_MODE=mock."
            )

    logging.getLogger("werkzeug").addFilter(RedactResetTokens())
    csrf.init_app(app)

    from app.database.connection import close_db
    app.teardown_appcontext(close_db)

    from app import health
    from app.auth.routes import bp as auth_bp
    from app.employee.routes import bp as employee_bp
    from app.hr.routes import bp as hr_bp
    from app.assessments.routes import bp as assessments_bp

    app.register_blueprint(health.bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(assessments_bp)

    from app.ui import init_ui
    init_ui(app)  # Sidebar navigation and friendly "coming soon" pages.

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")

        if g.get("user") or request.path.startswith("/reset-password"):
            resp.headers["Cache-Control"] = "no-store"

        return resp

    def show_error(code, title, message):
        return (
            render_template(
                "error.html",
                code=code,
                title=title,
                message=message,
            ),
            code,
        )

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return show_error(
            400,
            "This page expired",
            "Please go back, refresh the page and try again.",
        )

    @app.errorhandler(403)
    def forbidden(e):
        return show_error(
            403,
            "You do not have access to this page",
            "This page is for a different type of account.",
        )

    @app.errorhandler(404)
    def not_found(e):
        return show_error(
            404,
            "Page not found",
            "We could not find that page.",
        )

    @app.errorhandler(500)
    def server_error(e):
        return show_error(
            500,
            "Something went wrong",
            "Please try again. If it keeps happening, tell your project team.",
        )

    return app
