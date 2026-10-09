"""Night external analyst data: independent months, hour boundaries and RBAC."""
from __future__ import annotations

import unittest

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.config.seed import seed_foundation
from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository
from src.ui.admin.external_analysts import (
    NIGHT_HOURS,
    _as_frame,
    _hour_from_label,
    _indicator_summary,
    _partition_external_records,
    _people_summary,
    _monthly_indicator_summary,
    _monthly_external_people,
    _monthly_external_adherence_table,
    _external_name,
    _detail_table,
)
from tests.isolated_database import isolate_sqlite_database


class ExternalAnalystsNightTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        seed_foundation()
        self.users = UserRepository()
        self.segments = SegmentRepository()
        self.indicators = IndicatorRepository()
        self.service = DashboardService(access=AccessService(self.users))
        self.emp = self.segments.get_by_slug("empresarial")
        self.res = self.segments.get_by_slug("residencial")
        self.admin = self.service.access.context(self.users.get_by_login("ADMIN").id)

    def add_rows(self, segment, key, rows, month="2026-10"):
        definition = self.indicators.get_definition(segment.id, key)
        self.assertIsNotNone(definition)
        records = []
        for login, day, hour, vol, successful in rows:
            records.append({
                "scope": "external",
                "login": login,
                "period": day,
                "data_month": month,
                "dimension": "external_hour",
                "dimension_value": str(hour),
                "value": successful / vol * 100,
                "volume": vol,
                "successes": successful,
                "losses": vol-successful,
            })
        self.indicators.replace_breakdowns_for_months(
            segment_id=segment.id,
            indicator_definition_id=int(definition["id"]),
            rows=tuple(records),
            months=(month,),
        )

    def test_external_month_appears_without_any_team_results_for_same_month(self):
        self.add_rows(
            self.emp, "emp_etit_event",
            [("OUTSIDER", "2026-10-06", "22", 3, 2)],
        )
        self.assertIn(
            "2026-10", self.service.external_night_months(self.admin, [self.emp.id])
        )
        rows = self.service.external_night_payload(
            self.admin, [self.emp.id], "2026-10"
        )
        self.assertEqual(1, len(rows))
        self.assertEqual("OUTSIDER", rows[0]["login"])
        self.assertEqual(3, rows[0]["volume"])
        self.assertEqual(2, rows[0]["successes"])
        self.assertEqual("emp_etit_event", rows[0]["indicator_key"])

    def test_window_boundaries_and_unknown_time_never_pollute_night_totals(self):
        cases = [
            ("EXT", "2026-10-06", "21", 1, 1),
            ("EXT", "2026-10-06", "22", 1, 1),
            ("EXT", "2026-10-06", "23", 1, 1),
            ("EXT", "2026-10-07", "0", 1, 1),
            ("EXT", "2026-10-07", "5", 1, 0),
            ("EXT", "2026-10-07", "6", 1, 1),
            ("UNCERTAIN", "2026-10-07", "Madrugada", 1, 1),
            ("NOHOUR", "2026-10-07", "Sem horário", 1, 1),
        ]
        self.add_rows(self.res, "validacao_20m", cases)
        payload = self.service.external_night_payload(
            self.admin, [self.res.id], "2026-10"
        )
        results = _partition_external_records(payload)
        self.assertEqual(4, len(results["confirmed"]))
        self.assertEqual(2, len(results["outside_window"]))
        self.assertEqual(1, len(results["reported_shift"]))
        self.assertEqual(1, len(results["unknown_hour"]))
        self.assertEqual(4, sum(row["volume"] for row in results["confirmed"]))

    def test_unverifiable_dpa_can_be_audited_but_never_called_night(self):
        self.add_rows(
            self.res, "dpa_official",
            [("OTHER", "2026-10-06", "Sem horário", 3600, 2700)],
        )
        groups = _partition_external_records(
            self.service.external_night_payload(
                self.admin, [self.res.id], "2026-10"
            )
        )
        self.assertEqual([], groups["confirmed"])
        self.assertEqual(1, len(groups["unknown_hour"]))

    def test_registered_own_team_is_excluded_even_if_source_mislabeled_external(self):
        # Importações legadas podem conter b.scope='external' incorreto.
        # Nenhum membro da equipe de Nelson deve ser listado como "outra equipe".
        self.add_rows(
            self.res, "res_etit_gpon",
            [
                ("N5972428", "2026-10-06", "22", 10, 8),  # Cristiane: equipe
                ("N4014011", "2026-10-06", "22", 8, 7),   # Alan: equipe
                ("F106664", "2026-10-06", "23", 7, 7),    # Raissa: equipe
                ("N0239871", "2026-10-06", "0", 6, 6),    # Leonardo: equipe
                ("N5772086", "2026-10-06", "3", 4, 3),    # Thiago: equipe
                ("F104752", "2026-10-06", "5", 2, 2),     # Marcelo: equipe
                ("N6105010", "2026-10-06", "22", 8, 6),  # Jefferson: alias legado
                ("OTHERTEAM", "2026-10-06", "22", 5, 4), # outro analista
            ],
        )
        records = self.service.external_night_payload(
            self.admin, [self.res.id], "2026-10"
        )
        self.assertEqual({"OTHERTEAM"}, {r["login"] for r in records})
        self.assertEqual(5, sum(r["volume"] for r in records))
        self.assertIn(
            "2026-10", self.service.external_night_months(
                self.admin, [self.res.id]
            )
        )

    def test_month_with_only_own_team_members_has_no_external_records(self):
        self.add_rows(
            self.res, "res_assert_gpon",
            [("N5972428", "2026-10-06", "22", 2, 2)],
        )
        self.assertEqual(
            [], self.service.external_night_months(self.admin, [self.res.id])
        )
        self.assertEqual(
            [], self.service.external_night_payload(
                self.admin, [self.res.id], "2026-10"
            )
        )

    def test_admin_scope_and_permission_boundaries(self):
        self.add_rows(
            self.emp, "emp_etit_event",
            [("EMP_EXTERNAL", "2026-10-06", "22", 1, 1)],
        )
        self.add_rows(
            self.res, "res_etit_gpon",
            [("RES_EXTERNAL", "2026-10-06", "23", 2, 0)],
        )
        enterprise = self.service.external_night_payload(
            self.admin, [self.emp.id], "2026-10"
        )
        self.assertEqual({"EMP_EXTERNAL"}, {row["login"] for row in enterprise})
        general = self.service.external_night_payload(
            self.admin, [self.emp.id, self.res.id], "2026-10"
        )
        self.assertEqual(2, len(general))
        leader = self.service.access.context(self.users.get_by_login("N5619600").id)
        analyst = self.service.access.context(self.users.get_by_login("N0189105").id)
        for ctx in (leader, analyst):
            with self.subTest(login=ctx.user.login):
                with self.assertRaises(PermissionError):
                    self.service.external_night_months(ctx, [self.emp.id])
                with self.assertRaises(PermissionError):
                    self.service.external_night_payload(ctx, [self.emp.id], "2026-10")
        self.assertEqual(
            [], self.service.external_night_payload(self.admin, [self.emp.id], "2025-01")
        )

    def test_summary_uses_total_successes_not_mean_of_percentages(self):
        self.add_rows(
            self.emp, "emp_etit_event",
            [
                ("OUTSIDE", "2026-10-06", "22", 1, 0),
                ("OUTSIDE", "2026-10-07", "23", 9, 9),
            ],
        )
        frame = _as_frame(
            _partition_external_records(
                self.service.external_night_payload(
                    self.admin, [self.emp.id], "2026-10"
                )
            )["confirmed"]
        )
        people = _people_summary(frame)
        self.assertEqual("90,0%", people.iloc[0]["Aderência"])
        self.assertEqual(10, people.iloc[0]["Volume"])
        self.assertEqual(2, people.iloc[0]["Dias com dados"])
        table = _indicator_summary(frame)
        self.assertEqual("90,0%", table.iloc[0]["Aderência"])
        self.assertEqual(10, table.iloc[0]["Volume"])
        detail = _detail_table(frame)
        self.assertEqual({"22:00–22:59", "23:00–23:59"}, set(detail["Hora"]))

    def test_monthly_aggregation_is_weighted_by_volume_and_keeps_indicators_separate(self):
        # Um resultado de 0/1 em um dia e 9/9 em outro = 90% no mês,
        # não 50% (média incorreta das duas porcentagens diárias).
        rows = [
            {
                "month": month, "segment_name": "Residencial",
                "indicator_key": key, "name": name,
                "login": login, "analyst_name": login,
                "day": day, "hour_label": "22", "volume": volume,
                "successes": ok, "losses": volume-ok,
            }
            for month, key, name, login, day, volume, ok in [
                ("2026-10", "res_etit_fibra_hfc", "ETIT Fibra HFC",
                 "OUT", "2026-10-01", 1, 0),
                ("2026-10", "res_etit_fibra_hfc", "ETIT Fibra HFC",
                 "OUT", "2026-10-02", 9, 9),
                ("2026-10", "res_etit_fibra_hfc", "ETIT Fibra HFC",
                 "SECOND", "2026-10-02", 2, 1),
                ("2026-10", "res_assert_fibra_hfc", "Assertividade Fibra HFC",
                 "OUT", "2026-10-03", 4, 2),
                ("2026-09", "res_etit_fibra_hfc", "ETIT Fibra HFC",
                 "OUT", "2026-09-01", 20, 1),
            ]
        ]
        frame = _as_frame(rows)
        summary = _monthly_indicator_summary(frame)
        self.assertEqual(3, len(summary))
        oct_etit = summary[
            (summary["Competência"] == "2026-10")
            & (summary["Indicador"] == "ETIT Fibra HFC")
        ].iloc[0]
        self.assertEqual(12, oct_etit["Volume no mês"])
        self.assertEqual(10, oct_etit["Positivos no mês"])
        self.assertEqual(2, oct_etit["Analistas externos"])
        self.assertEqual("83,3%", oct_etit["Resultado mensal (%)"])

        people = _monthly_external_people(frame)
        self.assertEqual(4, len(people))
        oct_out = people[
            (people["Competência"] == "2026-10")
            & (people["Indicador"] == "ETIT Fibra HFC")
            & (people["Login"] == "OUT")
        ].iloc[0]
        self.assertEqual(10, oct_out["Volume no mês"])
        self.assertEqual(9, oct_out["Positivos no mês"])
        self.assertEqual("90,0%", oct_out["Resultado mensal (%)"])
        # Não deve exibir uma linha por dia, nem mesclar ETIT e Assertividade.
        self.assertNotIn("Dias com dados", people.columns)
        assert_sep = people[
            (people["Competência"] == "2026-10")
            & (people["Indicador"] == "Assertividade Fibra HFC")
            & (people["Login"] == "OUT")
        ].iloc[0]
        self.assertEqual("50,0%", assert_sep["Resultado mensal (%)"])

    def test_monthly_summary_applies_night_window_before_adding_days(self):
        self.add_rows(
            self.emp, "emp_etit_event",
            [
                ("EXT", "2026-10-06", "21", 4, 4),
                ("EXT", "2026-10-06", "22", 1, 0),
                ("EXT", "2026-10-07", "5", 9, 9),
                ("EXT", "2026-10-07", "6", 10, 0),
            ],
        )
        rows = self.service.external_night_payload(
            self.admin, [self.emp.id], "2026-10"
        )
        data = _as_frame(_partition_external_records(rows)["confirmed"])
        month = _monthly_external_people(data)
        self.assertEqual(1, len(month))
        self.assertEqual(10, month.iloc[0]["Volume no mês"])
        self.assertEqual("90,0%", month.iloc[0]["Resultado mensal (%)"])

    def test_separate_external_months_for_residential_gpon_and_hfc(self):
        self.add_rows(
            self.res, "res_etit_gpon",
            [("GPON_OUTSIDE", "2026-09-16", "22", 11, 10)],
            month="2026-09",
        )
        self.add_rows(
            self.res, "res_etit_fibra_hfc",
            [("HFC_OUTSIDE", "2026-10-06", "23", 9, 6)],
            month="2026-10",
        )
        coverage = self.service.external_night_coverage(
            self.admin, [self.res.id],
            ["res_etit_gpon", "res_etit_fibra_hfc",
             "res_assert_fibra_hfc", "res_assert_gpon"],
        )
        index = {(r["indicator_key"], r["month"]): r for r in coverage}
        self.assertEqual(
            11, index[("res_etit_gpon", "2026-09")]["volume"]
        )
        self.assertEqual(
            9, index[("res_etit_fibra_hfc", "2026-10")]["volume"]
        )
        self.assertNotIn(("res_etit_gpon", "2026-10"), index)
        self.assertEqual(
            {"2026-09"}, {
                row["month"] for row in coverage
                if row["indicator_key"] == "res_etit_gpon"
            },
        )

    def test_enterprise_external_coverage_is_separate_from_residential(self):
        self.add_rows(
            self.emp, "emp_etit_event",
            [("EMPOUT", "2026-10-06", "22", 33, 20)],
            month="2026-10",
        )
        self.add_rows(
            self.res, "res_etit_gpon",
            [("RESOUT", "2026-09-06", "22", 11, 10)],
            month="2026-09",
        )
        enterprise = self.service.external_night_coverage(
            self.admin, [self.emp.id], ["emp_etit_event"]
        )
        self.assertEqual(1, len(enterprise))
        self.assertEqual("emp_etit_event", enterprise[0]["indicator_key"])
        self.assertEqual("2026-10", enterprise[0]["month"])
        self.assertEqual(33, enterprise[0]["volume"])
        residential = self.service.external_night_coverage(
            self.admin, [self.res.id], ["res_etit_gpon"]
        )
        self.assertEqual(11, residential[0]["volume"])
        leader = self.service.access.context(
            self.users.get_by_login("N5619600").id
        )
        with self.assertRaises(PermissionError):
            self.service.external_night_coverage(
                leader, [self.emp.id], ["emp_etit_event"]
            )

    def test_render_shows_each_indicator_with_independent_latest_month(self):
        from contextlib import nullcontext
        from unittest.mock import patch
        from src.ui.admin.external_analysts import (
            render_external_monthly_by_indicator,
        )

        self.add_rows(
            self.res, "res_etit_gpon",
            [("GPON_OUT", "2026-09-07", "22", 11, 10)],
            month="2026-09",
        )
        self.add_rows(
            self.res, "res_etit_fibra_hfc",
            [("HFC_OUT", "2026-10-07", "23", 9, 6)],
            month="2026-10",
        )
        module = "src.ui.admin.external_analysts"
        chosen = {}
        def choose(label, options, **kwargs):
            chosen[kwargs["key"]] = list(options)
            return options[0]

        with (
            patch(f"{module}.st.markdown"),
            patch(f"{module}.st.caption"),
            patch(f"{module}.st.warning") as warning,
            patch(f"{module}.st.info"),
            patch(f"{module}.st.tabs", side_effect=lambda labels: [
                nullcontext() for _ in labels
            ]),
            patch(f"{module}.st.selectbox", side_effect=choose),
            patch(f"{module}.st.columns", side_effect=lambda count: [
                type("Col", (), {"metric": lambda *args, **kw: None})()
                for _ in range(count)
            ]),
            patch(f"{module}.st.dataframe"),
            patch(f"{module}.st.download_button"),
            patch(f"{module}.st.expander", return_value=nullcontext()),
        ):
            render_external_monthly_by_indicator(
                self.admin, self.service, self.res.id,
                {
                    "res_etit_fibra_hfc": "ETIT HFC",
                    "res_etit_gpon": "ETIT GPON",
                },
                widget_prefix="test_separated_periods",
                title="Analistas externos",
            )
        self.assertEqual(
            ["2026-10"],
            chosen["test_separated_periods_month_res_etit_fibra_hfc_v5"],
        )
        self.assertEqual(
            ["2026-09"],
            chosen["test_separated_periods_month_res_etit_gpon_v5"],
        )
        self.assertFalse(warning.called)

    def test_enterprise_source_appends_external_section_after_own_dashboard(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        import pandas as pd
        from src.ui.shared.management_indicators import _render_source

        scope = pd.DataFrame([{
            "segment_slug": "empresarial",
            "segment_id": self.emp.id,
            "indicator_key": "emp_etit_event",
        }])
        order = []
        with (
            patch("src.ui.shared.management_indicators.st.markdown"),
            patch("src.ui.shared.management_indicators.st.divider"),
            patch("src.ui.shared.management_indicators._render_indicator",
                  side_effect=lambda *a, **k: order.append("own")),
            patch("src.ui.admin.external_analysts."
                  "render_external_monthly_by_indicator",
                  side_effect=lambda *a, **k: order.append("external")) as view,
        ):
            _render_source(
                source_label="ETIT Empresarial",
                indicator_keys=("emp_etit_event",),
                ctx=SimpleNamespace(is_admin=True),
                dashboard=self.service,
                segment_df=scope,
                analyst_df=pd.DataFrame(),
                analyst_metrics_df=pd.DataFrame(),
                analyst_breakdowns_df=pd.DataFrame(),
                daily_df=pd.DataFrame(),
                breakdown_df=pd.DataFrame(),
                external_df=pd.DataFrame(),
                freshness_index={},
            )
        self.assertEqual(["own", "external"], order)
        self.assertEqual(self.emp.id, view.call_args.args[2])
        self.assertEqual(
            ["emp_etit_event"], list(view.call_args.args[3])
        )

    def test_names_come_from_legacy_portal_without_guessing_unknown_logins(self):
        self.assertEqual(
            "TIAGO ALMEIDA TIBURCIO DE SOUZA",
            _external_name("N5963881", "N5963881"),
        )
        self.assertEqual(
            "JOAO GABRIEL DE ALMEIDA FERREIRA",
            _external_name("F282772", "F282772"),
        )
        self.assertEqual(
            "JEFFERSON LUIS GONÇALVES COITINHO",
            _external_name("N6105010", "N6105010"),
        )
        self.assertEqual(
            "Nome não localizado no portal antigo",
            _external_name("F282187", "F282187"),
        )
        self.assertEqual(
            "NOME INFORMADO NA ORIGEM",
            _external_name("F282187", "NOME INFORMADO NA ORIGEM"),
        )

    def test_adherent_and_nonadherent_monthly_columns_are_volume_weighted(self):
        rows = [
            {
                "login": "N5963881", "analyst_name": "N5963881",
                "month": "2026-10", "segment_name": "Empresarial",
                "indicator_key": "emp_etit_event",
                "name": "ETIT Empresarial",
                "volume": 1, "successes": 0, "losses": 1,
                "day": "2026-10-02",
            },
            {
                "login": "N5963881", "analyst_name": "N5963881",
                "month": "2026-10", "segment_name": "Empresarial",
                "indicator_key": "emp_etit_event",
                "name": "ETIT Empresarial",
                "volume": 9, "successes": 9, "losses": 0,
                "day": "2026-10-05",
            },
            {
                "login": "F282187", "analyst_name": "F282187",
                "month": "2026-10", "segment_name": "Empresarial",
                "indicator_key": "emp_etit_event",
                "name": "ETIT Empresarial",
                "volume": 2, "successes": 1, "losses": 1,
                "day": "2026-10-06",
            },
        ]
        table = _monthly_external_adherence_table(_as_frame(rows))
        self.assertEqual(2, len(table))
        tiago = table[table["Login"] == "N5963881"].iloc[0]
        self.assertEqual(
            "TIAGO ALMEIDA TIBURCIO DE SOUZA", tiago["Nome"]
        )
        self.assertEqual(10, tiago["Volume no mês"])
        self.assertEqual(9, tiago["Aderentes"])
        self.assertEqual(1, tiago["Não aderentes"])
        self.assertEqual("90,0%", tiago["% aderente"])
        self.assertEqual("10,0%", tiago["% não aderente"])
        unknown = table[table["Login"] == "F282187"].iloc[0]
        self.assertEqual("Nome não localizado no portal antigo", unknown["Nome"])
        self.assertEqual(
            ["Nome", "Login", "Volume no mês", "Aderentes",
             "Não aderentes", "% aderente", "% não aderente"],
            list(table.columns),
        )

    def test_simple_external_view_has_exactly_two_percent_cards_and_one_table(self):
        from contextlib import nullcontext
        from unittest.mock import patch
        from src.ui.admin.external_analysts import (
            render_external_monthly_by_indicator,
        )

        self.add_rows(
            self.emp, "emp_etit_event",
            [("N5963881", "2026-10-06", "22", 4, 3)],
        )
        prefix = "src.ui.admin.external_analysts"
        metrics = []
        tables = []
        with (
            patch(f"{prefix}.st.markdown"),
            patch(f"{prefix}.st.caption"),
            patch(f"{prefix}.st.warning"),
            patch(f"{prefix}.st.info"),
            patch(f"{prefix}.st.selectbox", return_value="2026-10"),
            patch(f"{prefix}.st.tabs", return_value=[nullcontext()]),
            patch(f"{prefix}.st.columns",
                  side_effect=lambda n: [
                      type("Col", (), {
                          "metric": lambda self, label, value:
                              metrics.append((label, value))
                      })() for _ in range(n)
                  ]),
            patch(f"{prefix}.st.dataframe",
                  side_effect=lambda data, **kwargs: tables.append(data)),
            patch(f"{prefix}.st.download_button"),
            patch(f"{prefix}.st.expander", return_value=nullcontext()),
        ):
            render_external_monthly_by_indicator(
                self.admin, self.service, self.emp.id,
                {"emp_etit_event": "ETIT Empresarial"},
                widget_prefix="test_minimal", title="Outros analistas",
            )
        self.assertEqual([
            ("% aderente — mês", "75,0%"),
            ("% não aderente — mês", "25,0%"),
        ], metrics)
        # Monthly table and optional daily detail, but NO coverage table.
        self.assertEqual(2, len(tables))
        self.assertEqual(1, len(tables[0]))
        self.assertEqual("N5963881", tables[0].iloc[0]["Login"])

    def test_only_integer_hour_labels_can_prove_night_window(self):
        self.assertEqual(8, len(NIGHT_HOURS))
        for raw in ("22", "23", "0", "05"):
            self.assertIn(_hour_from_label(raw), NIGHT_HOURS)
        for raw in ("Madrugada", "Sem horário", "22:59", "24", "-1", None):
            self.assertIsNone(_hour_from_label(raw))


if __name__ == "__main__":
    unittest.main()
