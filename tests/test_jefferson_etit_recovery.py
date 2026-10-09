"""Safe Jefferson ETIT alias recovery tests, strictly on disposable SQLite."""
from __future__ import annotations

import math
import unittest

import pandas as pd

from src.application.etit_alias_recovery import (
    EtitRecoveryGuardError, recover_jefferson_etit,
)
from src.config.seed import seed_foundation
from src.infrastructure.database import connection, transaction
from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository
from src.ui.admin.indicators.etit_enterprise import (
    build_demand_analyst_table, build_ranking_table, demand_team_averages,
)
from tests.isolated_database import isolate_sqlite_database


class JeffersonLegacyEtitRecoveryTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        seed_foundation()
        self.segment = SegmentRepository().get_by_slug("empresarial")
        self.owner = UserRepository().get_by_login("N6173055")
        self.definition = IndicatorRepository().get_definition(
            self.segment.id, "emp_etit_event"
        )
        self.def_id = int(self.definition["id"])
        self.assertIsNotNone(self.owner)

    def _insert_bucket(self, month, date, volume, adherents, *, login="N6105010", hour="22"):
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO indicator_breakdowns(
                    segment_id,indicator_definition_id,scope,login,period,
                    data_month,dimension,dimension_value,value,volume,
                    successes,losses,tma_seconds_sum,tma_count,
                    tmr_seconds_sum,tmr_count
                ) VALUES (?,?, 'external',?,?,?,'external_hour',?,?,?,?,
                          ?,?,?,?,?)
                """,
                (
                    self.segment.id, self.def_id, login, date, month, hour,
                    round(100 * adherents / volume, 1), volume, adherents,
                    volume-adherents, float(volume)*5, volume,
                    float(volume)*12, volume,
                ),
            )

    def _load_verified_source(self):
        self._insert_bucket("2026-09", "2026-09-02", 30, 29)
        self._insert_bucket("2026-10", "2026-10-02", 4, 4, hour="0")
        self._insert_bucket("2026-10", "2026-10-06", 4, 4, hour="5")
        self._insert_bucket("2026-10", "2026-10-06", 9, 7, login="OTHERTEAM")

    def test_dry_run_never_writes_and_reports_exact_months(self):
        self._load_verified_source()
        before = recover_jefferson_etit()
        self.assertEqual("ready_to_recover", before["status"])
        self.assertEqual(30, before["months"]["2026-09"]["events"])
        self.assertEqual(8, before["months"]["2026-10"]["events"])
        self.assertIn("NÃO DISPONÍVEL", before["ral_rec"])
        with connection() as conn:
            results = conn.execute(
                "SELECT COUNT(*) AS n FROM indicator_results WHERE user_id=? "
                "AND indicator_definition_id=?",
                (self.owner.id, self.def_id),
            ).fetchone()
            self.assertEqual(0, results["n"])

    def test_apply_moves_only_jefferson_and_is_idempotent(self):
        self._load_verified_source()
        result = recover_jefferson_etit(apply=True)
        self.assertEqual("recovered", result["status"])
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT data_month, SUM(volume) AS volume
                FROM indicator_results
                WHERE indicator_definition_id=? AND user_id=?
                GROUP BY data_month ORDER BY data_month
                """,
                (self.def_id, self.owner.id),
            ).fetchall()
            self.assertEqual(
                [("2026-09", 30), ("2026-10", 8)],
                [(r["data_month"], r["volume"]) for r in rows],
            )
            metrics = conn.execute(
                """
                SELECT scope,login,dimension,data_month,SUM(volume) AS volume
                FROM indicator_breakdowns
                WHERE indicator_definition_id=?
                GROUP BY scope,login,dimension,data_month
                ORDER BY login,dimension,data_month
                """,
                (self.def_id,),
            ).fetchall()
            by_key = {
                (r["scope"],r["login"],r["dimension"],r["data_month"]): r["volume"]
                for r in metrics
            }
            self.assertEqual(
                8, by_key[("team", "N6173055", "overall", "2026-10")]
            )
            self.assertEqual(
                8, by_key[("team", "N6173055", "hour", "2026-10")]
            )
            self.assertEqual(
                9, by_key[("external", "OTHERTEAM", "external_hour", "2026-10")]
            )
            self.assertNotIn(
                ("external", "N6105010", "external_hour", "2026-10"), by_key
            )
        again = recover_jefferson_etit(apply=True)
        self.assertEqual("already_recovered_or_reimported", again["status"])
        self.assertEqual(0, again["rows_changed"])

        report = IndicatorRepository().management_payload([self.segment.id])
        people = pd.DataFrame(report["analyst_summary"])
        metrics = pd.DataFrame(report["analyst_metrics"])
        breakdowns = pd.DataFrame(report["analyst_breakdowns"])
        current = people[
            (people["indicator_key"] == "emp_etit_event")
            & (people["period"] == "2026-10")
        ]
        result = build_ranking_table(
            current, metrics[metrics["indicator_key"] == "emp_etit_event"],
            breakdowns[breakdowns["indicator_key"] == "emp_etit_event"],
        )
        jefferson = result[result["Nome"] == "Jefferson"].iloc[0]
        self.assertEqual(8, jefferson["Eventos"])
        self.assertEqual(8, jefferson["Aderentes"])
        self.assertEqual(100.0, jefferson["Aderência %"])
        self.assertEqual("—", jefferson["RAL"])
        self.assertEqual("—", jefferson["REC"])

        averages = demand_team_averages(current, breakdowns)
        self.assertEqual(0.0, averages["ral_adherents"])
        detail = build_demand_analyst_table(current, breakdowns)
        self.assertTrue(detail.empty)  # RAL/REC not preserved in hourly source.

    def test_unknown_demand_is_not_shown_as_zero_for_jefferson(self):
        people = pd.DataFrame({
            "login": ["N6173055", "N0189105"],
            "display_name": ["Jefferson", "Igor"],
            "volume": [8, 5],
            "value": [100, 80],
            "segment_name": ["Empresarial", "Empresarial"],
        })
        metrics = pd.DataFrame({
            "login": ["N6173055", "N0189105"],
            "volume": [8, 5],
            "successes": [8, 4], "losses": [0, 1],
        })
        breakdowns = pd.DataFrame({
            "login": ["N0189105"],
            "dimension": ["demand"],
            "dimension_value": ["RAL"],
            "volume": [5], "successes": [4], "losses": [1],
        })
        rank = build_ranking_table(people, metrics, breakdowns)
        jefferson = rank[rank["Nome"] == "Jefferson"].iloc[0]
        self.assertEqual("—", jefferson["RAL"])
        self.assertEqual("—", jefferson["REC"])
        detail = build_demand_analyst_table(people, breakdowns)
        jefferson_detail = detail[detail["Analista"] == "Jefferson"].iloc[0]
        self.assertTrue(math.isnan(jefferson_detail["RAL Ader."]))
        avg = demand_team_averages(people, breakdowns)
        self.assertEqual(4.0, avg["ral_adherents"])

    def test_guard_aborts_without_touching_data_if_volume_changes(self):
        self._load_verified_source()
        with transaction() as conn:
            conn.execute(
                "UPDATE indicator_breakdowns SET volume=9,successes=9 "
                "WHERE login='N6105010' AND data_month='2026-10'"
            )
        with self.assertRaises(EtitRecoveryGuardError):
            recover_jefferson_etit(apply=True)
        with connection() as conn:
            self.assertEqual(
                0, conn.execute(
                    "SELECT COUNT(*) AS n FROM indicator_results WHERE user_id=? "
                    "AND indicator_definition_id=?",
                    (self.owner.id, self.def_id),
                ).fetchone()["n"]
            )

    def test_guard_never_overwrites_already_imported_canonical_results(self):
        self._load_verified_source()
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO indicator_results(
                    segment_id,user_id,indicator_definition_id,
                    period,data_month,value,volume
                ) VALUES (?, ?, ?, '2026-10-06', '2026-10', 100, 5)
                """,
                (self.segment.id, self.owner.id, self.def_id),
            )
        with self.assertRaises(EtitRecoveryGuardError):
            recover_jefferson_etit(apply=True)


if __name__ == "__main__":
    unittest.main()
