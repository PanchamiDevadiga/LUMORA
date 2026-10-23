"""Create lumora_db and all tables from schema.sql.

Run from the LUMORA folder:
    python -m scripts.init_db            (safe: only creates what is missing)
    python -m scripts.init_db --reset    (deletes ALL data, then recreates)
"""
import re
import sys
from pathlib import Path

import mysql.connector

from app.config import BASE_DIR, Config
from app.database.connection import connect


def read_statements(path: Path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"--[^\n]*", "", text)  # remove comments (also the ones after code)
    return [s.strip() for s in text.split(";") if s.strip()]


def main():
    reset = "--reset" in sys.argv
    if not Config.DB_USER:
        sys.exit("DB_USER is empty. Fill your .env file first.")

    if reset:
        answer = input(f"This DELETES the database '{Config.DB_NAME}'. Type YES to continue: ")
        if answer.strip() != "YES":
            sys.exit("Cancelled. Nothing was changed.")

    try:
        conn = connect(Config, with_database=False)
    except mysql.connector.Error as exc:
        sys.exit(f"Could not connect to MySQL (error {getattr(exc, 'errno', '?')}). "
                 "Check that MySQL is running and DB_USER / DB_PASSWORD in .env are correct.")

    cur = conn.cursor()
    try:
        if reset:
            cur.execute(f"DROP DATABASE IF EXISTS `{Config.DB_NAME}`")
        for stmt in read_statements(BASE_DIR / "schema.sql"):
            cur.execute(stmt)
        conn.commit()
    except mysql.connector.Error as exc:
        sys.exit(f"Schema error: {exc}")
    finally:
        cur.close()
        conn.close()

    check = connect(Config)
    c = check.cursor()
    c.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
    print(f"Done. Database '{Config.DB_NAME}' is ready with {c.fetchone()[0]} tables.")
    c.close()
    check.close()


if __name__ == "__main__":
    main()
