"""A small page and a health check so we can confirm the app runs."""
import mysql.connector
from flask import Blueprint, current_app, jsonify

from app.database.connection import get_db

bp = Blueprint("health", __name__)


def _db_status():
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
        count = cur.fetchone()[0]
        cur.close()
        return "connected", count
    except mysql.connector.Error as exc:
        current_app.logger.warning("Database check failed: error %s", getattr(exc, "errno", "unknown"))
        return "not connected", 0


@bp.route("/health")
def health():
    status, tables = _db_status()
    return jsonify(
        app="LUMORA",
        phase=2,
        auth_mode=current_app.config["AUTH_MODE"],
        ai_mode=current_app.config["AI_MODE"],
        database=status,
        tables=tables,
    )
