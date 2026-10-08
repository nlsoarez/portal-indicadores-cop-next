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

    def test_only_integer_hour_labels_can_prove_night_window(self):
        self.assertEqual(8, len(NIGHT_HOURS))
        for raw in ("22", "23", "0", "05"):
            self.assertIn(_hour_from_label(raw), NIGHT_HOURS)
        for raw in ("Madrugada", "Sem horário", "22:59", "24", "-1", None):
            self.assertIsNone(_hour_from_label(raw))


if __name__ == "__main__":
    unittest.main()
