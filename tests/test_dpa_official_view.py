import unittest

import pandas as pd

from src.ui.admin.indicators.dpa_official import (
    GREEN_THRESHOLD,
    YELLOW_THRESHOLD,
    build_dpa_ranking,
    build_dpa_summary,
    build_sector_summaries,
    build_sector_tables,
    format_month_label,
    status_bucket,
)


class DpaOfficialAdminViewTest(unittest.TestCase):
    def test_summary_uses_weighted_team_dpa_and_status_counts(self):
        rows = pd.DataFrame(
            {
                "value": [92.0, 88.0],
                "volume": [1000, 500],
            }
        )
        people = pd.DataFrame(
            {
                "login": ["A", "B", "C", "D"],
                "display_name": ["A", "B", "C", "D"],
                "segment_name": ["Residencial", "Empresarial", "Residencial", "Empresarial"],
                "value": [101.0, 90.0, 87.0, 84.0],
                "period": ["2026-09"] * 4,
            }
        )

        result = build_dpa_summary(rows, people)

        self.assertAlmostEqual(90.6666667, result["team_dpa"], places=5)
        self.assertEqual(4, result["monitored"])
        self.assertEqual(2, result["green"])
        self.assertEqual(1, result["red"])

    def test_ranking_sorts_dpa_descending_and_applies_status(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "display_name": ["RAISSA", "RODRIGO", "KELLY"],
                "segment_name": ["Residencial", "Empresarial", "Residencial"],
                "value": [123.1, 87.2, 61.8],
                "period": ["2026-09"] * 3,
            }
        )

        table = build_dpa_ranking(people)

        self.assertEqual(["RAISSA", "RODRIGO", "KELLY"], table["Analista"].tolist())
        self.assertEqual(["🟢", "🟡", "🔴"], table["Status"].tolist())
        self.assertEqual([123.1, 87.2, 61.8], table["DPA %"].tolist())

    def test_sector_summary_uses_simple_average_of_analysts(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B", "C", "D"],
                "display_name": ["A", "B", "C", "D"],
                "segment_name": ["Empresarial", "Empresarial", "Residencial", "Residencial"],
                "value": [102.2, 80.8, 123.1, 53.9],
                "period": ["2026-09"] * 4,
            }
        )

        table = build_sector_summaries(people)
        business = table[table["Setor"] == "Empresarial"].iloc[0]
        residential = table[table["Setor"] == "Residencial"].iloc[0]

        self.assertEqual(91.5, float(business["Média DPA %"]))
        self.assertEqual(88.5, float(residential["Média DPA %"]))

    def test_sector_tables_re_rank_inside_each_sector(self):
        ranking = pd.DataFrame(
            {
                "#": [1, 2, 3, 4],
                "Status": ["🟢", "🟢", "🟡", "🔴"],
                "Analista": ["RAISSA", "FERNANDA", "RODRIGO", "KELLY"],
                "Setor": ["RESIDENCIAL", "EMPRESARIAL", "EMPRESARIAL", "RESIDENCIAL"],
                "DPA %": [123.1, 102.2, 87.2, 61.8],
            }
        )

        tables = build_sector_tables(ranking)

        self.assertEqual(["FERNANDA", "RODRIGO"], tables["EMPRESARIAL"]["Analista"].tolist())
        self.assertEqual([1, 2], tables["EMPRESARIAL"]["#"].tolist())
        self.assertEqual(["RAISSA", "KELLY"], tables["RESIDENCIAL"]["Analista"].tolist())

    def test_status_boundaries_match_reference(self):
        self.assertEqual("green", status_bucket(GREEN_THRESHOLD))
        self.assertEqual("yellow", status_bucket(YELLOW_THRESHOLD))
        self.assertEqual("yellow", status_bucket(89.9))
        self.assertEqual("red", status_bucket(84.9))

    def test_month_label_is_pt_br(self):
        self.assertEqual("Setembro 2026", format_month_label("2026-09"))
        self.assertEqual("Setembro 2026", format_month_label("2026-09-30"))


if __name__ == "__main__":
    unittest.main()
