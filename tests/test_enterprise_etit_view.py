import unittest

import pandas as pd

from src.ui.admin.indicators.etit_enterprise import (
    build_demand_analyst_table,
    build_dimension_table,
    build_ranking_table,
    demand_team_averages,
    overall_summary,
    sort_turn_table,
)


class EnterpriseEtitAdminViewTest(unittest.TestCase):
    def test_overall_summary_uses_events_adherents_and_durations(self):
        rows = pd.DataFrame(
            {
                "indicator_key": ["emp_etit_event"],
                "volume": [702],
                "value": [92.0],
                "analysts": [11],
            }
        )
        metrics = pd.DataFrame()
        details = pd.DataFrame(
            {
                "dimension": ["overall"],
                "dimension_value": ["Total"],
                "volume": [702],
                "successes": [646],
                "losses": [56],
                "tma_seconds": [95],
                "tmr_seconds": [2273],
            }
        )

        summary = overall_summary(rows, metrics, details)

        self.assertEqual(702, summary["events"])
        self.assertEqual(646, summary["adherents"])
        self.assertEqual(11, summary["analysts"])
        self.assertAlmostEqual(92.02, summary["adherence"], places=2)
        self.assertEqual(95, summary["tma_seconds"])
        self.assertEqual(2273, summary["tmr_seconds"])

    def test_ranking_uses_demand_volume_for_ral_and_rec(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B"],
                "display_name": ["SANDRO", "FERNANDA"],
                "segment_name": ["Empresarial", "Empresarial"],
                "volume": [137, 100],
                "value": [90.5, 92.0],
            }
        )
        metrics = pd.DataFrame(
            {
                "login": ["A", "B"],
                "volume": [137, 100],
                "successes": [124, 92],
                "losses": [13, 8],
                "tma_seconds": [150, 63],
                "tmr_seconds": [1300, 1236],
            }
        )
        demand = pd.DataFrame(
            {
                "login": ["A", "A", "B", "B"],
                "dimension": ["demand"] * 4,
                "dimension_value": ["RAL", "REC", "RAL", "REC"],
                "volume": [107, 30, 84, 16],
                "successes": [95, 29, 77, 15],
                "losses": [12, 1, 7, 1],
            }
        )

        table = build_ranking_table(people, metrics, demand)

        self.assertEqual("SANDRO", table.iloc[0]["Nome"])
        sandro = table[table["Nome"] == "SANDRO"].iloc[0]
        self.assertEqual(137, int(sandro["Eventos"]))
        self.assertEqual(124, int(sandro["Aderentes"]))
        self.assertEqual(107, int(sandro["RAL"]))
        self.assertEqual(30, int(sandro["REC"]))
        self.assertEqual("00:02:30", sandro["TMA"])

    def test_team_averages_zero_fill_missing_demand(self):
        people = pd.DataFrame(
            {
                "login": ["A", "B"],
                "display_name": ["A", "B"],
            }
        )
        demand = pd.DataFrame(
            {
                "login": ["A", "A", "B"],
                "dimension": ["demand"] * 3,
                "dimension_value": ["RAL", "REC", "RAL"],
                "volume": [10, 5, 10],
                "successes": [8, 4, 6],
                "losses": [2, 1, 4],
            }
        )

        values = demand_team_averages(people, demand)

        self.assertEqual(7.0, values["ral_adherents"])
        self.assertEqual(2.0, values["rec_adherents"])
        self.assertEqual(3.0, values["ral_non_adherents"])
        self.assertEqual(0.5, values["rec_non_adherents"])

    def test_demand_analyst_table_calculates_category_percentages(self):
        people = pd.DataFrame(
            {
                "login": ["A"],
                "display_name": ["SANDRO"],
            }
        )
        demand = pd.DataFrame(
            {
                "login": ["A", "A"],
                "dimension": ["demand", "demand"],
                "dimension_value": ["RAL", "REC"],
                "volume": [107, 30],
                "successes": [95, 29],
                "losses": [12, 1],
            }
        )

        table = build_demand_analyst_table(people, demand)
        row = table.iloc[0]

        self.assertEqual(95, int(row["RAL Ader."]))
        self.assertEqual(29, int(row["REC Ader."]))
        self.assertAlmostEqual(88.8, float(row["% RAL Ader."]), places=1)
        self.assertAlmostEqual(96.7, float(row["% REC Ader."]), places=1)

    def test_dimension_table_includes_duration_for_demand(self):
        details = pd.DataFrame(
            {
                "dimension": ["demand", "demand"],
                "dimension_value": ["RAL", "REC"],
                "volume": [584, 118],
                "successes": [533, 113],
                "losses": [51, 5],
                "tma_seconds": [104, 53],
                "tmr_seconds": [2114, 3056],
            }
        )

        table = build_dimension_table(
            details,
            "demand",
            "Demanda",
            durations=True,
        )

        ral = table[table["Demanda"] == "RAL"].iloc[0]
        self.assertEqual(584, int(ral["Eventos"]))
        self.assertEqual(533, int(ral["Aderentes"]))
        self.assertEqual("00:01:44", ral["TMA"])
        self.assertEqual("00:35:14", ral["TMR"])
        self.assertAlmostEqual(91.3, float(ral["Aderência %"]), places=1)

    def test_ral_rec_team_average_cards_use_legible_dark_theme_colors(self):
        from unittest.mock import patch

        from src.ui.admin.indicators.etit_enterprise import _inject_styles

        with patch("src.ui.admin.indicators.etit_enterprise.st.markdown") as markdown:
            _inject_styles()

        css = markdown.call_args.args[0]
        self.assertIn("background: linear-gradient(145deg, #10243b", css)
        self.assertIn(".cop-emp-average .cop-emp-average-label", css)
        self.assertIn("color: #aec4d9 !important", css)
        self.assertIn(".cop-emp-average .cop-emp-average-value", css)
        self.assertIn("color: #f4f8fe !important", css)
        self.assertNotIn(
            ".cop-emp-average-label {\n            color: #30343b", css
        )
        self.assertNotIn(
            ".cop-emp-average-value {\n            color: #1f2937", css
        )

    def test_ral_rec_average_card_values_remain_unchanged(self):
        from contextlib import nullcontext
        from unittest.mock import patch

        from src.ui.admin.indicators.etit_enterprise import _render_average_cards

        averages = {
            "ral_adherents": 13.4,
            "rec_adherents": 2.1,
            "ral_non_adherents": 1.3,
            "rec_non_adherents": 0.1,
        }
        with (
            patch(
                "src.ui.admin.indicators.etit_enterprise.st.columns",
                return_value=[nullcontext() for _ in range(4)],
            ),
            patch("src.ui.admin.indicators.etit_enterprise.st.markdown") as markdown,
        ):
            _render_average_cards(averages)
        cards = [call.args[0] for call in markdown.call_args_list]
        self.assertEqual(4, len(cards))
        self.assertIn("13.4", cards[0])
        self.assertIn("2.1", cards[1])
        self.assertIn("1.3", cards[2])
        self.assertIn("0.1", cards[3])
        self.assertTrue(all("cop-emp-average-value" in card for card in cards))

    def test_turn_sort_prioritizes_madrugada_then_manha(self):
        table = pd.DataFrame(
            {
                "Turno": ["MANHÃ", "MADRUGADA"],
                "Eventos": [24, 678],
                "Aderentes": [24, 622],
                "Aderência %": [100.0, 91.7],
            }
        )

        sorted_table = sort_turn_table(table)

        self.assertEqual(["MADRUGADA", "MANHÃ"], sorted_table["Turno"].tolist())


if __name__ == "__main__":
    unittest.main()
