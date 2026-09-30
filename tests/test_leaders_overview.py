import unittest
from types import SimpleNamespace

import pandas as pd

from src.ui.admin.leaders_overview import (
    build_leader_insights,
    build_leader_performance,
    build_peer_performance,
    combine_leaders_and_peers,
    enrich_leader_comparison,
    leader_detail_table,
    percent_vs,
)


class LeadersOverviewTest(unittest.TestCase):
    def test_build_leader_performance_uses_exact_total_components_and_latest_dpa(self):
        leader = SimpleNamespace(
            login="N1",
            display_name="Kelly",
            full_name="Kelly Lira da Silva",
        )
        segment = SimpleNamespace(name="Residencial")
        payload = {
            "summary": [
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09",
                    "value": 11.6,
                    "volume": 18,
                },
                {
                    "indicator_key": "dpa_official",
                    "period": "2026-08",
                    "value": 70.0,
                    "volume": 1,
                },
                {
                    "indicator_key": "dpa_official",
                    "period": "2026-09",
                    "value": 61.8,
                    "volume": 1,
                },
            ],
            "breakdowns": [
                {
                    "indicator_key": "productivity_avg_daily",
                    "dimension": "productivity_total",
                    "dimension_value": "Volume Total",
                    "successes": 208,
                },
                {
                    "indicator_key": "productivity_avg_daily",
                    "dimension": "productivity_component",
                    "dimension_value": "Tratativa REC",
                    "successes": 49,
                },
                {
                    "indicator_key": "productivity_avg_daily",
                    "dimension": "productivity_component",
                    "dimension_value": "Primeira Interação TOA",
                    "successes": 69,
                },
            ],
        }

        result = build_leader_performance(leader, segment, payload)

        self.assertEqual("KELLY LIRA", result["Líder"])
        self.assertEqual("RESIDENCIAL", result["Setor"])
        self.assertEqual(208, result["Vol. Total"])
        self.assertEqual(18, result["Dias"])
        self.assertEqual(11.6, result["Média/Dia"])
        self.assertEqual(61.8, result["DPA %"])
        self.assertEqual(49, result["Trat. REC"])
        self.assertEqual(69, result["1ª Interação TOA"])

    def test_peer_performance_uses_exact_total_and_dpa(self):
        analyst_summary = pd.DataFrame(
            [
                {
                    "indicator_key": "productivity_avg_daily",
                    "login": "A",
                    "display_name": "ANALISTA A",
                    "segment_name": "Residencial",
                    "value": 50.0,
                    "volume": 10,
                },
                {
                    "indicator_key": "dpa_official",
                    "login": "A",
                    "display_name": "ANALISTA A",
                    "segment_name": "Residencial",
                    "value": 96.5,
                    "volume": 1,
                },
            ]
        )
        breakdowns = pd.DataFrame(
            [
                {
                    "indicator_key": "productivity_avg_daily",
                    "login": "A",
                    "segment_name": "Residencial",
                    "dimension": "productivity_total",
                    "dimension_value": "Volume Total",
                    "successes": 510,
                },
                {
                    "indicator_key": "productivity_avg_daily",
                    "login": "A",
                    "segment_name": "Residencial",
                    "dimension": "productivity_component",
                    "dimension_value": "Fechamento SGO",
                    "successes": 119,
                },
            ]
        )

        result = build_peer_performance(analyst_summary, breakdowns)

        self.assertEqual(510, int(result.iloc[0]["Vol. Total"]))
        self.assertEqual(96.5, float(result.iloc[0]["DPA %"]))
        self.assertEqual(119, int(result.iloc[0]["Fech. SGO"]))

    def test_enrich_leader_comparison_excludes_leaders_from_team_average_but_ranks_with_them(self):
        leaders = pd.DataFrame(
            [
                {
                    "login": "L1",
                    "Líder": "KELLY LIRA",
                    "Nome": "KELLY LIRA",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 200,
                    "Dias": 20,
                    "Média/Dia": 10.0,
                    "DPA %": 90.0,
                    "is_leader": True,
                },
                {
                    "login": "L2",
                    "Líder": "MARLEY RIBEIRO",
                    "Nome": "MARLEY RIBEIRO",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 100,
                    "Dias": 20,
                    "Média/Dia": 5.0,
                    "DPA %": 85.0,
                    "is_leader": True,
                },
            ]
        )
        peers = pd.DataFrame(
            [
                {
                    "login": "A",
                    "Nome": "A",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 800,
                    "Dias": 20,
                    "Média/Dia": 40.0,
                    "DPA %": 95.0,
                    "is_leader": False,
                },
                {
                    "login": "B",
                    "Nome": "B",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 600,
                    "Dias": 20,
                    "Média/Dia": 30.0,
                    "DPA %": 90.0,
                    "is_leader": False,
                },
            ]
        )
        all_people = combine_leaders_and_peers(leaders, peers)

        result = enrich_leader_comparison(leaders, peers, all_people)
        kelly = result[result["Líder"] == "KELLY LIRA"].iloc[0]
        marley = result[result["Líder"] == "MARLEY RIBEIRO"].iloc[0]

        # Equipe média = 700 de volume e 35/dia, sem líderes.
        self.assertAlmostEqual(-71.4, float(kelly["vs Equipe Vol. %"]), places=1)
        self.assertAlmostEqual(-71.4, float(kelly["vs Equipe Média %"]), places=1)

        # Rank considera os dois analistas + os dois líderes.
        self.assertEqual(3, int(kelly["Rank"]))
        self.assertEqual(4, int(kelly["Peers"]))
        self.assertEqual(4, int(marley["Rank"]))

    def test_insights_find_strength_and_attention_by_sector_rank(self):
        component_cols = {
            "Ab. New Monitor": 0,
            "Fech. New Monitor": 0,
            "Ab. SGO": 0,
            "Fech. SGO": 0,
            "Trat. RAL": 0,
            "Trat. REC": 0,
            "Ab. Remedy": 0,
            "Ligações Realiz.": 0,
            "1ª Interação TOA": 0,
            "Fech. Tarefa TOA": 0,
        }
        leaders = pd.DataFrame(
            [
                {
                    **component_cols,
                    "Líder": "MARLEY RIBEIRO",
                    "Nome": "MARLEY RIBEIRO",
                    "login": "L1",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 3,
                    "Dias": 16,
                    "Média/Dia": 0.2,
                    "DPA %": 85.3,
                    "vs Equipe Vol. %": -99.0,
                    "Rank": 3,
                    "Peers": 3,
                    "1ª Interação TOA": 3,
                    "is_leader": True,
                }
            ]
        )
        peers = pd.DataFrame(
            [
                {
                    **component_cols,
                    "Nome": "A",
                    "login": "A",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 100,
                    "Dias": 10,
                    "Média/Dia": 10.0,
                    "DPA %": 90.0,
                    "1ª Interação TOA": 30,
                    "is_leader": False,
                },
                {
                    **component_cols,
                    "Nome": "B",
                    "login": "B",
                    "Setor": "RESIDENCIAL",
                    "Vol. Total": 80,
                    "Dias": 10,
                    "Média/Dia": 8.0,
                    "DPA %": 90.0,
                    "1ª Interação TOA": 20,
                    "is_leader": False,
                },
            ]
        )
        all_people = combine_leaders_and_peers(leaders, peers)

        insight = build_leader_insights(leaders, all_people)[0]

        self.assertEqual(["1ª Interação TOA"], insight["weaknesses"])
        self.assertEqual([], insight["strengths"])

    def test_detail_table_is_sorted_by_total_volume(self):
        leaders = pd.DataFrame(
            [
                {"Líder": "B", "Setor": "EMPRESARIAL", "Vol. Total": 50, "Dias": 10, "Média/Dia": 5.0},
                {"Líder": "A", "Setor": "RESIDENCIAL", "Vol. Total": 100, "Dias": 10, "Média/Dia": 10.0},
            ]
        )
        for column in [
            "Ab. New Monitor",
            "Fech. New Monitor",
            "Ab. SGO",
            "Fech. SGO",
            "Trat. RAL",
            "Trat. REC",
            "Ab. Remedy",
            "Ligações Realiz.",
            "1ª Interação TOA",
            "Fech. Tarefa TOA",
        ]:
            leaders[column] = 0

        table = leader_detail_table(leaders)

        self.assertEqual(["A", "B"], table["Líder"].tolist())
        self.assertEqual([1, 2], table["#"].tolist())

    def test_percent_vs(self):
        self.assertEqual(-50.0, percent_vs(50, 100))
        self.assertEqual(100.0, percent_vs(200, 100))
        self.assertEqual(0.0, percent_vs(10, 0))


if __name__ == "__main__":
    unittest.main()
