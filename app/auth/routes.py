"""Login, logout and password reset."""
from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from app.auth import services
from app.database import repositories as repo

bp = Blueprint("auth", __name__)

LOGIN_FAILED = "We could not sign you in. Please check your email and password."


def _home_for(user):
    return url_for("hr.overview") if user["role"] == "hr" else url_for("employee.overview")


@bp.before_app_request
def load_current_user():
    """Every request: trust the database, not the cookie."""
    g.user = None
    user_id = session.get("user_id")
    if user_id is None:
        return
    user = repo.get_user_by_id(user_id)
    if (user is None or user["status"] != "active"
            or user["session_version"] != session.get("sv")):
        session.clear()  # deactivated, deleted, or signed out everywhere
        return
    g.user = user


@bp.app_context_processor
def inject_globals():
    return {
        "current_user": g.get("user"),
        "auth_mode": current_app.config["AUTH_MODE"],
        "ai_mode": current_app.config["AI_MODE"],
    }


@bp.route("/")
def home():
    if g.user:
        return redirect(_home_for(g.user))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(_home_for(g.user))

    email = ""
    if request.method == "POST" and current_app.config["AUTH_MODE"] == "demo":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") in ("on", "1")
        ip = request.remote_addr

        if services.is_login_blocked(email, ip):
            flash("Too many sign-in attempts. Please wait a few minutes and try again.", "error")
            return render_template("auth/login.html", email=email,
                                   demo_password=current_app.config["DEMO_PASSWORD"]), 429

        valid_input = 0 < len(email) <= 190 and len(password) <= 256
        user = repo.get_user_by_email(email) if valid_input else None
        password_ok = services.verify_password(user["password_hash"] if user else None, password)

        if user and password_ok and user["status"] == "active":
            session.clear()  # new session on login
            session["user_id"] = user["id"]
            session["sv"] = user["session_version"]
            session.permanent = remember
            repo.delete_failed_logins(email)
            repo.record_login_attempt(email, ip, True)
            repo.add_audit_log(user["id"], "login_success", "user", user["id"], ip=ip)
            return redirect(_home_for(user))

        if valid_input:
            repo.record_login_attempt(email, ip, False)
        if user and password_ok:
            repo.add_audit_log(user["id"], "login_blocked_inactive", "user", user["id"], ip=ip)
        flash(LOGIN_FAILED, "error")  # same message for every failure

    return render_template("auth/login.html", email=email,
                           demo_password=current_app.config["DEMO_PASSWORD"])


@bp.route("/logout", methods=["POST"])
def logout():
    if g.user:
        repo.add_audit_log(g.user["id"], "logout", "user", g.user["id"], ip=request.remote_addr)
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    cfg = current_app.config
    submitted, dev_link = False, None

    if request.method == "POST" and cfg["AUTH_MODE"] == "demo":
        submitted = True  # the page says the same thing whether or not the email exists
        email = request.form.get("email", "").strip().lower()
        ip = request.remote_addr
        limited = repo.count_recent_audit(
            "password_reset_requested", ip, cfg["LOGIN_WINDOW_MINUTES"]) >= cfg["RESET_MAX_REQUESTS"]
        user = repo.get_user_by_email(email) if 0 < len(email) <= 190 else None
        repo.add_audit_log(None, "password_reset_requested", "user",
                           user["id"] if user else None, ip=ip)

        if user and user["status"] == "active" and not limited:
            token = services.create_reset_token(user["id"])
            link = url_for("auth.reset_password", token=token, _external=True)
            minutes = cfg["PASSWORD_RESET_MINUTES"]
            if services.mail_is_configured():
                services.send_email(
                    user["email"], "Reset your LUMORA password",
                    f"Hello {user['full_name']},\n\nUse this link to choose a new password. "
                    f"It works once and expires in {minutes} minutes:\n{link}\n\n"
                    "If you did not ask for this, you can ignore this email.")
            elif cfg["DEBUG"]:
                dev_link = link  # development only, see README
            else:
                current_app.logger.warning("A password reset was requested but email is not set up.")

    return render_template("auth/forgot_password.html", submitted=submitted, dev_link=dev_link)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_app.config["AUTH_MODE"] != "demo" or len(token) > 100:
        return render_template("auth/reset_password.html", invalid=True), 400
    record = repo.get_valid_reset_token(services.hash_token(token))
    if record is None:
        return render_template("auth/reset_password.html", invalid=True), 400

    if request.method == "POST":
        password = request.form.get("password", "")
        problem = services.validate_new_password(password, request.form.get("confirm", ""))
        if problem:
            flash(problem, "error")
            return render_template("auth/reset_password.html", invalid=False), 200

        done = repo.consume_reset_token_and_set_password(
            record["id"], record["user_id"], services.hash_password(password))
        if not done:
            return render_template("auth/reset_password.html", invalid=True), 400

        user = repo.get_user_by_id(record["user_id"])
        repo.add_audit_log(user["id"], "password_reset_completed", "user", user["id"],
                           ip=request.remote_addr)
        services.send_email(
            user["email"], "Your LUMORA password was changed",
            f"Hello {user['full_name']},\n\nYour password was just changed. "
            "If this was not you, please contact HR right away.")
        flash("Your password was changed. Please sign in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", invalid=False)
