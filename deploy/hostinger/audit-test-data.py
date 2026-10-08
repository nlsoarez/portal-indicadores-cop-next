"""Read-only report of synthetic records possibly inserted by old unit tests.

NEVER auto-delete these records: similar dates and values can be legitimate.
Review the report and take a database backup before remediation.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from src.infrastructure.database import connection


def _json_default(value):
    if isinstance(value, (Decimal, date, datetime)):
        return str(value)
    return str(value)


def main() -> None:
    with connection() as conn:
        users = conn.execute(
            """
            SELECT id, login, display_name, active, created_at
            FROM users
            WHERE UPPER(login)='TESTLEADER'
            """
        ).fetchall()
        definitions = conn.execute(
            """
            SELECT s.slug AS segment, d.id, d.indicator_key, d.name, d.active
            FROM indicator_definitions d
            JOIN segments s ON s.id=d.segment_id
            WHERE d.name='ETIT espelho'
            """
        ).fetchall()
        possible_results = conn.execute(
            """
            SELECT s.slug AS segment, u.login, d.indicator_key,
                   ir.period, ir.data_month, ir.value, ir.volume, ir.created_at
            FROM indicator_results ir
            JOIN users u ON u.id=ir.user_id
            JOIN segments s ON s.id=ir.segment_id
            JOIN indicator_definitions d ON d.id=ir.indicator_definition_id
            WHERE UPPER(u.login)='TESTLEADER'
               OR (
                  u.login IN (
                    'N6088107','N5619600','N5923221','N0238475'
                  )
                  AND d.indicator_key IN (
                    'dpa_official','emp_etit_event','res_etit_fibra_hfc'
                  )
                  AND ir.period IN (
                    '2026-09-03','2026-09-04','2026-09-05','2026-08-03',
                    '2026-09-02','2026-08-02','2026-10-02'
                  )
               )
            ORDER BY ir.created_at DESC, u.login, ir.period
            LIMIT 120
            """
        ).fetchall()
    print(
        json.dumps(
            {
                "warning": (
                    "SOMENTE LEITURA. Alguns registros podem ser legítimos; "
                    "não excluir automaticamente."
                ),
                "synthetic_user_candidates": [dict(row) for row in users],
                "synthetic_indicator_candidates": [dict(row) for row in definitions],
                "indicator_result_candidates": [dict(row) for row in possible_results],
            },
            indent=2,
            ensure_ascii=False,
            default=_json_default,
        )
    )


if __name__ == "__main__":
    main()
