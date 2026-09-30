import unittest

from src.ui.analyst.shell import (
    _build_summary_snapshot,
    _meets_target,
    _period_label,
)


class AnalystSummaryViewTest(unittest.TestCase):
    def test_period_label_formats_yyyymm_in_portuguese(self):
        self.assertEqual("Setembro 2026", _period_label("202609"))

    def test_target_direction_is_respected(self):
        self.assertTrue(_meets_target(92.0, 90.0, "higher_is_better"))
        self.assertFalse(_meets_target(81.0, 90.0, "higher_is_better"))
        self.assertTrue(_meets_target(8.0, 10.0, "lower_is_better"))
        self.assertFalse(_meets_target(12.0, 10.0, "lower_is_better"))

    def test_summary_snapshot_counts_targets_and_team_comparison(self):
        latest = [
            {
                "period": "202609",
                "indicator_key": "chat_10m",
                "name": "Chat 10 min",
                "value": 75.9,
                "target_value": 75.0,
                "direction": "higher_is_better",
                "unit": "percent",
            },
            {
                "period": "202609",
                "indicator_key": "dpa_official",
                "name": "DPA Oficial",
                "value": 81.0,
                "target_value": 90.0,
                "direction": "higher_is_better",
                "unit": "percent",
            },
            {
                "period": "202609",
                "indicator_key": "productivity_avg_daily",
                "name": "Produtividade média diária",
                "value": 34.8,
                "target_value": None,
                "direction": "higher_is_better",
                "unit": "number",
            },
        ]
        team_index = {
            ("202609", "chat_10m"): {"team_avg": 61.1},
            ("202609", "dpa_official"): {"team_avg": 96.4},
            ("202609", "productivity_avg_daily"): {"team_avg": 46.3},
        }
        freshness = [{"data_through": "2026-09-28"}]

        snapshot = _build_summary_snapshot(latest, team_index, freshness)

        self.assertEqual(3, snapshot["tracked"])
        self.assertEqual(2, snapshot["with_target"])
        self.assertEqual(1, snapshot["met"])
        self.assertEqual(3, snapshot["with_team"])
        self.assertEqual(1, snapshot["above_team"])
        self.assertEqual("28/09/2026", snapshot["freshness_label"])
        self.assertEqual("Chat 10 min", snapshot["best_title"])
        self.assertEqual("DPA Oficial", snapshot["attention_title"])


if __name__ == "__main__":
    unittest.main()
