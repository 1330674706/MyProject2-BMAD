"""每请求一条连接；事务边界不在这里（见 tx.py）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g

from src.data.migrations import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 1000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def initialize(db_path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        apply_migrations(conn, MIGRATIONS_DIR)
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["LAB_DB_PATH"])
    return g.db


def close_db(_exception=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()