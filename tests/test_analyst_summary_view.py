import unittest

import pandas as pd

from src.ui.analyst.shell import (
    _assertiveness_dimension_table,
    _assertiveness_service_scoped_details,
    _build_summary_snapshot,
    _chat_group_table,
    _closing_cause_table,
    _closing_dimension_table,
    _cancelled_tasks_user_summary,
    _cancellation_etit_base_for_period,
    _build_analyst_performance_feedback,
    _closing_review_rows,
    _dpa_chart_scale,
    _dpa_recent_chart_rows,
    _etit_dimension_table,
    _etit_operational_summary,
    _render_indicator_status_card,
    _enterprise_etit_demand_cards,
    _indicator_recent_rows,
    _indicator_volume_for_period,
    _meets_target,
    _period_label,
    _productivity_activity_table,
    _productivity_chart_scale,
    _productivity_recent_rows,
    _productivity_user_summary,
    _residential_certification_status,
    _residential_occurrence_type,
    _validation_group_table,
    _validation_time_user_summary,
    _enterprise_certification_status,
)


class AnalystSummaryViewTest(unittest.TestCase):
    def test_period_label_formats_yyyymm_in_portuguese(self):
        self.assertEqual("Setembro 2026", _period_label("202609"))

    def test_leader_summary_cards_show_team_peer_and_both_comparisons(self):
        from unittest.mock import patch

        row = {
            "indicator_key": "dpa_official",
            "name": "DPA Oficial",
            "value": 61.8,
            "target_value": 90.0,
            "direction": "higher_is_better",
            "unit": "percent",
            "volume": 1,
        }
        team = {"team_avg": 86.0}
        peer = {"peer_avg": 91.2, "peer_count": 1}

        with patch("src.ui.analyst.shell.st.markdown") as markdown:
            _render_indicator_status_card(row, team, peer=peer, leader_view=True)
            rendered = markdown.call_args.args[0]
            self.assertIn("Média da equipe", rendered)
            self.assertIn("86,0%", rendered)
            self.assertIn("Outro líder", rendered)
            self.assertIn("91,2%", rendered)
            self.assertIn("Comparação vs líderes", rendered)
            self.assertIn("29,4 pp pior", rendered)
            self.assertIn("todos os segmentos", rendered)

        etit_row = dict(row, indicator_key="emp_etit_event", name="ETIT por Evento")
        with patch("src.ui.analyst.shell.st.markdown") as markdown:
            _render_indicator_status_card(
                etit_row,
                team,
                peer={"peer_avg": 91.2, "peer_count": 1, "newest_period": "2026-08"},
                leader_view=True,
            )
            etit_rendered = markdown.call_args.args[0]
            self.assertIn("Outro líder do segmento", etit_rendered)
            self.assertIn("mesmo segmento", etit_rendered)

        with patch("src.ui.analyst.shell.st.markdown") as markdown:
            _render_indicator_status_card(row, team)
            rendered = markdown.call_args.args[0]
            self.assertNotIn("Outro líder do setor", rendered)
            self.assertNotIn("Comparação vs líderes", rendered)

    def test_leader_summary_with_no_peer_data_does_not_invent_zero(self):
        from unittest.mock import patch

        row = {
            "indicator_key": "chat_10m",
            "name": "Chat 10 min",
            "value": 80.0,
            "target_value": 75.0,
            "direction": "higher_is_better",
            "unit": "percent",
            "volume": 15,
        }
        with patch("src.ui.analyst.shell.st.markdown") as markdown:
            _render_indicator_status_card(
                row, {"team_avg": 70}, peer=None, leader_view=True
            )
            rendered = markdown.call_args.args[0]
            self.assertIn("Média dos outros líderes", rendered)
            self.assertIn("Comparação vs líderes", rendered)
            self.assertIn(">—</strong>", rendered)

    def test_leader_cards_disclose_small_team_base_and_missing_peers(self):
        from unittest.mock import patch

        row = {
            "indicator_key": "toa_cancellation_rate",
            "name": "Tarefas Canceladas",
            "value": 48.1,
            "target_value": 15.0,
            "direction": "lower_is_better",
            "unit": "percent",
            "volume": 27,
        }
        team = {
            "team_avg": 100.0,
            "team_volume": 1,
            "analysts_with_data": 1,
        }
        with patch("src.ui.analyst.shell.st.markdown") as markdown:
            _render_indicator_status_card(
                row, team, peer=None, leader_view=True
            )
            markup = markdown.call_args.args[0]
            self.assertIn("Base da equipe: 1 analista · volume 1", markup)
            self.assertIn("referência limitada", markup)
            self.assertIn("Comparação com a equipe", markup)
            self.assertIn(
                "Nenhum outro líder possui resultado disponível", markup
            )
            self.assertIn("Média dos outros líderes", markup)
        with patch("src.ui.analyst.shell.st.markdown") as markdown:
            _render_indicator_status_card(row, team)
            markup = markdown.call_args.args[0]
            self.assertNotIn("Base da equipe:", markup)
            self.assertNotIn("Nenhum outro líder possui", markup)

    def test_target_direction_is_respected(self):
        self.assertTrue(_meets_target(92.0, 90.0, "higher_is_better"))
        self.assertFalse(_meets_target(81.0, 90.0, "higher_is_better"))
        self.assertTrue(_meets_target(8.0, 10.0, "lower_is_better"))
        self.assertFalse(_meets_target(12.0, 10.0, "lower_is_better"))

    def test_closing_causes_are_grouped_without_duplicate_labels(self):
        details = pd.DataFrame(
            {
                "dimension": ["cause_toa", "cause_toa", "cause_toa"],
                "dimension_value": ["VANDALISMO", "VANDALISMO", "CARGA ALTA"],
                "losses": [1, 2, 1],
                "volume": [1, 2, 1],
                "successes": [0, 0, 0],
            }
        )

        table = _closing_cause_table(details, "cause_toa", "Causa TOA")

        self.assertEqual(["VANDALISMO", "CARGA ALTA"], table["Causa TOA"].tolist())
        self.assertEqual([3, 1], table["Não Assertivos"].tolist())

    def test_closing_group_and_demand_tables_compare_with_team(self):
        details = pd.DataFrame(
            {
                "dimension": ["group", "group", "demand", "demand"],
                "dimension_value": ["Rio e ES", "Norte", "RAL", "REC"],
                "volume": [10, 2, 8, 4],
                "successes": [9, 1, 6, 4],
                "losses": [1, 1, 2, 0],
            }
        )
        # O payload real do repositório retorna agregados team_* (não
        # os campos individuais volume/successes/losses) para a equipe.
        team = pd.DataFrame(
            {
                "dimension": ["group", "group", "demand", "demand"],
                "dimension_value": ["Rio e ES", "Norte", "RAL", "REC"],
                "team_avg": [95.0, 80.0, 90.0, 95.0],
                "team_volume": [100, 20, 80, 40],
                "team_successes": [95, 16, 72, 38],
                "team_losses": [5, 4, 8, 2],
                "team_analysts": [5, 4, 5, 3],
            }
        )

        groups = _closing_dimension_table(details, team, "group", "Grupo")
        demands = _closing_dimension_table(details, team, "demand", "Demanda")

        rio = groups[groups["Grupo"] == "Rio e ES"].iloc[0]
        ral = demands[demands["Demanda"] == "RAL"].iloc[0]

        self.assertEqual("90,0%", rio["Meu resultado"])
        self.assertEqual("95,0%", rio["Média da equipe"])
        self.assertEqual("75,0%", ral["Meu resultado"])
        self.assertEqual("90,0%", ral["Média da equipe"])

    def test_closing_review_rows_keep_ral_rec_and_daily_context(self):
        details = pd.DataFrame(
            {
                "dimension": ["incident", "incident"],
                "dimension_value": ["RAL|||24057920", "REC|||24058280"],
                "day": ["2026-09-17", "2026-09-16"],
                "losses": [1, 1],
                "volume": [1, 1],
                "successes": [0, 0],
            }
        )
        payload = {
            "individual": [
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-17",
                    "value": 0.0,
                    "volume": 1,
                },
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-16",
                    "value": 66.7,
                    "volume": 3,
                },
            ],
            "team_daily": [
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-17",
                    "team_avg": 66.7,
                },
                {
                    "indicator_key": "closing_assertiveness",
                    "period": "2026-09-16",
                    "team_avg": 75.0,
                },
            ],
        }

        rows = _closing_review_rows(details, payload)

        self.assertEqual(["RAL", "REC"], [row["Demanda"] for row in rows])
        self.assertEqual(
            ["24057920", "24058280"],
            [row["INC / Identificador"] for row in rows],
        )
        self.assertEqual("0,0%", rows[0]["Resultado do dia"])
        self.assertEqual("66,7%", rows[0]["Média da equipe no dia"])

    def test_assertiveness_dimension_table_matches_operational_columns(self):
        details = pd.DataFrame(
            {
                "dimension": ["impact", "impact", "impact"],
                "dimension_value": ["Massivo", "Massivo", "Não Massivo"],
                "volume": [2, 1, 2],
                "successes": [1, 1, 2],
                "losses": [1, 0, 0],
            }
        )

        table = _assertiveness_dimension_table(
            details,
            "impact",
            "Impacto",
        )

        self.assertEqual(
            [
                "Impacto",
                "Volume",
                "Assertivos",
                "Não Assertivos",
                "Assertividade %",
                "Não Assertividade %",
            ],
            table.columns.tolist(),
        )
        massivo = table[table["Impacto"] == "Massivo"].iloc[0]
        self.assertEqual(3, massivo["Volume"])
        self.assertEqual(2, massivo["Assertivos"])
        self.assertEqual(1, massivo["Não Assertivos"])
        self.assertEqual("66,7%", massivo["Assertividade %"])
        self.assertEqual("33,3%", massivo["Não Assertividade %"])

    def test_assertiveness_gpon_service_scope_rehydrates_compound_dimensions(self):
        details = pd.DataFrame(
            {
                "dimension": [
                    "service",
                    "service",
                    "service__overall",
                    "service__overall",
                    "service__group",
                    "service__group",
                ],
                "dimension_value": [
                    "BROWNFIELD",
                    "GREENFIELD",
                    "BROWNFIELD|||Total",
                    "GREENFIELD|||Total",
                    "BROWNFIELD|||Centro-Oeste",
                    "GREENFIELD|||Norte",
                ],
                "volume": [24, 13, 24, 13, 24, 13],
                "successes": [22, 13, 22, 13, 22, 13],
                "losses": [2, 0, 2, 0, 2, 0],
            }
        )

        scoped = _assertiveness_service_scoped_details(
            details,
            "BROWNFIELD",
        )

        overall = scoped[scoped["dimension"] == "overall"].iloc[0]
        group = scoped[scoped["dimension"] == "group"].iloc[0]
        self.assertEqual("Total", overall["dimension_value"])
        self.assertEqual(24, overall["volume"])
        self.assertEqual("Centro-Oeste", group["dimension_value"])
        self.assertFalse(
            scoped["dimension_value"].astype(str).str.contains("GREENFIELD").any()
        )

    def test_residential_etit_occurrence_type_labels_inm_as_outage(self):
        self.assertEqual(
            "Outage",
            _residential_occurrence_type("INM00002274788"),
        )
        self.assertEqual(
            "Incidente",
            _residential_occurrence_type("INC123456"),
        )
        self.assertEqual(
            "Incidente",
            _residential_occurrence_type("24057920"),
        )

    def test_etit_operational_summary_keeps_events_adherents_and_durations(self):
        details = pd.DataFrame(
            {
                "dimension": ["overall", "overall"],
                "dimension_value": ["Total", "Total"],
                "volume": [5, 3],
                "successes": [4, 2],
                "losses": [1, 1],
                "tma_seconds": [120.0, 240.0],
                "tmr_seconds": [600.0, 900.0],
            }
        )

        summary = _etit_operational_summary(details)

        self.assertEqual(8, summary["volume"])
        self.assertEqual(6, summary["successes"])
        self.assertEqual(2, summary["losses"])
        self.assertEqual(75.0, summary["adherence"])
        self.assertAlmostEqual(165.0, summary["tma_seconds"], places=1)
        self.assertAlmostEqual(712.5, summary["tmr_seconds"], places=1)

    def test_etit_residential_service_table_compares_with_team(self):
        details = pd.DataFrame(
            {
                "dimension": ["service", "service"],
                "dimension_value": ["BROWNFIELD", "GREENFIELD"],
                "volume": [10, 4],
                "successes": [9, 2],
                "losses": [1, 2],
                "tma_seconds": [60.0, 120.0],
                "tmr_seconds": [600.0, 900.0],
            }
        )
        team = pd.DataFrame(
            {
                "dimension": ["service", "service"],
                "dimension_value": ["BROWNFIELD", "GREENFIELD"],
                "team_avg": [95.0, 80.0],
                "team_volume": [100, 20],
                "team_successes": [95, 16],
                "team_losses": [5, 4],
                "team_analysts": [5, 5],
            }
        )

        table = _etit_dimension_table(
            details,
            team,
            "service",
            "Serviço",
            include_duration=True,
        )

        brownfield = table[table["Serviço"] == "BROWNFIELD"].iloc[0]
        greenfield = table[table["Serviço"] == "GREENFIELD"].iloc[0]

        self.assertEqual("90,0%", brownfield["Aderência %"])
        self.assertEqual("95,0%", brownfield["Média equipe %"])
        self.assertEqual("00:01:00", brownfield["TMA"])
        self.assertEqual("50,0%", greenfield["Aderência %"])

    def test_enterprise_etit_demand_cards_separate_my_results_from_team(self):
        details = pd.DataFrame(
            {
                "dimension": ["overall", "demand", "demand", "type"],
                "dimension_value": ["Total", " RAL ", "rec", "ACESSO CLIENTE"],
                "volume": [137, 107, 30, 38],
                "successes": [124, 95, 29, 36],
                "losses": [13, 12, 1, 2],
                "tma_seconds": [150.0, 183.0, 30.0, 120.0],
                "tmr_seconds": [1300.0, 1226.0, 1563.0, 1000.0],
            }
        )
        team = pd.DataFrame(
            {
                "dimension": ["demand", "demand"],
                "dimension_value": ["RAL", "REC"],
                "team_avg": [91.1, 95.6],
                "team_volume": [500, 300],
                "team_successes": [455.5, 286.8],
                "team_losses": [27, 4],
                "team_analysts": [5, 8],
            }
        )

        cards = _enterprise_etit_demand_cards(details, team)
        self.assertEqual(["RAL", "REC"], [card["demand"] for card in cards])
        ral, rec = cards

        self.assertEqual((107, 95, 12), (
            ral["volume"], ral["successes"], ral["losses"]
        ))
        self.assertAlmostEqual(95 / 107 * 100, ral["adherence"])
        self.assertEqual(91.1, ral["team_avg"])
        self.assertEqual("2,3 pp pior", ral["comparison"])
        self.assertEqual("attention", ral["comparison_tone"])
        self.assertEqual(183.0, ral["tma_seconds"])
        self.assertEqual(1226.0, ral["tmr_seconds"])
        self.assertAlmostEqual(5.4, ral["avg_team_losses"])

        self.assertEqual((30, 29, 1), (
            rec["volume"], rec["successes"], rec["losses"]
        ))
        self.assertAlmostEqual(29 / 30 * 100, rec["adherence"])
        self.assertEqual(95.6, rec["team_avg"])
        self.assertEqual("1,1 pp melhor", rec["comparison"])
        self.assertEqual("good", rec["comparison_tone"])
        self.assertEqual(30.0, rec["tma_seconds"])
        self.assertEqual(1563.0, rec["tmr_seconds"])
        self.assertAlmostEqual(0.5, rec["avg_team_losses"])

        # Somente a dimensão demand; outras dimensões repetem os eventos.
        self.assertEqual(137, ral["volume"] + rec["volume"])
        self.assertEqual(124, ral["successes"] + rec["successes"])
        self.assertEqual(13, ral["losses"] + rec["losses"])

    def test_enterprise_etit_missing_demand_is_not_reported_as_zero(self):
        details = pd.DataFrame(
            {
                "dimension": ["demand"],
                "dimension_value": ["RAL"],
                "volume": [9],
                "successes": [9],
                "losses": [0],
            }
        )
        cards = _enterprise_etit_demand_cards(details, pd.DataFrame())
        self.assertTrue(cards[0]["has_data"])
        self.assertEqual("RAL", cards[0]["demand"])
        self.assertIsNone(cards[0]["team_avg"])
        self.assertEqual("—", cards[0]["comparison"])
        self.assertFalse(cards[1]["has_data"])
        self.assertEqual("REC", cards[1]["demand"])

    def test_dpa_recent_chart_rows_include_all_available_days_without_team(self):
        payload = {
            "individual": [
                {
                    "indicator_key": "dpa_official",
                    "period": f"2026-09-{day:02d}",
                    "value": 80.0 + day,
                    "volume": 28800,
                }
                for day in range(1, 11)
            ],
            "team_daily": [
                {
                    "indicator_key": "dpa_official",
                    "period": "2026-09-10",
                    "team_avg": 94.0,
                }
            ],
        }

        rows = _dpa_recent_chart_rows(payload)

        self.assertEqual(10, len(rows))
        self.assertEqual("01/09", rows[0]["date_label"])
        self.assertEqual("10/09", rows[-1]["date_label"])
        self.assertNotIn("team_avg", rows[0])
        self.assertEqual(100.0, _dpa_chart_scale(rows))

    def test_dpa_chart_scale_expands_for_values_above_100(self):
        rows = [
            {"value": 123.1},
            {"value": 101.0},
        ]

        self.assertEqual(130.0, _dpa_chart_scale(rows))

    def test_productivity_summary_uses_exact_volume_days_and_sector_references(self):
        row = {
            "indicator_key": "productivity_avg_daily",
            "value": 63.8,
            "volume": 17,
        }
        details = pd.DataFrame(
            {
                "dimension": ["productivity_total"],
                "dimension_value": ["Volume Total"],
                "successes": [1085],
                "volume": [1085],
            }
        )
        team = {"team_avg": 84.0}
        team_details = pd.DataFrame(
            {
                "dimension": ["productivity_total"],
                "dimension_value": ["Volume Total"],
                "team_successes": [7045],
                "team_volume": [7045],
                "team_analysts": [5],
            }
        )

        summary = _productivity_user_summary(
            row,
            details,
            team,
            team_details,
        )

        self.assertEqual(1085.0, summary["volume_total"])
        self.assertEqual(63.8, summary["daily_avg"])
        self.assertEqual(17, summary["active_days"])
        self.assertEqual(1409.0, summary["team_volume_avg"])
        self.assertEqual(84.0, summary["team_daily_avg"])

    def test_productivity_activity_table_sums_and_sorts_components(self):
        details = pd.DataFrame(
            {
                "dimension": [
                    "productivity_component",
                    "productivity_component",
                    "productivity_component",
                ],
                "dimension_value": [
                    "Tratativa RAL",
                    "Tratativa RAL",
                    "Fechamento Tarefa TOA",
                ],
                "successes": [200, 99, 230],
            }
        )

        table = _productivity_activity_table(details)

        self.assertEqual(
            ["Tratativa RAL", "Fechamento Tarefa TOA"],
            table["Atividade"].tolist(),
        )
        self.assertEqual([299, 230], table["Volume"].tolist())

    def test_productivity_recent_rows_include_team_reference_and_chart_scale(self):
        payload = {
            "individual": [
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-28",
                    "value": 55.0,
                },
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-29",
                    "value": 80.0,
                },
            ],
            "team_daily": [
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-28",
                    "team_avg": 60.0,
                },
                {
                    "indicator_key": "productivity_avg_daily",
                    "period": "2026-09-29",
                    "team_avg": 75.0,
                },
            ],
        }

        rows = _productivity_recent_rows(payload)

        self.assertEqual(["28/09", "29/09"], [row["date_label"] for row in rows])
        self.assertEqual([55.0, 80.0], [row["value"] for row in rows])
        self.assertEqual([60.0, 75.0], [row["team_avg"] for row in rows])
        self.assertEqual(80.0, _productivity_chart_scale(rows))

    def test_cancelled_tasks_summary_uses_etit_volume_as_percentage_base(self):
        details = pd.DataFrame(
            {
                "dimension": ["overall", "overall"],
                "losses": [1, 1],
                "volume": [1, 1],
            }
        )
        team = pd.DataFrame(
            {
                "dimension": ["overall"],
                "team_losses": [15],
                "team_analysts": [7],
            }
        )

        summary = _cancelled_tasks_user_summary(
            details,
            team,
            etit_volume=137,
            target_pct=15.0,
        )

        self.assertEqual(2.0, summary["cancelled"])
        self.assertEqual(137.0, summary["etit_volume"])
        self.assertAlmostEqual((2 / 137) * 100, summary["analyst_pct"], places=6)
        self.assertEqual(15.0, summary["target_pct"])
        self.assertAlmostEqual(15 / 7, summary["team_average"], places=5)
        self.assertEqual("good", summary["tone"])

    def test_cancelled_tasks_uses_official_15_percent_max_target(self):
        team = pd.DataFrame()

        good = _cancelled_tasks_user_summary(
            pd.DataFrame({"dimension": ["overall"], "losses": [15]}),
            team,
            etit_volume=100,
        )
        attention = _cancelled_tasks_user_summary(
            pd.DataFrame({"dimension": ["overall"], "losses": [18]}),
            team,
            etit_volume=100,
        )
        bad = _cancelled_tasks_user_summary(
            pd.DataFrame({"dimension": ["overall"], "losses": [25]}),
            team,
            etit_volume=100,
        )

        self.assertEqual("good", good["tone"])
        self.assertEqual("attention", attention["tone"])
        self.assertEqual("bad", bad["tone"])

    def test_indicator_volume_for_period_uses_matching_etit_month(self):
        rows = [
            {"indicator_key": "emp_etit_event", "period": "2026-08", "volume": 99},
            {"indicator_key": "emp_etit_event", "period": "2026-09", "volume": 137},
            {"indicator_key": "toa_cancellation_rate", "period": "2026-09", "volume": 2},
        ]

        volume = _indicator_volume_for_period(
            rows,
            "emp_etit_event",
            "2026-09",
        )

        self.assertEqual(137.0, volume)
        self.assertIsNone(
            _indicator_volume_for_period(rows, "emp_etit_event", "2026-10")
        )

    def test_missing_etit_card_preserves_cancelled_count_and_blocks_percent(self):
        from unittest.mock import patch

        row = {
            "indicator_key": "toa_cancellation_rate",
            "name": "Tarefas Canceladas",
            "value": None,
            "target_value": 15.0,
            "direction": "lower_is_better",
            "unit": "percent",
            "volume": 27,
            "cancelled_count": 13,
            "missing_etit_base": True,
        }
        with patch("src.ui.analyst.shell.st.markdown") as markdown:
            _render_indicator_status_card(
                row, {"team_avg": 0.6, "team_volume": 179,
                      "analysts_with_data": 6},
                peer=None, leader_view=True,
            )
            markup = markdown.call_args.args[0]
            self.assertIn("Sem base ETIT", markup)
            self.assertIn("13 canceladas", markup)
            self.assertIn("27 registros", markup)
            self.assertNotIn("48,1%", markup)
            self.assertIn("0,6%", markup)

    def test_chat_group_table_exposes_group_volume_adherence_and_team_reference(self):
        details = pd.DataFrame(
            {
                "dimension": ["group", "group"],
                "dimension_value": ["Minas Gerais", "Centro-Oeste"],
                "volume": [10, 5],
                "successes": [8, 5],
                "losses": [2, 0],
            }
        )
        team = pd.DataFrame(
            {
                "dimension": ["group", "group"],
                "dimension_value": ["Minas Gerais", "Centro-Oeste"],
                "team_avg": [90.0, 95.0],
                "team_volume": [100, 50],
                "team_successes": [90, 47],
                "team_losses": [10, 3],
            }
        )

        table = _chat_group_table(details, team)

        minas = table[table["Grupo"] == "Minas Gerais"].iloc[0]
        self.assertEqual(10, minas["Volume"])
        self.assertEqual(8, minas["Aderentes"])
        self.assertEqual("80,0%", minas["Aderência %"])
        self.assertEqual("90,0%", minas["Média equipe %"])

    def test_indicator_recent_rows_limits_etit_to_last_seven_days_with_team(self):
        payload = {
            "individual": [
                {
                    "indicator_key": "emp_etit_event",
                    "period": f"2026-09-{day:02d}",
                    "value": 80.0 + day,
                }
                for day in range(1, 11)
            ],
            "team_daily": [
                {
                    "indicator_key": "emp_etit_event",
                    "period": f"2026-09-{day:02d}",
                    "team_avg": 90.0,
                }
                for day in range(1, 11)
            ],
        }

        rows = _indicator_recent_rows(
            payload,
            "emp_etit_event",
            limit=7,
            include_team=True,
        )

        self.assertEqual(7, len(rows))
        self.assertEqual("04/09", rows[0]["date_label"])
        self.assertEqual("10/09", rows[-1]["date_label"])
        self.assertEqual(90.0, rows[0]["team_avg"])

    def test_validation_summary_matches_total_adherents_losses_tmr_and_team(self):
        row = {
            "indicator_key": "validacao_20m",
            "value": 86.5,
            "volume": 104,
        }
        team = {"team_avg": 84.2}
        details = pd.DataFrame(
            {
                "dimension": ["overall", "overall"],
                "volume": [70, 34],
                "successes": [58, 32],
                "losses": [12, 2],
                "tmr_seconds": [942.0, 660.0],
            }
        )

        summary = _validation_time_user_summary(row, team, details)

        self.assertEqual(104.0, summary["total"])
        self.assertEqual(90.0, summary["successes"])
        self.assertEqual(14.0, summary["losses"])
        self.assertAlmostEqual(86.53846, summary["adherence"], places=4)
        self.assertAlmostEqual(
            ((942.0 * 70) + (660.0 * 34)) / 104 / 60,
            summary["tmr_minutes"],
            places=4,
        )
        self.assertEqual(84.2, summary["team_avg"])

    def test_validation_group_table_keeps_only_requested_operational_columns(self):
        details = pd.DataFrame(
            {
                "dimension": ["group", "group", "group"],
                "dimension_value": ["Minas Gerais", "Minas Gerais", "Nordeste"],
                "volume": [50, 20, 10],
                "successes": [40, 18, 10],
                "losses": [10, 2, 0],
                "tmr_seconds": [960.0, 780.0, 114.0],
            }
        )

        table = _validation_group_table(details)

        self.assertEqual(
            ["Grupo", "Total", "Aderentes", "Aderência %", "TMR (min)"],
            table.columns.tolist(),
        )
        minas = table[table["Grupo"] == "Minas Gerais"].iloc[0]
        self.assertEqual(70, minas["Total"])
        self.assertEqual(58, minas["Aderentes"])
        self.assertEqual("82,9%", minas["Aderência %"])

    def test_residential_cancellation_base_sums_hfc_and_gpon_etit(self):
        rows = [
            {
                "indicator_key": "res_etit_fibra_hfc",
                "period": "2026-09",
                "volume": 104,
            },
            {
                "indicator_key": "res_etit_gpon",
                "period": "2026-09",
                "volume": 37,
            },
            {
                "indicator_key": "toa_cancellation_rate",
                "period": "2026-09",
                "volume": 2,
            },
        ]

        base = _cancellation_etit_base_for_period(rows, "2026-09")

        self.assertEqual(141.0, base["volume"])
        self.assertEqual("VOLUME ETIT HFC + GPON", base["label"])
        self.assertEqual("res_etit_hfc_gpon", base["source"])

    def test_residential_certification_uses_legacy_three_rule_model(self):
        result = _residential_certification_status(
            100.0,
            83.2,
            66.7,
            94.6,
        )

        self.assertEqual("bad", result["status"])
        self.assertEqual("❌ Você NÃO está certificando", result["title"])
        self.assertAlmostEqual(80.65, result["assert_avg"], places=2)
        self.assertIn("DPA individual abaixo de 85%", result["message"])
        self.assertIn("Média Assertividade abaixo de 85%", result["message"])

    def test_residential_certification_keeps_dpa_alert_as_certifying(self):
        result = _residential_certification_status(
            92.0,
            87.0,
            88.0,
            90.0,
        )

        self.assertEqual("attention", result["status"])
        self.assertEqual("⚠️ Você está certificando", result["title"])
        self.assertAlmostEqual(89.0, result["assert_avg"], places=2)

    def test_residential_certification_treats_missing_values_as_non_blocking(self):
        result = _residential_certification_status(
            None,
            92.0,
            None,
            None,
        )

        self.assertEqual("good", result["status"])
        self.assertIn("Sem dados de ETIT Fibra HFC", result["message"])
        self.assertIn("Média Assertividade", result["message"])

    def test_enterprise_certification_green_requires_etit_and_dpa_at_90(self):
        result = _enterprise_certification_status(90.5, 92.5)

        self.assertEqual("good", result["status"])
        self.assertEqual("✅ Você está certificando", result["title"])
        self.assertIn("dentro da meta", result["message"])

    def test_enterprise_certification_uses_dpa_alert_band_between_85_and_90(self):
        result = _enterprise_certification_status(94.0, 87.5)

        self.assertEqual("attention", result["status"])
        self.assertEqual("⚠️ Você está certificando", result["title"])

    def test_enterprise_certification_fails_below_etit_or_low_dpa(self):
        result = _enterprise_certification_status(88.0, 82.0)

        self.assertEqual("bad", result["status"])
        self.assertIn("ETIT por Evento abaixo de 90%", result["message"])
        self.assertIn("DPA individual abaixo de 85%", result["message"])

    def test_performance_reading_combines_strength_attention_and_suggestion(self):
        latest = [
            {
                "indicator_key": "productivity_avg_daily",
                "period": "2026-09",
                "value": 80.0,
                "target_value": None,
                "direction": "higher_is_better",
            },
            {
                "indicator_key": "dpa_official",
                "period": "2026-09",
                "value": 92.0,
                "target_value": 90.0,
                "direction": "higher_is_better",
            },
            {
                "indicator_key": "chat_10m",
                "period": "2026-09",
                "value": 60.0,
                "target_value": 75.0,
                "direction": "higher_is_better",
            },
        ]
        team_index = {
            ("2026-09", "productivity_avg_daily"): {"team_avg": 70.0},
            ("2026-09", "dpa_official"): {"team_avg": 90.0},
            ("2026-09", "chat_10m"): {"team_avg": 72.0},
        }

        feedback = _build_analyst_performance_feedback(
            latest,
            team_index,
            [],
            [],
        )

        self.assertIn("bons fundamentos", feedback["summary"])
        self.assertIn("produtividade alta", feedback["point_strong"])
        self.assertIn("chat", feedback["point_attention"].lower())
        self.assertIn("padronizar respostas", feedback["suggestion"].lower())

    def test_summary_snapshot_counts_targets_and_team_comparison(self):
        latest = [
            {
                "period": "202609",
                "indicator_key": "chat_10m",
                "name": "Chat 10 min",
                "value": 75.9,
                "target_value": 75.0,
                "direction": "higher_is_better",
                "unit": "percent",
            },
            {
                "period": "202609",
                "indicator_key": "dpa_official",
                "name": "DPA Oficial",
                "value": 81.0,
                "target_value": 90.0,
                "direction": "higher_is_better",
                "unit": "percent",
            },
            {
                "period": "202609",
                "indicator_key": "productivity_avg_daily",
                "name": "Produtividade média diária",
                "value": 34.8,
                "target_value": None,
                "direction": "higher_is_better",
                "unit": "number",
            },
        ]
        team_index = {
            ("202609", "chat_10m"): {"team_avg": 61.1},
            ("202609", "dpa_official"): {"team_avg": 96.4},
            ("202609", "productivity_avg_daily"): {"team_avg": 46.3},
        }
        freshness = [{"data_through": "2026-09-28"}]

        snapshot = _build_summary_snapshot(latest, team_index, freshness)

        self.assertEqual(3, snapshot["tracked"])
        self.assertEqual(2, snapshot["with_target"])
        self.assertEqual(1, snapshot["met"])
        self.assertEqual(3, snapshot["with_team"])
        self.assertEqual(1, snapshot["above_team"])
        self.assertEqual("28/09/2026", snapshot["freshness_label"])
        self.assertEqual("Chat 10 min", snapshot["best_title"])
        self.assertEqual("DPA Oficial", snapshot["attention_title"])


if __name__ == "__main__":
    unittest.main()
