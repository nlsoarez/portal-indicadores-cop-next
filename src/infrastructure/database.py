from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("COP_PORTAL_DB", "data/portal.db"))

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_segments (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, segment_id)
);

CREATE TABLE IF NOT EXISTS user_performance_segments (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, segment_id)
);

CREATE TABLE IF NOT EXISTS indicator_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    indicator_key TEXT NOT NULL,
    name TEXT NOT NULL,
    target_value REAL,
    direction TEXT NOT NULL DEFAULT 'higher_is_better',
    unit TEXT NOT NULL DEFAULT 'percent',
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(segment_id, indicator_key)
);

CREATE TABLE IF NOT EXISTS indicator_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    indicator_definition_id INTEGER NOT NULL REFERENCES indicator_definitions(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    data_month TEXT NOT NULL,
    value REAL,
    volume INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(segment_id, user_id, indicator_definition_id, data_month, period)
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS indicator_freshness (
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    indicator_definition_id INTEGER NOT NULL REFERENCES indicator_definitions(id) ON DELETE CASCADE,
    data_through TEXT NOT NULL,
    source_key TEXT NOT NULL,
    upload_id INTEGER REFERENCES uploads(id) ON DELETE SET NULL,
    refreshed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (segment_id, indicator_definition_id)
);

CREATE TABLE IF NOT EXISTS access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_results_segment_period ON indicator_results(segment_id, period);
CREATE INDEX IF NOT EXISTS idx_results_user_segment ON indicator_results(user_id, segment_id);
CREATE INDEX IF NOT EXISTS idx_uploads_segment_created ON uploads(segment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_freshness_segment ON indicator_freshness(segment_id);
CREATE INDEX IF NOT EXISTS idx_access_user_created ON access_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_perf_segment ON user_performance_segments(segment_id, user_id);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    with transaction() as conn:
        conn.executescript(SCHEMA)
        # Resíduo de uma versão inicial que não faz parte do escopo atual.
        conn.execute("DROP TABLE IF EXISTS scales")
        _ensure_column(conn, "indicator_definitions", "unit", "TEXT NOT NULL DEFAULT 'percent'")
        _ensure_column(conn, "indicator_results", "data_month", "TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE indicator_results SET data_month=substr(period,1,7) WHERE data_month='' OR data_month IS NULL")
        _migrate_indicator_results_unique(conn)
        _ensure_result_indexes(conn)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_indicator_results_unique(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='indicator_results'"
    ).fetchone()
    table_sql = "" if not row or not row["sql"] else "".join(str(row["sql"]).lower().split())
    expected = "unique(segment_id,user_id,indicator_definition_id,data_month,period)"
    if expected in table_sql:
        return

    conn.execute("DROP TABLE IF EXISTS indicator_results_v2")
    conn.execute(
        """
        CREATE TABLE indicator_results_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            indicator_definition_id INTEGER NOT NULL REFERENCES indicator_definitions(id) ON DELETE CASCADE,
            period TEXT NOT NULL,
            data_month TEXT NOT NULL,
            value REAL,
            volume INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(segment_id, user_id, indicator_definition_id, data_month, period)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO indicator_results_v2(
            id, segment_id, user_id, indicator_definition_id, period, data_month, value, volume, created_at
        )
        SELECT id, segment_id, user_id, indicator_definition_id, period,
               CASE WHEN data_month IS NULL OR data_month='' THEN substr(period,1,7) ELSE data_month END,
               value, volume, created_at
        FROM indicator_results
        """
    )
    conn.execute("DROP TABLE indicator_results")
    conn.execute("ALTER TABLE indicator_results_v2 RENAME TO indicator_results")


def _ensure_result_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_segment_period ON indicator_results(segment_id, period)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_user_segment ON indicator_results(user_id, segment_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_segment_month ON indicator_results(segment_id, data_month)"
    )
