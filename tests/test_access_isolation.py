import os
import tempfile
import unittest


class AccessIsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = os.path.join(self.tmp.name, "portal.db")
        from src.infrastructure import database
        database.DB_PATH = __import__("pathlib").Path(os.environ["COP_PORTAL_DB"])
        from src.infrastructure.database import initialize_database
        from src.config.seed import seed_foundation
        initialize_database()
        seed_foundation()

    def tearDown(self):
        self.tmp.cleanup()

    def test_analyst_only_sees_self_and_cannot_view_peer(self):
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        users = UserRepository()
        daniel = users.get_by_login("N5604148")
        rosana = users.get_by_login("N5941223")
        segment = SegmentRepository().get_by_slug("preventiva")
        ctx = AccessService(users).context(daniel.id)
        visible = AccessService(users).visible_users(ctx, segment.id)
        self.assertEqual([daniel.id], [u.id for u in visible])
        with self.assertRaises(PermissionError):
            AccessService(users).assert_can_view_user(ctx, segment.id, rosana.id)

    def test_admin_sees_preventiva_team(self):
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        users = UserRepository()
        admin = users.get_by_login("ADMIN")
        segment = SegmentRepository().get_by_slug("preventiva")
        ctx = AccessService(users).context(admin.id)
        visible = AccessService(users).visible_users(ctx, segment.id)
        analyst_logins = {u.login for u in visible}
        self.assertEqual(
            {"N5604148", "N5941223", "N0158974", "N5577565"},
            analyst_logins,
        )


if __name__ == "__main__":
    unittest.main()
