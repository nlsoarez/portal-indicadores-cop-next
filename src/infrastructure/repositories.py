from __future__ import annotations

from src.domain.entities import AccessContext, RoleCode, Segment, User
from src.infrastructure.database import connection, insert_returning_id, transaction


class UserRepository:
    def get_by_login(self, login: str) -> User | None:
        with connection() as conn:
            row = conn.execute(
                "SELECT id, login, full_name, display_name, active FROM users WHERE UPPER(login)=UPPER(?)",
                (login.strip(),),
            ).fetchone()
        return _user(row) if row else None

    def get_credentials(self, login: str):
        with connection() as conn:
            row = conn.execute(
                "SELECT id, login, password_hash, password_salt, must_change_password, active "
                "FROM users WHERE UPPER(login)=UPPER(?)",
                (login.strip(),),
            ).fetchone()
        return row

    def get_by_id(self, user_id: int) -> User | None:
        with connection() as conn:
            row = conn.execute(
                "SELECT id, login, full_name, display_name, active FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
        return _user(row) if row else None

    def list_for_segment(self, segment_id: int) -> list[User]:
        """Somente analistas ativos; líderes/subadmins nunca entram na lista comum."""
        with connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT u.id, u.login, u.full_name, u.display_name, u.active "
                "FROM users u "
                "JOIN user_segments us ON us.user_id=u.id "
                "JOIN user_roles ur ON ur.user_id=u.id "
                "JOIN roles r ON r.id=ur.role_id "
                "WHERE us.segment_id=? AND u.active=1 AND r.code='analyst' "
                "ORDER BY u.display_name",
                (segment_id,),
            ).fetchall()
        return [_user(row) for row in rows]

    def list_subadmins(self) -> list[User]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT u.id, u.login, u.full_name, u.display_name, u.active "
                "FROM users u JOIN user_roles ur ON ur.user_id=u.id "
                "JOIN roles r ON r.id=ur.role_id "
                "WHERE u.active=1 AND r.code='subadmin' ORDER BY u.display_name"
            ).fetchall()
        return [_user(row) for row in rows]

    def list_subadmins_for_segment(self, segment_id: int) -> list[User]:
        """Líderes cujo desempenho pertence operacionalmente ao segmento."""
        with connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT u.id, u.login, u.full_name, u.display_name, u.active "
                "FROM users u "
                "JOIN user_performance_segments ups ON ups.user_id=u.id "
                "JOIN user_roles ur ON ur.user_id=u.id "
                "JOIN roles r ON r.id=ur.role_id "
                "WHERE ups.segment_id=? AND u.active=1 AND r.code='subadmin' "
                "ORDER BY u.display_name",
                (segment_id,),
            ).fetchall()
        return [_user(row) for row in rows]

    def list_performance_users_for_segment(self, segment_id: int) -> list[User]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT u.id, u.login, u.full_name, u.display_name, u.active "
                "FROM users u "
                "JOIN user_performance_segments ups ON ups.user_id=u.id "
                "JOIN user_roles ur ON ur.user_id=u.id "
                "JOIN roles r ON r.id=ur.role_id "
                "WHERE ups.segment_id=? AND u.active=1 AND r.code IN ('analyst','subadmin') "
                "ORDER BY u.display_name",
                (segment_id,),
            ).fetchall()
        return [_user(row) for row in rows]

    def performance_segments_for_user(self, user_id: int) -> list[Segment]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT s.id, s.slug, s.name, s.active FROM segments s "
                "JOIN user_performance_segments ups ON ups.segment_id=s.id "
                "WHERE ups.user_id=? AND s.active=1 ORDER BY s.name",
                (user_id,),
            ).fetchall()
        return [_segment(row) for row in rows]

    def roles_for_user(self, user_id: int) -> frozenset[RoleCode]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT r.code FROM roles r JOIN user_roles ur ON ur.role_id=r.id WHERE ur.user_id=?",
                (user_id,),
            ).fetchall()
        return frozenset(RoleCode(row["code"]) for row in rows)

    def segment_ids_for_user(self, user_id: int) -> frozenset[int]:
        with connection() as conn:
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
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT u.id, u.login, u.display_name, MAX(al.created_at) AS last_access
                FROM users u
                JOIN user_segments us ON us.user_id=u.id AND us.segment_id=?
                JOIN user_roles ur ON ur.user_id=u.id
                JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
                LEFT JOIN access_logs al ON al.user_id=u.id AND al.event_type='login'
                WHERE u.active=1
                GROUP BY u.id, u.login, u.display_name
                ORDER BY u.display_name
                """,
                (segment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def last_access_for_subadmins(self) -> list[dict]:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT u.id, u.login, u.display_name, MAX(al.created_at) AS last_access
                FROM users u
                JOIN user_roles ur ON ur.user_id=u.id
                JOIN roles r ON r.id=ur.role_id AND r.code='subadmin'
                LEFT JOIN access_logs al ON al.user_id=u.id AND al.event_type='login'
                WHERE u.active=1
                GROUP BY u.id, u.login, u.display_name
                ORDER BY u.display_name
                """
            ).fetchall()
        return [dict(row) for row in rows]


class SegmentRepository:
    def list_for_user(self, user_id: int) -> list[Segment]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT s.id, s.slug, s.name, s.active FROM segments s "
                "JOIN user_segments us ON us.segment_id=s.id "
                "WHERE us.user_id=? AND s.active=1 ORDER BY s.name",
                (user_id,),
            ).fetchall()
        return [_segment(row) for row in rows]

    def get_by_slug(self, slug: str) -> Segment | None:
        with connection() as conn:
            row = conn.execute(
                "SELECT id, slug, name, active FROM segments WHERE slug=?", (slug,)
            ).fetchone()
        return _segment(row) if row else None


class IndicatorRepository:
    def definitions(self, segment_id: int) -> list[dict]:
        with connection() as conn:
            rows = conn.execute(
                "SELECT id, indicator_key, name, target_value, direction, unit "
                "FROM indicator_definitions WHERE segment_id=? AND active=1 ORDER BY name",
                (segment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_definition(self, segment_id: int, indicator_key: str) -> dict | None:
        with connection() as conn:
            row = conn.execute(
                "SELECT id, indicator_key, name, target_value, direction, unit "
                "FROM indicator_definitions WHERE segment_id=? AND indicator_key=? AND active=1",
                (segment_id, indicator_key),
            ).fetchone()
        return dict(row) if row else None

    def results_for_user(self, segment_id: int, user_id: int, period: str | None = None) -> list[dict]:
        sql = (
            "SELECT ir.period, ir.data_month, ir.value, ir.volume, d.indicator_key, d.name, "
            "d.target_value, d.direction, d.unit "
            "FROM indicator_results ir JOIN indicator_definitions d ON d.id=ir.indicator_definition_id "
            "WHERE ir.segment_id=? AND ir.user_id=?"
        )
        params: list[object] = [segment_id, user_id]
        if period:
            sql += " AND ir.period=?"
            params.append(period)
        sql += " ORDER BY ir.period DESC, d.name"
        with connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def monthly_summary_for_user(self, segment_id: int, user_id: int) -> list[dict]:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    ir.data_month AS period,
                    d.indicator_key,
                    d.name,
                    d.target_value,
                    d.direction,
                    d.unit,
                    ROUND(CAST(SUM(ir.value * ir.volume) AS NUMERIC) / NULLIF(SUM(ir.volume), 0), 1) AS value,
                    SUM(ir.volume) AS volume
                FROM indicator_results ir
                JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                WHERE ir.segment_id=? AND ir.user_id=?
                GROUP BY ir.data_month, d.indicator_key, d.name,
                         d.target_value, d.direction, d.unit
                ORDER BY period DESC, d.name
                """,
                (segment_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def team_monthly_summary(self, segment_id: int) -> list[dict]:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    ir.data_month AS period,
                    d.indicator_key,
                    d.name,
                    d.unit,
                    ROUND(CAST(SUM(ir.value * ir.volume) AS NUMERIC) / NULLIF(SUM(ir.volume), 0), 1) AS team_avg,
                    SUM(ir.volume) AS team_volume,
                    COUNT(DISTINCT ir.user_id) AS analysts_with_data,
                    ROUND(CAST(SUM(ir.volume) AS NUMERIC) / NULLIF(COUNT(DISTINCT ir.user_id), 0), 1)
                        AS avg_volume_per_analyst
                FROM indicator_results ir
                JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                JOIN user_roles ur ON ur.user_id=ir.user_id
                JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
                WHERE ir.segment_id=?
                GROUP BY ir.data_month, d.indicator_key, d.name, d.unit
                ORDER BY period DESC, d.name
                """,
                (segment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def team_averages(self, segment_id: int, period: str | None = None) -> list[dict]:
        sql = (
            "SELECT ir.period, d.indicator_key, d.name, d.unit, "
            "SUM(ir.value * ir.volume) / NULLIF(SUM(ir.volume), 0) AS team_avg, "
            "SUM(ir.volume) AS team_volume "
            "FROM indicator_results ir JOIN indicator_definitions d ON d.id=ir.indicator_definition_id "
            "JOIN user_roles ur ON ur.user_id=ir.user_id "
            "JOIN roles r ON r.id=ur.role_id AND r.code='analyst' "
            "WHERE ir.segment_id=?"
        )
        params: list[object] = [segment_id]
        if period:
            sql += " AND ir.period=?"
            params.append(period)
        sql += " GROUP BY ir.period, d.indicator_key, d.name, d.unit ORDER BY ir.period DESC, d.name"
        with connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def replace_results_for_months(
        self,
        *,
        segment_id: int,
        indicator_definition_id: int,
        login_to_user_id: dict[str, int],
        rows: tuple[dict, ...],
        months: tuple[str, ...],
    ) -> None:
        normalized_users = {str(login).upper(): int(user_id) for login, user_id in login_to_user_id.items()}
        with transaction() as conn:
            for month in months:
                conn.execute(
                    "DELETE FROM indicator_results "
                    "WHERE segment_id=? AND indicator_definition_id=? AND data_month=?",
                    (segment_id, indicator_definition_id, month),
                )

            payload = []
            for row in rows:
                user_id = normalized_users.get(str(row.get("login", "")).strip().upper())
                if user_id is None:
                    continue
                payload.append(
                    (
                        segment_id,
                        user_id,
                        indicator_definition_id,
                        str(row["period"]),
                        str(row.get("data_month") or str(row["period"])[:7]),
                        float(row["value"]),
                        int(row.get("volume", 0) or 0),
                    )
                )
            if payload:
                conn.executemany(
                    """
                    INSERT INTO indicator_results(
                        segment_id, user_id, indicator_definition_id, period, data_month, value, volume
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(segment_id, user_id, indicator_definition_id, data_month, period)
                    DO UPDATE SET value=excluded.value, volume=excluded.volume, created_at=CURRENT_TIMESTAMP
                    """,
                    payload,
                )

    def upsert_freshness(
        self,
        segment_id: int,
        indicator_definition_id: int,
        data_through: str,
        source_key: str,
        upload_id: int | None = None,
    ) -> None:
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO indicator_freshness(
                    segment_id, indicator_definition_id, data_through, source_key, upload_id, refreshed_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(segment_id, indicator_definition_id)
                DO UPDATE SET data_through=excluded.data_through,
                              source_key=excluded.source_key,
                              upload_id=excluded.upload_id,
                              refreshed_at=CURRENT_TIMESTAMP
                """,
                (segment_id, indicator_definition_id, data_through, source_key, upload_id),
            )

    def freshness(self, segment_id: int) -> list[dict]:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.indicator_key, d.name, d.target_value, d.direction, d.unit,
                       f.data_through, f.source_key, f.refreshed_at,
                       u.filename, u.created_at AS uploaded_at
                FROM indicator_definitions d
                LEFT JOIN indicator_freshness f
                  ON f.segment_id=d.segment_id AND f.indicator_definition_id=d.id
                LEFT JOIN uploads u ON u.id=f.upload_id
                WHERE d.segment_id=? AND d.active=1
                ORDER BY d.name
                """,
                (segment_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class UploadRepository:
    def create(self, segment_id: int, source_key: str, filename: str, uploaded_by: int) -> int:
        with transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO uploads(segment_id, source_key, filename, uploaded_by) VALUES (?, ?, ?, ?)",
                (segment_id, source_key, filename, uploaded_by),
            )

    def latest_by_source(self) -> dict[str, dict]:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT up.source_key, up.filename, up.created_at,
                       s.slug AS segment_slug, u.display_name AS uploaded_by
                FROM uploads up
                JOIN users u ON u.id=up.uploaded_by
                JOIN segments s ON s.id=up.segment_id
                ORDER BY up.created_at DESC, up.id DESC
                """
            ).fetchall()
        latest: dict[str, dict] = {}
        for row in rows:
            latest.setdefault(str(row["source_key"]), dict(row))
        return latest

    def list_recent(self, segment_id: int, limit: int = 20) -> list[dict]:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT up.id, up.source_key, up.filename, up.created_at,
                       u.display_name AS uploaded_by
                FROM uploads up
                JOIN users u ON u.id=up.uploaded_by
                WHERE up.segment_id=?
                ORDER BY up.created_at DESC, up.id DESC
                LIMIT ?
                """,
                (segment_id, limit),
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
