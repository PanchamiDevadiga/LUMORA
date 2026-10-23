"""Check that Python can reach MySQL:  python -m scripts.check_db"""
import sys

import mysql.connector

from app.config import Config
from app.database.connection import connect

try:
    conn = connect(Config, with_database=False)
    cur = conn.cursor()
    cur.execute("SELECT VERSION()")
    print("MySQL connection OK. Server version:", cur.fetchone()[0])
    cur.execute("SHOW DATABASES LIKE %s", (Config.DB_NAME,))
    print(f"Database '{Config.DB_NAME}':", "found" if cur.fetchone() else "not created yet")
    cur.close()
    conn.close()
except mysql.connector.Error as exc:
    sys.exit(f"Connection failed (error {getattr(exc, 'errno', '?')}). "
             "Is MySQL running? Are DB_USER and DB_PASSWORD in .env correct?")
