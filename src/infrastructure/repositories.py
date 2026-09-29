from __future__ import annotations

from collections.abc import Iterable

from src.domain.entities import AccessContext, RoleCode, Segment, User
from src.infrastructure.database import connect, transaction


class UserRepository:
    def get_by_login(self, login: str) -> User | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, login, full_name, display_name, active FROM users WHERE UPPER(login)=UPPER(?)",
                (login.strip(),),
            ).fetchone()
        return _user(row) if row else None

    def get_credentials(self, login: str):
        with connect() as conn:
            return conn.execute(
                "SELECT id, login, password_hash, password_salt, must_change_password, active "
                "FROM users WHERE UPPER(login)=UPPER(?)",
                (login.strip(),),
            ).fetchone()

    def get_by_id(self, user_id: int) -> User | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, login, full_name, display_name, active FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
        return _user(row) if row else None

    def list_for_segment(self, segment_id: int) -> list[User]:
        """Lista somente analistas ativos do segmento; contas administrativas não viram pessoas da equipe."""
        with connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT u.id, u.login, u.full_name, u.display_name, u.active "
                "FROM users u "
                "JOIN user_segments us ON us.user_id=u.id "
                "JOIN user_roles ur ON ur.user_id=u.id "
                "JOIN roles r ON r.id=ur.role_id "
                "WHERE us.segment_id=? AND u.active=1 AND r.code='analyst' ORDER BY u.display_name",
                (segment_id,),
            ).fetchall()
        return [_user(row) for row in rows]

    def roles_for_user(self, user_id: int) -> frozenset[RoleCode]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT r.code FROM roles r JOIN user_roles ur ON ur.role_id=r.id WHERE ur.user_id=?",
                (user_id,),
            ).fetchall()
        return frozenset(RoleCode(row["code"]) for row in rows)

    def segment_ids_for_user(self, user_id: int) -> frozenset[int]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT segment_id FROM user_segments WHERE user_id=?", (user_id,)
            ).fetchall()
        return frozenset(int(row["segment_id"]) for row in rows)

    def access_context(self, user_id: int) -> AccessContext:
        user = self.get_by_id(user_id)
        if not user or not user.active:
            raise PermissionError("Usuário inativo ou inexistente")
        return AccessContext(
            user=user,
            roles=self.roles_for_user(user_id),
            segment_ids=self.segment_ids_for_user(user_id),
        )

    def change_password(self, user_id: int, password_hash: str, salt: str) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE users SET password_hash=?, password_salt=?, must_change_password=0 WHERE id=?",
                (password_hash, salt, user_id),
            )

    def last_access_for_segment(self, segment_id: int) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT u.id, u.login, u.display_name, MAX(al.created_at) AS last_access
                FROM users u
                JOIN user_segments us ON us.user_id=u.id AND us.segment_id=?
                LEFT JOIN access_logs al ON al.user_id=u.id AND al.event_type='login'
                WHERE u.active=1
                GROUP BY u.id, u.login, u.display_name
                ORDER BY u.display_name
                """,
                (segment_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class SegmentRepository:
    def list_for_user(self, user_id: int) -> list[Segment]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT s.id, s.slug, s.name, s.active FROM segments s "
                "JOIN user_segments us ON us.segment_id=s.id "
                "WHERE us.user_id=? AND s.active=1 ORDER BY s.name",
                (user_id,),
            ).fetchall()
        return [_segment(row) for row in rows]

    def get_by_slug(self, slug: str) -> Segment | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT id, slug, name, active FROM segments WHERE slug=?", (slug,)
            ).fetchone()
        return _segment(row) if row else None


class IndicatorRepository:
    def definitions(self, segment_id: int) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, indicator_key, name, target_value, direction FROM indicator_definitions "
                "WHERE segment_id=? AND active=1 ORDER BY name",
                (segment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def results_for_user(self, segment_id: int, user_id: int, period: str | None = None) -> list[dict]:
        sql = (
            "SELECT ir.period, ir.value, ir.volume, d.indicator_key, d.name, d.target_value, d.direction "
            "FROM indicator_results ir JOIN indicator_definitions d ON d.id=ir.indicator_definition_id "
            "WHERE ir.segment_id=? AND ir.user_id=?"
        )
        params: list[object] = [segment_id, user_id]
        if period:
            sql += " AND ir.period=?"
            params.append(period)
        sql += " ORDER BY ir.period DESC, d.name"
        with connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def team_averages(self, segment_id: int, period: str | None = None) -> list[dict]:
        sql = (
            "SELECT ir.period, d.indicator_key, d.name, AVG(ir.value) AS team_avg, SUM(ir.volume) AS team_volume "
            "FROM indicator_results ir JOIN indicator_definitions d ON d.id=ir.indicator_definition_id "
            "WHERE ir.segment_id=?"
        )
        params: list[object] = [segment_id]
        if period:
            sql += " AND ir.period=?"
            params.append(period)
        sql += " GROUP BY ir.period, d.indicator_key, d.name ORDER BY ir.period DESC, d.name"
        with connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


class ScaleRepository:
    def for_user(self, segment_id: int, user_id: int) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT work_date, assignment FROM scales WHERE segment_id=? AND user_id=? ORDER BY work_date DESC",
                (segment_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]


class AuditRepository:
    def record_access(self, user_id: int, event_type: str = "login") -> None:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO access_logs(user_id, event_type) VALUES (?, ?)",
                (user_id, event_type),
            )


def _user(row) -> User:
    return User(
        id=int(row["id"]),
        login=str(row["login"]),
        full_name=str(row["full_name"]),
        display_name=str(row["display_name"]),
        active=bool(row["active"]),
    )


def _segment(row) -> Segment:
    return Segment(
        id=int(row["id"]), slug=str(row["slug"]), name=str(row["name"]), active=bool(row["active"])
    )
