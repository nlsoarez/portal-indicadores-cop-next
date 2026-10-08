import os
import tempfile
import unittest
from pathlib import Path


from tests.isolated_database import isolate_sqlite_database

class AdminPasswordResetTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        from src.config.seed import seed_foundation
        seed_foundation()


    def test_admin_can_reset_password_and_force_change_on_next_login(self):
        from src.application.access_service import AccessService
        from src.application.auth_service import AuthService
        from src.infrastructure.repositories import UserRepository

        users = UserRepository()
        access = AccessService(users)
        auth = AuthService(users=users)

        admin = users.get_by_login("ADMIN")
        target = users.get_by_login("N5737414")
        ctx = access.context(admin.id)

        auth.reset_password_as_admin(ctx, target.id, "TempPass123")

        result = auth.authenticate(target.login, "TempPass123")
        self.assertIsNotNone(result)
        self.assertTrue(result.must_change_password)

    def test_non_admin_cannot_reset_another_user_password(self):
        from src.application.access_service import AccessService
        from src.application.auth_service import AuthService
        from src.infrastructure.repositories import UserRepository

        users = UserRepository()
        access = AccessService(users)
        auth = AuthService(users=users)

        actor = users.get_by_login("N5737414")
        target = users.get_by_login("N5802257")
        ctx = access.context(actor.id)

        with self.assertRaises(PermissionError):
            auth.reset_password_as_admin(ctx, target.id, "TempPass123")

    def test_manageable_accounts_exclude_admin_and_retired_user(self):
        from src.infrastructure.repositories import UserRepository

        accounts = UserRepository().list_manageable_accounts()
        logins = {row["login"] for row in accounts}

        self.assertNotIn("ADMIN", logins)
        self.assertNotIn("F218860", logins)
        self.assertIn("N5737414", logins)
        self.assertIn("N0238475", logins)


if __name__ == "__main__":
    unittest.main()
