"""Test setup. The tests use a SEPARATE database called lumora_test_db."""
import pytest
import mysql.connector

from app import create_app
from app.auth import services
from app.config import BASE_DIR, TestConfig
from app.database import repositories as repo
from app.database.connection import connect

PASSWORD = "Test@12345"
EMP_EMAIL = "emp@test.example"
EMP2_EMAIL = "emp2@test.example"
HR_EMAIL = "hr@test.example"
OFF_EMAIL = "gone@test.example"

TABLES = ["review_requests", "learning_progress", "recommendations", "competency_findings", "assessments",
          "responses", "assignment_recipients", "assignments", "training_activities", "scenario_competencies",
          "scenarios", "competencies", "login_attempts", "password_reset_tokens", "audit_logs",
          "account_status_history", "hr_role_history", "team_memberships", "teams", "users", "companies"]


@pytest.fixture(scope="session")
def db_ready():
    try:
        conn = connect(TestConfig, with_database=False)
    except mysql.connector.Error:
        pytest.skip("MySQL is not reachable. Check DB_USER and DB_PASSWORD in .env")
    schema = (BASE_DIR / "schema.sql").read_text(encoding="utf-8").replace("lumora_db", TestConfig.DB_NAME)
    import re
    schema = re.sub(r"--[^\n]*", "", schema)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{TestConfig.DB_NAME}`")
    for stmt in [s.strip() for s in schema.split(";") if s.strip()]:
        cur.execute(stmt)
    conn.commit()
    cur.close()
    conn.close()
    yield
    conn = connect(TestConfig, with_database=False)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{TestConfig.DB_NAME}`")
    cur.close()
    conn.close()


def run_sql(sql, params=()):
    """Direct SQL on the test database (used by tests to change data)."""
    conn = connect(TestConfig)
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture
def make_app(db_ready):
    def _make(config_class=TestConfig):
        conn = connect(TestConfig)
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in TABLES:
            cur.execute(f"TRUNCATE TABLE {table}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        cur.close()
        conn.close()

        app = create_app(config_class)
        with app.app_context():
            company = repo.ensure_company("Test Co")
            pw = services.hash_password(PASSWORD)
            repo.create_user(company, "E1", "Eva Employee", EMP_EMAIL, "employee", pw)
            repo.create_user(company, "E2", "Eli Employee", EMP2_EMAIL, "employee", pw)
            repo.create_user(company, "H1", "Hana HR", HR_EMAIL, "hr", pw)
            gone = repo.create_user(company, "E3", "Gary Gone", OFF_EMAIL, "employee", pw)
            run_sql("UPDATE users SET status = 'inactive' WHERE id = %s", (gone,))
        return app
    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email, password=PASSWORD, remember=False):
    data = {"email": email, "password": password}
    if remember:
        data["remember"] = "on"
    return client.post("/login", data=data)
