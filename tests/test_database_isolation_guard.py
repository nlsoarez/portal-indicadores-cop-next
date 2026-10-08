"""Regression coverage for accidental production DB access during unit tests."""
import unittest

from src.infrastructure import database
from tests.isolated_database import isolate_sqlite_database


class DatabaseIsolationGuardTest(unittest.TestCase):
    def test_isolation_overrides_existing_postgres_configuration(self):
        class InnerTestCase:
            def __init__(self):
                self.cleanups = []

            def addCleanup(self, callback):
                self.cleanups.append(callback)

        case = InnerTestCase()
        original = database.DATABASE_URL
        database.DATABASE_URL = "postgresql://invalid-unreachable/unit-test-must-not-connect"
        try:
            isolate_sqlite_database(case)
            self.assertEqual("sqlite", database.database_backend())
            with database.connection() as conn:
                self.assertEqual("sqlite", conn.backend)
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
                ).fetchone()
                self.assertEqual("users", row["name"])
        finally:
            for callback in reversed(case.cleanups):
                callback()
            database.DATABASE_URL = original

    def test_test_case_restores_original_database_configuration(self):
        class InnerTestCase:
            def __init__(self):
                self.cleanups = []

            def addCleanup(self, callback):
                self.cleanups.append(callback)

        original_path = database.DB_PATH
        original_url = database.DATABASE_URL
        case = InnerTestCase()
        try:
            isolate_sqlite_database(case)
            self.assertNotEqual(original_path, database.DB_PATH)
        finally:
            for callback in reversed(case.cleanups):
                callback()
        self.assertEqual(original_path, database.DB_PATH)
        self.assertEqual(original_url, database.DATABASE_URL)


if __name__ == "__main__":
    unittest.main()
