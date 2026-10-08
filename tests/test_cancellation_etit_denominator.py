"""Official cancellation rate: cancelled tasks / ETIT event volume of the same month."""
from __future__ import annotations

import unittest

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.config.seed import seed_foundation
from src.infrastructure.database import transaction
from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository
from tests.isolated_database import isolate_sqlite_database


class CancellationEtitDenominatorTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        seed_foundation()
        self.users = UserRepository()
        self.segments = SegmentRepository()
        self.service = DashboardService(access=AccessService(self.users))
        self.res = self.segments.get_by_slug("residencial")
        self.emp = self.segments.get_by_slug("empresarial")

    def insert(self, login, segment, key, value, volume, day="2026-09-11"):
        user = self.users.get_by_login(login)
        definition = IndicatorRepository().get_definition(segment.id, key)
        self.assertIsNotNone(definition, (segment.slug, key))
        with transaction() as conn:
            conn.execute(
                "INSERT INTO indicator_results "
                "(segment_id,user_id,indicator_definition_id,period,data_month,value,volume) "
                "VALUES (?,?,?,?,?,?,?)",
                (segment.id, user.id, int(definition["id"]), day, day[:7], value, volume),
            )

    def ctx(self, login):
        return self.service.access.context(self.users.get_by_login(login).id)

    def test_personal_cancellation_uses_same_month_hfc_plus_gpon(self):
        self.insert("F104752", self.res, "toa_cancellation_rate", 100, 2)
        self.insert("F104752", self.res, "res_etit_gpon", 80, 70)
        self.insert("F104752", self.res, "res_etit_fibra_hfc", 90, 67)
        user = self.users.get_by_login("F104752")
        result = self.service.analyst_payload(self.ctx("F104752"), self.res.id)
        cancel = next(
            row for row in result["summary"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertEqual(2, cancel["cancelled_count"])
        self.assertEqual(137, cancel["etit_volume"])
        self.assertAlmostEqual(1.5, cancel["value"], places=1)
        self.assertFalse(cancel["missing_etit_base"])
        self.assertFalse(cancel["incompatible_etit_base"])
        daily = next(
            row for row in result["individual"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertIsNone(daily["value"])

    def test_missing_etit_does_not_display_source_rate_or_use_previous_month(self):
        self.insert("N5923221", self.res, "toa_cancellation_rate", 48.1, 27)
        self.insert("N5923221", self.res, "res_etit_gpon", 91, 100, "2026-08-11")
        result = self.service.analyst_payload(self.ctx("N5923221"), self.res.id)
        cancel = next(
            row for row in result["summary"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertIsNone(cancel["value"])
        self.assertEqual(13, cancel["cancelled_count"])
        self.assertEqual(0, cancel["etit_volume"])
        self.assertTrue(cancel["missing_etit_base"])

    def test_team_cancel_percentage_uses_all_analyst_etit_volume(self):
        self.insert("F104752", self.res, "toa_cancellation_rate", 100, 1)
        self.insert("F104752", self.res, "res_etit_gpon", 70, 10)
        self.insert("N4014011", self.res, "res_etit_fibra_hfc", 80, 30)
        ctx = self.ctx("N5923221")
        result = self.service.analyst_payload(ctx, self.res.id)
        team = next(
            row for row in result["team_averages"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertEqual(2.5, team["team_avg"])
        self.assertEqual(40, team["team_volume"])
        self.assertEqual(1, team["team_cancelled_count"])
        self.assertEqual(2, team["analysts_with_data"])
        self.assertEqual(0, team["team_unmatched_cancelled"])

        manager = self.service.management_payload(ctx, [self.res.id])
        segment_row = next(
            row for row in manager["segment_summary"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertEqual(2.5, segment_row["value"])
        self.assertEqual(40, segment_row["volume"])
        analyst_row = next(
            row for row in manager["analyst_summary"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertEqual(10.0, analyst_row["value"])
        self.assertEqual(10, analyst_row["etit_volume"])

    def test_unmatched_cancellations_invalidate_team_rate(self):
        self.insert("F104752", self.res, "toa_cancellation_rate", 100, 1)
        self.insert("N4014011", self.res, "res_etit_fibra_hfc", 80, 30)
        data = self.service.analyst_payload(self.ctx("N5923221"), self.res.id)
        team = next(
            row for row in data["team_averages"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertIsNone(team["team_avg"])
        self.assertEqual(1, team["team_unmatched_cancelled"])

    def test_more_cancellations_than_etit_suspends_rate_and_peer_reference(self):
        self.insert("N5619600", self.emp, "toa_cancellation_rate", 50, 4)
        self.insert("N5619600", self.emp, "emp_etit_event", 85, 1)
        data = self.service.analyst_payload(self.ctx("N5619600"), self.emp.id)
        cancel = next(
            row for row in data["summary"]
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertEqual(2, cancel["cancelled_count"])
        self.assertEqual(1, cancel["etit_volume"])
        self.assertIsNone(cancel["value"])
        self.assertTrue(cancel["incompatible_etit_base"])

        refs = self.service.leader_peer_averages(
            self.ctx("N6088107"), self.emp.id
        )
        self.assertNotIn(
            "toa_cancellation_rate", {row["indicator_key"] for row in refs}
        )

    def test_valid_peer_cancellations_use_real_etit_rate_and_latest_month(self):
        self.insert("N5619600", self.emp, "toa_cancellation_rate", 50, 4)
        self.insert("N5619600", self.emp, "emp_etit_event", 90, 20)
        self.insert("N0238475", self.res, "toa_cancellation_rate", 100, 1)
        self.insert("N0238475", self.res, "res_etit_gpon", 85, 20)
        peers = self.service.leader_peer_averages(
            self.ctx("N6088107"), self.emp.id
        )
        cancel = next(
            row for row in peers
            if row["indicator_key"] == "toa_cancellation_rate"
        )
        self.assertEqual(7.5, cancel["peer_avg"])
        self.assertEqual(2, cancel["peer_count"])


if __name__ == "__main__":
    unittest.main()
