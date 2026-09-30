import unittest

import pandas as pd

from src.ui.admin.indicators.chat_toa import (
    build_tma_ranking,
    build_tma_sector_tables,
    sector_tma_summary,
    compact_period,
    overall_summary,
    ranking_extremes,
)


class ChatToaAdminViewTest(unittest.TestCase):
    def test_overall_summary_uses_volume_adherents_and_tma(self):
        rows = pd.DataFrame(
            {
                "indicator_key": ["chat_10m"],
                "volume": [1296],
                "value": [65.1],
            }
        )
        metrics = pd.DataFrame()
        details = pd.DataFrame(
            {
                "dimension": ["overall"],
                "dimension_value": ["Total"],
                "volume": [1296],
                "successes": [844],
                "losses": [452],
                "tma_seconds": [1044],
            }
        )

        result = overall_summary(rows, metrics, details)

        self.assertEqual(1296, result["volume"])
        self.assertEqual(844, result["adherents"])
        self.assertAlmostEqual(65.1, result["adherence"], places=1)
        self.assertEqual(17.4, result["tma_minutes"])

    def test_ranking_is_ordered_by_chat_volume(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "display_name": ["RAISSA", "SANDRO", "MONICA"],
                "segment_name": ["Residencial", "Empresarial", "Empresarial"],
                "volume": [153, 115, 40],
                "value": [49.0, 75.7, 92.5],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "volume": [153, 115, 40],
                "successes": [75, 87, 37],
                "losses": [78, 28, 3],
                "tma_seconds": [3334.8, 483.0, 360.0],
            }
        )

        table = build_tma_ranking(people, metrics)

        self.assertEqual(["RAISSA", "SANDRO", "MONICA"], table["Analista"].tolist())
        self.assertEqual([153, 115, 40], table["Vol. TMA"].tolist())
        self.assertEqual([75, 87, 37], table["Aderentes"].tolist())
        self.assertAlmostEqual(49.0, float(table.iloc[0]["TMA %"]), places=1)
        self.assertAlmostEqual(55.58, float(table.iloc[0]["TMA Médio (min)"]), places=2)

    def test_extremes_consider_entire_team_not_only_top_volume(self):
        ranking = pd.DataFrame(
            {
                "Analista": ["RAISSA", "MONICA", "KELLY"],
                "Vol. TMA": [153, 40, 20],
                "TMA %": [49.0, 92.5, 23.1],
            }
        )

        best, worst = ranking_extremes(ranking)

        self.assertEqual("MONICA", best["Analista"])
        self.assertEqual("KELLY", worst["Analista"])


    def test_metrics_display_name_resolves_login_even_without_people_result(self):
        people = pd.DataFrame(
            {
                "login": ["A"],
                "display_name": ["RAISSA"],
                "segment_name": ["Residencial"],
                "volume": [153],
                "value": [49.0],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["N5923221", "A"],
                "display_name": ["KELLY LIRA", None],
                "segment_name": ["Residencial", "Residencial"],
                "volume": [20, 153],
                "successes": [5, 75],
                "losses": [15, 78],
                "tma_seconds": [1200.0, 3334.8],
            }
        )

        table = build_tma_ranking(people, metrics)

        self.assertIn("KELLY LIRA", table["Analista"].tolist())
        self.assertNotIn("N5923221", table["Analista"].tolist())

    def test_sector_tables_show_analysts_and_percentages_per_segment(self):
        ranking = pd.DataFrame(
            {
                "#": [1, 2, 3],
                "Analista": ["MARISTELLA", "RAISSA", "FERNANDA"],
                "Setor": ["PREVENTIVA", "RESIDENCIAL", "EMPRESARIAL"],
                "Vol. TMA": [201, 153, 141],
                "Aderentes": [124, 75, 82],
                "TMA %": [61.7, 49.0, 58.2],
                "TMA Médio (min)": [21.52, 55.58, 12.88],
            }
        )

        tables = build_tma_sector_tables(ranking)

        self.assertEqual(
            ["MARISTELLA"],
            tables["PREVENTIVA"]["Analista"].tolist(),
        )
        self.assertAlmostEqual(
            61.7,
            float(tables["PREVENTIVA"].iloc[0]["TMA %"]),
            places=1,
        )
        self.assertEqual(
            ["RAISSA"],
            tables["RESIDENCIAL"]["Analista"].tolist(),
        )
        self.assertEqual(
            ["FERNANDA"],
            tables["EMPRESARIAL"]["Analista"].tolist(),
        )

    def test_sector_summary_is_weighted_by_chat_volume(self):
        table = pd.DataFrame(
            {
                "Vol. TMA": [100, 50],
                "Aderentes": [80, 25],
                "TMA Médio (min)": [8.0, 20.0],
            }
        )

        summary = sector_tma_summary(table)

        self.assertEqual(150, summary["volume"])
        self.assertEqual(105, summary["adherents"])
        self.assertEqual(70.0, summary["adherence"])
        self.assertEqual(12.0, summary["tma_minutes"])

    def test_period_is_displayed_as_yyyymm(self):
        self.assertEqual("202609", compact_period("2026-09"))
        self.assertEqual("202609", compact_period("2026-09-30"))


if __name__ == "__main__":
    unittest.main()
