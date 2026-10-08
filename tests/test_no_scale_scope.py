import os, tempfile, unittest
from pathlib import Path
from tests.isolated_database import isolate_sqlite_database

class NoScaleScopeTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
    def test_database_has_no_scale_table(self):
        from src.infrastructure.database import connection
        with connection() as conn: row=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scales'").fetchone()
        self.assertIsNone(row)
    def test_ui_has_no_scale_navigation(self):
        self.assertNotIn('"Escala"',Path("src/ui/admin/shell.py").read_text(encoding="utf-8")); self.assertNotIn('"Minha escala"',Path("src/ui/analyst/shell.py").read_text(encoding="utf-8"))
