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

    def test_only_same_sector_other_leader_same_month_is_returned(self):
        # Leandro: próprio valor não pode contaminar a média.
        self._insert_result("N6088107", self.emp, "dpa_official",
                            "2026-09", "2026-09-03", 45, 100)
        # Bruno: consolidação ponderada de seu mês = (70*10 + 100*90) / 100 = 97.
        self._insert_result("N5619600", self.emp, "dpa_official",
                            "2026-09", "2026-09-04", 70, 10)
        self._insert_result("N5619600", self.emp, "dpa_official",
                            "2026-09", "2026-09-05", 100, 90)
        self._insert_result("N5619600", self.emp, "dpa_official",
                            "2026-08", "2026-08-03", 10, 30)
        # Líder do Residencial não entra na média Empresarial.
        self._insert_result("N5923221", self.res, "dpa_official",
                            "2026-09", "2026-09-03", 20, 100)

        ctx = self.access.context(self.users.get_by_login("N6088107").id)
        rows = self.dashboard.leader_peer_averages(ctx, self.emp.id)
        values = {(row["period"], row["indicator_key"]): row for row in rows}
        self.assertEqual(97.0, values[("2026-09", "dpa_official")]["peer_avg"])
        self.assertEqual(1, values[("2026-09", "dpa_official")]["peer_count"])
        self.assertEqual(10.0, values[("2026-08", "dpa_official")]["peer_avg"])
        self.assertNotIn("login", values[("2026-09", "dpa_official")])
        self.assertNotIn("user_id", values[("2026-09", "dpa_official")])
        self.assertEqual(
            "52,0 pp pior",
            _comparison_label(45, 97, "higher_is_better", "percent"),
        )

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
