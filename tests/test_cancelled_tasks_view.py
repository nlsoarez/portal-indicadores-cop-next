import unittest

import pandas as pd

from src.ui.admin.indicators.cancelled_tasks import (
    build_cancelled_ranking,
    build_group_cancelled_table,
    build_sector_cancelled_tables,
)


class CancelledTasksAdminViewTest(unittest.TestCase):
    def test_ranking_keeps_only_analysts_with_cancellations(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "display_name": ["KELLY LIRA", "FERNANDA FREITAS", "SEM CANCELAMENTO"],
                "segment_name": ["Residencial", "Empresarial", "Residencial"],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B", "C"],
                "volume": [100, 50, 30],
                "successes": [73, 45, 30],
                "losses": [27, 5, 0],
                "tmr_seconds": [25308, 14292, 1000],
            }
        )

        table = build_cancelled_ranking(people, metrics)

        self.assertEqual(["KELLY LIRA", "FERNANDA FREITAS"], table["Analista"].tolist())
        self.assertEqual([27, 5], table["Canceladas"].tolist())
        self.assertAlmostEqual(7.03, float(table.iloc[0]["TMR Médio (h)"]), places=2)
        self.assertAlmostEqual(3.97, float(table.iloc[1]["TMR Médio (h)"]), places=2)

    def test_group_table_sums_cancelled_tasks(self):
        details = pd.DataFrame(
            {
                "dimension": ["group", "group", "group", "group"],
                "dimension_value": ["Minas Gerais", "Minas Gerais", "Rio e ES", "Bahia/Sergipe"],
                "volume": [20, 10, 30, 5],
                "successes": [15, 4, 20, 4],
                "losses": [5, 6, 10, 1],
            }
        )

        table = build_group_cancelled_table(details)

        self.assertEqual(
            ["Minas Gerais", "Rio e ES", "Bahia/Sergipe"],
            table["Grupo"].tolist(),
        )
        self.assertEqual([11, 10, 1], table["Canceladas"].tolist())

    def test_sector_tables_re_rank_each_sector(self):
        ranking = pd.DataFrame(
            {
                "#": [1, 2, 3, 4],
                "Analista": ["KELLY", "FERNANDA", "BRUNO", "SANDRO"],
                "Setor": ["RESIDENCIAL", "EMPRESARIAL", "EMPRESARIAL", "EMPRESARIAL"],
                "Canceladas": [27, 5, 4, 2],
                "TMR Médio (h)": [7.03, 3.97, 18.14, 8.49],
            }
        )

        tables = build_sector_cancelled_tables(ranking)

        self.assertEqual(["KELLY"], tables["RESIDENCIAL"]["Analista"].tolist())
        self.assertEqual(
            ["FERNANDA", "BRUNO", "SANDRO"],
            tables["EMPRESARIAL"]["Analista"].tolist(),
        )
        self.assertEqual([1, 2, 3], tables["EMPRESARIAL"]["#"].tolist())


if __name__ == "__main__":
    unittest.main()
