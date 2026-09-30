import unittest

import pandas as pd

from src.ui.admin.indicators.productivity import (
    build_component_pivot,
    build_dpa_map,
    build_sector_detail,
    build_total_ranking,
    preferred_sector_order,
    sector_highlights,
)


class ProductivityAdminViewTest(unittest.TestCase):
    def test_total_ranking_uses_exact_breakdown_when_available(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B"],
                "display_name": ["MARISTELLA SANTOS", "SANDRO CARVALHO"],
                "segment_name": ["Residencial", "Empresarial"],
                "value": [83.8, 63.8],
                "volume": [19, 17],
            }
        )
        breakdowns = pd.DataFrame(
            {
                "login": ["A", "B"],
                "segment_name": ["Residencial", "Empresarial"],
                "dimension": ["productivity_total", "productivity_total"],
                "dimension_value": ["Volume Total", "Volume Total"],
                "successes": [1593, 1085],
            }
        )

        table = build_total_ranking(people, breakdowns)

        self.assertEqual(["MARISTELLA SANTOS", "SANDRO CARVALHO"], table["Analista"].tolist())
        self.assertEqual([1593, 1085], table["Vol. Total"].tolist())
        self.assertEqual([19, 17], table["Dias"].tolist())

    def test_total_ranking_falls_back_to_average_times_days(self):
        people = pd.DataFrame(
            {
                "login": ["A"],
                "display_name": ["ANALISTA"],
                "segment_name": ["Residencial"],
                "value": [50.0],
                "volume": [10],
            }
        )

        table = build_total_ranking(people, pd.DataFrame())

        self.assertEqual(500, int(table.iloc[0]["Vol. Total"]))

    def test_component_pivot_sums_components_by_analyst(self):
        breakdowns = pd.DataFrame(
            {
                "login": ["A", "A", "A"],
                "segment_name": ["Residencial"] * 3,
                "dimension": ["productivity_component"] * 3,
                "dimension_value": [
                    "Abertura SGO",
                    "Abertura SGO",
                    "Fechamento SGO",
                ],
                "successes": [20, 18, 131],
            }
        )

        pivot = build_component_pivot(breakdowns)

        self.assertEqual(38, int(pivot.iloc[0]["Abertura SGO"]))
        self.assertEqual(131, int(pivot.iloc[0]["Fechamento SGO"]))

    def test_dpa_map_uses_latest_value(self):
        dpa = pd.DataFrame(
            {
                "login": ["A", "A"],
                "segment_name": ["Residencial", "Residencial"],
                "period": ["2026-08", "2026-09"],
                "value": [90.0, 96.5],
            }
        )

        mapping = build_dpa_map(dpa)

        self.assertEqual(96.5, mapping[("A", "RESIDENCIAL")])

    def test_sector_detail_includes_components_dpa_and_vs_average(self):
        ranking = pd.DataFrame(
            {
                "#": [1, 2],
                "Analista": ["MARISTELLA", "THIAGO"],
                "Setor": ["RESIDENCIAL", "RESIDENCIAL"],
                "Vol. Total": [1593, 740],
                "Dias": [19, 17],
                "Média/Dia": [83.8, 43.5],
                "login": ["A", "B"],
            }
        )
        pivot = pd.DataFrame(
            {
                "login": ["A", "B"],
                "segment_name": ["Residencial", "Residencial"],
                "Abertura SGO": [38, 18],
                "Fechamento SGO": [131, 119],
                "Primeira Interação TOA": [740, 195],
                "Fechamento Tarefa TOA": [564, 241],
            }
        )
        dpa_map = {
            ("A", "RESIDENCIAL"): 89.7,
            ("B", "RESIDENCIAL"): 96.5,
        }

        table = build_sector_detail(
            ranking,
            sector="RESIDENCIAL",
            component_pivot=pivot,
            dpa_map=dpa_map,
        )

        self.assertEqual(38, int(table.iloc[0]["Ab. SGO"]))
        self.assertEqual(131, int(table.iloc[0]["Fech. SGO"]))
        self.assertEqual(740, int(table.iloc[0]["1ª Interação TOA"]))
        self.assertEqual(89.7, float(table.iloc[0]["DPA %"]))
        self.assertGreater(float(table.iloc[0]["vs Média"]), 0)
        self.assertLess(float(table.iloc[1]["vs Média"]), 0)

    def test_sector_highlights_identify_volume_extremes_and_best_dpa(self):
        table = pd.DataFrame(
            {
                "Analista": ["A", "B", "C"],
                "Vol. Total": [1000, 500, 700],
                "Média/Dia": [60.0, 40.0, 50.0],
                "DPA %": [90.0, 95.0, 100.0],
            }
        )

        result = sector_highlights(table)

        self.assertEqual("A", result["highest"]["Analista"])
        self.assertEqual("B", result["lowest"]["Analista"])
        self.assertEqual("C", result["best_dpa"]["Analista"])

    def test_sector_order_matches_reference(self):
        result = preferred_sector_order(["EMPRESARIAL", "PREVENTIVA", "RESIDENCIAL"])

        self.assertEqual(["RESIDENCIAL", "EMPRESARIAL", "PREVENTIVA"], result)


if __name__ == "__main__":
    unittest.main()
