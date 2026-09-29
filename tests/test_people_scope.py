import os
import tempfile
import unittest
from pathlib import Path


class PeopleScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = str(Path(self.tmp.name) / "portal.db")

        from src.infrastructure import database

        database.DB_PATH = Path(os.environ["COP_PORTAL_DB"])
        from src.infrastructure.database import initialize_database
        from src.config.seed import seed_foundation

        initialize_database()
        seed_foundation()

    def tearDown(self):
        self.tmp.cleanup()

    def test_maristella_only_preventiva_and_marcelo_residential(self):
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        users = UserRepository()
        preventiva = SegmentRepository().get_by_slug("preventiva")
        residencial = SegmentRepository().get_by_slug("residencial")

        preventiva_logins = {user.login for user in users.list_for_segment(preventiva.id)}
        residencial_logins = {user.login for user in users.list_for_segment(residencial.id)}

        self.assertIn("N5577565", preventiva_logins)
        self.assertNotIn("N5577565", residencial_logins)
        self.assertIn("F104752", residencial_logins)

        marcelo = users.get_by_login("F104752")
        self.assertEqual("Marcelo", marcelo.display_name)
        self.assertEqual("MARCELO DE SOUZA ALMEIDA", marcelo.full_name)

    def test_leaders_do_not_appear_as_common_users(self):
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        users = UserRepository()
        preventiva = SegmentRepository().get_by_slug("preventiva")

        analyst_logins = {user.login for user in users.list_for_segment(preventiva.id)}
        leader_logins = {user.login for user in users.list_subadmins_for_segment(preventiva.id)}

        self.assertTrue({"N5619600", "N6088107", "N5923221", "N0238475"}.isdisjoint(analyst_logins))
        self.assertEqual(
            {"N5619600", "N6088107", "N5923221", "N0238475"},
            leader_logins,
        )

    def test_leaders_are_subadmins_and_access_all_active_segments(self):
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        users = UserRepository()
        access = AccessService(users)
        expected_segments = {"preventiva", "residencial", "empresarial"}

        for login in ("N5619600", "N6088107", "N5923221", "N0238475"):
            leader = users.get_by_login(login)
            self.assertIsNotNone(leader)

            ctx = access.context(leader.id)
            self.assertFalse(ctx.is_admin)
            self.assertTrue(ctx.is_subadmin)
            self.assertFalse(ctx.is_analyst)

            segments = SegmentRepository().list_for_user(leader.id)
            self.assertEqual(expected_segments, {segment.slug for segment in segments})


if __name__ == "__main__":
    unittest.main()
