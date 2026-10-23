"""Employee portal: isolation, submission, analysis, learning and reviews. These need MySQL (test database)."""
import pytest

from app.ai import schemas, service
from app.database import repositories as repo
from app.database.connection import execute, query_all, query_one
from tests.conftest import EMP2_EMAIL, EMP_EMAIL, HR_EMAIL, login

GOOD = ("I would let the client know about the delay today and explain what happened. "
        "I will take responsibility and list the options for recovering time.")


@pytest.fixture
def world(app):
    """One scenario assigned to Eva (EMP) and Eli (EMP2), with one training activity per competency."""
    with app.app_context():
        eva, eli = repo.get_user_by_email(EMP_EMAIL), repo.get_user_by_email(EMP2_EMAIL)
        hr = repo.get_user_by_email(HR_EMAIL)
        cid = eva["company_id"]
        comp = {n: execute("INSERT INTO competencies (company_id, name, description) VALUES (%s, %s, 'd')", (cid, n))
                for n in ("Communication", "Accountability", "Problem Solving")}
        for n, c in comp.items():
            execute("INSERT INTO training_activities (company_id, competency_id, title, description, "
                    "learning_objective) VALUES (%s, %s, %s, 'd', 'o')", (cid, c, f"Practise {n}"))
        sid = execute("INSERT INTO scenarios (company_id, title, scenario_text, instructions, status, created_by) "
                      "VALUES (%s, 'Late delivery', 'text', 'instr', 'published', %s)", (cid, hr["id"]))
        for c in comp.values():
            execute("INSERT INTO scenario_competencies (scenario_id, competency_id, rubric) VALUES (%s, %s, 'r')", (sid, c))
        aid = execute("INSERT INTO assignments (scenario_id, assigned_by) VALUES (%s, %s)", (sid, hr["id"]))
        rec = {u["id"]: execute("INSERT INTO assignment_recipients (assignment_id, user_id) VALUES (%s, %s)",
                                (aid, u["id"])) for u in (eva, eli)}
        return {"eva": eva["id"], "eli": eli["id"], "eva_rec": rec[eva["id"]], "eli_rec": rec[eli["id"]]}


def submit(client, rec, text=GOOD):
    return client.post(f"/employee/assessments/{rec}/submit", data={"response_text": text})


def test_employee_pages_load(client, world):
    login(client, EMP_EMAIL)
    for path in ("/employee/", "/employee/assessments", "/employee/insights", "/employee/learning",
                 "/employee/progress", "/employee/reviews", "/employee/reviews/new", "/employee/profile",
                 f"/employee/assessments/{world['eva_rec']}"):
        assert client.get(path).status_code == 200, path


def test_employee_sees_only_own_assignment(client, world):
    login(client, EMP_EMAIL)
    assert client.get(f"/employee/assessments/{world['eli_rec']}").status_code == 404
    assert submit(client, world["eli_rec"]).status_code == 404


def test_submission_is_saved_and_analysed_in_mock_mode(client, app, world):
    login(client, EMP_EMAIL)
    resp = submit(client, world["eva_rec"])
    assert resp.status_code == 302 and "/employee/insights/" in resp.headers["Location"]
    with app.app_context():
        row = query_one("SELECT response_text FROM responses WHERE user_id = %s", (world["eva"],))
        assert row["response_text"] == GOOD
        asm = query_one("SELECT analysis_status, analysis_mode FROM assessments")
        assert asm == {"analysis_status": "completed", "analysis_mode": "mock"}
        findings = query_all("SELECT evidence, status FROM competency_findings")
        assert len(findings) == 3
        for f in findings:
            if f["status"] == "completed":
                assert schemas.evidence_is_real(f["evidence"], GOOD)
        assert query_one("SELECT status FROM assignment_recipients WHERE id = %s", (world["eva_rec"],))["status"] == "analysed"
    page = client.get(resp.headers["Location"])
    assert b"Demonstration analysis" in page.data


def test_duplicate_submission_is_blocked_and_original_kept(client, app, world):
    login(client, EMP_EMAIL)
    submit(client, world["eva_rec"])
    again = submit(client, world["eva_rec"], "A different answer that is long enough to be accepted here.")
    assert again.status_code == 302
    with app.app_context():
        rows = query_all("SELECT response_text FROM responses")
        assert len(rows) == 1 and rows[0]["response_text"] == GOOD


def test_short_response_is_rejected(client, app, world):
    login(client, EMP_EMAIL)
    assert submit(client, world["eva_rec"], "too short").status_code == 400
    with app.app_context():
        assert query_all("SELECT id FROM responses") == []


def test_other_employee_cannot_open_my_insights(client, app, world):
    login(client, EMP_EMAIL)
    location = submit(client, world["eva_rec"]).headers["Location"]
    client.post("/logout")
    login(client, EMP2_EMAIL)
    assert client.get(location).status_code == 404


def test_ai_failure_keeps_response_and_allows_retry(client, app, world, monkeypatch):
    app.config["AI_MODE"], app.config["AI_MODEL"], app.config["AI_API_KEY"] = "live", "m", "k"

    def boom(job, competencies):
        raise service.AIUnavailable("could not reach the AI service")
    monkeypatch.setattr(service, "_call_live", boom)

    login(client, EMP_EMAIL)
    submit(client, world["eva_rec"])
    with app.app_context():
        asm = query_one("SELECT id, analysis_status FROM assessments")
        assert asm["analysis_status"] == "failed"
        assert query_one("SELECT response_text FROM responses")["response_text"] == GOOD
        assert query_all("SELECT id FROM competency_findings") == []  # nothing fabricated

    app.config["AI_MODE"] = "mock"  # service is back: controlled retry
    assert client.post(f"/employee/assessments/analysis/{asm['id']}/retry").status_code == 302
    with app.app_context():
        assert query_one("SELECT analysis_status FROM assessments")["analysis_status"] == "completed"


def test_analysis_cannot_run_twice_at_once(client, app, world):
    login(client, EMP_EMAIL)
    submit(client, world["eva_rec"])
    with app.app_context():
        asm_id = query_one("SELECT id FROM assessments")["id"]
        assert service.analyse(asm_id)[0] == "busy"  # already completed, so it will not be claimed again


def test_learning_activity_can_be_completed_only_by_its_owner(client, app, world):
    login(client, EMP_EMAIL)
    submit(client, world["eva_rec"])
    with app.app_context():
        reco = query_one("SELECT id FROM recommendations LIMIT 1")
    assert reco is not None
    assert client.get("/employee/learning").status_code == 200
    client.post("/logout")
    login(client, EMP2_EMAIL)
    assert client.post(f"/employee/learning/{reco['id']}", data={"status": "completed"}).status_code == 404
    client.post("/logout")
    login(client, EMP_EMAIL)
    assert client.post(f"/employee/learning/{reco['id']}", data={"status": "completed"}).status_code == 302
    with app.app_context():
        assert query_one("SELECT status FROM learning_progress")["status"] == "completed"


def test_review_request_created_once_and_only_for_own_findings(client, app, world):
    login(client, EMP_EMAIL)
    submit(client, world["eva_rec"])
    with app.app_context():
        finding = query_one("SELECT id FROM competency_findings LIMIT 1")["id"]
    data = {"finding_id": finding, "concern": "The quoted sentence does not show this."}
    assert client.post("/employee/reviews/new", data=data).status_code == 302
    assert client.post("/employee/reviews/new", data=data).status_code == 302  # duplicate: redirected, not added
    with app.app_context():
        assert len(query_all("SELECT id FROM review_requests")) == 1
    client.post("/logout")
    login(client, EMP2_EMAIL)
    assert client.post("/employee/reviews/new", data=data).status_code == 400  # not Eli's finding
    with app.app_context():
        assert len(query_all("SELECT id FROM review_requests")) == 1


def test_hr_cannot_use_employee_pages_or_submit(client, world):
    login(client, HR_EMAIL)
    assert client.get("/employee/assessments").status_code == 403
    assert submit(client, world["eva_rec"]).status_code == 403


def test_password_change_needs_current_password(client, app):
    login(client, EMP_EMAIL)
    bad = client.post("/employee/profile/password", data={"current_password": "wrong", "new_password": "Brand New 9", "confirm_password": "Brand New 9"})
    assert bad.status_code == 302
    good = client.post("/employee/profile/password", data={"current_password": "Test@12345", "new_password": "Brand New 9", "confirm_password": "Brand New 9"})
    assert good.status_code == 302
    assert client.get("/employee/").status_code == 200  # this browser stays signed in
    client.post("/logout")
    assert login(client, EMP_EMAIL, "Brand New 9").status_code == 302
