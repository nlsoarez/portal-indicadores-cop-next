from __future__ import annotations

from src.application.security import hash_password
from src.features.segments.catalog import SEGMENTS
from src.features.segments.preventiva import PREVENTIVA_ANALYSTS, PREVENTIVA_INDICATORS
from src.infrastructure.database import transaction

DEFAULT_PASSWORD = "claro123"


def seed_foundation() -> None:
    with transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO roles(code, name) VALUES ('admin', 'Administrador')")
        conn.execute("INSERT OR IGNORE INTO roles(code, name) VALUES ('analyst', 'Analista')")
        for segment in SEGMENTS:
            conn.execute(
                "INSERT OR IGNORE INTO segments(slug, name, active) VALUES (?, ?, ?)",
                (segment["slug"], segment["name"], int(segment["active"])),
            )

        _ensure_user(conn, "ADMIN", "Administrador", "Administrador", "admin")
        preventiva_id = conn.execute("SELECT id FROM segments WHERE slug='preventiva'").fetchone()["id"]
        admin_id = conn.execute("SELECT id FROM users WHERE login='ADMIN'").fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO user_segments(user_id, segment_id) VALUES (?, ?)",
            (admin_id, preventiva_id),
        )

        for login, full_name, display_name in PREVENTIVA_ANALYSTS:
            user_id = _ensure_user(conn, login, full_name, display_name, "analyst")
            conn.execute(
                "INSERT OR IGNORE INTO user_segments(user_id, segment_id) VALUES (?, ?)",
                (user_id, preventiva_id),
            )

        for indicator in PREVENTIVA_INDICATORS:
            conn.execute(
                """
                INSERT INTO indicator_definitions(
                    segment_id, indicator_key, name, target_value, direction, active
                ) VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(segment_id, indicator_key)
                DO UPDATE SET
                    name=excluded.name,
                    target_value=excluded.target_value,
                    direction=excluded.direction,
                    active=1
                """,
                (
                    preventiva_id,
                    indicator["indicator_key"],
                    indicator["name"],
                    indicator["target_value"],
                    indicator["direction"],
                ),
            )


def _ensure_user(conn, login: str, full_name: str, display_name: str, role_code: str) -> int:
    existing = conn.execute("SELECT id FROM users WHERE login=?", (login,)).fetchone()
    if existing:
        user_id = int(existing["id"])
    else:
        password_hash, salt = hash_password(DEFAULT_PASSWORD)
        cur = conn.execute(
            "INSERT INTO users(login, full_name, display_name, password_hash, password_salt, must_change_password) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (login, full_name, display_name, password_hash, salt),
        )
        user_id = int(cur.lastrowid)
    role_id = conn.execute("SELECT id FROM roles WHERE code=?", (role_code,)).fetchone()["id"]
    conn.execute(
        "INSERT OR IGNORE INTO user_roles(user_id, role_id) VALUES (?, ?)",
        (user_id, role_id),
    )
    return user_id
