"""MySQL connection helpers. Every query must use %s placeholders."""
import mysql.connector
from flask import current_app, g


def _val(cfg, key):
    """Read a setting from a Flask config (dict) or from the Config class."""
    return cfg[key] if hasattr(cfg, "__getitem__") else getattr(cfg, key)


def build_params(cfg, with_database=True):
    params = {
        "host": _val(cfg, "DB_HOST"),
        "port": _val(cfg, "DB_PORT"),
        "user": _val(cfg, "DB_USER"),
        "password": _val(cfg, "DB_PASSWORD"),
        "charset": "utf8mb4",
        "use_pure": True,
        "connection_timeout": 10,
    }
    if with_database:
        params["database"] = _val(cfg, "DB_NAME")
    return params


def connect(cfg, with_database=True):
    """Open a new connection. Used by scripts and by get_db()."""
    return mysql.connector.connect(**build_params(cfg, with_database))


def get_db():
    """One connection per web request, reused until the request ends."""
    if "db" not in g:
        g.db = connect(current_app.config)
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except mysql.connector.Error:
            pass


def query_all(sql, params=()):
    cur = get_db().cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()


def query_one(sql, params=()):
    cur = get_db().cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        cur.close()


def execute(sql, params=(), commit=True, rowcount=False):
    """Run INSERT/UPDATE/DELETE. Returns the new row id, or the changed-row count if rowcount=True."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(sql, params)
        if commit:
            db.commit()
        return cur.rowcount if rowcount else cur.lastrowid
    except mysql.connector.Error:
        db.rollback()
        raise
    finally:
        cur.close()
