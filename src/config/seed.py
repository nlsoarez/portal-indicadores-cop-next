from __future__ import annotations

import os
import secrets

from src.application.security import hash_password
from src.config.leaders import LEADER_SUBADMINS
from src.features.segments.catalog import SEGMENTS
from src.features.segments.empresarial import ENTERPRISE_ANALYSTS, ENTERPRISE_INDICATORS
from src.features.segments.preventiva import PREVENTIVA_ANALYSTS, PREVENTIVA_INDICATORS
from src.features.segments.residencial import RESIDENTIAL_ANALYSTS, RESIDENTIAL_INDICATORS
from src.infrastructure.database import insert_returning_id, transaction, using_postgres

ADMIN_BOOTSTRAP_PASSWORD_ENV = "COP_ADMIN_BOOTSTRAP_PASSWORD"
RETIRED_ANALYST_LOGINS = ("F218860",)


def seed_foundation() -> None:
    with transaction() as conn:
        conn.execute("INSERT INTO roles(code, name) VALUES ('admin', 'Administrador') ON CONFLICT(code) DO NOTHING")
        conn.execute("INSERT INTO roles(code, name) VALUES ('subadmin', 'Subadministrador') ON CONFLICT(code) DO NOTHING")
        conn.execute("INSERT INTO roles(code, name) VALUES ('analyst', 'Analista') ON CONFLICT(code) DO NOTHING")

        for segment in SEGMENTS:
            conn.execute(
                "INSERT INTO segments(slug, name, active) VALUES (?, ?, ?) "
                "ON CONFLICT(slug) DO UPDATE SET name=excluded.name, active=excluded.active",
                (segment["slug"], segment["name"], int(segment["active"])),
            )

        segment_ids = {
            row["slug"]: int(row["id"])
            for row in conn.execute("SELECT id, slug FROM segments").fetchall()
        }
        active_segment_ids = [
            int(row["id"])
            for row in conn.execute("SELECT id FROM segments WHERE active=1").fetchall()
        ]

        admin_id = _ensure_user(conn, "ADMIN", "Administrador", "Administrador")
        _set_single_role(conn, admin_id, "admin")
        _replace_access_segments(conn, admin_id, active_segment_ids)
        _replace_performance_segments(conn, admin_id, [])

        for login, full_name, display_name, performance_slug in LEADER_SUBADMINS:
            leader_id = _ensure_user(conn, login, full_name, display_name)
            _set_single_role(conn, leader_id, "subadmin")
            _replace_access_segments(conn, leader_id, active_segment_ids)
            _replace_performance_segments(conn, leader_id, [segment_ids[performance_slug]])

        _seed_analysts(conn, segment_ids["preventiva"], PREVENTIVA_ANALYSTS)
        _seed_analysts(conn, segment_ids["residencial"], RESIDENTIAL_ANALYSTS)
        _seed_analysts(conn, segment_ids["empresarial"], ENTERPRISE_ANALYSTS)

        # Ex-colaboradores permanecem no histórico, mas deixam de aparecer
        # nas listas, uploads e visões individuais.
        for retired_login in RETIRED_ANALYST_LOGINS:
            retired = conn.execute(
                "SELECT id FROM users WHERE UPPER(login)=UPPER(?)",
                (retired_login,),
            ).fetchone()
            if retired:
                retired_id = int(retired["id"])
                conn.execute("UPDATE users SET active=0 WHERE id=?", (retired_id,))
                conn.execute("DELETE FROM user_segments WHERE user_id=?", (retired_id,))
                conn.execute(
                    "DELETE FROM user_performance_segments WHERE user_id=?",
                    (retired_id,),
                )

        # Maristella é exclusiva da Preventiva neste portal.
        maristella = conn.execute("SELECT id FROM users WHERE login='N5577565'").fetchone()
        if maristella:
            user_id = int(maristella["id"])
            for slug in ("residencial", "empresarial"):
                conn.execute(
                    "DELETE FROM user_segments WHERE user_id=? AND segment_id=?",
                    (user_id, segment_ids[slug]),
                )
                conn.execute(
                    "DELETE FROM user_performance_segments WHERE user_id=? AND segment_id=?",
                    (user_id, segment_ids[slug]),
                )

        _seed_indicators(conn, segment_ids["preventiva"], PREVENTIVA_INDICATORS)
        _seed_indicators(conn, segment_ids["residencial"], RESIDENTIAL_INDICATORS)
        _seed_indicators(conn, segment_ids["empresarial"], ENTERPRISE_INDICATORS)


def _seed_analysts(conn, segment_id: int, people: tuple[tuple[str, str, str], ...]) -> None:
    for login, full_name, display_name in people:
        user_id = _ensure_user(conn, login, full_name, display_name)
        _set_single_role(conn, user_id, "analyst")
        _replace_access_segments(conn, user_id, [segment_id])
        _replace_performance_segments(conn, user_id, [segment_id])


def _seed_indicators(conn, segment_id: int, indicators: tuple[dict, ...]) -> None:
    configured_keys = [str(indicator["indicator_key"]) for indicator in indicators]
    if configured_keys:
        placeholders = ",".join("?" for _ in configured_keys)
        conn.execute(
            f"UPDATE indicator_definitions SET active=0 "
            f"WHERE segment_id=? AND indicator_key NOT IN ({placeholders})",
            (segment_id, *configured_keys),
        )
    else:
        conn.execute(
            "UPDATE indicator_definitions SET active=0 WHERE segment_id=?",
            (segment_id,),
        )

    for indicator in indicators:
        conn.execute(
            """
            INSERT INTO indicator_definitions(
                segment_id, indicator_key, name, target_value, direction, unit, active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(segment_id, indicator_key)
            DO UPDATE SET
                name=excluded.name,
                target_value=excluded.target_value,
                direction=excluded.direction,
                unit=excluded.unit,
                active=1
            """,
            (
                segment_id,
                indicator["indicator_key"],
                indicator["name"],
                indicator.get("target_value"),
                indicator.get("direction", "higher_is_better"),
                indicator.get("unit", "percent"),
            ),
        )


def _ensure_user(conn, login: str, full_name: str, display_name: str) -> int:
    existing = conn.execute("SELECT id FROM users WHERE UPPER(login)=UPPER(?)", (login,)).fetchone()
    if existing:
        user_id = int(existing["id"])
        conn.execute(
            "UPDATE users SET full_name=?, display_name=?, active=1 WHERE id=?",
            (full_name, display_name, user_id),
        )
        return user_id

    password_hash, salt = hash_password(_initial_password(login))
    return insert_returning_id(
        conn,
        "INSERT INTO users(login, full_name, display_name, password_hash, password_salt, must_change_password) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (login, full_name, display_name, password_hash, salt),
    )


def _initial_password(login: str) -> str:
    """Generate a non-shared initial secret.

    Existing users are never changed here. On a brand-new PostgreSQL database,
    the first ADMIN must be bootstrapped explicitly through an environment
    secret. Regular accounts receive an unguessable secret and must be issued a
    temporary password through the Admin password-reset flow before first use.
    """
    if login.strip().upper() == "ADMIN":
        configured = os.environ.get(ADMIN_BOOTSTRAP_PASSWORD_ENV, "").strip()
        if configured:
            if len(configured) < 12:
                raise RuntimeError(
                    f"{ADMIN_BOOTSTRAP_PASSWORD_ENV} precisa ter pelo menos 12 caracteres"
                )
            return configured
        if using_postgres():
            raise RuntimeError(
                "Banco PostgreSQL novo sem senha de bootstrap do ADMIN. "
                f"Configure {ADMIN_BOOTSTRAP_PASSWORD_ENV} antes da primeira inicialização."
            )
    return secrets.token_urlsafe(32)


def _set_single_role(conn, user_id: int, role_code: str) -> None:
    role_id = conn.execute("SELECT id FROM roles WHERE code=?", (role_code,)).fetchone()["id"]
    conn.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
    conn.execute("INSERT INTO user_roles(user_id, role_id) VALUES (?, ?)", (user_id, role_id))


def _replace_access_segments(conn, user_id: int, segment_ids: list[int]) -> None:
    conn.execute("DELETE FROM user_segments WHERE user_id=?", (user_id,))
    conn.executemany(
        "INSERT INTO user_segments(user_id, segment_id) VALUES (?, ?)",
        [(user_id, segment_id) for segment_id in segment_ids],
    )


def _replace_performance_segments(conn, user_id: int, segment_ids: list[int]) -> None:
    conn.execute("DELETE FROM user_performance_segments WHERE user_id=?", (user_id,))
    conn.executemany(
        "INSERT INTO user_performance_segments(user_id, segment_id) VALUES (?, ?)",
        [(user_id, segment_id) for segment_id in segment_ids],
    )
