import unittest

import pandas as pd

from src.ui.admin.indicators.residential_overview import (
    build_outside_analyst_table,
    build_outside_indicator_table,
    build_turn_table,
    build_window_summary,
    indicator_summary,
)


class ResidentialOverviewTest(unittest.TestCase):
    def test_residential_overview_shows_own_team_first(self):
        from contextlib import nullcontext
        from unittest.mock import Mock, patch

        from src.ui.admin.indicators.residential_overview import (
            render_admin_residential_overview,
        )
        segment = pd.DataFrame([{
            "indicator_key": "res_etit_gpon",
            "segment_slug": "residencial",
            "segment_id": 1,
            "value": 90.0,
            "volume": 10,
        }])
        prefix = "src.ui.admin.indicators.residential_overview"
        with (
            patch(f"{prefix}._render_external_residential_night") as external,
            patch(f"{prefix}._inject_styles"),
            patch(f"{prefix}._render_summary_card"),
            patch(f"{prefix}._render_window_card"),
            patch(f"{prefix}.st.markdown"),
            patch(f"{prefix}.st.caption"),
            patch(f"{prefix}.st.columns", side_effect=lambda amount: [
                nullcontext() for _ in range(amount)
            ]),
            patch(f"{prefix}.st.expander", return_value=nullcontext()) as team,
        ):
            render_admin_residential_overview(
                indicator_keys=("res_etit_gpon",),
                ctx=Mock(),
                dashboard=Mock(),
                segment_df=segment,
                analyst_df=pd.DataFrame(),
                analyst_breakdowns_df=pd.DataFrame(),
                breakdown_df=pd.DataFrame(),
            )
        external.assert_not_called()
        team.assert_called_once()
        self.assertTrue(team.call_args.kwargs.get("expanded"))
        self.assertIn("Atuação da minha equipe", team.call_args.args[0])

    def test_external_section_is_after_all_own_team_indicator_tabs(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import patch
        from src.ui.shared.management_indicators import _render_source

        team = pd.DataFrame([
            {
                "segment_id": 1, "segment_slug": "residencial",
                "indicator_key": key, "name": label,
            }
            for key, label in [
                ("res_etit_gpon", "ETIT GPON"),
                ("res_assert_gpon", "Assertividade GPON"),
            ]
        ])
        order = []
        prefix = "src.ui.shared.management_indicators"
        with (
            patch(f"{prefix}.st.markdown"),
            patch(f"{prefix}.st.divider"),
            patch(f"{prefix}.st.tabs", return_value=[
                nullcontext(), nullcontext()
            ]),
            patch(f"{prefix}.render_admin_residential_overview", create=True),
            patch(f"{prefix}._render_indicator",
                  side_effect=lambda *a, **k: order.append("meu_indicador")),
            patch(
                "src.ui.admin.indicators.residential_overview."
                "render_admin_residential_overview",
                side_effect=lambda *a, **k: order.append("minha_equipe")
            ),
            patch(
                "src.ui.admin.indicators.residential_overview."
                "_render_external_residential_night",
                side_effect=lambda *a, **k: order.append("externos")
            ),
        ):
            _render_source(
                source_label="Indicadores Residencial",
                indicator_keys=("res_etit_gpon", "res_assert_gpon"),
                ctx=SimpleNamespace(is_admin=True),
                dashboard=object(),
                segment_df=team,
                analyst_df=pd.DataFrame(),
                analyst_metrics_df=pd.DataFrame(),
                analyst_breakdowns_df=pd.DataFrame(),
                daily_df=pd.DataFrame(),
                breakdown_df=pd.DataFrame(),
                external_df=pd.DataFrame(),
                freshness_index={},
            )
        self.assertEqual([
            "minha_equipe", "meu_indicador", "meu_indicador", "externos",
        ], order)

    def test_indicator_summary_uses_overall_breakdown(self):
        segment = pd.DataFrame(
            {
                "indicator_key": ["res_etit_gpon"],
                "volume": [128],
                "value": [93.8],
            }
        )
        breakdown = pd.DataFrame(
            {
                "indicator_key": ["res_etit_gpon"],
                "dimension": ["overall"],
                "volume": [128],
                "successes": [120],
                "losses": [8],
                "tma_seconds": [36],
                "tmr_seconds": [1325],
            }
        )

        result = indicator_summary(segment, breakdown, "res_etit_gpon")

        self.assertEqual(128, result["volume"])
        self.assertEqual(120, result["successes"])
        self.assertEqual(8, result["losses"])
        self.assertEqual(93.75, result["rate"])
        self.assertEqual(6.25, result["non_rate"])
        self.assertEqual(36, result["tma_seconds"])
        self.assertEqual(1325, result["tmr_seconds"])

    def test_turn_table_consolidates_four_residential_indicators(self):
        keys = [
            "res_etit_fibra_hfc",
            "res_etit_gpon",
            "res_assert_fibra_hfc",
            "res_assert_gpon",
        ]
        rows = []
        for key, volume, successes in zip(keys, [10, 20, 30, 40], [8, 18, 24, 36]):
            rows.append(
                {
                    "indicator_key": key,
                    "dimension": "turn",
                    "dimension_value": "Madrugada",
                    "volume": volume,
                    "successes": successes,
                    "losses": volume - successes,
                }
            )
        frame = pd.DataFrame(rows)

        table = build_turn_table(frame, keys)

        self.assertEqual(["Madrugada"], table["Turno"].tolist())
        self.assertEqual(100, int(table.iloc[0]["Volume"]))
        self.assertEqual(86, int(table.iloc[0]["Positivos"]))
        self.assertEqual(86.0, float(table.iloc[0]["Aderência / Assertividade %"]))

    def test_window_summary_uses_exact_22_to_0559_rule(self):
        key = "res_etit_gpon"
        frame = pd.DataFrame(
            {
                "indicator_key": [key] * 6,
                "dimension": ["hour"] * 6,
                "dimension_value": ["21", "22", "23", "0", "5", "6"],
                "volume": [10, 10, 10, 10, 10, 10],
                "successes": [5, 10, 9, 8, 7, 6],
                "losses": [5, 0, 1, 2, 3, 4],
            }
        )

        result = build_window_summary(frame, [key])

        self.assertEqual(40, result["inside_volume"])
        self.assertEqual(20, result["outside_volume"])
        self.assertEqual(85.0, result["inside_rate"])
        self.assertAlmostEqual(55.0, result["outside_rate"], places=8)
        self.assertAlmostEqual(33.3333333333, result["outside_share"], places=5)

    def test_outside_indicator_table_reports_share_of_each_indicator(self):
        frame = pd.DataFrame(
            {
                "indicator_key": [
                    "res_etit_gpon",
                    "res_etit_gpon",
                    "res_assert_gpon",
                    "res_assert_gpon",
                ],
                "dimension": ["hour"] * 4,
                "dimension_value": ["23", "10", "23", "14"],
                "volume": [80, 20, 60, 40],
                "successes": [72, 10, 54, 20],
                "losses": [8, 10, 6, 20],
            }
        )

        table = build_outside_indicator_table(
            frame,
            ["res_etit_gpon", "res_assert_gpon"],
        )

        by_name = table.set_index("Indicador")
        self.assertEqual(20, int(by_name.loc["ETIT GPON", "Volume fora"]))
        self.assertEqual(20.0, float(by_name.loc["ETIT GPON", "% do indicador fora"]))
        self.assertEqual(40, int(by_name.loc["ASSERT. ACION. GPON", "Volume fora"]))
        self.assertEqual(40.0, float(by_name.loc["ASSERT. ACION. GPON", "% do indicador fora"]))

    def test_outside_analyst_table_identifies_who_worked_outside_window(self):
        key = "res_etit_gpon"
        breakdowns = pd.DataFrame(
            {
                "indicator_key": [key, key, key],
                "dimension": ["hour", "hour", "hour"],
                "dimension_value": ["10", "23", "14"],
                "login": ["A", "A", "B"],
                "volume": [4, 6, 5],
                "successes": [3, 6, 2],
                "losses": [1, 0, 3],
            }
        )
        people = pd.DataFrame(
            {
                "login": ["A", "B"],
                "display_name": ["ANA", "BRUNO"],
            }
        )

        table = build_outside_analyst_table(breakdowns, people, [key])

        self.assertEqual(["BRUNO", "ANA"], table["Analista"].tolist())
        self.assertEqual([5, 4], table["Volume"].tolist())
        self.assertEqual([40.0, 75.0], table["Resultado %"].tolist())


if __name__ == "__main__":
    unittest.main()
