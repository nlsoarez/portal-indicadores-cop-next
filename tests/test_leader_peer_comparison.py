import os
import tempfile
import unittest
from pathlib import Path

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.config.seed import seed_foundation
from src.infrastructure import database
from src.infrastructure.database import initialize_database, transaction
from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository
from src.ui.analyst.shell import _comparison_label


class LeaderPeerComparisonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = str(Path(self.tmp.name) / "portal.db")
        database.DB_PATH = Path(os.environ["COP_PORTAL_DB"])
        initialize_database()
        seed_foundation()
        self.users = UserRepository()
        self.segments = SegmentRepository()
        self.access = AccessService(self.users)
        self.dashboard = DashboardService(access=self.access)
        self.emp = self.segments.get_by_slug("empresarial")
        self.res = self.segments.get_by_slug("residencial")

    def tearDown(self):
        self.tmp.cleanup()

    def _insert_result(self, login, segment, key, month, day, value, volume):
        user = self.users.get_by_login(login)
        with transaction() as conn:
            definition = conn.execute(
                "SELECT id FROM indicator_definitions "
                "WHERE segment_id=? AND indicator_key=?",
                (segment.id, key),
            ).fetchone()
            self.assertIsNotNone(definition)
            conn.execute(
                "INSERT INTO indicator_results("
                "segment_id,user_id,indicator_definition_id,period,data_month,value,volume"
                ") VALUES (?,?,?,?,?,?,?)",
                (segment.id, user.id, int(definition["id"]), day, month, value, volume),
            )

    def test_non_etit_compares_three_other_leaders_across_segments_and_months(self):
        # O próprio resultado do Leandro nunca entra na referência.
        self._insert_result("N6088107", self.emp, "dpa_official",
                            "2026-09", "2026-09-03", 45, 100)
        # Bruno: utiliza a sua ÚLTIMA competência (setembro),
        # consolidando os dois lançamentos por volume: 97.
        self._insert_result("N5619600", self.emp, "dpa_official",
                            "2026-09", "2026-09-04", 70, 10)
        self._insert_result("N5619600", self.emp, "dpa_official",
                            "2026-09", "2026-09-05", 100, 90)
        self._insert_result("N5619600", self.emp, "dpa_official",
                            "2026-08", "2026-08-03", 10, 30)
        # Kelly (outro segmento): setembro, 20.
        self._insert_result("N5923221", self.res, "dpa_official",
                            "2026-09", "2026-09-03", 20, 100)
        # Marley (outro segmento): último dado em agosto, 75.
        self._insert_result("N0238475", self.res, "dpa_official",
                            "2026-08", "2026-08-03", 75, 100)

        ctx = self.access.context(self.users.get_by_login("N6088107").id)
        rows = self.dashboard.leader_peer_averages(ctx, self.emp.id)
        by_key = {row["indicator_key"]: row for row in rows}
        benchmark = by_key["dpa_official"]
        self.assertAlmostEqual(64.0, benchmark["peer_avg"])
        self.assertEqual(3, benchmark["peer_count"])
        self.assertEqual("2026-08", benchmark["oldest_period"])
        self.assertEqual("2026-09", benchmark["newest_period"])
        self.assertNotIn("login", benchmark)
        self.assertNotIn("user_id", benchmark)
        self.assertNotIn("period", benchmark)
        self.assertEqual(
            "19,0 pp pior",
            _comparison_label(45, 64, "higher_is_better", "percent"),
        )

    def test_etit_only_compares_leaders_from_same_segment(self):
        self._insert_result("N6088107", self.emp, "emp_etit_event",
                            "2026-09", "2026-09-02", 75, 100)
        self._insert_result("N5619600", self.emp, "emp_etit_event",
                            "2026-08", "2026-08-02", 90, 100)

        # Proteção contra futuras duplicações de chaves ETIT entre setores:
        # mesmo que o indicador exista em outro setor, deve ser ignorado.
        with transaction() as conn:
            conn.execute(
                "INSERT INTO indicator_definitions("
                "segment_id,indicator_key,name,target_value,direction,unit,active"
                ") VALUES (?,?,?,?,?,?,1)",
                (self.res.id, "emp_etit_event", "ETIT espelho",
                 90.0, "higher_is_better", "percent"),
            )
        self._insert_result("N5923221", self.res, "emp_etit_event",
                            "2026-10", "2026-10-02", 10, 100)

        ctx = self.access.context(self.users.get_by_login("N6088107").id)
        rows = self.dashboard.leader_peer_averages(ctx, self.emp.id)
        benchmark = next(row for row in rows
                         if row["indicator_key"] == "emp_etit_event")
        self.assertEqual(1, benchmark["peer_count"])
        self.assertEqual(90.0, benchmark["peer_avg"])
        self.assertEqual("2026-08", benchmark["newest_period"])

        # ETIT HFC e GPON seguem a mesma restrição no Residencial.
        self._insert_result("N5923221", self.res, "res_etit_fibra_hfc",
                            "2026-09", "2026-09-02", 91, 100)
        self._insert_result("N0238475", self.res, "res_etit_fibra_hfc",
                            "2026-08", "2026-08-02", 85, 100)
        kelly_ctx = self.access.context(self.users.get_by_login("N5923221").id)
        residential = self.dashboard.leader_peer_averages(
            kelly_ctx, self.res.id
        )
        hfc = next(row for row in residential
                   if row["indicator_key"] == "res_etit_fibra_hfc")
        self.assertEqual(85.0, hfc["peer_avg"])
        self.assertEqual(1, hfc["peer_count"])

    def test_lower_is_better_and_no_data_do_not_invent_benchmark(self):
        self.assertEqual(
            "5,0 pp melhor",
            _comparison_label(10, 15, "lower_is_better", "percent"),
        )
        self.assertEqual(
            "—",
            _comparison_label(10, None, "lower_is_better", "percent"),
        )
        leandro = self.users.get_by_login("N6088107")
        rows = self.dashboard.leader_peer_averages(
            self.access.context(leandro.id), self.emp.id
        )
        self.assertEqual([], rows)

    def test_average_weighted_within_each_peer_but_equal_across_peers(self):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO users(login,full_name,display_name,password_hash,password_salt) "
                "VALUES ('TESTLEADER','Líder extra','Extra','x','x')"
            )
            user = conn.execute(
                "SELECT id FROM users WHERE login='TESTLEADER'"
            ).fetchone()
            role = conn.execute(
                "SELECT id FROM roles WHERE code='subadmin'"
            ).fetchone()
            conn.execute(
                "INSERT INTO user_roles(user_id,role_id) VALUES (?,?)",
                (int(user["id"]),int(role["id"])),
            )
            conn.execute(
                "INSERT INTO user_performance_segments(user_id,segment_id) VALUES (?,?)",
                (int(user["id"]),self.emp.id),
            )
        self._insert_result("N5619600", self.emp, "dpa_official",
                            "2026-09", "2026-09-04", 80, 1)
        self._insert_result("TESTLEADER", self.emp, "dpa_official",
                            "2026-09", "2026-09-04", 100, 999)
        ctx=self.access.context(self.users.get_by_login("N6088107").id)
        rows=self.dashboard.leader_peer_averages(ctx, self.emp.id)
        match=next(x for x in rows if x["indicator_key"]=="dpa_official")
        self.assertEqual(90.0, match["peer_avg"])
        self.assertEqual(2, match["peer_count"])

    def test_authorization_denies_analyst_and_other_sector(self):
        analyst = self.users.get_by_login("N0189105")
        with self.assertRaises(PermissionError):
            self.dashboard.leader_peer_averages(
                self.access.context(analyst.id), self.emp.id
            )
        leader = self.users.get_by_login("N6088107")
        with self.assertRaises(PermissionError):
            self.dashboard.leader_peer_averages(
                self.access.context(leader.id), self.res.id
            )


if __name__ == "__main__":
    unittest.main()
