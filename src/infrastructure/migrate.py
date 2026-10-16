from __future__ import annotations

import os
import sys


def main() -> int:
    admin_url = os.environ.get("DATABASE_ADMIN_URL", "").strip()
    if not admin_url:
        print("DATABASE_ADMIN_URL não configurada; migração abortada.", file=sys.stderr)
        return 2

    # database.py reads these values at import time, so set them first.
    os.environ["DATABASE_URL"] = admin_url
    os.environ["COP_DB_AUTO_MIGRATE"] = "1"

    from src.config.seed import seed_foundation
    from src.infrastructure.database import initialize_database

    initialize_database()
    seed_foundation()
    print("Migração de schema e seed de configuração concluídos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
