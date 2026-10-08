import os
import tempfile
import unittest
from pathlib import Path


class AccessIsolationTest(unittest.TestCase):
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

    def test_analyst_only_sees_self_and_cannot_view_peer(self):
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); access = AccessService(users)
        daniel = users.get_by_login("N5604148"); rosana = users.get_by_login("N5941223")
        segment = SegmentRepository().get_by_slug("preventiva")
        ctx = access.context(daniel.id)
        self.assertEqual([daniel.id], [u.id for u in access.visible_users(ctx, segment.id)])
        with self.assertRaises(PermissionError):
            access.assert_can_view_user(ctx, segment.id, rosana.id)

    def test_admin_can_access_all_active_segments(self):
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); admin = users.get_by_login("ADMIN")
        self.assertEqual(
            {"preventiva", "residencial", "empresarial"},
            {s.slug for s in SegmentRepository().list_for_user(admin.id)},
        )

    def test_admin_sees_only_common_analysts_in_team_list(self):
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); access = AccessService(users)
        admin = users.get_by_login("ADMIN"); segment = SegmentRepository().get_by_slug("preventiva")
        visible = access.visible_users(access.context(admin.id), segment.id)
        self.assertEqual(
            {"N5604148", "N5941223", "N0158974", "N5577565"},
            {u.login for u in visible},
        )

    def test_subadmin_can_view_self_and_own_analysts_but_not_other_leader(self):
        from src.application.access_service import AccessService
        from src.application.dashboard_service import DashboardService
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); access = AccessService(users)
        leader = users.get_by_login("N0238475"); other = users.get_by_login("N5923221")
        analyst = users.get_by_login("N5772086")
        segment = SegmentRepository().get_by_slug("residencial")
        ctx = access.context(leader.id)
        access.assert_can_view_user(ctx, segment.id, leader.id)
        access.assert_can_view_user(ctx, segment.id, analyst.id)
        with self.assertRaises(PermissionError):
            access.assert_can_view_user(ctx, segment.id, other.id)
        # The personal leader payload uses the same access control path.
        payload = DashboardService(access=access).analyst_payload(ctx, segment.id, leader.id)
        self.assertIn("summary", payload)

    def test_leader_cannot_fetch_other_segment_even_with_legacy_access(self):
        from src.application.access_service import AccessService
        from src.application.dashboard_service import DashboardService
        from src.infrastructure.database import transaction
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users = UserRepository(); access = AccessService(users)
        leader = users.get_by_login("N5619600")
        foreign = SegmentRepository().get_by_slug("residencial")
        foreign_analyst = users.get_by_login("N5772086")
        # Simulates pre-migration DB grants; the runtime guard must still work.
        with transaction() as conn:
            conn.execute(
                "INSERT INTO user_segments(user_id, segment_id) VALUES (?, ?) "
                "ON CONFLICT(user_id, segment_id) DO NOTHING",
                (leader.id, foreign.id),
            )
        ctx = access.context(leader.id)
        self.assertIn(foreign.id, ctx.segment_ids)
        with self.assertRaises(PermissionError):
            access.visible_users(ctx, foreign.id)
        with self.assertRaises(PermissionError):
            access.assert_can_view_user(ctx, foreign.id, foreign_analyst.id)
        dashboard = DashboardService(access=access)
        with self.assertRaises(PermissionError):
            dashboard.management_payload(ctx, [foreign.id])
        with self.assertRaises(PermissionError):
            dashboard.analyst_payload(ctx, foreign.id, foreign_analyst.id)

    def test_only_admin_can_list_leaders(self):
        from src.application.access_service import AccessService
        from src.infrastructure.repositories import UserRepository
        users = UserRepository(); access = AccessService(users)
        admin = users.get_by_login("ADMIN"); leader = users.get_by_login("N0238475")
        self.assertEqual(4, len(access.visible_subadmins(access.context(admin.id))))
        with self.assertRaises(PermissionError):
            access.visible_subadmins(access.context(leader.id))


if __name__ == "__main__":
    unittest.main()
