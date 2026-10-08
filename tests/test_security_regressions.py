import shutil
import tempfile
import unittest
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from src.infrastructure import database
from src.infrastructure.database import initialize_database, transaction
from src.infrastructure.repositories import UserRepository
from src.application.access_service import AccessService
from src.application.auth_service import AuthService
from src.config.seed import seed_foundation, _ensure_user
from src.application.security import hash_password


class SecurityRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.base.name) / 'fixture.db'
        database.DB_PATH = cls.fixture
        initialize_database()
        seed_foundation()

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.tmp.name) / 'test.db'
        shutil.copyfile(self.fixture, database.DB_PATH)
        self.users = UserRepository()
        self.auth = AuthService(users=self.users)
        self.admin = self.users.get_by_login('ADMIN')
        self.actor = self.users.get_by_login('N5737414')
        self.ctx = AccessService(self.users).context(self.admin.id)

    def tearDown(self):
        self.tmp.cleanup()

    def login(self):
        self.auth.reset_password_as_admin(self.ctx, self.actor.id, 'IndividualPassword123!')
        return self.auth.authenticate(self.actor.login, 'IndividualPassword123!')

    def test_reset_revokes_two_existing_sessions(self):
        first = self.login()
        second = self.auth.authenticate(self.actor.login, 'IndividualPassword123!')
        self.auth.reset_password_as_admin(self.ctx, self.actor.id, 'NewIndividualPassword123!')
        for session in (first, second):
            with self.assertRaises(PermissionError):
                self.auth.validate_session(session.user_id, session.credential_version)
        current = self.auth.authenticate(self.actor.login, 'NewIndividualPassword123!')
        self.assertTrue(self.auth.validate_session(current.user_id, current.credential_version))

    def test_password_change_revokes_session(self):
        session = self.login()
        self.auth.change_password(self.actor.id, 'UpdatedIndividualPassword123!')
        with self.assertRaises(PermissionError):
            self.auth.validate_session(session.user_id, session.credential_version)

    def test_disabled_account_and_legacy_session_denied(self):
        session = self.login()
        with self.assertRaises(PermissionError):
            self.auth.validate_session(session.user_id, '')
        with transaction() as conn:
            conn.execute('UPDATE users SET active=0 WHERE id=?', (self.actor.id,))
        with self.assertRaises(PermissionError):
            self.auth.validate_session(session.user_id, session.credential_version)

    def test_seed_preserves_disabled_account_and_access_decisions(self):
        with transaction() as conn:
            conn.execute('UPDATE users SET active=0 WHERE id=?', (self.actor.id,))
            conn.execute('DELETE FROM user_segments WHERE user_id=?', (self.actor.id,))
            conn.execute('DELETE FROM user_roles WHERE user_id=?', (self.actor.id,))
        seed_foundation()
        self.assertFalse(self.users.get_by_id(self.actor.id).active)
        self.assertFalse(self.users.segment_ids_for_user(self.actor.id))
        self.assertFalse(self.users.roles_for_user(self.actor.id))

    def test_seed_uses_independent_unknown_credentials(self):
        with patch('src.config.seed.hash_password', wraps=hash_password) as hash_call:
            with transaction() as conn:
                _ensure_user(conn, 'NEW_A', 'A', 'A')
                _ensure_user(conn, 'NEW_B', 'B', 'B')
            first = hash_call.call_args_list[0].args[0]
            second = hash_call.call_args_list[1].args[0]
            self.assertTrue(first != second)
            self.assertGreaterEqual(len(first), 32)

    def test_concurrent_reservations_shared_between_instances(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            allowed = list(pool.map(lambda _: UserRepository().reserve_login_attempt('concurrent', 120), range(12)))
        self.assertEqual(sum(allowed), 5)
        self.assertTrue(UserRepository().reserve_login_attempt('concurrent', 180))

    def test_normalized_login_throttled_and_recovers(self):
        with patch('src.application.auth_service.time.time', return_value=120), patch('src.application.auth_service.verify_password', return_value=False) as verify:
            for i in range(7):
                login = self.actor.login.lower() if i % 2 else ' ' + self.actor.login + ' '
                self.assertIsNone(AuthService().authenticate(login, 'wrong'))
            self.assertEqual(verify.call_count, 5)
        with patch('src.application.auth_service.time.time', return_value=180), patch('src.application.auth_service.verify_password', return_value=False) as verify:
            self.auth.authenticate(self.actor.login, 'wrong')
            verify.assert_called_once()

    def test_retired_password_cannot_login_or_be_reused(self):
        with patch('src.application.auth_service.is_retired_bootstrap_password', return_value=True):
            self.assertIsNone(self.auth.authenticate(self.actor.login, 'retired'))
            with self.assertRaises(ValueError):
                self.auth.change_password(self.actor.id, 'retired-password')
            with self.assertRaises(ValueError):
                self.auth.reset_password_as_admin(self.ctx, self.actor.id, 'retired-password')

    def test_terminal_provisioning_and_retirement(self):
        from src.application.credentials_cli import main
        session = self.login()
        with patch('sys.argv', ['credentials_cli', 'retire-password']), patch('src.application.credentials_cli.getpass', return_value='IndividualPassword123!'), patch('sys.stdout', new_callable=io.StringIO):
            main()
        with self.assertRaises(PermissionError):
            self.auth.validate_session(session.user_id, session.credential_version)
        self.assertIsNone(self.auth.authenticate(self.actor.login, 'IndividualPassword123!'))
        with patch('sys.argv', ['credentials_cli', 'set-password', self.actor.login]), patch('src.application.credentials_cli.getpass', return_value='RecoveredIndividualPassword123!'), patch('sys.stdout', new_callable=io.StringIO):
            main()
        result = self.auth.authenticate(self.actor.login, 'RecoveredIndividualPassword123!')
        self.assertIsNotNone(result)
        self.assertTrue(result.must_change_password)

    def test_streamlit_gate_denies_revoked_session_before_rendering(self):
        from src import app
        session = self.login()
        self.auth.reset_password_as_admin(self.ctx, self.actor.id, 'NewIndividualPassword123!')
        state = {'user_id': session.user_id, 'credential_version': session.credential_version}
        ui = SimpleNamespace(session_state=state, set_page_config=Mock(), rerun=Mock())
        with patch.object(app, 'st', ui), patch.object(app, '_bootstrap'), patch.object(app, 'inject_global_style'), patch.object(app, '_access_snapshot') as snapshot:
            app.run()
        self.assertFalse(state)
        snapshot.assert_not_called()
        ui.rerun.assert_called_once()


if __name__ == '__main__':
    unittest.main()
