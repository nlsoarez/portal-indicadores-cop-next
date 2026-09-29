from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("POSTGRES_URL_NON_POOLING")
    or ""
).strip()
DB_PATH = Path(os.environ.get("COP_PORTAL_DB", "data/portal.db"))
POSTGRES_APP_SCHEMA = "cop_portal"


SQLITE_SCHEMA = """
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
CREATE INDEX IF NOT EXISTS idx_freshness_definition ON indicator_freshness(indicator_definition_id);
CREATE INDEX IF NOT EXISTS idx_access_user_created ON access_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_perf_segment ON user_performance_segments(segment_id, user_id);
"""


POSTGRES_SCHEMA = """
CREATE SCHEMA IF NOT EXISTS cop_portal;
SET search_path TO cop_portal, public;
REVOKE ALL ON SCHEMA cop_portal FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS segments (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_segments (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    segment_id BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, segment_id)
);

CREATE TABLE IF NOT EXISTS user_performance_segments (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    segment_id BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, segment_id)
);

CREATE TABLE IF NOT EXISTS indicator_definitions (
    id BIGSERIAL PRIMARY KEY,
    segment_id BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    indicator_key TEXT NOT NULL,
    name TEXT NOT NULL,
    target_value DOUBLE PRECISION,
    direction TEXT NOT NULL DEFAULT 'higher_is_better',
    unit TEXT NOT NULL DEFAULT 'percent',
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(segment_id, indicator_key)
);

CREATE TABLE IF NOT EXISTS indicator_results (
    id BIGSERIAL PRIMARY KEY,
    segment_id BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    indicator_definition_id BIGINT NOT NULL REFERENCES indicator_definitions(id) ON DELETE CASCADE,
    period TEXT NOT NULL,
    data_month TEXT NOT NULL,
    value DOUBLE PRECISION,
    volume INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(segment_id, user_id, indicator_definition_id, data_month, period)
);

CREATE TABLE IF NOT EXISTS uploads (
    id BIGSERIAL PRIMARY KEY,
    segment_id BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    uploaded_by BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS indicator_freshness (
    segment_id BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    indicator_definition_id BIGINT NOT NULL REFERENCES indicator_definitions(id) ON DELETE CASCADE,
    data_through TEXT NOT NULL,
    source_key TEXT NOT NULL,
    upload_id BIGINT REFERENCES uploads(id) ON DELETE SET NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (segment_id, indicator_definition_id)
);

CREATE TABLE IF NOT EXISTS access_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_results_segment_period ON indicator_results(segment_id, period);
CREATE INDEX IF NOT EXISTS idx_results_user_segment ON indicator_results(user_id, segment_id);
CREATE INDEX IF NOT EXISTS idx_results_segment_month ON indicator_results(segment_id, data_month);
CREATE INDEX IF NOT EXISTS idx_uploads_segment_created ON uploads(segment_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_freshness_segment ON indicator_freshness(segment_id);
CREATE INDEX IF NOT EXISTS idx_freshness_definition ON indicator_freshness(indicator_definition_id);
CREATE INDEX IF NOT EXISTS idx_access_user_created ON access_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_perf_segment ON user_performance_segments(segment_id, user_id);

REVOKE ALL ON ALL TABLES IN SCHEMA cop_portal FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA cop_portal FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA cop_portal REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA cop_portal REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
"""


def using_postgres() -> bool:
    return bool(DATABASE_URL)


def database_backend() -> str:
    return "postgresql" if using_postgres() else "sqlite"


def database_is_persistent() -> bool:
    if using_postgres():
        return True
    return not (os.environ.get("VERCEL") == "1" or str(DB_PATH).startswith("/tmp/"))


def persistence_diagnostics() -> dict[str, str | bool]:
    return {
        "backend": database_backend(),
        "persistent": database_is_persistent(),
        "database_url_detected": bool(os.environ.get("DATABASE_URL", "").strip()),
        "postgres_url_detected": bool(os.environ.get("POSTGRES_URL", "").strip()),
        "postgres_non_pooling_detected": bool(
            os.environ.get("POSTGRES_URL_NON_POOLING", "").strip()
        ),
        "vercel": os.environ.get("VERCEL") == "1",
        "vercel_env": os.environ.get("VERCEL_ENV", ""),
        "commit": os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:12],
    }


def _postgres_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class ConnectionAdapter:
    def __init__(self, raw: Any, backend: str):
        self.raw = raw
        self.backend = backend

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        values = tuple(params or ())
        if self.backend == "postgresql":
            return self.raw.execute(_postgres_sql(sql), values)
        return self.raw.execute(sql, values)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]):
        if self.backend == "postgresql":
            with self.raw.cursor() as cur:
                cur.executemany(_postgres_sql(sql), rows)
                return cur
        return self.raw.executemany(sql, rows)

    def executescript(self, sql: str) -> None:
        if self.backend == "postgresql":
            for statement in _split_statements(sql):
                self.raw.execute(statement)
            return
        self.raw.executescript(sql)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def _split_statements(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


def connect() -> ConnectionAdapter:
    if using_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL foi configurada, mas o driver PostgreSQL não está instalado"
            ) from exc

        raw = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            prepare_threshold=None,
            application_name="portal-indicadores-cop",
        )
        raw.execute("SET search_path TO cop_portal, public")
        return ConnectionAdapter(raw, "postgresql")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return ConnectionAdapter(raw, "sqlite")


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


def insert_returning_id(conn: ConnectionAdapter, sql: str, params: Iterable[Any]) -> int:
    if conn.backend == "postgresql":
        row = conn.execute(sql.rstrip().rstrip(";") + " RETURNING id", params).fetchone()
        if not row:
            raise RuntimeError("INSERT não retornou id")
        return int(row["id"])

    cur = conn.execute(sql, params)
    return int(cur.lastrowid)


def initialize_database() -> None:
    if using_postgres():
        with transaction() as conn:
            conn.executescript(POSTGRES_SCHEMA)
            conn.execute("DROP TABLE IF EXISTS scales")
            conn.execute(
                "ALTER TABLE indicator_definitions ADD COLUMN IF NOT EXISTS unit TEXT NOT NULL DEFAULT 'percent'"
            )
            conn.execute(
                "ALTER TABLE indicator_results ADD COLUMN IF NOT EXISTS data_month TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "UPDATE indicator_results SET data_month=substring(period from 1 for 7) "
                "WHERE data_month='' OR data_month IS NULL"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_indicator_results_competence "
                "ON indicator_results(segment_id, user_id, indicator_definition_id, data_month, period)"
            )
        return

    with transaction() as conn:
        conn.executescript(SQLITE_SCHEMA)
        conn.execute("DROP TABLE IF EXISTS scales")
        _ensure_column_sqlite(conn, "indicator_definitions", "unit", "TEXT NOT NULL DEFAULT 'percent'")
        _ensure_column_sqlite(conn, "indicator_results", "data_month", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE indicator_results SET data_month=substr(period,1,7) "
            "WHERE data_month='' OR data_month IS NULL"
        )
        _migrate_indicator_results_unique_sqlite(conn)
        _ensure_result_indexes_sqlite(conn)


def _ensure_column_sqlite(
    conn: ConnectionAdapter, table: str, column: str, definition: str
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_indicator_results_unique_sqlite(conn: ConnectionAdapter) -> None:
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


def _ensure_result_indexes_sqlite(conn: ConnectionAdapter) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_segment_period ON indicator_results(segment_id, period)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_user_segment ON indicator_results(user_id, segment_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_results_segment_month ON indicator_results(segment_id, data_month)"
    )
