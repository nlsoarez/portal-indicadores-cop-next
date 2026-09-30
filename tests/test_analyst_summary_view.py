import unittest

import pandas as pd

from src.ui.analyst.shell import (
    _build_summary_snapshot,
    _closing_cause_table,
    _closing_dimension_table,
    _closing_review_rows,
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

    def test_closing_causes_are_grouped_without_duplicate_labels(self):
        details = pd.DataFrame(
            {
                "dimension": ["cause_toa", "cause_toa", "cause_toa"],
                "dimension_value": ["VANDALISMO", "VANDALISMO", "CARGA ALTA"],
                "losses": [1, 2, 1],
                "volume": [1, 2, 1],
                "successes": [0, 0, 0],
            }
        )

        table = _closing_cause_table(details, "cause_toa", "Causa TOA")

        self.assertEqual(["VANDALISMO", "CARGA ALTA"], table["Causa TOA"].tolist())
        self.assertEqual([3, 1], table["Não Assertivos"].tolist())

    def test_closing_group_and_demand_tables_compare_with_team(self):
        details = pd.DataFrame(
            {
                "dimension": ["group", "group", "demand", "demand"],
                "dimension_value": ["Rio e ES", "Norte", "RAL", "REC"],
                "volume": [10, 2, 8, 4],
                "successes": [9, 1, 6, 4],
                "losses": [1, 1, 2, 0],
            }
        )
        team = pd.DataFrame(
            {
                "dimension": ["group", "group", "demand", "demand"],
                "dimension_value": ["Rio e ES", "Norte", "RAL", "REC"],
                "volume": [100, 20, 80, 40],
                "successes": [95, 16, 72, 38],
                "losses": [5, 4, 8, 2],
            }
        )

        groups = _closing_dimension_table(details, team, "group", "Grupo")
        demands = _closing_dimension_table(details, team, "demand", "Demanda")

        rio = groups[groups["Grupo"] == "Rio e ES"].iloc[0]
        ral = demands[demands["Demanda"] == "RAL"].iloc[0]

        self.assertEqual("90,0%", rio["Meu resultado"])
        self.assertEqual("95,0%", rio["Média da equipe"])
        self.assertEqual("75,0%", ral["Meu resultado"])
        self.assertEqual("90,0%", ral["Média da equipe"])

    def test_closing_review_rows_keep_ral_rec_and_daily_context(self):
        details = pd.DataFrame(
            {
                "dimension": ["incident", "incident"],
                "dimension_value": ["RAL|||24057920", "REC|||24058280"],
                "day": ["2026-09-17", "2026-09-16"],
                "losses": [1, 1],
                "volume": [1, 1],
                "successes": [0, 0],
            }
        )
        payload = {
            "individual": [
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-17",
                    "value": 0.0,
                    "volume": 1,
                },
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-16",
                    "value": 66.7,
                    "volume": 3,
                },
            ],
            "team_daily": [
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-17",
                    "team_avg": 66.7,
                },
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-16",
                    "team_avg": 75.0,
                },
            ],
        }

        rows = _closing_review_rows(details, payload)

        self.assertEqual(["RAL", "REC"], [row["Demanda"] for row in rows])
        self.assertEqual(
            ["24057920", "24058280"],
            [row["INC / Identificador"] for row in rows],
        )
        self.assertEqual("0,0%", rows[0]["Resultado do dia"])
        self.assertEqual("66,7%", rows[0]["Média da equipe no dia"])

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
