import os
import tempfile
import unittest
from pathlib import Path


class NoScaleScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = str(Path(self.tmp.name) / "portal.db")

        from src.infrastructure import database

        database.DB_PATH = Path(os.environ["COP_PORTAL_DB"])
        from src.infrastructure.database import initialize_database

        initialize_database()

    def tearDown(self):
        self.tmp.cleanup()

    def test_database_has_no_scale_table(self):
        from src.infrastructure.database import connection

        with connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scales'"
            ).fetchone()
        self.assertIsNone(row)

    def test_ui_has_no_scale_navigation(self):
        admin_source = Path("src/ui/admin/shell.py").read_text(encoding="utf-8")
        analyst_source = Path("src/ui/analyst/shell.py").read_text(encoding="utf-8")

        self.assertNotIn('"Escala"', admin_source)
        self.assertNotIn('"Minha escala"', analyst_source)


if __name__ == "__main__":
    unittest.main()
