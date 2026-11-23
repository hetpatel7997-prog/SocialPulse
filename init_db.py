"""Create the MySQL database (if missing) and all tables.

Run once:  python init_db.py
"""
import os
import pymysql
from config import Config
from app import create_app
from extensions import db


def create_database():
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
    )
    name = os.environ.get("DB_NAME", "socialpulse")
    if not name.replace("_", "").isalnum():
        raise SystemExit("DB_NAME may only contain letters, numbers and underscores.")
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.close()
    print(f"Database '{name}' is ready.")


if __name__ == "__main__":
    create_database()
    app = create_app(Config)
    with app.app_context():
        db.create_all()
        print("Tables created:", ", ".join(sorted(db.metadata.tables)))
