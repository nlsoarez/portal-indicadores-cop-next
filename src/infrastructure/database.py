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

CREATE TABLE IF NOT EXISTS indicator_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    indicator_key TEXT NOT NULL,
    name TEXT NOT NULL,
    target_value REAL,
    direction TEXT NOT NULL DEFAULT 'higher_is_better',
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(segment_id, indicator_key)
);

CREATE TABLE IF NOT EXISTS indicator_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    indicator_definition_id INTEGER NOT NULL REFERENCES indicator_definitions(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    value REAL,
    volume INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(segment_id, user_id, indicator_definition_id, period)
);

CREATE TABLE IF NOT EXISTS scales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    work_date TEXT NOT NULL,
    assignment TEXT NOT NULL,
    UNIQUE(segment_id, user_id, work_date)
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
CREATE INDEX IF NOT EXISTS idx_scale_segment_date ON scales(segment_id, work_date);
CREATE INDEX IF NOT EXISTS idx_uploads_segment_created ON uploads(segment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_freshness_segment ON indicator_freshness(segment_id);
CREATE INDEX IF NOT EXISTS idx_access_user_created ON access_logs(user_id, created_at DESC);
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
