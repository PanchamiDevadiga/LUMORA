"""Database queries. All SQL uses %s placeholders, never string formatting of values."""
import json

import mysql.connector

from app.database.connection import execute, get_db, query_one

USER_COLUMNS = (
    "id, company_id, employee_id, full_name, email, role, status, "
    "password_hash, session_version, "
    "(SELECT t.name FROM team_memberships tm JOIN teams t ON t.id = tm.team_id "
    " WHERE tm.user_id = users.id ORDER BY t.name LIMIT 1) AS team"
)


# ---------- users, companies, teams ----------

def get_user_by_email(email):
    return query_one(f"SELECT {USER_COLUMNS} FROM users WHERE email = %s", (email,))


def get_user_by_id(user_id):
    return query_one(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,))


def create_user(company_id, employee_id, full_name, email, role, password_hash):
    return execute(
        "INSERT INTO users (company_id, employee_id, full_name, email, role, password_hash) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (company_id, employee_id, full_name, email, role, password_hash),
    )


def ensure_company(name):
    row = query_one("SELECT id FROM companies WHERE name = %s", (name,))
    return row["id"] if row else execute("INSERT INTO companies (name) VALUES (%s)", (name,))


def ensure_team(company_id, name):
    row = query_one("SELECT id FROM teams WHERE company_id = %s AND name = %s", (company_id, name))
    if row:
        return row["id"]
    return execute("INSERT INTO teams (company_id, name) VALUES (%s, %s)", (company_id, name))


def add_team_member(user_id, team_id):
    execute("INSERT IGNORE INTO team_memberships (user_id, team_id) VALUES (%s, %s)", (user_id, team_id))


def add_role_history(user_id, old_role, new_role, changed_by, reason):
    execute(
        "INSERT INTO hr_role_history (user_id, old_role, new_role, changed_by, reason) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, old_role, new_role, changed_by, reason),
    )


# ---------- login attempts (rate limiting) ----------

def record_login_attempt(email, ip, was_successful):
    execute(
        "INSERT INTO login_attempts (email, ip_address, was_successful) VALUES (%s, %s, %s)",
        (email[:190], ip, 1 if was_successful else 0),
    )


def count_failed_logins(email, minutes):
    row = query_one(
        "SELECT COUNT(*) AS n FROM login_attempts "
        "WHERE email = %s AND was_successful = 0 AND attempted_at > NOW() - INTERVAL %s MINUTE",
        (email[:190], minutes),
    )
    return row["n"]


def count_failed_logins_by_ip(ip, minutes):
    row = query_one(
        "SELECT COUNT(*) AS n FROM login_attempts "
        "WHERE ip_address = %s AND was_successful = 0 AND attempted_at > NOW() - INTERVAL %s MINUTE",
        (ip, minutes),
    )
    return row["n"]


def delete_failed_logins(email):
    execute("DELETE FROM login_attempts WHERE email = %s AND was_successful = 0", (email[:190],))


# ---------- audit log ----------

def add_audit_log(actor_user_id, action, target_type=None, target_id=None, details=None, ip=None):
    """Never put passwords, tokens or full responses in details."""
    execute(
        "INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, details, ip_address) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (actor_user_id, action, target_type, target_id,
         json.dumps(details) if details is not None else None, ip),
    )


def count_recent_audit(action, ip, minutes):
    row = query_one(
        "SELECT COUNT(*) AS n FROM audit_logs "
        "WHERE action = %s AND ip_address = %s AND created_at > NOW() - INTERVAL %s MINUTE",
        (action, ip, minutes),
    )
    return row["n"]


# ---------- password reset tokens (only hashes are stored) ----------

def invalidate_reset_tokens(user_id):
    execute(
        "UPDATE password_reset_tokens SET used_at = UTC_TIMESTAMP() "
        "WHERE user_id = %s AND used_at IS NULL",
        (user_id,),
    )


def insert_reset_token(user_id, token_hash, minutes):
    execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
        "VALUES (%s, %s, UTC_TIMESTAMP() + INTERVAL %s MINUTE)",
        (user_id, token_hash, minutes),
    )


def get_valid_reset_token(token_hash):
    return query_one(
        "SELECT t.id, t.user_id FROM password_reset_tokens t "
        "JOIN users u ON u.id = t.user_id "
        "WHERE t.token_hash = %s AND t.used_at IS NULL "
        "AND t.expires_at > UTC_TIMESTAMP() AND u.status = 'active'",
        (token_hash,),
    )


def consume_reset_token_and_set_password(token_id, user_id, password_hash):
    """Use the token once and change the password in ONE transaction.
    Returns False if the token was already used or has expired."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "UPDATE password_reset_tokens SET used_at = UTC_TIMESTAMP() "
            "WHERE id = %s AND used_at IS NULL AND expires_at > UTC_TIMESTAMP()",
            (token_id,),
        )
        if cur.rowcount != 1:
            db.rollback()
            return False
        cur.execute(
            "UPDATE users SET password_hash = %s, session_version = session_version + 1 WHERE id = %s",
            (password_hash, user_id),
        )
        cur.execute(
            "UPDATE password_reset_tokens SET used_at = UTC_TIMESTAMP() "
            "WHERE user_id = %s AND used_at IS NULL",
            (user_id,),
        )
        db.commit()
        return True
    except mysql.connector.Error:
        db.rollback()
        raise
    finally:
        cur.close()


def update_password(user_id, password_hash):
    """Change a password and sign the user out everywhere else (session_version + 1)."""
    execute(
        "UPDATE users SET password_hash = %s, session_version = session_version + 1 WHERE id = %s",
        (password_hash, user_id),
    )
