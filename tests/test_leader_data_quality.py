"""Safety and scope tests for the read-only leader data quality panel."""
from __future__ import annotations

import unittest

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.application.indicator_quality import (
    ETIT_SMALL_SAMPLE_THRESHOLD,
    build_leader_quality_report,
    classify_etit_quality,
)
from src.config.seed import seed_foundation
from src.infrastructure.database import transaction
from src.infrastructure.repositories import SegmentRepository, UserRepository
from tests.isolated_database import isolate_sqlite_database


class LeaderDataQualityTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        seed_foundation()
        self.users = UserRepository()
        self.segments = SegmentRepository()
        self.service = DashboardService(access=AccessService(self.users))
        self.emp = self.segments.get_by_slug("empresarial")
        self.res = self.segments.get_by_slug("residencial")

    def ctx(self, login):
        return self.service.access.context(self.users.get_by_login(login).id)

    def insert(self, login, segment, key, value, volume, month="2026-09", day=11):
        u = self.users.get_by_login(login)
        with transaction() as conn:
            definition = conn.execute(
                "SELECT id FROM indicator_definitions "
                "WHERE segment_id=? AND indicator_key=? AND active=1",
                (segment.id, key),
            ).fetchone()
            self.assertIsNotNone(definition, (segment.slug, key))
            conn.execute(
                "INSERT INTO indicator_results("
                "segment_id,user_id,indicator_definition_id,period,data_month,value,volume"
                ") VALUES (?,?,?,?,?,?,?)",
                (segment.id, u.id, int(definition["id"]),
                 f"{month}-{day:02}", month, value, volume),
            )

    def test_quality_categories_are_explanatory_not_official_targets(self):
        self.assertEqual(10, ETIT_SMALL_SAMPLE_THRESHOLD)
        self.assertEqual(
            "Incompatível",
            classify_etit_quality({"cancelled": 13, "source_volume": 27, "etit_volume": 0})["status"],
        )
        self.assertEqual(
            "Incompatível",
            classify_etit_quality({"cancelled": 2, "source_volume": 4, "etit_volume": 1})["status"],
        )
        self.assertEqual(
            "Amostra reduzida",
            classify_etit_quality({"cancelled": 0, "source_volume": 0, "etit_volume": 1})["status"],
        )
        self.assertEqual(
            "Sem alerta",
            classify_etit_quality({"cancelled": 1, "source_volume": 2, "etit_volume": 137})["status"],
        )
        self.assertEqual(
            "Sem ETIT", classify_etit_quality(None)["status"]
        )

    def test_bruno_has_low_etit_and_unmatched_cancellations_in_same_month(self):
        self.insert("N5619600", self.emp, "emp_etit_event", 100, 1)
        self.insert("N5619600", self.emp, "toa_cancellation_rate", 50, 4, day=12)
        report = self.service.leader_quality_report(self.ctx("N5619600"), self.emp.id)
        self.assertEqual("2026-09", report["period"])
        own = next(x for x in report["people"] if x["login"] == "N5619600")
        self.assertEqual(1, own["etit_volume"])
        self.assertEqual(2, own["cancelled"])
        self.assertEqual("Incompatível", own["status"])
        self.assertGreaterEqual(report["incompatible"], 1)

    def test_quality_report_never_exposes_another_leader_or_another_sector(self):
        self.insert("N5619600", self.emp, "emp_etit_event", 100, 1)
        self.insert("N0189105", self.emp, "emp_etit_event", 80, 30)
        leandro = self.service.leader_quality_report(self.ctx("N6088107"), self.emp.id)
        logins = {row["login"] for row in leandro["people"]}
        self.assertIn("N6088107", logins)
        self.assertIn("N0189105", logins)
        self.assertNotIn("N5619600", logins)
        self.assertNotIn("N5923221", logins)
        self.assertNotIn("N0238475", logins)
        with self.assertRaises(PermissionError):
            self.service.leader_quality_report(self.ctx("N6088107"), self.res.id)
        with self.assertRaises(PermissionError):
            self.service.leader_quality_report(self.ctx("N0189105"), self.emp.id)

    def test_quality_report_follows_latest_uploaded_source_month(self):
        self.insert("N5923221", self.res, "toa_cancellation_rate", 48.1, 27)
        with transaction() as conn:
            definition = conn.execute(
                "SELECT id FROM indicator_definitions WHERE segment_id=? "
                "AND indicator_key='res_etit_gpon'", (self.res.id,),
            ).fetchone()
            conn.execute(
                "INSERT INTO indicator_freshness("
                "segment_id,indicator_definition_id,data_through,source_key"
                ") VALUES (?,?,?,?)",
                (self.res.id,int(definition["id"]),"2026-09-28","residential_indicators"),
            )
        report = self.service.leader_quality_report(self.ctx("N5923221"), self.res.id)
        kelly = next(x for x in report["people"] if x["login"] == "N5923221")
        self.assertEqual("2026-09", report["period"])
        self.assertEqual(13, kelly["cancelled"])
        self.assertEqual(0, kelly["etit_volume"])
        self.assertEqual("Incompatível", kelly["status"])
        self.assertTrue(
            any(x["indicator_key"]=="res_etit_gpon"
                and x["data_through"]=="2026-09-28" for x in report["sources"])
        )

    def test_monthly_source_mismatch_is_reported_not_silently_reconciled(self):
        leader = {"id": 4, "login": "LEADER", "name": "Leader"}
        report = build_leader_quality_report(
            segment_id=2, month="2026-10",
            current_leader=leader, analysts=[], stats={},
            source_rows=[
                {"indicator_key": "res_etit_gpon", "data_through": "2026-10-05"},
                {"indicator_key": "toa_cancellation_rate", "data_through": "2026-09-28"},
            ],
        )
        self.assertTrue(report["sources_out_of_sync"])
        self.assertEqual(["2026-09", "2026-10"], report["source_months"])
        self.assertEqual("Sem ETIT", report["people"][0]["status"])

    def test_quality_report_is_pure_and_only_contains_permitted_people(self):
        subject = {"id": 4, "login": "LEADER", "name": "Leader"}
        analysts = [{"id": 5, "login": "A1", "name": "Analyst"}]
        stats = {
            (2, 4, "2026-09"): {"cancelled": 0, "etit_volume": 1, "source_volume": 0},
            (2, 5, "2026-09"): {"cancelled": 1, "etit_volume": 10, "source_volume": 1},
            (2, 6, "2026-09"): {"cancelled": 100, "etit_volume": 0, "source_volume": 100},
        }
        report = build_leader_quality_report(
            segment_id=2, month="2026-09", current_leader=subject,
            analysts=analysts, stats=stats, source_rows=[],
        )
        self.assertEqual({"LEADER", "A1"}, {x["login"] for x in report["people"]})
        self.assertEqual(1, report["small_samples"])
        self.assertEqual(1, report["no_alert"])
        self.assertEqual(0, report["incompatible"])


if __name__ == "__main__":
    unittest.main()
