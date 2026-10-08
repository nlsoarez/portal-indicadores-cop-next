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
        initialize_database(); seed_foundation()

    def tearDown(self):
        self.tmp.cleanup()

    def test_maristella_only_preventiva_and_marcelo_residential(self):
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); segments = SegmentRepository()
        preventiva = segments.get_by_slug("preventiva"); residencial = segments.get_by_slug("residencial")
        self.assertIn("N5577565", {u.login for u in users.list_for_segment(preventiva.id)})
        self.assertNotIn("N5577565", {u.login for u in users.list_for_segment(residencial.id)})
        self.assertIn("F104752", {u.login for u in users.list_for_segment(residencial.id)})

    def test_residential_and_enterprise_rosters_are_migrated(self):
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); segments = SegmentRepository()
        residential = {u.login for u in users.list_for_segment(segments.get_by_slug("residencial").id)}
        enterprise = {u.login for u in users.list_for_segment(segments.get_by_slug("empresarial").id)}
        self.assertEqual(
            {"N5772086", "N0239871", "N5972428", "N4014011", "F106664", "F104752"},
            residential,
        )
        self.assertEqual(
            {"N0189105", "N5737414", "N5713690", "N5802257", "F201714", "N6173055", "N0125317", "N5819183", "N5926003", "N5932064"},
            enterprise,
        )

    def test_leaders_are_subadmins_not_common_users(self):
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); access = AccessService(users); segments = SegmentRepository()
        expected = {"N5619600", "N6088107", "N5923221", "N0238475"}
        self.assertEqual(expected, {u.login for u in users.list_subadmins()})
        for segment_slug in ("preventiva", "residencial", "empresarial"):
            analyst_logins = {u.login for u in users.list_for_segment(segments.get_by_slug(segment_slug).id)}
            self.assertTrue(expected.isdisjoint(analyst_logins))
        for login in expected:
            ctx = access.context(users.get_by_login(login).id)
            self.assertTrue(ctx.is_subadmin); self.assertFalse(ctx.is_admin); self.assertFalse(ctx.is_analyst)
            expected_segment = {
                "N5619600": "empresarial",
                "N6088107": "empresarial",
                "N5923221": "residencial",
                "N0238475": "residencial",
            }[login]
            self.assertEqual(
                {expected_segment},
                {s.slug for s in segments.list_for_user(ctx.user.id)},
            )

    def test_leader_performance_segments_are_not_duplicated(self):
        from src.infrastructure.repositories import UserRepository
        users = UserRepository()
        expected = {
            "N5619600": "empresarial",
            "N6088107": "empresarial",
            "N5923221": "residencial",
            "N0238475": "residencial",
        }
        for login, slug in expected.items():
            segments = users.performance_segments_for_user(users.get_by_login(login).id)
            self.assertEqual([slug], [segment.slug for segment in segments])


if __name__ == "__main__":
    unittest.main()
