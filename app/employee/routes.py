"""Employee portal (Phase 4).

Every route here is protected by the guard below (signed in + role 'employee') and every
database query filters on the signed-in user's id, so changing an id in the URL
shows a 404, never another person's data.
"""
from datetime import date

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from app.ai import service as ai_service
from app.auth import services as auth_services
from app.database import employee_repo as er
from app.database import repositories as repo
from app.reports import services as reports

bp = Blueprint("employee", __name__, url_prefix="/employee")

MIN_RESPONSE, MAX_RESPONSE = 40, 5000
MIN_CONCERN, MAX_CONCERN = 10, 1000


@bp.before_request
def guard():
    """Runs before every employee page: signed in, active (checked at load) and role 'employee'."""
    if g.get("user") is None:
        flash("Please sign in to continue.", "info")
        return redirect(url_for("auth.login"))
    if g.user["role"] != "employee":
        abort(403)


@bp.app_template_filter("fmt_date")
def fmt_date(value):
    return value.strftime("%d %b %Y") if value else ""


def due_info(deadline):
    if not deadline:
        return {"label": "No deadline", "state": "none"}
    days = (deadline - date.today()).days
    when = deadline.strftime("%d %b")
    if days < 0:
        return {"label": f"Was due {when}", "state": "overdue"}
    if days == 0:
        return {"label": "Due today", "state": "soon"}
    if days <= 3:
        return {"label": f"Due in {days} day{'s' if days > 1 else ''}", "state": "soon"}
    return {"label": f"Due {when}", "state": "ok"}


def can_submit(assignment, last):
    """A first answer is allowed. A repeat only if HR allowed reassessment and the last analysis finished."""
    if last is None:
        return assignment["status"] == "assigned"
    return bool(assignment["allow_reassessment"]) and last["analysis_status"] == "completed"


def _decorate(rows):
    for r in rows:
        r["due"] = due_info(r["deadline"])
    return rows


# ---------- overview ----------

@bp.route("/")
def overview():
    uid = g.user["id"]
    assignments = _decorate(er.list_assignments(uid))
    pending = [a for a in assignments if a["status"] == "assigned"]
    learning = er.list_learning(uid)
    return render_template(
        "employee/overview.html",
        counts=er.assignment_counts(uid),
        learning_counts=er.learning_counts(uid),
        upcoming=[a for a in pending if a["deadline"]][:3] or pending[:3],
        recent=[a for a in er.list_assessments(uid, limit=3) if a["analysis_status"] == "completed"],
        next_learning=[l for l in learning if l["status"] != "completed"][:3],
        first_name=g.user["full_name"].split()[0],
    )


# ---------- assessments ----------

@bp.route("/assessments")
def assessments():
    return render_template("employee/assessments.html", items=_decorate(er.list_assignments(g.user["id"])))


def _render_open(recipient_id, text="", status=200):
    a = er.get_assignment(g.user["id"], recipient_id)
    if a is None:
        abort(404)
    last = er.latest_response(recipient_id)
    a["due"] = due_info(a["deadline"])
    return render_template(
        "employee/assessment_open.html", a=a, last=last, text=text,
        competencies=er.scenario_competencies(a["scenario_id"]),
        allowed=can_submit(a, last), min_len=MIN_RESPONSE, max_len=MAX_RESPONSE), status


@bp.route("/assessments/<int:recipient_id>")
def assessment_open(recipient_id):
    return _render_open(recipient_id)


@bp.route("/assessments/<int:recipient_id>/submit", methods=["POST"])
def assessment_submit(recipient_id):
    uid = g.user["id"]
    a = er.get_assignment(uid, recipient_id)
    if a is None:
        abort(404)
    if not can_submit(a, er.latest_response(recipient_id)):
        flash("You have already submitted this assessment. Your original response is kept as it was.", "info")
        return redirect(url_for("employee.assessment_open", recipient_id=recipient_id))

    text = (request.form.get("response_text") or "").strip()
    if len(text) < MIN_RESPONSE:
        flash(f"Please write a little more. A response needs at least {MIN_RESPONSE} characters so there is something to learn from.", "error")
        return _render_open(recipient_id, text, 400)
    if len(text) > MAX_RESPONSE:
        flash(f"That is too long. Please keep it under {MAX_RESPONSE} characters.", "error")
        return _render_open(recipient_id, text, 400)

    cfg = current_app.config
    model = cfg["AI_MODEL"] if cfg["AI_MODE"] == "live" else "lumora-mock-v1"
    created = er.create_response_with_assessment(recipient_id, uid, text, cfg["AI_MODE"], model)
    if created is None:
        flash("That response was already saved.", "info")
        return redirect(url_for("employee.assessment_open", recipient_id=recipient_id))
    _response_id, assessment_id = created
    repo.add_audit_log(uid, "response_submitted", "assessment", assessment_id, ip=request.remote_addr)

    outcome, message = ai_service.analyse(assessment_id)
    if outcome == "completed":
        flash("Your response was saved. Here is what it demonstrated.", "success")
        return redirect(url_for("employee.insight_detail", assessment_id=assessment_id))
    flash("Your response was saved. " + message, "warning")
    return redirect(url_for("employee.insight_detail", assessment_id=assessment_id))


@bp.route("/assessments/analysis/<int:assessment_id>/retry", methods=["POST"])
def analysis_retry(assessment_id):
    """Controlled retry after a failed analysis. Only for the owner of the response."""
    if er.get_assessment(g.user["id"], assessment_id) is None:
        abort(404)
    outcome, message = ai_service.analyse(assessment_id)
    flash(message, "success" if outcome == "completed" else "warning")
    return redirect(url_for("employee.insight_detail", assessment_id=assessment_id))


# ---------- insights ----------

@bp.route("/insights")
def insights():
    return render_template("employee/insights.html", items=er.list_assessments(g.user["id"]))


@bp.route("/insights/<int:assessment_id>")
def insight_detail(assessment_id):
    asm = er.get_assessment(g.user["id"], assessment_id)
    if asm is None:
        abort(404)
    findings = er.findings_for(assessment_id) if asm["analysis_status"] == "completed" else []
    return render_template("employee/insight_detail.html", asm=asm, findings=findings)


# ---------- learning ----------

@bp.route("/learning")
def learning():
    items = er.list_learning(g.user["id"])
    return render_template("employee/learning.html", items=items,
                           todo=[i for i in items if i["status"] != "completed"],
                           done=[i for i in items if i["status"] == "completed"])


@bp.route("/learning/<int:reco_id>", methods=["POST"])
def learning_update(reco_id):
    status = request.form.get("status")
    if status not in ("in_progress", "completed", "not_started"):
        abort(400)
    if not er.set_learning_status(g.user["id"], reco_id, status):
        abort(404)
    if status == "completed":
        repo.add_audit_log(g.user["id"], "learning_completed", "recommendation", reco_id)
        flash("Nice work. That activity is marked as completed.", "success")
    return redirect(url_for("employee.learning"))


# ---------- progress ----------

@bp.route("/progress")
def progress():
    uid = g.user["id"]
    return render_template("employee/progress.html",
                           history=er.list_assessments(uid),
                           learning_counts=er.learning_counts(uid),
                           comparisons=reports.build_comparisons(uid))


# ---------- review requests ----------

@bp.route("/reviews")
def reviews():
    return render_template("employee/reviews.html", items=er.list_reviews(g.user["id"]))


@bp.route("/reviews/new", methods=["GET", "POST"])
def review_new():
    uid = g.user["id"]
    options = er.reviewable_findings(uid)
    allowed = {o["id"] for o in options}
    selected = request.args.get("finding", type=int)
    concern = ""

    if request.method == "POST":
        selected = request.form.get("finding_id", type=int)
        concern = (request.form.get("concern") or "").strip()
        if selected not in allowed:  # not the user's own finding
            flash("Please choose one of your own findings.", "error")
        elif not MIN_CONCERN <= len(concern) <= MAX_CONCERN:
            flash(f"Please describe your concern in {MIN_CONCERN} to {MAX_CONCERN} characters.", "error")
        elif er.open_review_exists(uid, selected):
            flash("You already have an open review request for this finding.", "info")
            return redirect(url_for("employee.reviews"))
        else:
            review_id = er.create_review(uid, selected, concern)
            repo.add_audit_log(uid, "review_requested", "review_request", review_id, ip=request.remote_addr)
            flash("Your review request was sent. A person in HR will look at it.", "success")
            return redirect(url_for("employee.reviews"))

    return render_template("employee/review_new.html", options=options, selected=selected,
                           concern=concern, max_len=MAX_CONCERN), (400 if request.method == "POST" else 200)


# ---------- profile ----------

@bp.route("/profile")
def profile():
    return render_template("employee/profile.html")


@bp.route("/profile/password", methods=["POST"])
def change_password():
    user = g.user
    current = request.form.get("current_password", "")
    if not auth_services.verify_password(user["password_hash"], current):
        flash("Your current password was not correct.", "error")
        return redirect(url_for("employee.profile"))
    problem = auth_services.validate_new_password(request.form.get("new_password", ""),
                                                  request.form.get("confirm_password", ""))
    if problem:
        flash(problem, "error")
        return redirect(url_for("employee.profile"))
    repo.update_password(user["id"], auth_services.hash_password(request.form["new_password"]))
    session["sv"] = repo.get_user_by_id(user["id"])["session_version"]  # keep THIS browser signed in
    repo.add_audit_log(user["id"], "password_changed", "user", user["id"], ip=request.remote_addr)
    flash("Your password was changed. Other devices were signed out.", "success")
    return redirect(url_for("employee.profile"))
