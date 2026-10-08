"""Database isolation for unittest cases.

Never let tests seed, modify users or insert synthetic metrics into the VPS
production PostgreSQL simply because DATABASE_URL is present in the container.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.infrastructure import database


def isolate_sqlite_database(test_case) -> None:
    """Configure a disposable SQLite database for one test; restore afterward.

    Register cleanup *before* initialization so it still runs if setup fails.
    SQLite isolation is explicit; COP_PORTAL_DB by itself is NOT sufficient to
    switch away from PostgreSQL, because DATABASE_URL is cached at import time.
    """
    previous_url = database.DATABASE_URL
    previous_path = database.DB_PATH
    previous_env = os.environ.get("COP_PORTAL_DB")

    tmp = tempfile.TemporaryDirectory(prefix="cop-portal-unit-")
    path = Path(tmp.name) / "portal.db"

    def restore() -> None:
        database.DATABASE_URL = previous_url
        database.DB_PATH = previous_path
        if previous_env is None:
            os.environ.pop("COP_PORTAL_DB", None)
        else:
            os.environ["COP_PORTAL_DB"] = previous_env
        tmp.cleanup()

    test_case.addCleanup(restore)
    database.DATABASE_URL = ""
    database.DB_PATH = path
    os.environ["COP_PORTAL_DB"] = str(path)
    if database.using_postgres() or database.database_backend() != "sqlite":
        raise RuntimeError("FALHA DE SEGURANÇA: testes tentaram acessar PostgreSQL")

    database.initialize_database()
