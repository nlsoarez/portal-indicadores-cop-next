import unittest

import pandas as pd

from src.ui.analyst.shell import (
    _build_summary_snapshot,
    _closing_cause_table,
    _closing_dimension_table,
    _closing_review_rows,
    _dpa_chart_scale,
    _dpa_recent_chart_rows,
    _etit_dimension_table,
    _etit_operational_summary,
    _etit_team_demand_cards,
    _meets_target,
    _period_label,
    _productivity_activity_table,
    _productivity_chart_scale,
    _productivity_recent_rows,
    _productivity_user_summary,
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

    def test_etit_operational_summary_keeps_events_adherents_and_durations(self):
        details = pd.DataFrame(
            {
                "dimension": ["overall", "overall"],
                "dimension_value": ["Total", "Total"],
                "volume": [5, 3],
                "successes": [4, 2],
                "losses": [1, 1],
                "tma_seconds": [120.0, 240.0],
                "tmr_seconds": [600.0, 900.0],
            }
        )

        summary = _etit_operational_summary(details)

        self.assertEqual(8, summary["volume"])
        self.assertEqual(6, summary["successes"])
        self.assertEqual(2, summary["losses"])
        self.assertEqual(75.0, summary["adherence"])
        self.assertAlmostEqual(165.0, summary["tma_seconds"], places=1)
        self.assertAlmostEqual(712.5, summary["tmr_seconds"], places=1)

    def test_etit_residential_service_table_compares_with_team(self):
        details = pd.DataFrame(
            {
                "dimension": ["service", "service"],
                "dimension_value": ["BROWNFIELD", "GREENFIELD"],
                "volume": [10, 4],
                "successes": [9, 2],
                "losses": [1, 2],
                "tma_seconds": [60.0, 120.0],
                "tmr_seconds": [600.0, 900.0],
            }
        )
        team = pd.DataFrame(
            {
                "dimension": ["service", "service"],
                "dimension_value": ["BROWNFIELD", "GREENFIELD"],
                "team_avg": [95.0, 80.0],
                "team_volume": [100, 20],
                "team_successes": [95, 16],
                "team_losses": [5, 4],
                "team_analysts": [5, 5],
            }
        )

        table = _etit_dimension_table(
            details,
            team,
            "service",
            "Serviço",
            include_duration=True,
        )

        brownfield = table[table["Serviço"] == "BROWNFIELD"].iloc[0]
        greenfield = table[table["Serviço"] == "GREENFIELD"].iloc[0]

        self.assertEqual("90,0%", brownfield["Aderência %"])
        self.assertEqual("95,0%", brownfield["Média equipe %"])
        self.assertEqual("00:01:00", brownfield["TMA"])
        self.assertEqual("50,0%", greenfield["Aderência %"])

    def test_etit_enterprise_team_demand_cards_show_ral_rec(self):
        team = pd.DataFrame(
            {
                "dimension": ["demand", "demand"],
                "dimension_value": ["RAL", "REC"],
                "team_avg": [92.2, 94.6],
                "team_volume": [100, 50],
                "team_successes": [92.2, 47.3],
                "team_losses": [7.8, 2.7],
                "team_analysts": [2, 2],
            }
        )

        cards = _etit_team_demand_cards(team)
        labels = [item["label"] for item in cards]

        self.assertIn("% RAL Ader. (média equipe)", labels)
        self.assertIn("RAL N. Ader. (média equipe)", labels)
        self.assertIn("% REC Ader. (média equipe)", labels)
        self.assertIn("REC N. Ader. (média equipe)", labels)

    def test_dpa_recent_chart_rows_merge_personal_and_team_daily_values(self):
        payload = {
            "individual": [
                {
                    "indicator_key": "dpa_official",
                    "period": "2026-09-28",
                    "value": 88.0,
                    "volume": 28800,
                },
                {
                    "indicator_key": "dpa_official",
                    "period": "2026-09-29",
                    "value": 92.5,
                    "volume": 28800,
                },
            ],
            "team_daily": [
                {
                    "indicator_key": "dpa_official",
                    "period": "2026-09-28",
                    "team_avg": 90.0,
                },
                {
                    "indicator_key": "dpa_official",
                    "period": "2026-09-29",
                    "team_avg": 94.0,
                },
            ],
        }

        rows = _dpa_recent_chart_rows(payload)

        self.assertEqual(["28/09", "29/09"], [row["date_label"] for row in rows])
        self.assertEqual([88.0, 92.5], [row["value"] for row in rows])
        self.assertEqual([90.0, 94.0], [row["team_avg"] for row in rows])
        self.assertEqual(100.0, _dpa_chart_scale(rows))

    def test_dpa_chart_scale_expands_for_values_above_100(self):
        rows = [
            {"value": 123.1, "team_avg": 96.4},
            {"value": 101.0, "team_avg": 92.0},
        ]

        self.assertEqual(130.0, _dpa_chart_scale(rows))

    def test_productivity_summary_uses_exact_volume_days_and_sector_references(self):
        row = {
            "indicator_key": "productivity_avg_daily",
            "value": 63.8,
            "volume": 17,
        }
        details = pd.DataFrame(
            {
                "dimension": ["productivity_total"],
                "dimension_value": ["Volume Total"],
                "successes": [1085],
                "volume": [1085],
            }
        )
        team = {"team_avg": 84.0}
        team_details = pd.DataFrame(
            {
                "dimension": ["productivity_total"],
                "dimension_value": ["Volume Total"],
                "team_successes": [7045],
                "team_volume": [7045],
                "team_analysts": [5],
            }
        )

        summary = _productivity_user_summary(
            row,
            details,
            team,
            team_details,
        )

        self.assertEqual(1085.0, summary["volume_total"])
        self.assertEqual(63.8, summary["daily_avg"])
        self.assertEqual(17, summary["active_days"])
        self.assertEqual(1409.0, summary["team_volume_avg"])
        self.assertEqual(84.0, summary["team_daily_avg"])

    def test_productivity_activity_table_sums_and_sorts_components(self):
        details = pd.DataFrame(
            {
                "dimension": [
                    "productivity_component",
                    "productivity_component",
                    "productivity_component",
                ],
                "dimension_value": [
                    "Tratativa RAL",
                    "Tratativa RAL",
                    "Fechamento Tarefa TOA",
                ],
                "successes": [200, 99, 230],
            }
        )

        table = _productivity_activity_table(details)

        self.assertEqual(
            ["Tratativa RAL", "Fechamento Tarefa TOA"],
            table["Atividade"].tolist(),
        )
        self.assertEqual([299, 230], table["Volume"].tolist())

    def test_productivity_recent_rows_include_team_reference_and_chart_scale(self):
        payload = {
            "individual": [
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-28",
                    "value": 55.0,
                },
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-29",
                    "value": 80.0,
                },
            ],
            "team_daily": [
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-28",
                    "team_avg": 60.0,
                },
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-29",
                    "team_avg": 75.0,
                },
            ],
        }

        rows = _productivity_recent_rows(payload)

        self.assertEqual(["28/09", "29/09"], [row["date_label"] for row in rows])
        self.assertEqual([55.0, 80.0], [row["value"] for row in rows])
        self.assertEqual([60.0, 75.0], [row["team_avg"] for row in rows])
        self.assertEqual(80.0, _productivity_chart_scale(rows))

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
