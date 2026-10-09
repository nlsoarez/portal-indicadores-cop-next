"""Controlled, one-time recovery of Jefferson's misclassified ETIT events.

Reconstructs ONLY verifiable nightly event counts from stored external-hour
breakdowns. RAL/REC labels were not preserved and MUST NOT be fabricated.
The complete original XLSX is still required to recover those dimensions.
"""
from __future__ import annotations

from collections import defaultdict
from src.infrastructure.database import connection, transaction

ALIAS_LOGIN = "N6105010"
CANONICAL_LOGIN = "N6173055"
EXPECTED = {
    "2026-09": (30, 29, 1),
    "2026-10": (8, 8, 0),
}


class EtitRecoveryGuardError(RuntimeError):
    pass


def recover_jefferson_etit(*, apply: bool = False) -> dict:
    """Preview or atomically reattribute exact verified historical buckets.

    Never touches any other analyst, definition, or month.
    Aborts if source counts changed or existing canonical events could overlap.
    """
    manager = transaction() if apply else connection()
    with manager as conn:
        owner = conn.execute(
            """
            SELECT u.id, u.login FROM users u
            JOIN user_roles ur ON ur.user_id=u.id
            JOIN roles r ON r.id=ur.role_id AND r.code='analyst'
            JOIN user_performance_segments ups ON ups.user_id=u.id
            JOIN segments s ON s.id=ups.segment_id AND s.slug='empresarial'
            WHERE u.login=? AND u.active=1
            """,
            (CANONICAL_LOGIN,),
        ).fetchone()
        definition = conn.execute(
            """
            SELECT d.id, d.segment_id FROM indicator_definitions d
            JOIN segments s ON s.id=d.segment_id AND s.slug='empresarial'
            WHERE d.indicator_key='emp_etit_event' AND d.active=1
            """,
        ).fetchone()
        if not owner or not definition:
            raise EtitRecoveryGuardError(
                "Cadastro de Jefferson ou definição ETIT Empresarial não encontrado"
            )
        user_id = int(owner["id"])
        def_id = int(definition["id"])
        seg_id = int(definition["segment_id"])
        rows = conn.execute(
            """
            SELECT id, period, data_month, dimension_value, volume,
                   successes, losses, tma_seconds_sum, tma_count,
                   tmr_seconds_sum, tmr_count
            FROM indicator_breakdowns
            WHERE segment_id=? AND indicator_definition_id=?
              AND scope='external' AND dimension='external_hour'
              AND UPPER(login)=?
              AND data_month IN ('2026-09','2026-10')
            ORDER BY id
            """,
            (seg_id, def_id, ALIAS_LOGIN),
        ).fetchall()
        existing_results = conn.execute(
            """
            SELECT COUNT(*) AS n FROM indicator_results
            WHERE segment_id=? AND indicator_definition_id=? AND user_id=?
              AND data_month IN ('2026-09','2026-10')
            """,
            (seg_id, def_id, user_id),
        ).fetchone()["n"]
        existing_team = conn.execute(
            """
            SELECT COUNT(*) AS n FROM indicator_breakdowns
            WHERE segment_id=? AND indicator_definition_id=?
              AND scope='team' AND UPPER(login)=?
              AND data_month IN ('2026-09','2026-10')
            """,
            (seg_id, def_id, CANONICAL_LOGIN),
        ).fetchone()["n"]

        if not rows:
            if existing_results and existing_team:
                return {
                    "status": "already_recovered_or_reimported",
                    "rows_changed": 0,
                    "message": "Nenhuma fonte externa pendente; dados internos já existentes.",
                }
            raise EtitRecoveryGuardError(
                "Nenhum bucket externo recuperável foi encontrado. "
                "Use o XLSX original se a fonte já foi substituída."
            )
        if existing_results or existing_team:
            raise EtitRecoveryGuardError(
                "Há dados internos de Jefferson para estas competências: "
                "reconciliação bloqueada para evitar duplicação."
            )

        by_month = defaultdict(lambda: [0, 0, 0])
        per_day = defaultdict(lambda: [0, 0, 0, 0.0, 0, 0.0, 0])
        events_with_date_outside_competence = 0
        for row in rows:
            month = str(row["data_month"])
            hour = str(row["dimension_value"])
            volume = int(row["volume"])
            positives = int(row["successes"])
            negatives = int(row["losses"])
            if hour not in {str(x) for x in range(24)} or int(hour) not in {
                0, 1, 2, 3, 4, 5, 22, 23
            }:
                raise EtitRecoveryGuardError("Bucket com horário não noturno")
            if volume <= 0 or positives < 0 or negatives < 0 or positives + negatives != volume:
                raise EtitRecoveryGuardError("Volume/aderência inconsistente no histórico")
            if not str(row["period"]).startswith(month):
                events_with_date_outside_competence += volume
            by_month[month][0] += volume
            by_month[month][1] += positives
            by_month[month][2] += negatives
            values = per_day[(month, str(row["period"]))]
            values[0] += volume
            values[1] += positives
            values[2] += negatives
            values[3] += float(row["tma_seconds_sum"] or 0)
            values[4] += int(row["tma_count"] or 0)
            values[5] += float(row["tmr_seconds_sum"] or 0)
            values[6] += int(row["tmr_count"] or 0)

        actual = {month: tuple(values) for month, values in by_month.items()}
        if actual != EXPECTED:
            raise EtitRecoveryGuardError(
                f"Fonte diferente da auditoria: esperado={EXPECTED}, encontrado={actual}. "
                "Não realizar backfill automático."
            )
        snapshot = {
            "status": "ready_to_recover" if not apply else "recovered",
            "login_source": ALIAS_LOGIN,
            "login_canonical": CANONICAL_LOGIN,
            "person": "JEFFERSON LUIS GONÇALVES COITINHO",
            "months": {
                month: {
                    "events": value[0], "adherent": value[1],
                    "not_adherent": value[2],
                }
                for month, value in sorted(actual.items())
            },
            "source_buckets": len(rows),
            "days": len(per_day),
            "events_with_date_outside_competence": events_with_date_outside_competence,
            "ral_rec": "NÃO DISPONÍVEL nesta fonte; exige reimportação completa",
        }
        if not apply:
            return snapshot

        for (month, period), (
            volume, successes, losses, tma_sum, tma_count, tmr_sum, tmr_count
        ) in sorted(per_day.items()):
            adherence = round(100 * successes / volume, 1)
            conn.execute(
                """
                INSERT INTO indicator_results (
                    segment_id, user_id, indicator_definition_id,
                    period, data_month, value, volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (seg_id, user_id, def_id, period, month, adherence, volume),
            )
            conn.execute(
                """
                INSERT INTO indicator_breakdowns (
                    segment_id, indicator_definition_id, scope, login,
                    period, data_month, dimension, dimension_value,
                    value, volume, successes, losses, tma_seconds_sum,
                    tma_count, tmr_seconds_sum, tmr_count
                ) VALUES (?,?, 'team', ?, ?, ?, 'overall', 'Total',
                          ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (seg_id, def_id, CANONICAL_LOGIN, period, month, adherence,
                 volume, successes, losses, tma_sum, tma_count, tmr_sum, tmr_count),
            )

        ids = [int(row["id"]) for row in rows]
        params = ", ".join("?" for _ in ids)
        cur = conn.execute(
            "UPDATE indicator_breakdowns SET scope='team', login=?, "
            "dimension='hour' WHERE id IN (" + params + ") "
            "AND scope='external' AND UPPER(login)=?",
            (CANONICAL_LOGIN, *ids, ALIAS_LOGIN),
        )
        if cur.rowcount != len(rows):
            raise EtitRecoveryGuardError(
                "Alteração de escopo incompleta, transação revertida"
            )
        check = conn.execute(
            """
            SELECT data_month, SUM(volume) AS volume
            FROM indicator_results
            WHERE segment_id=? AND indicator_definition_id=? AND user_id=?
              AND data_month IN ('2026-09','2026-10')
            GROUP BY data_month
            """,
            (seg_id, def_id, user_id),
        ).fetchall()
        if {str(r["data_month"]): int(r["volume"]) for r in check} != {
            month: values[0] for month, values in EXPECTED.items()
        }:
            raise EtitRecoveryGuardError("Totais não conferem; transação revertida")
        snapshot["rows_changed"] = len(rows) + 2 * len(per_day)
        return snapshot
