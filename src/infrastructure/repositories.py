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
        # Uma única conexão para montar todo o contexto de autorização.
        with connection() as conn:
            user_row = conn.execute(
                "SELECT id, login, full_name, display_name, active FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            if not user_row or not bool(user_row["active"]):
                raise PermissionError("Usuário inativo ou inexistente")

            role_rows = conn.execute(
                "SELECT r.code FROM roles r "
                "JOIN user_roles ur ON ur.role_id=r.id "
                "WHERE ur.user_id=?",
                (user_id,),
            ).fetchall()
            segment_rows = conn.execute(
                "SELECT segment_id FROM user_segments WHERE user_id=?",
                (user_id,),
            ).fetchall()

        return AccessContext(
            user=_user(user_row),
            roles=frozenset(RoleCode(row["code"]) for row in role_rows),
            segment_ids=frozenset(int(row["segment_id"]) for row in segment_rows),
        )

    def can_view_user_in_segment(
        self,
        target_user_id: int,
        segment_id: int,
        *,
        include_subadmins: bool,
    ) -> bool:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM users u
                JOIN user_roles ur ON ur.user_id=u.id
                JOIN roles r ON r.id=ur.role_id
                LEFT JOIN user_segments us
                  ON us.user_id=u.id AND us.segment_id=?
                LEFT JOIN user_performance_segments ups
                  ON ups.user_id=u.id AND ups.segment_id=?
                WHERE u.id=? AND u.active=1
                  AND (
                    (r.code='analyst' AND us.segment_id IS NOT NULL)
                    OR (?=1 AND r.code='subadmin' AND ups.segment_id IS NOT NULL)
                  )
                LIMIT 1
                """,
                (segment_id, segment_id, target_user_id, int(include_subadmins)),
            ).fetchone()
        return row is not None

    def change_password(self, user_id: int, password_hash: str, salt: str) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE users SET password_hash=?, password_salt=?, must_change_password=0 WHERE id=?",
                (password_hash, salt, user_id),
            )
    def reset_password(self, user_id: int, password_hash: str, salt: str) -> None:
        """Define senha temporária e força troca no próximo login."""
        with transaction() as conn:
            conn.execute(
                "UPDATE users SET password_hash=?, password_salt=?, must_change_password=1 "
                "WHERE id=? AND active=1",
                (password_hash, salt, user_id),
            )

    def list_manageable_accounts(self) -> list[dict]:
        """Contas ativas que um Admin pode gerenciar (analistas e lideranças)."""
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT
                       u.id, u.login, u.display_name, u.full_name,
                       r.code AS role_code, r.name AS role_name,
                       s.id AS segment_id, s.name AS segment_name
                FROM users u
                JOIN user_roles ur ON ur.user_id=u.id
                JOIN roles r ON r.id=ur.role_id
                LEFT JOIN user_segments us ON us.user_id=u.id
                LEFT JOIN segments s ON s.id=us.segment_id AND s.active=1
                WHERE u.active=1 AND r.code IN ('analyst', 'subadmin')
                ORDER BY u.display_name, u.login, s.name
                """
            ).fetchall()

        accounts: dict[int, dict] = {}
        for row in rows:
            user_id = int(row["id"])
            item = accounts.setdefault(
                user_id,
                {
                    "id": user_id,
                    "login": str(row["login"]),
                    "display_name": str(row["display_name"]),
                    "full_name": str(row["full_name"]),
                    "role_code": str(row["role_code"]),
                    "role_name": str(row["role_name"]),
                    "segments": [],
                },
            )
            segment_name = row["segment_name"]
            if segment_name and str(segment_name) not in item["segments"]:
                item["segments"].append(str(segment_name))

        return list(accounts.values())

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

    def management_payload(self, segment_ids: list[int], *, include_external: bool = False) -> dict:
        """Visão gerencial consolidada e detalhada dos indicadores."""
        if not segment_ids:
            return {
                "segment_summary": [],
                "analyst_summary": [],
                "analyst_metrics": [],
                "analyst_breakdowns": [],
                "daily_summary": [],
                "breakdowns": [],
                "external": [],
                "freshness": [],
            }

        placeholders = ",".join("?" for _ in segment_ids)
        params = tuple(int(segment_id) for segment_id in segment_ids)

        with connection() as conn:
            segment_summary = conn.execute(
                f"""
                WITH base AS (
                    SELECT ir.segment_id, ir.user_id, ir.data_month, ir.value, ir.volume,
                           d.indicator_key, d.name, d.target_value, d.direction, d.unit,
                           s.slug AS segment_slug, s.name AS segment_name
                    FROM indicator_results ir
                    JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                    JOIN segments s ON s.id=ir.segment_id
                    JOIN user_roles ur ON ur.user_id=ir.user_id
                    JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
                    WHERE ir.segment_id IN ({placeholders})
                ),
                latest AS (
                    SELECT indicator_key, MAX(data_month) AS data_month
                    FROM base GROUP BY indicator_key
                )
                SELECT b.data_month AS period, b.segment_id, b.segment_slug, b.segment_name,
                       b.indicator_key, b.name, b.target_value, b.direction, b.unit,
                       ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS value,
                       SUM(b.volume) AS volume,
                       COUNT(DISTINCT b.user_id) AS analysts
                FROM base b
                JOIN latest l ON l.indicator_key=b.indicator_key AND l.data_month=b.data_month
                GROUP BY b.data_month, b.segment_id, b.segment_slug, b.segment_name,
                         b.indicator_key, b.name, b.target_value, b.direction, b.unit
                ORDER BY b.name, b.segment_name
                """,
                params,
            ).fetchall()

            analyst_summary = conn.execute(
                f"""
                WITH base AS (
                    SELECT ir.segment_id, ir.user_id, ir.data_month, ir.value, ir.volume,
                           d.indicator_key, d.name, d.target_value, d.direction, d.unit,
                           s.slug AS segment_slug, s.name AS segment_name,
                           u.login, u.display_name
                    FROM indicator_results ir
                    JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                    JOIN segments s ON s.id=ir.segment_id
                    JOIN users u ON u.id=ir.user_id AND u.active=1
                    JOIN user_roles ur ON ur.user_id=ir.user_id
                    JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
                    WHERE ir.segment_id IN ({placeholders})
                ),
                latest AS (
                    SELECT indicator_key, MAX(data_month) AS data_month
                    FROM base GROUP BY indicator_key
                )
                SELECT b.data_month AS period, b.segment_id, b.segment_slug, b.segment_name,
                       b.indicator_key, b.name, b.target_value, b.direction, b.unit,
                       b.user_id, b.login, b.display_name,
                       ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS value,
                       SUM(b.volume) AS volume
                FROM base b
                JOIN latest l ON l.indicator_key=b.indicator_key AND l.data_month=b.data_month
                GROUP BY b.data_month, b.segment_id, b.segment_slug, b.segment_name,
                         b.indicator_key, b.name, b.target_value, b.direction, b.unit,
                         b.user_id, b.login, b.display_name
                ORDER BY b.name, b.segment_name, b.display_name
                """,
                params,
            ).fetchall()

            breakdowns = conn.execute(
                f"""
                WITH base AS (
                    SELECT b.segment_id, b.data_month, b.dimension, b.dimension_value,
                           b.value, b.volume, b.successes, b.losses,
                           b.tma_seconds_sum, b.tma_count, b.tmr_seconds_sum, b.tmr_count,
                           d.indicator_key, d.name,
                           s.slug AS segment_slug, s.name AS segment_name
                    FROM indicator_breakdowns b
                    JOIN indicator_definitions d ON d.id=b.indicator_definition_id
                    JOIN segments s ON s.id=b.segment_id
                    WHERE b.segment_id IN ({placeholders})
                      AND b.scope='team'
                ),
                latest AS (
                    SELECT indicator_key, MAX(data_month) AS data_month
                    FROM base GROUP BY indicator_key
                )
                SELECT b.data_month AS period, b.segment_id, b.segment_slug, b.segment_name,
                       b.indicator_key, b.name, b.dimension, b.dimension_value,
                       ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS value,
                       SUM(b.volume) AS volume,
                       SUM(b.successes) AS successes,
                       SUM(b.losses) AS losses,
                       SUM(b.tma_seconds_sum) / NULLIF(SUM(b.tma_count), 0) AS tma_seconds,
                       SUM(b.tmr_seconds_sum) / NULLIF(SUM(b.tmr_count), 0) AS tmr_seconds
                FROM base b
                JOIN latest l ON l.indicator_key=b.indicator_key AND l.data_month=b.data_month
                GROUP BY b.data_month, b.segment_id, b.segment_slug, b.segment_name,
                         b.indicator_key, b.name, b.dimension, b.dimension_value
                ORDER BY b.name, b.dimension, b.dimension_value, b.segment_name
                """,
                params,
            ).fetchall()

            analyst_metrics = conn.execute(
                f"""
                WITH base AS (
                    SELECT b.segment_id, b.data_month, b.login, b.volume, b.successes, b.losses,
                           b.tma_seconds_sum, b.tma_count, b.tmr_seconds_sum, b.tmr_count,
                           d.indicator_key, s.slug AS segment_slug, s.name AS segment_name,
                           COALESCE(u.display_name, u.full_name) AS display_name
                    FROM indicator_breakdowns b
                    JOIN indicator_definitions d ON d.id=b.indicator_definition_id
                    JOIN segments s ON s.id=b.segment_id
                    JOIN users u ON UPPER(u.login)=UPPER(b.login) AND u.active=1
                    WHERE b.segment_id IN ({placeholders})
                      AND b.scope='team' AND b.dimension='overall'
                ),
                latest AS (
                    SELECT indicator_key, MAX(data_month) AS data_month
                    FROM base GROUP BY indicator_key
                )
                SELECT b.data_month AS period, b.segment_id, b.segment_slug, b.segment_name,
                       b.indicator_key, b.login, MAX(b.display_name) AS display_name,
                       SUM(b.volume) AS volume,
                       SUM(b.successes) AS successes,
                       SUM(b.losses) AS losses,
                       SUM(b.tma_seconds_sum) / NULLIF(SUM(b.tma_count), 0) AS tma_seconds,
                       SUM(b.tmr_seconds_sum) / NULLIF(SUM(b.tmr_count), 0) AS tmr_seconds
                FROM base b
                JOIN latest l ON l.indicator_key=b.indicator_key AND l.data_month=b.data_month
                GROUP BY b.data_month, b.segment_id, b.segment_slug, b.segment_name,
                         b.indicator_key, b.login
                ORDER BY b.indicator_key, b.segment_name, b.login
                """,
                params,
            ).fetchall()

            analyst_breakdowns = conn.execute(
                f"""
                WITH base AS (
                    SELECT b.segment_id, b.data_month, b.login, b.dimension, b.dimension_value,
                           b.value, b.volume, b.successes, b.losses,
                           d.indicator_key, d.name,
                           s.slug AS segment_slug, s.name AS segment_name
                    FROM indicator_breakdowns b
                    JOIN indicator_definitions d ON d.id=b.indicator_definition_id
                    JOIN segments s ON s.id=b.segment_id
                    WHERE b.segment_id IN ({placeholders})
                      AND b.scope='team'
                      AND b.dimension IN (
                          'demand', 'service', 'hour',
                          'productivity_component', 'productivity_total'
                      )
                ),
                latest AS (
                    SELECT indicator_key, MAX(data_month) AS data_month
                    FROM base GROUP BY indicator_key
                )
                SELECT b.data_month AS period, b.segment_id, b.segment_slug, b.segment_name,
                       b.indicator_key, b.name, b.login, b.dimension, b.dimension_value,
                       ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS value,
                       SUM(b.volume) AS volume,
                       SUM(b.successes) AS successes,
                       SUM(b.losses) AS losses
                FROM base b
                JOIN latest l ON l.indicator_key=b.indicator_key AND l.data_month=b.data_month
                GROUP BY b.data_month, b.segment_id, b.segment_slug, b.segment_name,
                         b.indicator_key, b.name, b.login, b.dimension, b.dimension_value
                ORDER BY b.indicator_key, b.segment_name, b.dimension, b.dimension_value, b.login
                """,
                params,
            ).fetchall()

            daily_summary = conn.execute(
                f"""
                WITH base AS (
                    SELECT ir.segment_id, ir.period, ir.data_month, ir.value, ir.volume,
                           d.indicator_key, d.name, d.unit,
                           s.slug AS segment_slug, s.name AS segment_name
                    FROM indicator_results ir
                    JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                    JOIN segments s ON s.id=ir.segment_id
                    JOIN user_roles ur ON ur.user_id=ir.user_id
                    JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
                    WHERE ir.segment_id IN ({placeholders})
                ),
                latest AS (
                    SELECT indicator_key, MAX(data_month) AS data_month
                    FROM base GROUP BY indicator_key
                )
                SELECT b.period, b.data_month, b.segment_id, b.segment_slug, b.segment_name,
                       b.indicator_key, b.name, b.unit,
                       ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS value,
                       SUM(b.volume) AS volume
                FROM base b
                JOIN latest l ON l.indicator_key=b.indicator_key AND l.data_month=b.data_month
                GROUP BY b.period, b.data_month, b.segment_id, b.segment_slug, b.segment_name,
                         b.indicator_key, b.name, b.unit
                ORDER BY b.indicator_key, b.period, b.segment_name
                """,
                params,
            ).fetchall()

            freshness = conn.execute(
                f"""
                SELECT d.indicator_key, d.name,
                       MAX(f.data_through) AS data_through,
                       MAX(f.refreshed_at) AS refreshed_at
                FROM indicator_definitions d
                LEFT JOIN indicator_freshness f
                  ON f.indicator_definition_id=d.id AND f.segment_id=d.segment_id
                WHERE d.segment_id IN ({placeholders}) AND d.active=1
                GROUP BY d.indicator_key, d.name
                ORDER BY d.name
                """,
                params,
            ).fetchall()

            external = []
            if include_external:
                external = conn.execute(
                    f"""
                    WITH latest AS (
                        SELECT d.indicator_key, MAX(ir.data_month) AS data_month
                        FROM indicator_results ir
                        JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                        WHERE ir.segment_id IN ({placeholders})
                        GROUP BY d.indicator_key
                    ),
                    base AS (
                        SELECT b.data_month, b.login, b.dimension_value, b.value, b.volume,
                               b.successes, b.losses,
                               b.tma_seconds_sum, b.tma_count, b.tmr_seconds_sum, b.tmr_count,
                               d.indicator_key, d.name
                        FROM indicator_breakdowns b
                        JOIN indicator_definitions d ON d.id=b.indicator_definition_id
                        JOIN latest l ON l.indicator_key=d.indicator_key AND l.data_month=b.data_month
                        WHERE b.segment_id IN ({placeholders})
                          AND b.scope='external' AND b.dimension='external_hour'
                    )
                    SELECT b.data_month AS period, b.indicator_key, b.name, b.login,
                           b.dimension_value AS hour,
                           ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS value,
                           SUM(b.volume) AS volume,
                           SUM(b.successes) AS successes,
                           SUM(b.losses) AS losses,
                           SUM(b.tma_seconds_sum) / NULLIF(SUM(b.tma_count), 0) AS tma_seconds,
                           SUM(b.tmr_seconds_sum) / NULLIF(SUM(b.tmr_count), 0) AS tmr_seconds
                    FROM base b
                    GROUP BY b.data_month, b.indicator_key, b.name, b.login, b.dimension_value
                    ORDER BY b.name, b.login, b.dimension_value
                    """,
                    params + params,
                ).fetchall()

        return {
            "segment_summary": [dict(row) for row in segment_summary],
            "analyst_summary": [dict(row) for row in analyst_summary],
            "analyst_metrics": [dict(row) for row in analyst_metrics],
            "analyst_breakdowns": [dict(row) for row in analyst_breakdowns],
            "daily_summary": [dict(row) for row in daily_summary],
            "breakdowns": [dict(row) for row in breakdowns],
            "external": [dict(row) for row in external],
            "freshness": [dict(row) for row in freshness],
        }

    def replace_breakdowns_for_months(
        self,
        *,
        segment_id: int,
        indicator_definition_id: int,
        rows: tuple[dict, ...],
        months: tuple[str, ...],
    ) -> None:
        with transaction() as conn:
            for month in months:
                conn.execute(
                    "DELETE FROM indicator_breakdowns "
                    "WHERE segment_id=? AND indicator_definition_id=? AND data_month=?",
                    (segment_id, indicator_definition_id, month),
                )
            payload = []
            for row in rows:
                payload.append(
                    (
                        segment_id,
                        indicator_definition_id,
                        str(row.get("scope") or "team"),
                        str(row.get("login") or "").strip().upper(),
                        str(row.get("period") or ""),
                        str(row.get("data_month") or str(row.get("period") or "")[:7]),
                        str(row.get("dimension") or ""),
                        str(row.get("dimension_value") or ""),
                        float(row.get("value") or 0),
                        int(row.get("volume") or 0),
                        int(row.get("successes") or 0),
                        int(row.get("losses") or 0),
                        float(row.get("tma_seconds_sum") or 0),
                        int(row.get("tma_count") or 0),
                        float(row.get("tmr_seconds_sum") or 0),
                        int(row.get("tmr_count") or 0),
                    )
                )
            if payload:
                conn.executemany(
                    """
                    INSERT INTO indicator_breakdowns(
                        segment_id, indicator_definition_id, scope, login, period, data_month,
                        dimension, dimension_value, value, volume, successes, losses,
                        tma_seconds_sum, tma_count, tmr_seconds_sum, tmr_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )

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

    def dashboard_payload(self, segment_id: int, user_id: int) -> dict:
        """Carrega apenas os dados necessários para a visão individual do analista."""
        with connection() as conn:
            user_row = conn.execute(
                "SELECT login FROM users WHERE id=? AND active=1",
                (user_id,),
            ).fetchone()
            login = str(user_row["login"] if user_row else "").strip().upper()

            individual = conn.execute(
                """
                SELECT ir.period, ir.data_month, ir.value, ir.volume,
                       d.indicator_key, d.name, d.target_value, d.direction, d.unit
                FROM indicator_results ir
                JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                WHERE ir.segment_id=? AND ir.user_id=? AND d.active=1
                ORDER BY ir.period DESC, d.name
                """,
                (segment_id, user_id),
            ).fetchall()

            summary = conn.execute(
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
                WHERE ir.segment_id=? AND ir.user_id=? AND d.active=1
                GROUP BY ir.data_month, d.indicator_key, d.name,
                         d.target_value, d.direction, d.unit
                ORDER BY period DESC, d.name
                """,
                (segment_id, user_id),
            ).fetchall()

            team_averages = conn.execute(
                """
                WITH user_month AS (
                    SELECT
                        ir.data_month AS period,
                        d.indicator_key,
                        d.name,
                        d.unit,
                        ir.user_id,
                        ROUND(
                            CAST(SUM(ir.value * ir.volume) AS NUMERIC)
                            / NULLIF(SUM(ir.volume), 0),
                            4
                        ) AS user_avg,
                        SUM(ir.value * ir.volume) AS weighted_value,
                        SUM(ir.volume) AS user_volume
                    FROM indicator_results ir
                    JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                    JOIN users u ON u.id=ir.user_id AND u.active=1
                    JOIN user_roles ur ON ur.user_id=ir.user_id
                    JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
                    WHERE ir.segment_id=? AND d.active=1
                    GROUP BY
                        ir.data_month,
                        d.indicator_key,
                        d.name,
                        d.unit,
                        ir.user_id
                )
                SELECT
                    period,
                    indicator_key,
                    name,
                    unit,
                    CASE
                        WHEN indicator_key IN ('dpa_official', 'productivity_avg_daily')
                            THEN ROUND(AVG(user_avg), 1)
                        ELSE ROUND(
                            CAST(SUM(weighted_value) AS NUMERIC)
                            / NULLIF(SUM(user_volume), 0),
                            1
                        )
                    END AS team_avg,
                    SUM(user_volume) AS team_volume,
                    COUNT(*) AS analysts_with_data,
                    ROUND(
                        CAST(SUM(user_volume) AS NUMERIC)
                        / NULLIF(COUNT(*), 0),
                        1
                    ) AS avg_volume_per_analyst
                FROM user_month
                GROUP BY period, indicator_key, name, unit
                ORDER BY period DESC, name
                """,
                (segment_id,),
            ).fetchall()

            team_daily = conn.execute(
                """
                WITH user_day AS (
                    SELECT
                        ir.period,
                        ir.data_month,
                        d.indicator_key,
                        d.name,
                        d.unit,
                        ir.user_id,
                        ROUND(
                            CAST(SUM(ir.value * ir.volume) AS NUMERIC)
                            / NULLIF(SUM(ir.volume), 0),
                            4
                        ) AS user_avg,
                        SUM(ir.value * ir.volume) AS weighted_value,
                        SUM(ir.volume) AS user_volume
                    FROM indicator_results ir
                    JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
                    JOIN users u ON u.id=ir.user_id AND u.active=1
                    JOIN user_roles ur ON ur.user_id=ir.user_id
                    JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
                    WHERE ir.segment_id=? AND d.active=1
                    GROUP BY
                        ir.period,
                        ir.data_month,
                        d.indicator_key,
                        d.name,
                        d.unit,
                        ir.user_id
                )
                SELECT
                    period,
                    data_month,
                    indicator_key,
                    name,
                    unit,
                    CASE
                        WHEN indicator_key IN ('dpa_official', 'productivity_avg_daily')
                            THEN ROUND(AVG(user_avg), 1)
                        ELSE ROUND(
                            CAST(SUM(weighted_value) AS NUMERIC)
                            / NULLIF(SUM(user_volume), 0),
                            1
                        )
                    END AS team_avg,
                    SUM(user_volume) AS team_volume
                FROM user_day
                GROUP BY period, data_month, indicator_key, name, unit
                ORDER BY period, name
                """,
                (segment_id,),
            ).fetchall()

            team_breakdowns = conn.execute(
                """
                SELECT
                    b.data_month AS period,
                    d.indicator_key,
                    d.name,
                    d.unit,
                    b.dimension,
                    b.dimension_value,
                    ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS team_avg,
                    SUM(b.volume) AS team_volume,
                    SUM(b.successes) AS team_successes,
                    SUM(b.losses) AS team_losses,
                    COUNT(DISTINCT b.login) AS team_analysts
                FROM indicator_breakdowns b
                JOIN indicator_definitions d ON d.id=b.indicator_definition_id
                WHERE b.segment_id=? AND b.scope='team' AND d.active=1
                  AND b.dimension IN (
                    'overall', 'group', 'service', 'demand', 'cause', 'cause_toa', 'cause_sir',
                    'area', 'area_involved', 'network', 'activity_type', 'incident_type',
                    'aging', 'hour', 'turn', 'base', 'queue', 'queue_type', 'productivity_component',
                    'nature', 'impact', 'solution', 'city', 'technology', 'type'
                  )
                GROUP BY b.data_month, d.indicator_key, d.name, d.unit,
                         b.dimension, b.dimension_value
                ORDER BY d.name, b.data_month DESC, b.dimension, b.dimension_value
                """,
                (segment_id,),
            ).fetchall()

            analyst_breakdowns = []
            if login:
                analyst_breakdowns = conn.execute(
                    """
                    SELECT
                        b.period AS day,
                        b.data_month AS period,
                        d.indicator_key,
                        d.name,
                        d.target_value,
                        d.direction,
                        d.unit,
                        b.dimension,
                        b.dimension_value,
                        ROUND(CAST(SUM(b.value * b.volume) AS NUMERIC) / NULLIF(SUM(b.volume), 0), 1) AS value,
                        SUM(b.volume) AS volume,
                        SUM(b.successes) AS successes,
                        SUM(b.losses) AS losses,
                        SUM(b.tma_seconds_sum) / NULLIF(SUM(b.tma_count), 0) AS tma_seconds,
                        SUM(b.tmr_seconds_sum) / NULLIF(SUM(b.tmr_count), 0) AS tmr_seconds
                    FROM indicator_breakdowns b
                    JOIN indicator_definitions d ON d.id=b.indicator_definition_id
                    WHERE b.segment_id=? AND b.scope='team'
                      AND UPPER(b.login)=UPPER(?) AND d.active=1
                    GROUP BY b.period, b.data_month, d.indicator_key, d.name, d.target_value,
                             d.direction, d.unit, b.dimension, b.dimension_value
                    ORDER BY d.name, b.period, b.dimension, b.dimension_value
                    """,
                    (segment_id, login),
                ).fetchall()

            freshness = conn.execute(
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

        return {
            "individual": [dict(row) for row in individual],
            "summary": [dict(row) for row in summary],
            "team_averages": [dict(row) for row in team_averages],
            "team_daily": [dict(row) for row in team_daily],
            "team_breakdowns": [dict(row) for row in team_breakdowns],
            "breakdowns": [dict(row) for row in analyst_breakdowns],
            "freshness": [dict(row) for row in freshness],
        }


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
