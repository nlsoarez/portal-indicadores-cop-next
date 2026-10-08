import unittest
from types import SimpleNamespace

from src.ui.subadmin.shell import (
    _operational_segment,
    _team_ranking,
    _team_snapshot,
)


class LeaderWorkspaceTest(unittest.TestCase):
    def test_sector_is_unique_and_independent_of_extra_sidebar_segments(self):
        segments = [
            SimpleNamespace(id=1, slug="preventiva", name="Preventiva"),
            SimpleNamespace(id=2, slug="residencial", name="Residencial"),
            SimpleNamespace(id=3, slug="empresarial", name="Empresarial"),
        ]

        class FakeUsers:
            def performance_segments_for_user(self, user_id):
                return [segments[2]]

        class FakeAccess:
            def assert_segment_access(self, ctx, segment_id):
                if segment_id != 3:
                    raise PermissionError("segmento incorreto")

        ctx = SimpleNamespace(
            user=SimpleNamespace(id=7),
            is_subadmin=True,
            is_admin=False,
        )
        own = _operational_segment(ctx, segments, FakeUsers(), FakeAccess())
        self.assertEqual("empresarial", own.slug)

    def test_segment_must_be_unique_for_leader(self):
        segment = SimpleNamespace(id=2, slug="residencial")

        class FakeUsers:
            def performance_segments_for_user(self, user_id):
                return []

        ctx = SimpleNamespace(
            user=SimpleNamespace(id=7),
            is_subadmin=True,
            is_admin=False,
        )
        with self.assertRaises(PermissionError):
            _operational_segment(ctx, [segment], FakeUsers(), None)

    def test_team_snapshot_does_not_assume_missing_metrics_are_zero(self):
        rows = [
            {
                "period": "2026-09", "indicator_key": "emp_etit_event",
                "name": "ETIT", "value": 91.0,
                "target_value": 90.0, "direction": "higher_is_better",
            },
            {
                "period": "2026-09", "indicator_key": "toa_cancellation_rate",
                "name": "Canceladas", "value": 19.0,
                "target_value": 15.0, "direction": "lower_is_better",
            },
            {
                "period": "2026-09", "indicator_key": "productivity_avg_daily",
                "name": "Produtividade", "value": 12.0,
                "target_value": None, "direction": "higher_is_better",
            },
            {
                "period": "2026-09", "indicator_key": "chat_10m",
                "name": "Chat", "value": None,
                "target_value": 75.0, "direction": "higher_is_better",
            },
        ]
        result = _team_snapshot(rows, 9)
        self.assertEqual(9, result["analysts"])
        self.assertEqual(4, result["indicators"])
        self.assertEqual(2, result["with_target"])
        self.assertEqual(1, result["met"])
        self.assertEqual(1, result["attention"])

    def test_team_ranking_respects_latest_period_and_lower_better(self):
        summary = [{
            "indicator_key": "toa_cancellation_rate",
            "period": "2026-10", "direction": "lower_is_better",
            "unit": "percent",
        }]
        analysts = [
            {
                "indicator_key": "toa_cancellation_rate",
                "period": "2026-10", "display_name": "Analista A",
                "login": "A", "value": 9.0, "volume": 80,
            },
            {
                "indicator_key": "toa_cancellation_rate",
                "period": "2026-10", "display_name": "Analista B",
                "login": "B", "value": 3.0, "volume": 60,
            },
            {
                "indicator_key": "toa_cancellation_rate",
                "period": "2026-09", "display_name": "Dado antigo",
                "login": "OLD", "value": 1.0, "volume": 100,
            },
        ]
        ranking = _team_ranking(summary, analysts, "toa_cancellation_rate")
        self.assertEqual(["B", "A"], ranking["Login"].tolist())
        self.assertEqual(["3,0%", "9,0%"], ranking["Resultado"].tolist())


if __name__ == "__main__":
    unittest.main()
