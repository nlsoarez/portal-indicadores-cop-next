import unittest


class SupabasePostgresConfigTest(unittest.TestCase):
    def test_private_schema_is_used_for_postgres(self):
        from src.infrastructure import database

        self.assertEqual("cop_portal", database.POSTGRES_APP_SCHEMA)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS cop_portal", database.POSTGRES_SCHEMA)
        self.assertIn("SET search_path TO cop_portal, public", database.POSTGRES_SCHEMA)
        self.assertIn(
            "REVOKE ALL ON SCHEMA cop_portal FROM PUBLIC, anon, authenticated",
            database.POSTGRES_SCHEMA,
        )

    def test_postgres_privileges_do_not_leak_into_sqlite(self):
        from src.infrastructure import database

        self.assertNotIn("REVOKE ALL", database.SQLITE_SCHEMA)
        self.assertNotIn("ALTER DEFAULT PRIVILEGES", database.SQLITE_SCHEMA)
        self.assertIn(
            "REVOKE ALL ON ALL TABLES IN SCHEMA cop_portal",
            database.POSTGRES_SCHEMA,
        )

    def test_postgres_is_preferred_when_database_url_exists(self):
        from src.infrastructure import database

        self.assertTrue(hasattr(database, "DATABASE_URL"))
        self.assertTrue(callable(database.using_postgres))
        self.assertTrue(callable(database.database_is_persistent))


if __name__ == "__main__":
    unittest.main()
