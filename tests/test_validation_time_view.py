import unittest

import pandas as pd

from src.ui.admin.indicators.validation_time import (
    build_group_table,
    build_ranking_table,
    build_sector_summary,
    build_sector_tables,
    overall_summary,
    ranking_extremes,
)


class ValidationTimeAdminViewTest(unittest.TestCase):
    def test_overall_summary_uses_validation_breakdown(self):
        rows = pd.DataFrame(
            {
                "indicator_key": ["validacao_20m"],
                "volume": [1767],
                "value": [79.7],
            }
        )
        metrics = pd.DataFrame()
        details = pd.DataFrame(
            {
                "dimension": ["overall"],
                "dimension_value": ["Total"],
                "volume": [1767],
                "successes": [1408],
                "losses": [359],
                "tmr_seconds": [972],
            }
        )

        result = overall_summary(rows, metrics, details)

        self.assertEqual(1767, result["total"])
        self.assertEqual(1408, result["adherents"])
        self.assertEqual(359, result["non_adherents"])
        self.assertAlmostEqual(79.68, result["adherence"], places=2)
        self.assertEqual(16.2, result["tmr_minutes"])

    def test_ranking_orders_by_adherence(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "display_name": ["THIAGO SILVA", "MONICA RODRIGUES", "KELLY LIRA"],
                "segment_name": ["Residencial", "Empresarial", "Residencial"],
                "volume": [125, 92, 64],
                "value": [100.0, 98.9, 42.2],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "volume": [125, 92, 64],
                "successes": [125, 91, 27],
                "losses": [0, 1, 37],
                "tmr_seconds": [264, 204, 2190],
            }
        )

        table = build_ranking_table(people, metrics)

        self.assertEqual("THIAGO SILVA", table.iloc[0]["Analista"])
        self.assertEqual("KELLY LIRA", table.iloc[-1]["Analista"])
        self.assertEqual(4.4, table.iloc[0]["TMR Médio (min)"])
        self.assertAlmostEqual(42.2, float(table.iloc[-1]["Aderência %"]), places=1)

    def test_ranking_extremes_use_full_ranking(self):
        ranking = pd.DataFrame(
            {
                "Analista": ["A", "B", "C"],
                "Total": [10, 20, 30],
                "Aderência %": [90.0, 100.0, 40.0],
                "TMR Médio (min)": [5.0, 4.0, 30.0],
            }
        )

        best, worst = ranking_extremes(ranking)

        self.assertEqual("B", best["Analista"])
        self.assertEqual("C", worst["Analista"])

    def test_sector_summary_calculates_adherence_and_tmr(self):
        rows = pd.DataFrame(
            {
                "segment_name": ["Empresarial", "Residencial"],
                "volume": [1000, 767],
                "value": [86.2, 73.0],
            }
        )
        metrics = pd.DataFrame(
            {
                "segment_name": ["Empresarial", "Empresarial", "Residencial"],
                "login": ["A", "B", "C"],
                "volume": [600, 400, 767],
                "successes": [540, 322, 560],
                "losses": [60, 78, 207],
                "tmr_seconds": [600, 1050, 1140],
            }
        )

        table = build_sector_summary(rows, metrics)
        business = table[table["Setor"] == "Empresarial"].iloc[0]
        residential = table[table["Setor"] == "Residencial"].iloc[0]

        self.assertAlmostEqual(86.2, float(business["Aderência Média"]), places=1)
        self.assertAlmostEqual(13.0, float(business["TMR Médio (min)"]), places=1)
        self.assertAlmostEqual(73.0, float(residential["Aderência Média"]), places=1)
        self.assertEqual(19.0, float(residential["TMR Médio (min)"]))

    def test_sector_tables_keep_only_sector_analysts(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B"],
                "display_name": ["MONICA", "THIAGO"],
                "segment_name": ["Empresarial", "Residencial"],
                "volume": [92, 125],
                "value": [98.9, 100.0],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B"],
                "volume": [92, 125],
                "successes": [91, 125],
                "losses": [1, 0],
                "tmr_seconds": [204, 264],
            }
        )

        tables = build_sector_tables(people, metrics)

        self.assertEqual(["MONICA"], tables["Empresarial"]["Analista"].tolist())
        self.assertEqual(["THIAGO"], tables["Residencial"]["Analista"].tolist())

    def test_group_table_includes_tmr_minutes(self):
        details = pd.DataFrame(
            {
                "dimension": ["group", "group"],
                "dimension_value": ["Rio e ES", "Norte"],
                "volume": [716, 185],
                "successes": [628, 118],
                "losses": [88, 67],
                "tmr_seconds": [582, 1422],
            }
        )

        table = build_group_table(details)
        rio = table[table["Grupo"] == "Rio e ES"].iloc[0]
        norte = table[table["Grupo"] == "Norte"].iloc[0]

        self.assertEqual(716, int(rio["Total"]))
        self.assertEqual(628, int(rio["Aderentes"]))
        self.assertAlmostEqual(87.7, float(rio["Aderência %"]), places=1)
        self.assertEqual(9.7, float(rio["TMR (min)"]))
        self.assertAlmostEqual(63.8, float(norte["Aderência %"]), places=1)


if __name__ == "__main__":
    unittest.main()
