import unittest

import pandas as pd

from src.ui.admin.indicators.etit_residential import (
    _indicator_labels,
    _overall_numbers,
    _presentation_table,
    analyst_table_for_etit,
    dimension_table,
)


class AdminEtitViewTest(unittest.TestCase):
    def test_dimension_table_calculates_adherence_and_sorts_by_volume(self):
        rows = pd.DataFrame(
            {
                "dimension_value": ["Rio e ES", "Minas Gerais", "Rio e ES"],
                "volume": [30, 16, 20],
                "successes": [29, 13, 20],
                "losses": [1, 3, 0],
            }
        )

        table = dimension_table(rows, "IN_GRUPO")

        self.assertEqual(["Rio e ES", "Minas Gerais"], table["IN_GRUPO"].tolist())
        self.assertEqual(50, int(table.iloc[0]["Volume"]))
        self.assertEqual(49, int(table.iloc[0]["Aderentes"]))
        self.assertEqual(98.0, round(float(table.iloc[0]["Aderência %"]), 1))
        self.assertEqual(18.8, round(float(table.iloc[1]["Não Aderência %"]), 1))

    def test_analyst_table_can_use_service_scoped_rows(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B"],
                "display_name": ["ANA", "BRUNO"],
                "segment_name": ["Residencial", "Residencial"],
                "volume": [10, 10],
                "value": [90.0, 80.0],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B"],
                "successes": [9, 8],
                "losses": [1, 2],
            }
        )
        service_rows = pd.DataFrame(
            {
                "login": ["A", "B"],
                "volume": [4, 5],
                "successes": [4, 3],
                "losses": [0, 2],
            }
        )

        table = analyst_table_for_etit(
            people,
            metrics,
            service_rows=service_rows,
        )

        self.assertEqual(["ANA", "BRUNO"], table["Analista"].tolist())
        self.assertEqual([100.0, 60.0], table["Aderência %"].tolist())
        self.assertEqual([4, 5], table["Volume"].tolist())

    def test_overall_numbers_preserve_duration_metrics(self):
        rows = pd.DataFrame({"volume": [128], "value": [93.8]})
        detail = {
            "volume": 128,
            "successes": 120,
            "losses": 8,
            "tma_seconds": 36,
            "tmr_seconds": 1325,
        }

        numbers = _overall_numbers(rows, detail)

        self.assertEqual(128, numbers["volume"])
        self.assertEqual(120, numbers["successes"])
        self.assertEqual(8, numbers["losses"])
        self.assertEqual(93.75, numbers["adherence"])
        self.assertEqual(6.25, numbers["non_adherence"])
        self.assertEqual(36, numbers["tma_seconds"])
        self.assertEqual(1325, numbers["tmr_seconds"])


    def test_assertiveness_gpon_uses_same_service_split_with_correct_labels(self):
        labels = _indicator_labels("res_assert_gpon")

        self.assertTrue(labels["is_gpon"])
        self.assertTrue(labels["is_assertiveness"])
        self.assertEqual("Assertividade GPON", labels["title"])
        self.assertEqual("Assertivos", labels["success"])
        self.assertEqual("Não Assertivos", labels["loss"])

        table = pd.DataFrame(
            {
                "Serviço": ["BROWNFIELD", "GREENFIELD"],
                "Volume": [10, 5],
                "Aderentes": [9, 3],
                "Não Aderentes": [1, 2],
                "Aderência %": [90.0, 60.0],
                "Não Aderência %": [10.0, 40.0],
            }
        )
        presented = _presentation_table(table, labels)

        self.assertIn("Assertivos", presented.columns)
        self.assertIn("Não Assertivos", presented.columns)
        self.assertIn("Assertividade %", presented.columns)
        self.assertIn("Não Assertividade %", presented.columns)
        self.assertEqual(["BROWNFIELD", "GREENFIELD"], presented["Serviço"].tolist())

    def test_assertiveness_hfc_remains_without_service_split(self):
        labels = _indicator_labels("res_assert_fibra_hfc")

        self.assertFalse(labels["is_gpon"])
        self.assertTrue(labels["is_assertiveness"])
        self.assertEqual("Assertividade HFC", labels["title"])


if __name__ == "__main__":
    unittest.main()
