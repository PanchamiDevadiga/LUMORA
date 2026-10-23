"""Login, roles, sessions and password reset. These need MySQL (the test database)."""
import hashlib
import re

from app.auth import services
from app.config import TestConfig
from app.database import repositories as repo
from tests.conftest import (EMP2_EMAIL, EMP_EMAIL, HR_EMAIL, OFF_EMAIL, PASSWORD,
                            login, run_sql)
from app.database.connection import connect


class CsrfOn(TestConfig):
    WTF_CSRF_ENABLED = True


class DevMode(CsrfOn):
    DEBUG = True


def _user(app, email):
    with app.app_context():
        return repo.get_user_by_email(email)


# ---------- passwords ----------

def test_password_is_hashed_not_plain(app):
    user = _user(app, EMP_EMAIL)
    assert user["password_hash"] != PASSWORD
    assert PASSWORD not in user["password_hash"]
    assert services.verify_password(user["password_hash"], PASSWORD)
    assert not services.verify_password(user["password_hash"], "wrong-password1")


def test_password_rules():
    assert services.validate_new_password("abc12345", "abc12345") is None
    assert services.validate_new_password("short1", "short1")
    assert services.validate_new_password("onlyletters", "onlyletters")
    assert services.validate_new_password("abc12345", "different1")


# ---------- login ----------

def test_employee_login_goes_to_employee_page(client):
    resp = login(client, EMP_EMAIL)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/employee/")
    assert client.get("/employee/").status_code == 200


def test_hr_login_goes_to_hr_page(client):
    resp = login(client, HR_EMAIL)
    assert resp.headers["Location"].endswith("/hr/")


def test_wrong_password_and_unknown_email_look_the_same(client):
    a = login(client, EMP_EMAIL, "Wrong@12345")
    b = login(client, "nobody@test.example", "Wrong@12345")
    assert a.status_code == b.status_code == 200
    assert b"could not sign you in" in a.data and b"could not sign you in" in b.data
    assert client.get("/employee/").status_code == 302  # still signed out


def test_inactive_account_cannot_sign_in(client):
    resp = login(client, OFF_EMAIL)
    assert resp.status_code == 200 and b"could not sign you in" in resp.data
    assert client.get("/employee/").status_code == 302


def test_too_many_failures_block_even_the_right_password(client):
    for _ in range(5):
        login(client, EMP_EMAIL, "Wrong@12345")
    resp = login(client, EMP_EMAIL)
    assert resp.status_code == 429
    assert client.get("/employee/").status_code == 302


def test_login_without_csrf_token_is_refused(make_app):
    client = make_app(CsrfOn).test_client()
    assert login(client, EMP_EMAIL).status_code == 400


# ---------- roles ----------

def test_anonymous_is_sent_to_login(client):
    for path in ("/employee/", "/hr/"):
        resp = client.get(path)
        assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_employee_cannot_open_hr_pages(client):
    login(client, EMP_EMAIL)
    assert client.get("/hr/").status_code == 403


def test_hr_cannot_open_employee_pages(client):
    login(client, HR_EMAIL)
    assert client.get("/employee/").status_code == 403


def test_role_cannot_be_chosen_from_the_browser(client):
    client.post("/login", data={"email": EMP_EMAIL, "password": PASSWORD, "role": "hr"})
    assert client.get("/hr/").status_code == 403


# ---------- sessions ----------

def test_logout_ends_the_session(client):
    login(client, EMP_EMAIL)
    client.post("/logout")
    assert client.get("/employee/").status_code == 302


def test_deactivated_user_is_blocked_on_next_request(app, client):
    login(client, EMP_EMAIL)
    assert client.get("/employee/").status_code == 200
    run_sql("UPDATE users SET status = 'inactive' WHERE email = %s", (EMP_EMAIL,))
    assert client.get("/employee/").status_code == 302


def test_other_sessions_end_when_session_version_changes(app, client):
    login(client, EMP2_EMAIL)
    run_sql("UPDATE users SET session_version = session_version + 1 WHERE email = %s", (EMP2_EMAIL,))
    assert client.get("/employee/").status_code == 302


# ---------- password reset ----------

def _token_from(page):
    return re.search(rb"/reset-password/([A-Za-z0-9_\-]+)", page).group(1).decode()


def test_forgot_password_gives_the_same_answer_for_everyone(client):
    a = client.post("/forgot-password", data={"email": EMP_EMAIL})
    b = client.post("/forgot-password", data={"email": "nobody@test.example"})
    assert a.status_code == b.status_code == 200
    assert a.data == b.data
    assert b"/reset-password/" not in a.data


def test_reset_token_is_saved_only_as_a_hash(app):
    user = _user(app, EMP_EMAIL)
    with app.app_context():
        raw = services.create_reset_token(user["id"])
    conn = connect(TestConfig)
    cur = conn.cursor()
    cur.execute("SELECT token_hash FROM password_reset_tokens WHERE user_id = %s", (user["id"],))
    stored = [r[0] for r in cur.fetchall()]
    conn.close()
    assert raw not in stored
    assert hashlib.sha256(raw.encode()).hexdigest() in stored


def test_expired_reset_token_is_rejected(app, client):
    user = _user(app, EMP_EMAIL)
    with app.app_context():
        raw = services.create_reset_token(user["id"], minutes=-1)
    assert client.get(f"/reset-password/{raw}").status_code == 400


def test_full_reset_flow_and_token_works_only_once(make_app):
    client = make_app(DevMode).test_client()
    # CSRF is on in this app, so read the token from each form first
    def csrf(path):
        page = client.get(path).data
        return re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()

    page = client.post("/forgot-password", data={"email": EMP_EMAIL, "csrf_token": csrf("/forgot-password")})
    token = _token_from(page.data)
    path = f"/reset-password/{token}"

    weak = client.post(path, data={"password": "short", "confirm": "short", "csrf_token": csrf(path)})
    assert weak.status_code == 200 and b"at least 8" in weak.data
    assert client.get(path).status_code == 200  # token still valid after a weak password

    new_pw = "Brand@New123"
    done = client.post(path, data={"password": new_pw, "confirm": new_pw, "csrf_token": csrf(path)})
    assert done.status_code == 302
    assert client.get(path).status_code == 400  # second use is refused

    tok = csrf("/login")
    bad = client.post("/login", data={"email": EMP_EMAIL, "password": PASSWORD, "csrf_token": tok})
    assert b"could not sign you in" in bad.data
    good = client.post("/login", data={"email": EMP_EMAIL, "password": new_pw, "csrf_token": csrf("/login")})
    assert good.status_code == 302


def test_reset_link_not_shown_when_not_in_dev_mode(make_app):
    client = make_app(CsrfOn).test_client()
    page = client.get("/forgot-password").data
    tok = re.search(rb'name="csrf_token" value="([^"]+)"', page).group(1).decode()
    resp = client.post("/forgot-password", data={"email": EMP_EMAIL, "csrf_token": tok})
    assert b"/reset-password/" not in resp.data
