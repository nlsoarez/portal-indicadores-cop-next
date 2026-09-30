import unittest

import pandas as pd

from src.ui.admin.dashboard_insights import (
    _short_name,
    build_analyst_insights,
)


class DashboardInsightsTest(unittest.TestCase):
    def test_insights_match_legacy_sector_comparison_logic(self):
        peers = pd.DataFrame(
            [
                {
                    "Nome": "MARISTELLA MARCIA DOS SANTOS",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 1593,
                    "Média/Dia": 83.8,
                    "DPA %": 89.7,
                    "Ab. New Monitor": 0,
                    "Fech. New Monitor": 0,
                    "Ab. SGO": 38,
                    "Fech. SGO": 131,
                    "Ab. Remedy": 1,
                    "Ligações Realiz.": 0,
                    "1ª Interação TOA": 740,
                    "Fech. Tarefa TOA": 564,
                },
                {
                    "Nome": "LEONARDO FERREIRA LIMA DE ALMEIDA",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 887,
                    "Média/Dia": 49.3,
                    "DPA %": 88.0,
                    "Ab. New Monitor": 1,
                    "Fech. New Monitor": 53,
                    "Ab. SGO": 3,
                    "Fech. SGO": 123,
                    "Ab. Remedy": 23,
                    "Ligações Realiz.": 82,
                    "1ª Interação TOA": 269,
                    "Fech. Tarefa TOA": 285,
                },
                {
                    "Nome": "RAISSA LIMA DE OLIVEIRA",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 749,
                    "Média/Dia": 49.9,
                    "DPA %": 92.4,
                    "Ab. New Monitor": 16,
                    "Fech. New Monitor": 52,
                    "Ab. SGO": 5,
                    "Fech. SGO": 146,
                    "Ab. Remedy": 13,
                    "Ligações Realiz.": 0,
                    "1ª Interação TOA": 296,
                    "Fech. Tarefa TOA": 187,
                },
                {
                    "Nome": "THIAGO PEREIRA DA SILVA",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 740,
                    "Média/Dia": 43.5,
                    "DPA %": 96.5,
                    "Ab. New Monitor": 23,
                    "Fech. New Monitor": 29,
                    "Ab. SGO": 18,
                    "Fech. SGO": 119,
                    "Ab. Remedy": 35,
                    "Ligações Realiz.": 12,
                    "1ª Interação TOA": 195,
                    "Fech. Tarefa TOA": 241,
                },
                {
                    "Nome": "ALAN MARINHO DIAS",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 626,
                    "Média/Dia": 34.8,
                    "DPA %": 79.3,
                    "Ab. New Monitor": 0,
                    "Fech. New Monitor": 13,
                    "Ab. SGO": 2,
                    "Fech. SGO": 69,
                    "Ab. Remedy": 15,
                    "Ligações Realiz.": 9,
                    "1ª Interação TOA": 228,
                    "Fech. Tarefa TOA": 251,
                },
                {
                    "Nome": "CRISTIANE HERMOGENES DA SILVA",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 538,
                    "Média/Dia": 76.9,
                    "DPA %": 83.4,
                    "Ab. New Monitor": 0,
                    "Fech. New Monitor": 8,
                    "Ab. SGO": 3,
                    "Fech. SGO": 62,
                    "Ab. Remedy": 15,
                    "Ligações Realiz.": 47,
                    "1ª Interação TOA": 189,
                    "Fech. Tarefa TOA": 163,
                },
            ]
        )

        insights = build_analyst_insights(peers)
        by_name = {item["nome"]: item for item in insights}

        maristella = by_name["MARISTELLA SANTOS"]
        self.assertEqual(1, maristella["vol_rank"])
        self.assertEqual(6, maristella["n_peers"])
        self.assertAlmostEqual(86.2, maristella["vol_diff"], places=1)
        self.assertIn("Ab. SGO", maristella["strengths"])
        self.assertIn("1ª Interação TOA", maristella["strengths"])
        self.assertIn("Fech. Tarefa TOA", maristella["strengths"])
        self.assertIn("Ab. Remedy", maristella["weaknesses"])

        cristiane = by_name["CRISTIANE SILVA"]
        self.assertEqual(6, cristiane["vol_rank"])
        self.assertLess(cristiane["vol_diff"], 0)
        self.assertIn("Fech. SGO", cristiane["weaknesses"])
        self.assertIn("1ª Interação TOA", cristiane["weaknesses"])
        self.assertIn("Fech. Tarefa TOA", cristiane["weaknesses"])

    def test_first_and_last_name_matches_legacy_dashboard(self):
        self.assertEqual(
            "FERNANDA FREITAS",
            _short_name("FERNANDA MESQUITA DE FREITAS"),
        )
        self.assertEqual("SANDRO CARVALHO", _short_name("SANDRO DA SILVA CARVALHO"))
        self.assertEqual("MONICA RODRIGUES", _short_name("MONICA RODRIGUES"))

    def test_segments_are_compared_independently(self):
        peers = pd.DataFrame(
            [
                {
                    "Nome": "A RES",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 100,
                    "Média/Dia": 10,
                    "DPA %": 90,
                    "Ab. New Monitor": 10,
                    "Fech. New Monitor": 0,
                    "Ab. SGO": 0,
                    "Fech. SGO": 0,
                    "Ab. Remedy": 0,
                    "Ligações Realiz.": 0,
                    "1ª Interação TOA": 0,
                    "Fech. Tarefa TOA": 0,
                    "Trat. RAL": 0,
                    "Trat. REC": 0,
                },
                {
                    "Nome": "B RES",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 50,
                    "Média/Dia": 5,
                    "DPA %": 90,
                    "Ab. New Monitor": 5,
                    "Fech. New Monitor": 0,
                    "Ab. SGO": 0,
                    "Fech. SGO": 0,
                    "Ab. Remedy": 0,
                    "Ligações Realiz.": 0,
                    "1ª Interação TOA": 0,
                    "Fech. Tarefa TOA": 0,
                    "Trat. RAL": 0,
                    "Trat. REC": 0,
                },
                {
                    "Nome": "A EMP",
                    "Setor": "EMPRESARIAL",
                    "Vol. Total": 1000,
                    "Média/Dia": 100,
                    "DPA %": 90,
                    "Ab. New Monitor": 0,
                    "Fech. New Monitor": 0,
                    "Ab. SGO": 0,
                    "Fech. SGO": 0,
                    "Ab. Remedy": 0,
                    "Ligações Realiz.": 0,
                    "1ª Interação TOA": 0,
                    "Fech. Tarefa TOA": 0,
                    "Trat. RAL": 10,
                    "Trat. REC": 5,
                },
                {
                    "Nome": "B EMP",
                    "Setor": "EMPRESARIAL",
                    "Vol. Total": 500,
                    "Média/Dia": 50,
                    "DPA %": 90,
                    "Ab. New Monitor": 0,
                    "Fech. New Monitor": 0,
                    "Ab. SGO": 0,
                    "Fech. SGO": 0,
                    "Ab. Remedy": 0,
                    "Ligações Realiz.": 0,
                    "1ª Interação TOA": 0,
                    "Fech. Tarefa TOA": 0,
                    "Trat. RAL": 5,
                    "Trat. REC": 1,
                },
            ]
        )

        insights = build_analyst_insights(peers)
        by_name = {item["nome"]: item for item in insights}

        self.assertAlmostEqual(33.3, by_name["A RES"]["vol_diff"], places=1)
        self.assertAlmostEqual(33.3, by_name["A EMP"]["vol_diff"], places=1)
        self.assertEqual(2, by_name["A RES"]["n_peers"])
        self.assertEqual(2, by_name["A EMP"]["n_peers"])


if __name__ == "__main__":
    unittest.main()
