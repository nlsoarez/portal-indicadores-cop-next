import unittest

import pandas as pd

from src.ui.admin.indicators.closing_toa_sir import (
    build_analyst_ranking,
    build_assertiveness_dimension_table,
    build_non_assertive_cause_table,
    compact_period,
    overall_summary,
    ranking_extremes,
)


class ClosingToaSirAdminViewTest(unittest.TestCase):
    def test_overall_summary_uses_actual_volume_and_losses(self):
        rows = pd.DataFrame(
            {
                "volume": [103],
                "value": [91.3],
                "analysts": [10],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B"],
                "volume": [50, 53],
                "successes": [45, 49],
                "losses": [5, 4],
            }
        )
        details = pd.DataFrame(
            {
                "dimension": ["overall"],
                "dimension_value": ["Total"],
                "volume": [103],
                "successes": [94],
                "losses": [9],
            }
        )

        result = overall_summary(rows, metrics, details)

        self.assertEqual(103, result["total"])
        self.assertEqual(94, result["assertive"])
        self.assertEqual(9, result["non_assertive"])
        self.assertAlmostEqual(91.3, result["assertiveness"], places=1)
        self.assertEqual(2, result["analysts"])

    def test_ranking_orders_by_assertiveness_then_volume(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "display_name": ["ROBERTO", "MONICA", "SANDRO"],
                "segment_name": ["Empresarial"] * 3,
                "volume": [18, 18, 8],
                "value": [100.0, 100.0, 62.5],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "volume": [18, 18, 8],
                "successes": [18, 18, 5],
                "losses": [0, 0, 3],
            }
        )

        table = build_analyst_ranking(people, metrics)

        self.assertEqual(["MONICA", "ROBERTO", "SANDRO"], sorted(table.iloc[:2]["Analista"].tolist()) + ["SANDRO"])
        self.assertEqual(62.5, float(table.iloc[-1]["Assertividade %"]))

    def test_extremes_consider_full_ranking(self):
        ranking = pd.DataFrame(
            {
                "Analista": ["A", "B", "C"],
                "Tarefas": [18, 12, 8],
                "Assertividade %": [100.0, 87.5, 62.5],
            }
        )

        best, worst = ranking_extremes(ranking)

        self.assertEqual("A", best["Analista"])
        self.assertEqual("C", worst["Analista"])

    def test_non_assertive_causes_sum_losses(self):
        details = pd.DataFrame(
            {
                "dimension": ["cause_toa", "cause_toa", "cause_toa"],
                "dimension_value": ["ROMPIDO", "ROMPIDO", "VANDALISMO"],
                "volume": [2, 1, 1],
                "successes": [0, 0, 0],
                "losses": [2, 1, 1],
            }
        )

        table = build_non_assertive_cause_table(details, "cause_toa", "Causa TOA")

        self.assertEqual(["ROMPIDO", "VANDALISMO"], table["Causa TOA"].tolist())
        self.assertEqual([3, 1], table["Não Assertivo"].tolist())

    def test_group_and_demand_table_calculate_assertiveness(self):
        details = pd.DataFrame(
            {
                "dimension": ["group", "group", "demand", "demand"],
                "dimension_value": ["Rio e ES", "Norte", "RAL", "REC"],
                "volume": [62, 1, 90, 13],
                "successes": [61, 0, 81, 13],
                "losses": [1, 1, 9, 0],
            }
        )

        groups = build_assertiveness_dimension_table(details, "group", "Grupo")
        demands = build_assertiveness_dimension_table(details, "demand", "Demanda")

        rio = groups[groups["Grupo"] == "Rio e ES"].iloc[0]
        norte = groups[groups["Grupo"] == "Norte"].iloc[0]
        ral = demands[demands["Demanda"] == "RAL"].iloc[0]
        rec = demands[demands["Demanda"] == "REC"].iloc[0]

        self.assertAlmostEqual(98.4, float(rio["Assertividade %"]), places=1)
        self.assertEqual(0.0, float(norte["Assertividade %"]))
        self.assertEqual(90.0, float(ral["Assertividade %"]))
        self.assertEqual(100.0, float(rec["Assertividade %"]))

    def test_period_is_displayed_as_yyyymm(self):
        self.assertEqual("202609", compact_period("2026-09"))
        self.assertEqual("202609", compact_period("2026-09-30"))


if __name__ == "__main__":
    unittest.main()
