import unittest

import pandas as pd

from src.ui.admin.indicators.chat_toa import (
    build_tma_ranking,
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

    def test_period_is_displayed_as_yyyymm(self):
        self.assertEqual("202609", compact_period("2026-09"))
        self.assertEqual("202609", compact_period("2026-09-30"))


if __name__ == "__main__":
    unittest.main()
