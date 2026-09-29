from __future__ import annotations

from src.application.security import hash_password
from src.config.leaders import LEADER_ADMINS
from src.features.segments.catalog import SEGMENTS
from src.features.segments.preventiva import PREVENTIVA_ANALYSTS, PREVENTIVA_INDICATORS
from src.features.segments.residencial import RESIDENTIAL_ANALYSTS
from src.infrastructure.database import transaction

DEFAULT_PASSWORD = "claro123"


def seed_foundation() -> None:
    with transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO roles(code, name) VALUES ('admin', 'Administrador')")
        conn.execute("INSERT OR IGNORE INTO roles(code, name) VALUES ('subadmin', 'Subadministrador')")
        conn.execute("INSERT OR IGNORE INTO roles(code, name) VALUES ('analyst', 'Analista')")
        for segment in SEGMENTS:
            conn.execute(
                "INSERT OR IGNORE INTO segments(slug, name, active) VALUES (?, ?, ?)",
                (segment["slug"], segment["name"], int(segment["active"])),
            )

        _ensure_user(conn, "ADMIN", "Administrador", "Administrador", "admin")
        preventiva_id = conn.execute("SELECT id FROM segments WHERE slug='preventiva'").fetchone()["id"]
        residencial_id = conn.execute("SELECT id FROM segments WHERE slug='residencial'").fetchone()["id"]
        active_segment_ids = conn.execute("SELECT id FROM segments WHERE active=1").fetchall()

        admin_id = _ensure_user(conn, "ADMIN", "Administrador", "Administrador", "admin")
        _set_single_role(conn, admin_id, "admin")
        for segment_row in active_segment_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_segments(user_id, segment_id) VALUES (?, ?)",
                (admin_id, int(segment_row["id"])),
            )

        for login, full_name, display_name in LEADER_ADMINS:
            leader_id = _ensure_user(conn, login, full_name, display_name, "subadmin")
            _set_single_role(conn, leader_id, "subadmin")
            for segment_row in active_segment_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO user_segments(user_id, segment_id) VALUES (?, ?)",
                    (leader_id, int(segment_row["id"])),
                )

        for login, full_name, display_name in PREVENTIVA_ANALYSTS:
            user_id = _ensure_user(conn, login, full_name, display_name, "analyst")
            conn.execute(
                "INSERT OR IGNORE INTO user_segments(user_id, segment_id) VALUES (?, ?)",
                (user_id, preventiva_id),
            )

        for login, full_name, display_name in RESIDENTIAL_ANALYSTS:
            user_id = _ensure_user(conn, login, full_name, display_name, "analyst")
            conn.execute(
                "INSERT OR IGNORE INTO user_segments(user_id, segment_id) VALUES (?, ?)",
                (user_id, residencial_id),
            )

        # Maristella pertence somente à Preventiva neste portal.
        maristella = conn.execute("SELECT id FROM users WHERE login='N5577565'").fetchone()
        if maristella:
            conn.execute(
                "DELETE FROM user_segments WHERE user_id=? AND segment_id=?",
                (int(maristella["id"]), residencial_id),
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
        conn.execute(
            "UPDATE users SET full_name=?, display_name=?, active=1 WHERE id=?",
            (full_name, display_name, user_id),
        )
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


def _set_single_role(conn, user_id: int, role_code: str) -> None:
    role_id = conn.execute("SELECT id FROM roles WHERE code=?", (role_code,)).fetchone()["id"]
    conn.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
    conn.execute(
        "INSERT INTO user_roles(user_id, role_id) VALUES (?, ?)",
        (user_id, role_id),
    )
