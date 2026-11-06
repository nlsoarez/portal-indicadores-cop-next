import io
import os
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


class SecurityHardeningTest(unittest.TestCase):
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

    def test_seeded_account_does_not_accept_legacy_shared_password(self):
        from src.application.auth_service import AuthService

        self.assertIsNone(AuthService().authenticate("N5737414", "claro123"))

    def test_password_reset_revokes_previous_session_version(self):
        from src.application.access_service import AccessService
        from src.application.auth_service import AuthService
        from src.infrastructure.repositories import UserRepository

        users = UserRepository()
        auth = AuthService(users=users)
        admin = users.get_by_login("ADMIN")
        target = users.get_by_login("N5737414")
        ctx = AccessService(users).context(admin.id)

        auth.reset_password_as_admin(ctx, target.id, "Temporary123")
        signed_in = auth.authenticate(target.login, "Temporary123")
        self.assertIsNotNone(signed_in)
        self.assertTrue(auth.session_is_valid(target.id, signed_in.auth_version))

        auth.reset_password_as_admin(ctx, target.id, "Temporary456")
        self.assertFalse(auth.session_is_valid(target.id, signed_in.auth_version))

    def test_failed_logins_create_shared_throttle_state(self):
        from src.application.auth_service import AuthService, LOGIN_FAILURE_THRESHOLD

        auth = AuthService()
        for _ in range(LOGIN_FAILURE_THRESHOLD):
            self.assertIsNone(auth.authenticate("N5737414", "wrong-password"))

        state = auth.throttle.get("N5737414")
        self.assertIsNotNone(state)
        self.assertGreaterEqual(int(state["failure_count"]), LOGIN_FAILURE_THRESHOLD)
        self.assertTrue(state["blocked_until"])

    def test_unknown_login_does_not_create_throttle_rows(self):
        from src.application.auth_service import AuthService

        auth = AuthService()
        self.assertIsNone(auth.authenticate("DOES-NOT-EXIST", "wrong-password"))
        self.assertIsNone(auth.throttle.get("DOES-NOT-EXIST"))

    def test_successful_login_clears_throttle_state(self):
        from src.application.access_service import AccessService
        from src.application.auth_service import AuthService
        from src.infrastructure.repositories import UserRepository

        users = UserRepository()
        auth = AuthService(users=users)
        admin = users.get_by_login("ADMIN")
        target = users.get_by_login("N5737414")
        ctx = AccessService(users).context(admin.id)

        auth.reset_password_as_admin(ctx, target.id, "Temporary123")
        self.assertIsNone(auth.authenticate(target.login, "wrong-password"))
        self.assertIsNotNone(auth.throttle.get(target.login))

        self.assertIsNotNone(auth.authenticate(target.login, "Temporary123"))
        self.assertIsNone(auth.throttle.get(target.login))

    def test_suspicious_zip_expansion_is_rejected(self):
        from src.features.ingestion.archive_safety import validate_workbook_bytes
        from src.features.ingestion.excel import ImportValidationError

        payload = io.BytesIO()
        with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("xl/sharedStrings.xml", b"A" * (2 * 1024 * 1024))

        with self.assertRaises(ImportValidationError):
            validate_workbook_bytes(payload.getvalue())

    def test_graph_client_rejects_foreign_absolute_url(self):
        from src.integrations.m365_etit import GraphClient, GraphRequestError

        with self.assertRaises(GraphRequestError):
            GraphClient("not-a-real-token")._resolve_graph_url(
                "https://example.invalid/steal"
            )


if __name__ == "__main__":
    unittest.main()
