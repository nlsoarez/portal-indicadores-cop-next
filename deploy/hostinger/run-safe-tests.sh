#!/usr/bin/env bash
set -Eeuo pipefail

# Execute unit tests only with DB credentials removed from the child process.
# The in-test fixture additionally forces a disposable SQLite DB.
APP_CONTAINER="${APP_CONTAINER:-portal-indicadores-cop}"
PATTERN="${1:-test_*.py}"

if [[ "${PATTERN}" != test_*.py ]]; then
  echo "ERRO: padrão inválido. Use test_*.py ou test_leader*.py." >&2
  exit 2
fi
docker exec \
  -e DATABASE_URL= \
  -e POSTGRES_URL= \
  -e POSTGRES_URL_NON_POOLING= \
  "${APP_CONTAINER}" \
  python -m unittest discover -s tests -p "${PATTERN}"
