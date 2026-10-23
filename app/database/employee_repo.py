"""Queries for the employee portal and the AI pipeline.

Every function that returns private data takes user_id and filters on it,
so one employee can never read another employee's records by changing a URL.
"""
import mysql.connector

from app.database.connection import execute, get_db, query_all, query_one

_ASSIGN_BASE = (
    "SELECT ar.id AS recipient_id, ar.status, a.deadline, a.allow_reassessment, "
    "s.id AS scenario_id, s.title, s.scenario_text, s.instructions, s.version, s.is_demo "
    "FROM assignment_recipients ar "
    "JOIN assignments a ON a.id = ar.assignment_id "
    "JOIN scenarios s ON s.id = a.scenario_id "
)


# ---------- assignments ----------

def list_assignments(user_id):
    return query_all(
        _ASSIGN_BASE + "WHERE ar.user_id = %s "
        "ORDER BY (ar.status = 'assigned') DESC, a.deadline IS NULL, a.deadline, ar.id DESC",
        (user_id,),
    )


def get_assignment(user_id, recipient_id):
    return query_one(_ASSIGN_BASE + "WHERE ar.id = %s AND ar.user_id = %s", (recipient_id, user_id))


def scenario_competencies(scenario_id):
    return query_all(
        "SELECT c.id, c.name, c.description, sc.rubric FROM scenario_competencies sc "
        "JOIN competencies c ON c.id = sc.competency_id WHERE sc.scenario_id = %s ORDER BY c.name",
        (scenario_id,),
    )


def latest_response(recipient_id):
    return query_one(
        "SELECT r.id, r.attempt_no, r.response_text, r.submitted_at, "
        "asm.id AS assessment_id, asm.analysis_status "
        "FROM responses r LEFT JOIN assessments asm ON asm.response_id = r.id "
        "WHERE r.recipient_id = %s ORDER BY r.attempt_no DESC LIMIT 1",
        (recipient_id,),
    )


def create_response_with_assessment(recipient_id, user_id, text, mode, model):
    """Save the response (never edited later) and a pending assessment in ONE transaction.
    Returns (response_id, assessment_id), or None if this attempt already exists."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM responses "
                    "WHERE recipient_id = %s FOR UPDATE", (recipient_id,))
        attempt = cur.fetchone()[0]
        cur.execute("INSERT INTO responses (recipient_id, user_id, attempt_no, response_text) "
                    "VALUES (%s, %s, %s, %s)", (recipient_id, user_id, attempt, text))
        response_id = cur.lastrowid
        cur.execute("INSERT INTO assessments (response_id, analysis_mode, model_name) "
                    "VALUES (%s, %s, %s)", (response_id, mode, model))
        assessment_id = cur.lastrowid
        cur.execute("UPDATE assignment_recipients SET status = 'submitted' WHERE id = %s", (recipient_id,))
        db.commit()
        return response_id, assessment_id
    except mysql.connector.IntegrityError:
        db.rollback()
        return None
    except mysql.connector.Error:
        db.rollback()
        raise
    finally:
        cur.close()


# ---------- dashboard ----------

def assignment_counts(user_id):
    row = query_one(
        "SELECT COUNT(*) AS total, "
        "SUM(status = 'assigned') AS pending, "
        "SUM(status IN ('submitted', 'analysed')) AS done "
        "FROM assignment_recipients WHERE user_id = %s", (user_id,))
    return {k: int(row[k] or 0) for k in ("total", "pending", "done")}


def learning_counts(user_id):
    row = query_one(
        "SELECT COUNT(*) AS total, SUM(status = 'completed') AS done "
        "FROM learning_progress WHERE user_id = %s", (user_id,))
    return {"total": int(row["total"] or 0), "done": int(row["done"] or 0)}


# ---------- assessments, findings ----------

_ASM_BASE = (
    "SELECT asm.id AS assessment_id, asm.analysis_status, asm.analysis_mode, asm.model_name, "
    "asm.limitations, asm.error_message, asm.completed_at, "
    "r.id AS response_id, r.attempt_no, r.submitted_at, r.response_text, "
    "ar.id AS recipient_id, s.title, s.id AS scenario_id "
    "FROM assessments asm "
    "JOIN responses r ON r.id = asm.response_id "
    "JOIN assignment_recipients ar ON ar.id = r.recipient_id "
    "JOIN assignments a ON a.id = ar.assignment_id "
    "JOIN scenarios s ON s.id = a.scenario_id "
)


def list_assessments(user_id, limit=None):
    sql = _ASM_BASE + "WHERE r.user_id = %s ORDER BY r.submitted_at DESC, asm.id DESC"
    if limit:
        sql += " LIMIT %d" % int(limit)
    return query_all(sql, (user_id,))


def get_assessment(user_id, assessment_id):
    return query_one(_ASM_BASE + "WHERE asm.id = %s AND r.user_id = %s", (assessment_id, user_id))


def findings_for(assessment_id):
    return query_all(
        "SELECT cf.id, cf.finding, cf.evidence, cf.development_area, cf.recommendation, "
        "cf.confidence, cf.status, c.name AS competency, "
        "(SELECT rr.status FROM review_requests rr WHERE rr.finding_id = cf.id "
        " ORDER BY rr.created_at DESC, rr.id DESC LIMIT 1) AS review_status "
        "FROM competency_findings cf JOIN competencies c ON c.id = cf.competency_id "
        "WHERE cf.assessment_id = %s ORDER BY c.name", (assessment_id,))


def comparison_rows(user_id):
    return query_all(
        "SELECT s.id AS scenario_id, s.title, r.submitted_at, asm.id AS assessment_id, "
        "c.name AS competency, cf.status, "
        "(cf.development_area IS NOT NULL AND cf.development_area <> '') AS has_dev "
        "FROM competency_findings cf "
        "JOIN assessments asm ON asm.id = cf.assessment_id "
        "JOIN responses r ON r.id = asm.response_id "
        "JOIN assignment_recipients ar ON ar.id = r.recipient_id "
        "JOIN assignments a ON a.id = ar.assignment_id "
        "JOIN scenarios s ON s.id = a.scenario_id "
        "JOIN competencies c ON c.id = cf.competency_id "
        "WHERE r.user_id = %s AND asm.analysis_status = 'completed' "
        "ORDER BY s.id, r.submitted_at, asm.id, c.name", (user_id,))


# ---------- AI pipeline ----------

def load_for_analysis(assessment_id):
    return query_one(
        "SELECT asm.id AS assessment_id, asm.analysis_status, r.id AS response_id, "
        "r.response_text, r.user_id, ar.id AS recipient_id, s.id AS scenario_id, "
        "s.title, s.scenario_text, s.instructions "
        "FROM assessments asm JOIN responses r ON r.id = asm.response_id "
        "JOIN assignment_recipients ar ON ar.id = r.recipient_id "
        "JOIN assignments a ON a.id = ar.assignment_id "
        "JOIN scenarios s ON s.id = a.scenario_id WHERE asm.id = %s", (assessment_id,))


def claim_assessment(assessment_id):
    """Atomically move pending/failed -> processing. False means someone else has it (no double work)."""
    return execute(
        "UPDATE assessments SET analysis_status = 'processing', attempt_count = attempt_count + 1, "
        "error_message = NULL WHERE id = %s AND analysis_status IN ('pending', 'failed')",
        (assessment_id,), rowcount=True) == 1


def mark_failed(assessment_id, message):
    execute("UPDATE assessments SET analysis_status = 'failed', error_message = %s WHERE id = %s",
            (message[:250], assessment_id))


def save_findings(job, findings, limitations, mode, model):
    """Store findings, recommended activities and learning rows, and mark the work done. One transaction."""
    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        for f in findings:
            cur.execute("SELECT id FROM competencies WHERE name = %s AND company_id = "
                        "(SELECT company_id FROM scenarios WHERE id = %s)", (f["competency"], job["scenario_id"]))
            comp = cur.fetchone()
            cur.execute(
                "INSERT INTO competency_findings (assessment_id, competency_id, finding, evidence, "
                "development_area, recommendation, confidence, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (job["assessment_id"], comp["id"], f["finding"], f["evidence"], f["development_area"],
                 f["recommendation"], f["confidence"], f["status"]))
            finding_id = cur.lastrowid
            if f["status"] == "completed" and f["development_area"]:
                cur.execute("SELECT id, title FROM training_activities WHERE competency_id = %s "
                            "AND is_active = 1 ORDER BY id LIMIT 2", (comp["id"],))
                for act in cur.fetchall():
                    cur.execute("INSERT IGNORE INTO recommendations (finding_id, activity_id, user_id, reason) "
                                "VALUES (%s, %s, %s, %s)",
                                (finding_id, act["id"], job["user_id"], f["development_area"]))
                    if cur.lastrowid:
                        cur.execute("INSERT IGNORE INTO learning_progress (recommendation_id, user_id) "
                                    "VALUES (%s, %s)", (cur.lastrowid, job["user_id"]))
        cur.execute("UPDATE assessments SET analysis_status = 'completed', analysis_mode = %s, "
                    "model_name = %s, limitations = %s, error_message = NULL, completed_at = NOW() "
                    "WHERE id = %s", (mode, model, limitations, job["assessment_id"]))
        cur.execute("UPDATE assignment_recipients SET status = 'analysed' WHERE id = %s", (job["recipient_id"],))
        db.commit()
    except mysql.connector.Error:
        db.rollback()
        raise
    finally:
        cur.close()


# ---------- learning ----------

def list_learning(user_id):
    return query_all(
        "SELECT rc.id AS reco_id, rc.reason, ta.title, ta.description, ta.learning_objective, "
        "ta.resource_type, ta.resource_url, ta.is_demo_resource, ta.duration_minutes, "
        "c.name AS competency, lp.status, lp.completed_at, s.title AS scenario_title "
        "FROM recommendations rc "
        "JOIN training_activities ta ON ta.id = rc.activity_id "
        "JOIN competencies c ON c.id = ta.competency_id "
        "JOIN learning_progress lp ON lp.recommendation_id = rc.id "
        "JOIN competency_findings cf ON cf.id = rc.finding_id "
        "JOIN assessments asm ON asm.id = cf.assessment_id "
        "JOIN responses r ON r.id = asm.response_id "
        "JOIN assignment_recipients ar ON ar.id = r.recipient_id "
        "JOIN assignments a ON a.id = ar.assignment_id "
        "JOIN scenarios s ON s.id = a.scenario_id "
        "WHERE rc.user_id = %s ORDER BY (lp.status = 'completed'), rc.created_at DESC, rc.id DESC",
        (user_id,))


def set_learning_status(user_id, reco_id, status):
    """Returns False when this recommendation does not belong to the user."""
    row = query_one("SELECT id FROM learning_progress WHERE recommendation_id = %s AND user_id = %s",
                    (reco_id, user_id))
    if row is None:
        return False
    execute("UPDATE learning_progress SET status = %s, completed_at = "
            "IF(%s = 'completed', NOW(), NULL) WHERE id = %s", (status, status, row["id"]))
    return True


# ---------- review requests ----------

def reviewable_findings(user_id):
    return query_all(
        "SELECT cf.id, c.name AS competency, s.title, r.submitted_at "
        "FROM competency_findings cf "
        "JOIN assessments asm ON asm.id = cf.assessment_id "
        "JOIN responses r ON r.id = asm.response_id "
        "JOIN assignment_recipients ar ON ar.id = r.recipient_id "
        "JOIN assignments a ON a.id = ar.assignment_id "
        "JOIN scenarios s ON s.id = a.scenario_id "
        "JOIN competencies c ON c.id = cf.competency_id "
        "WHERE r.user_id = %s AND asm.analysis_status = 'completed' "
        "ORDER BY r.submitted_at DESC, c.name", (user_id,))


def list_reviews(user_id):
    return query_all(
        "SELECT rr.id, rr.concern, rr.status, rr.outcome, rr.created_at, rr.resolved_at, "
        "c.name AS competency, s.title "
        "FROM review_requests rr "
        "JOIN competency_findings cf ON cf.id = rr.finding_id "
        "JOIN competencies c ON c.id = cf.competency_id "
        "JOIN assessments asm ON asm.id = cf.assessment_id "
        "JOIN responses r ON r.id = asm.response_id "
        "JOIN assignment_recipients ar ON ar.id = r.recipient_id "
        "JOIN assignments a ON a.id = ar.assignment_id "
        "JOIN scenarios s ON s.id = a.scenario_id "
        "WHERE rr.user_id = %s ORDER BY rr.created_at DESC, rr.id DESC", (user_id,))


def open_review_exists(user_id, finding_id):
    return query_one("SELECT id FROM review_requests WHERE user_id = %s AND finding_id = %s "
                     "AND status IN ('open', 'under_review')", (user_id, finding_id)) is not None


def create_review(user_id, finding_id, concern):
    return execute("INSERT INTO review_requests (finding_id, user_id, concern) VALUES (%s, %s, %s)",
                   (finding_id, user_id, concern))
