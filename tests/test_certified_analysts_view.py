import unittest

import pandas as pd

from src.ui.admin.certified_analysts import (
    build_certification_table,
    certification_summary,
    mean_available,
    sort_certification_table,
)


class CertifiedAnalystsViewTest(unittest.TestCase):
    def test_residential_rules_match_legacy_dashboard(self):
        roster = pd.DataFrame(
            [
                {
                    "login": "A",
                    "Analista": "ALAN",
                    "Matrícula": "A",
                    "Segmento": "Residencial",
                    "Equipe": "Nelson (Res.)",
                },
                {
                    "login": "B",
                    "Analista": "CRISTIANE",
                    "Matrícula": "B",
                    "Segmento": "Residencial",
                    "Equipe": "Nelson (Res.)",
                },
                {
                    "login": "C",
                    "Analista": "RAISSA",
                    "Matrícula": "C",
                    "Segmento": "Residencial",
                    "Equipe": "Nelson (Res.)",
                },
            ]
        )
        analyst_summary = pd.DataFrame(
            [
                {"login": "A", "segment_slug": "residencial", "indicator_key": "res_etit_fibra_hfc", "value": 100.0},
                {"login": "A", "segment_slug": "residencial", "indicator_key": "dpa_official", "value": 90.0},
                {"login": "A", "segment_slug": "residencial", "indicator_key": "res_assert_fibra_hfc", "value": 100.0},
                {"login": "A", "segment_slug": "residencial", "indicator_key": "res_assert_gpon", "value": 100.0},
                {"login": "B", "segment_slug": "residencial", "indicator_key": "res_etit_fibra_hfc", "value": 100.0},
                {"login": "B", "segment_slug": "residencial", "indicator_key": "dpa_official", "value": 87.0},
                {"login": "B", "segment_slug": "residencial", "indicator_key": "res_assert_fibra_hfc", "value": 90.0},
                {"login": "B", "segment_slug": "residencial", "indicator_key": "res_assert_gpon", "value": 90.0},
                {"login": "C", "segment_slug": "residencial", "indicator_key": "res_etit_fibra_hfc", "value": 85.7},
                {"login": "C", "segment_slug": "residencial", "indicator_key": "dpa_official", "value": 123.1},
                {"login": "C", "segment_slug": "residencial", "indicator_key": "res_assert_fibra_hfc", "value": 55.6},
                {"login": "C", "segment_slug": "residencial", "indicator_key": "res_assert_gpon", "value": 80.6},
            ]
        )

        result = build_certification_table(roster, analyst_summary)

        by_name = result.set_index("Analista")
        self.assertEqual("Certificando", by_name.loc["ALAN", "Situação"])
        self.assertEqual("🟢", by_name.loc["ALAN", "Status"])

        self.assertEqual(
            "Certificando (DPA fora da meta)",
            by_name.loc["CRISTIANE", "Situação"],
        )
        self.assertEqual("🟡", by_name.loc["CRISTIANE", "Status"])

        self.assertEqual("NÃO Certificando", by_name.loc["RAISSA", "Situação"])
        self.assertEqual("🔴", by_name.loc["RAISSA", "Status"])
        self.assertIn("ETIT HFC 85.7%", by_name.loc["RAISSA", "Observação"])
        self.assertIn("Média Assert. 68.1%", by_name.loc["RAISSA", "Observação"])

    def test_enterprise_rules_match_legacy_dashboard(self):
        roster = pd.DataFrame(
            [
                {
                    "login": "A",
                    "Analista": "FERNANDA",
                    "Matrícula": "A",
                    "Segmento": "Empresarial",
                    "Equipe": "Nelson (Emp.)",
                },
                {
                    "login": "B",
                    "Analista": "RODRIGO",
                    "Matrícula": "B",
                    "Segmento": "Empresarial",
                    "Equipe": "Nelson (Emp.)",
                },
            ]
        )
        analyst_summary = pd.DataFrame(
            [
                {"login": "A", "segment_slug": "empresarial", "indicator_key": "emp_etit_event", "value": 92.0},
                {"login": "A", "segment_slug": "empresarial", "indicator_key": "dpa_official", "value": 102.2},
                {"login": "B", "segment_slug": "empresarial", "indicator_key": "emp_etit_event", "value": 84.7},
                {"login": "B", "segment_slug": "empresarial", "indicator_key": "dpa_official", "value": 87.2},
            ]
        )

        result = build_certification_table(roster, analyst_summary).set_index("Analista")

        self.assertEqual("Certificando", result.loc["FERNANDA", "Situação"])
        self.assertEqual("NÃO Certificando", result.loc["RODRIGO", "Situação"])
        self.assertEqual("ETIT Evento 84.7%", result.loc["RODRIGO", "Observação"])

    def test_missing_data_is_considered_within_target_and_noted(self):
        roster = pd.DataFrame(
            [
                {
                    "login": "A",
                    "Analista": "ALDENES",
                    "Matrícula": "A",
                    "Segmento": "Empresarial",
                    "Equipe": "Nelson (Emp.)",
                }
            ]
        )

        result = build_certification_table(roster, pd.DataFrame()).iloc[0]

        self.assertEqual("🟢", result["Status"])
        self.assertEqual("Certificando", result["Situação"])
        self.assertIn("sem dados de ETIT por Evento, DPA", result["Observação"])

    def test_dpa_below_85_is_red_even_if_other_indicators_pass(self):
        roster = pd.DataFrame(
            [
                {
                    "login": "A",
                    "Analista": "GABRIELA",
                    "Matrícula": "A",
                    "Segmento": "Empresarial",
                    "Equipe": "Nelson (Emp.)",
                }
            ]
        )
        analyst_summary = pd.DataFrame(
            [
                {"login": "A", "segment_slug": "empresarial", "indicator_key": "emp_etit_event", "value": 92.0},
                {"login": "A", "segment_slug": "empresarial", "indicator_key": "dpa_official", "value": 84.9},
            ]
        )

        result = build_certification_table(roster, analyst_summary).iloc[0]

        self.assertEqual("🔴", result["Status"])
        self.assertIn("DPA 84.9%", result["Observação"])

    def test_summary_counts_yellow_as_certified(self):
        table = pd.DataFrame(
            {
                "Status": ["🟢", "🟡", "🔴", "🟢"],
            }
        )

        summary = certification_summary(table)

        self.assertEqual(4, summary.total)
        self.assertEqual(2, summary.green)
        self.assertEqual(1, summary.yellow)
        self.assertEqual(1, summary.red)
        self.assertEqual(3, summary.certified)
        self.assertEqual(75.0, summary.certified_pct)

    def test_sort_places_non_certified_first(self):
        table = pd.DataFrame(
            {
                "Analista": ["VERDE", "AMARELO", "VERMELHO"],
                "Segmento": ["Empresarial"] * 3,
                "Situação": [
                    "Certificando",
                    "Certificando (DPA fora da meta)",
                    "NÃO Certificando",
                ],
            }
        )

        result = sort_certification_table(table)

        self.assertEqual(
            ["VERMELHO", "AMARELO", "VERDE"],
            result["Analista"].tolist(),
        )

    def test_mean_assertiveness_uses_available_indicators(self):
        self.assertEqual(90.0, mean_available(80.0, 100.0))
        self.assertEqual(80.0, mean_available(80.0, None))
        self.assertEqual(100.0, mean_available(None, 100.0))
        self.assertIsNone(mean_available(None, None))


if __name__ == "__main__":
    unittest.main()
