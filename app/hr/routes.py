"""HR portal (Drop 2).

Every route is protected by the guard below: signed in AND role 'hr' (role comes from the
database via g.user, never from the browser). All SQL uses %s placeholders only.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.database import repositories as repo
from app.database.connection import execute, get_db, query_all, query_one

bp = Blueprint("hr", __name__, url_prefix="/hr")

MIN_GROUP = 3  # minimum people before an aggregate is shown


@bp.before_request
def guard():
    if g.get("user") is None:
        flash("Please sign in to continue.", "info")
        return redirect(url_for("auth.login"))
    if g.user["role"] != "hr":
        abort(403)


@bp.app_template_filter("fmt_dt")
def fmt_dt(value):
    return value.strftime("%d %b %Y, %H:%M") if value else ""


def _company():
    if "hr_company" not in g:
        g.hr_company = query_one("SELECT company_id FROM users WHERE id=%s", (g.user["id"],))["company_id"]
    return g.hr_company


def _employee_or_404(user_id):
    row = query_one(
        "SELECT id, employee_id, full_name, email, role, status, created_at FROM users "
        "WHERE id=%s AND company_id=%s AND role='employee'", (user_id, _company()))
    if row is None:
        abort(404)
    return row


# ---------------------------------------------------------------- overview

@bp.route("/")
def overview():
    co = _company()
    active = query_one("SELECT COUNT(*) AS n FROM users WHERE company_id=%s AND role='employee' AND status='active'", (co,))["n"]
    rows = query_all(
        "SELECT ar.status, COUNT(*) AS n FROM assignment_recipients ar "
        "JOIN assignments a ON a.id=ar.assignment_id JOIN scenarios s ON s.id=a.scenario_id "
        "WHERE s.company_id=%s GROUP BY ar.status", (co,))
    by = {r["status"]: r["n"] for r in rows}
    awaiting = by.get("assigned", 0)
    completed = by.get("submitted", 0) + by.get("analysed", 0)
    learn_rows = query_all(
        "SELECT lp.status, COUNT(*) AS n FROM learning_progress lp JOIN users u ON u.id=lp.user_id "
        "WHERE u.company_id=%s GROUP BY lp.status", (co,))
    learn = {r["status"]: r["n"] for r in learn_rows}
    open_reviews = query_one(
        "SELECT COUNT(*) AS n FROM review_requests rr JOIN users u ON u.id=rr.user_id "
        "WHERE u.company_id=%s AND rr.status IN ('open','under_review')", (co,))["n"]
    return render_template(
        "hr/pages/overview.html",
        active=active, assigned=awaiting + completed, completed=completed, awaiting=awaiting,
        learn=learn, learning_done=learn.get("completed", 0), open_reviews=open_reviews,
        assign_chart={"labels": ["Awaiting", "Completed"], "values": [awaiting, completed]},
        learn_chart={"labels": ["Not started", "In progress", "Completed"],
                     "values": [learn.get("not_started", 0), learn.get("in_progress", 0), learn.get("completed", 0)]})


# ---------------------------------------------------------------- directory

@bp.route("/directory")
def directory():
    co = _company()
    q = (request.args.get("q") or "").strip()
    team = request.args.get("team", type=int)
    status = request.args.get("status", "")
    sql = ("SELECT u.id, u.employee_id, u.full_name, u.email, u.status, "
           "(SELECT GROUP_CONCAT(t.name ORDER BY t.name SEPARATOR ', ') FROM team_memberships tm "
           " JOIN teams t ON t.id=tm.team_id WHERE tm.user_id=u.id) AS teams "
           "FROM users u WHERE u.company_id=%s AND u.role='employee'")
    params = [co]
    if q:
        sql += " AND (u.full_name LIKE %s OR u.employee_id LIKE %s)"
        params += ["%" + q + "%", "%" + q + "%"]
    if team:
        sql += " AND EXISTS (SELECT 1 FROM team_memberships tm WHERE tm.user_id=u.id AND tm.team_id=%s)"
        params.append(team)
    if status in ("active", "inactive"):
        sql += " AND u.status=%s"
        params.append(status)
    sql += " ORDER BY u.full_name"
    return render_template("hr/pages/directory.html", people=query_all(sql, tuple(params)),
                           teams=query_all("SELECT id, name FROM teams WHERE company_id=%s ORDER BY name", (co,)),
                           q=q, team=team, status=status)


@bp.route("/directory/<int:user_id>")
def directory_detail(user_id):
    person = _employee_or_404(user_id)
    history = query_all(
        "SELECT h.old_status, h.new_status, h.reason, h.changed_at, u.full_name AS changed_by_name "
        "FROM account_status_history h LEFT JOIN users u ON u.id=h.changed_by "
        "WHERE h.user_id=%s ORDER BY h.changed_at DESC, h.id DESC", (user_id,))
    teams = query_all("SELECT t.name FROM team_memberships tm JOIN teams t ON t.id=tm.team_id "
                      "WHERE tm.user_id=%s ORDER BY t.name", (user_id,))
    counts = query_one(
        "SELECT COUNT(*) AS total, SUM(status IN ('submitted','analysed')) AS done "
        "FROM assignment_recipients WHERE user_id=%s", (user_id,))
    return render_template("hr/pages/directory_detail.html", p=person, history=history, teams=teams, counts=counts)


@bp.route("/directory/<int:user_id>/status", methods=["POST"])
def directory_status(user_id):
    action = request.form.get("action")
    if action not in ("deactivate", "reactivate"):
        abort(400)
    target = _employee_or_404(user_id)
    back = redirect(url_for("hr.directory_detail", user_id=user_id))
    if not request.form.get("confirm"):
        flash("Please tick the confirmation box first.", "error")
        return back
    new = "inactive" if action == "deactivate" else "active"
    if target["status"] == new:
        flash("That account is already " + new + ".", "info")
        return back
    reason = (request.form.get("reason") or "").strip()[:255] or None
    db = get_db()
    try:
        # Bumping session_version signs the person out of every device on their next request.
        execute("UPDATE users SET status=%s, session_version=session_version+1 WHERE id=%s",
                (new, user_id), commit=False)
        execute("INSERT INTO account_status_history (user_id, old_status, new_status, changed_by, reason) "
                "VALUES (%s,%s,%s,%s,%s)", (user_id, target["status"], new, g.user["id"], reason), commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    repo.add_audit_log(g.user["id"], "account_" + new, "user", user_id, ip=request.remote_addr)
    flash(target["full_name"] + (" was deactivated. History is kept." if new == "inactive" else " was reactivated."), "success")
    return back


# ---------------------------------------------------------------- scenarios

def _scenario_or_404(scenario_id):
    row = query_one("SELECT * FROM scenarios WHERE id=%s AND company_id=%s", (scenario_id, _company()))
    if row is None:
        abort(404)
    return row


@bp.route("/scenarios")
def scenarios():
    items = query_all(
        "SELECT s.id, s.title, s.status, s.version, s.is_demo, s.published_at, "
        "(SELECT COUNT(*) FROM scenario_competencies sc WHERE sc.scenario_id=s.id) AS comp_count, "
        "(SELECT COUNT(*) FROM assignments a WHERE a.scenario_id=s.id) AS assign_count "
        "FROM scenarios s WHERE s.company_id=%s ORDER BY s.status='archived', s.title, s.version DESC", (_company(),))
    return render_template("hr/pages/scenarios.html", items=items)


@bp.route("/scenarios/<int:scenario_id>")
def scenario_preview(scenario_id):
    s = _scenario_or_404(scenario_id)
    comps = query_all("SELECT c.name, c.description, sc.rubric FROM scenario_competencies sc "
                      "JOIN competencies c ON c.id=sc.competency_id WHERE sc.scenario_id=%s ORDER BY c.name", (scenario_id,))
    return render_template("hr/pages/scenario_preview.html", s=s, comps=comps)


@bp.route("/scenarios/<int:scenario_id>/edit", methods=["GET", "POST"])
def scenario_edit(scenario_id):
    s = _scenario_or_404(scenario_id)
    if s["status"] != "draft":
        flash("Published scenarios are never edited. Create a new version instead.", "info")
        return redirect(url_for("hr.scenario_preview", scenario_id=scenario_id))
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        text = (request.form.get("scenario_text") or "").strip()
        instr = (request.form.get("instructions") or "").strip()
        if not (3 <= len(title) <= 200 and len(text) >= 20 and len(instr) >= 10):
            flash("Please fill in a title, the scenario and the instructions.", "error")
        else:
            execute("UPDATE scenarios SET title=%s, scenario_text=%s, instructions=%s WHERE id=%s AND status='draft'",
                    (title, text, instr, scenario_id))
            repo.add_audit_log(g.user["id"], "scenario_edited", "scenario", scenario_id, ip=request.remote_addr)
            flash("Draft saved.", "success")
            return redirect(url_for("hr.scenario_preview", scenario_id=scenario_id))
    return render_template("hr/pages/scenario_edit.html", s=s)


@bp.route("/scenarios/<int:scenario_id>/action", methods=["POST"])
def scenario_action(scenario_id):
    s = _scenario_or_404(scenario_id)
    action = request.form.get("action")
    if action == "publish":
        has = query_one("SELECT COUNT(*) AS n FROM scenario_competencies WHERE scenario_id=%s", (scenario_id,))["n"]
        if s["status"] != "draft" or not has:
            flash("Only a draft with at least one competency and rubric can be published.", "error")
        else:
            execute("UPDATE scenarios SET status='published', published_at=NOW() WHERE id=%s", (scenario_id,))
            repo.add_audit_log(g.user["id"], "scenario_published", "scenario", scenario_id, ip=request.remote_addr)
            flash("Scenario published. Its rubric is now fixed for the assessments that use it.", "success")
    elif action == "archive":
        if s["status"] != "published":
            flash("Only published scenarios can be archived.", "error")
        else:
            execute("UPDATE scenarios SET status='archived' WHERE id=%s", (scenario_id,))
            repo.add_audit_log(g.user["id"], "scenario_archived", "scenario", scenario_id, ip=request.remote_addr)
            flash("Scenario archived. Past assessments keep their original rubric.", "success")
    elif action == "new_version":
        if s["status"] == "draft":
            flash("This is already a draft. You can edit it directly.", "info")
        else:
            db = get_db()
            try:
                new_id = execute(
                    "INSERT INTO scenarios (company_id, title, scenario_text, instructions, status, version, "
                    "previous_version_id, created_by, is_demo) VALUES (%s,%s,%s,%s,'draft',%s,%s,%s,%s)",
                    (s["company_id"], s["title"], s["scenario_text"], s["instructions"], s["version"] + 1,
                     s["id"], g.user["id"], s["is_demo"]), commit=False)
                execute("INSERT INTO scenario_competencies (scenario_id, competency_id, rubric) "
                        "SELECT %s, competency_id, rubric FROM scenario_competencies WHERE scenario_id=%s",
                        (new_id, scenario_id), commit=False)
                db.commit()
            except Exception:
                db.rollback()
                raise
            repo.add_audit_log(g.user["id"], "scenario_new_version", "scenario", new_id, ip=request.remote_addr)
            flash("A new draft version was created. The earlier version is unchanged.", "success")
            return redirect(url_for("hr.scenario_edit", scenario_id=new_id))
    else:
        abort(400)
    return redirect(url_for("hr.scenario_preview", scenario_id=scenario_id))


# ---------------------------------------------------------------- assignments

@bp.route("/assignments")
def assignments():
    items = query_all(
        "SELECT a.id, a.deadline, a.created_at, s.title, s.version, "
        "COUNT(ar.id) AS total, SUM(ar.status IN ('submitted','analysed')) AS done "
        "FROM assignments a JOIN scenarios s ON s.id=a.scenario_id "
        "LEFT JOIN assignment_recipients ar ON ar.assignment_id=a.id "
        "WHERE s.company_id=%s GROUP BY a.id, a.deadline, a.created_at, s.title, s.version "
        "ORDER BY a.created_at DESC", (_company(),))
    return render_template("hr/pages/assignments.html", items=items)


@bp.route("/assignments/new", methods=["GET", "POST"])
def assignment_new():
    co = _company()
    scen = query_all("SELECT id, title, version FROM scenarios WHERE company_id=%s AND status='published' ORDER BY title", (co,))
    people = query_all("SELECT id, employee_id, full_name FROM users WHERE company_id=%s AND role='employee' "
                       "AND status='active' ORDER BY full_name", (co,))
    teams = query_all("SELECT id, name FROM teams WHERE company_id=%s ORDER BY name", (co,))
    if request.method == "POST":
        sid = request.form.get("scenario_id", type=int)
        deadline = (request.form.get("deadline") or "").strip() or None
        valid_s = {s["id"] for s in scen}
        chosen = set(request.form.getlist("user_ids", type=int))
        for tid in request.form.getlist("team_ids", type=int):
            chosen |= {r["user_id"] for r in query_all(
                "SELECT tm.user_id FROM team_memberships tm JOIN teams t ON t.id=tm.team_id "
                "WHERE tm.team_id=%s AND t.company_id=%s", (tid, co))}
        active_ids = {p["id"] for p in people}          # only authorised, active employees
        skipped_inactive = len(chosen - active_ids)
        chosen &= active_ids
        if sid not in valid_s:
            flash("Please choose a published scenario.", "error")
        elif not chosen:
            flash("Please choose at least one active employee or team.", "error")
        else:
            already = {r["user_id"] for r in query_all(
                "SELECT ar.user_id FROM assignment_recipients ar JOIN assignments a ON a.id=ar.assignment_id "
                "WHERE a.scenario_id=%s", (sid,))}
            fresh = sorted(chosen - already)
            if not fresh:
                flash("Everyone selected already has this scenario. Nothing was added.", "info")
            else:
                db = get_db()
                try:
                    aid = execute("INSERT INTO assignments (scenario_id, assigned_by, deadline, allow_reassessment) "
                                  "VALUES (%s,%s,%s,%s)",
                                  (sid, g.user["id"], deadline, 1 if request.form.get("allow_reassessment") else 0),
                                  commit=False)
                    for uid in fresh:
                        execute("INSERT INTO assignment_recipients (assignment_id, user_id) VALUES (%s,%s)",
                                (aid, uid), commit=False)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                repo.add_audit_log(g.user["id"], "assignment_created", "assignment", aid, ip=request.remote_addr)
                msg = "Assigned to %d employee(s)." % len(fresh)
                if len(chosen) - len(fresh):
                    msg += " %d already had this scenario and were skipped." % (len(chosen) - len(fresh))
                if skipped_inactive:
                    msg += " %d inactive account(s) were skipped." % skipped_inactive
                flash(msg, "success")
                return redirect(url_for("hr.assignments"))
    return render_template("hr/pages/assignment_new.html", scenarios=scen, people=people, teams=teams)


@bp.route("/assignments/<int:assignment_id>")
def assignment_detail(assignment_id):
    a = query_one("SELECT a.id, a.deadline, a.created_at, s.title, s.version FROM assignments a "
                  "JOIN scenarios s ON s.id=a.scenario_id WHERE a.id=%s AND s.company_id=%s", (assignment_id, _company()))
    if a is None:
        abort(404)
    rec = query_all("SELECT u.full_name, u.employee_id, u.status AS account_status, ar.status FROM assignment_recipients ar "
                    "JOIN users u ON u.id=ar.user_id WHERE ar.assignment_id=%s ORDER BY u.full_name", (assignment_id,))
    return render_template("hr/pages/assignment_detail.html", a=a, rec=rec)


# ---------------------------------------------------------------- individual reports

@bp.route("/reports")
def reports():
    people = query_all(
        "SELECT u.id, u.employee_id, u.full_name, u.status, "
        "(SELECT COUNT(*) FROM responses r JOIN assessments a ON a.response_id=r.id "
        " WHERE r.user_id=u.id AND a.analysis_status='completed') AS analysed "
        "FROM users u WHERE u.company_id=%s AND u.role='employee' ORDER BY u.full_name", (_company(),))
    return render_template("hr/pages/reports.html", people=people)


@bp.route("/reports/<int:user_id>")
def report_detail(user_id):
    p = _employee_or_404(user_id)
    asms = query_all(
        "SELECT a.id, a.analysis_status, a.analysis_mode, a.limitations, a.completed_at, r.submitted_at, "
        "r.attempt_no, s.title AS scenario FROM assessments a JOIN responses r ON r.id=a.response_id "
        "JOIN assignment_recipients ar ON ar.id=r.recipient_id JOIN assignments asg ON asg.id=ar.assignment_id "
        "JOIN scenarios s ON s.id=asg.scenario_id WHERE r.user_id=%s ORDER BY r.submitted_at DESC", (user_id,))
    for a in asms:
        a["findings"] = query_all(
            "SELECT cf.id, c.name AS competency, cf.finding, cf.evidence, cf.development_area, cf.recommendation, "
            "cf.confidence, cf.status FROM competency_findings cf JOIN competencies c ON c.id=cf.competency_id "
            "WHERE cf.assessment_id=%s ORDER BY c.name", (a["id"],))
    learning = query_all(
        "SELECT ta.title, ta.duration_minutes, lp.status FROM recommendations rc "
        "JOIN training_activities ta ON ta.id=rc.activity_id LEFT JOIN learning_progress lp ON lp.recommendation_id=rc.id "
        "WHERE rc.user_id=%s ORDER BY ta.title", (user_id,))
    reviews = query_all(
        "SELECT rr.status, rr.concern, rr.outcome, rr.created_at, c.name AS competency FROM review_requests rr "
        "JOIN competency_findings cf ON cf.id=rr.finding_id JOIN competencies c ON c.id=cf.competency_id "
        "WHERE rr.user_id=%s ORDER BY rr.created_at DESC", (user_id,))
    return render_template("hr/pages/report_detail.html", p=p, asms=asms, learning=learning, reviews=reviews)


# ---------------------------------------------------------------- talent explorer

@bp.route("/talent")
def talent():
    co = _company()
    comps = query_all("SELECT id, name FROM competencies WHERE company_id=%s AND is_active=1 ORDER BY name", (co,))
    cid = request.args.get("competency", type=int) or (comps[0]["id"] if comps else None)
    q = (request.args.get("q") or "").strip()
    rows = []
    if cid and cid in {c["id"] for c in comps}:
        sql = ("SELECT u.id, u.full_name, u.employee_id, cf.finding, cf.evidence, cf.confidence, cf.status AS fstatus, "
               "asm.completed_at, asm.analysis_mode FROM users u "
               "LEFT JOIN competency_findings cf ON cf.id = (SELECT cf2.id FROM competency_findings cf2 "
               " JOIN assessments a2 ON a2.id=cf2.assessment_id AND a2.analysis_status='completed' "
               " JOIN responses r2 ON r2.id=a2.response_id WHERE r2.user_id=u.id AND cf2.competency_id=%s "
               " ORDER BY a2.completed_at DESC, cf2.id DESC LIMIT 1) "
               "LEFT JOIN assessments asm ON asm.id=cf.assessment_id "
               "WHERE u.company_id=%s AND u.role='employee' AND u.status='active'")
        params = [cid, co]
        if q:
            sql += " AND (u.full_name LIKE %s OR u.employee_id LIKE %s)"
            params += ["%" + q + "%", "%" + q + "%"]
        sql += " ORDER BY u.full_name"          # alphabetical on purpose: no rankings
        rows = query_all(sql, tuple(params))
    return render_template("hr/pages/talent.html", comps=comps, cid=cid, q=q, rows=rows)


# ---------------------------------------------------------------- matching (next drop)

@bp.route("/matching")
def matching():
    return render_template("hr/pages/matching.html")


# ---------------------------------------------------------------- organisational insights

@bp.route("/insights")
def insights():
    co = _company()
    comp = query_all(
        "SELECT c.name, COUNT(DISTINCT r.user_id) AS people, SUM(cf.confidence='high') AS hi, "
        "SUM(cf.confidence='moderate') AS mo, SUM(cf.confidence='low') AS lo, "
        "SUM(cf.status='insufficient_evidence') AS insufficient "
        "FROM competency_findings cf JOIN competencies c ON c.id=cf.competency_id "
        "JOIN assessments a ON a.id=cf.assessment_id AND a.analysis_status='completed' "
        "JOIN responses r ON r.id=a.response_id WHERE c.company_id=%s GROUP BY c.id, c.name ORDER BY c.name", (co,))
    training = query_all(
        "SELECT ta.title, COUNT(DISTINCT rc.user_id) AS people FROM recommendations rc "
        "JOIN training_activities ta ON ta.id=rc.activity_id WHERE ta.company_id=%s "
        "GROUP BY ta.id, ta.title ORDER BY people DESC, ta.title", (co,))
    return render_template("hr/pages/insights.html", comp=comp, training=training, min_group=MIN_GROUP)


# ---------------------------------------------------------------- governance

@bp.route("/governance")
def governance():
    co = _company()
    reviews = query_all(
        "SELECT rr.id, rr.status, rr.concern, rr.outcome, rr.created_at, rr.resolved_at, u.full_name, "
        "c.name AS competency, cf.finding, cf.evidence, rv.full_name AS reviewer FROM review_requests rr "
        "JOIN users u ON u.id=rr.user_id JOIN competency_findings cf ON cf.id=rr.finding_id "
        "JOIN competencies c ON c.id=cf.competency_id LEFT JOIN users rv ON rv.id=rr.reviewed_by "
        "WHERE u.company_id=%s ORDER BY FIELD(rr.status,'open','under_review','resolved','declined'), rr.created_at DESC", (co,))
    audit = query_all(
        "SELECT l.action, l.target_type, l.target_id, l.created_at, u.full_name AS actor FROM audit_logs l "
        "LEFT JOIN users u ON u.id=l.actor_user_id ORDER BY l.id DESC LIMIT 25")
    status_hist = query_all(
        "SELECT h.old_status, h.new_status, h.reason, h.changed_at, u.full_name, b.full_name AS by_name "
        "FROM account_status_history h JOIN users u ON u.id=h.user_id LEFT JOIN users b ON b.id=h.changed_by "
        "WHERE u.company_id=%s ORDER BY h.id DESC LIMIT 25", (co,))
    role_hist = query_all(
        "SELECT h.old_role, h.new_role, h.reason, h.changed_at, u.full_name, b.full_name AS by_name "
        "FROM hr_role_history h JOIN users u ON u.id=h.user_id LEFT JOIN users b ON b.id=h.changed_by "
        "WHERE u.company_id=%s ORDER BY h.id DESC LIMIT 25", (co,))
    return render_template("hr/pages/governance.html", reviews=reviews, audit=audit,
                           status_hist=status_hist, role_hist=role_hist)


@bp.route("/governance/reviews/<int:review_id>", methods=["POST"])
def review_update(review_id):
    row = query_one("SELECT rr.id, rr.status FROM review_requests rr JOIN users u ON u.id=rr.user_id "
                    "WHERE rr.id=%s AND u.company_id=%s", (review_id, _company()))
    if row is None:
        abort(404)
    status = request.form.get("status")
    outcome = (request.form.get("outcome") or "").strip()
    if status not in ("under_review", "resolved", "declined"):
        abort(400)
    if status in ("resolved", "declined") and len(outcome) < 10:
        flash("Please write a short outcome (at least 10 characters) so the employee understands the decision.", "error")
        return redirect(url_for("hr.governance"))
    final = status in ("resolved", "declined")
    execute("UPDATE review_requests SET status=%s, outcome=%s, reviewed_by=%s, resolved_at=" +
            ("NOW()" if final else "NULL") + " WHERE id=%s",
            (status, outcome or None, g.user["id"], review_id))
    repo.add_audit_log(g.user["id"], "review_" + status, "review_request", review_id, ip=request.remote_addr)
    flash("Review updated.", "success")
    return redirect(url_for("hr.governance"))


# ---------------------------------------------------------------- settings (read-only in this drop)

@bp.route("/settings")
def settings():
    co = _company()
    comps = query_all("SELECT name, description, is_active FROM competencies WHERE company_id=%s ORDER BY name", (co,))
    acts = query_all("SELECT ta.title, ta.resource_type, ta.duration_minutes, ta.is_demo_resource, c.name AS competency "
                     "FROM training_activities ta JOIN competencies c ON c.id=ta.competency_id "
                     "WHERE ta.company_id=%s ORDER BY c.name, ta.title", (co,))
    return render_template("hr/pages/settings.html", comps=comps, acts=acts)
