#!/usr/bin/env bash
# One-time safeguarded reconciliation of Jefferson's historical ETIT alias.
# Run on the Hostinger VPS, NOT through GitHub Actions.
set -euo pipefail

cd /opt/portal-indicadores-cop-next

echo "=== 1. UNIT TESTS IN ISOLATED DATABASE ==="
bash deploy/hostinger/run-safe-tests.sh 'test_jefferson_etit_recovery.py'
bash deploy/hostinger/run-safe-tests.sh 'test_all_source_adapters.py'

echo "=== 2. READ-ONLY PREVIEW OF PRODUCTION DATA ==="
docker exec -e PYTHONPATH=/app portal-indicadores-cop \
    python deploy/hostinger/reconcile-jefferson-etit.py

if [[ "${1:-}" != "--apply" ]]; then
  echo ""
  echo "PREVIEW ONLY: no data changed."
  echo "To back up and apply run: bash deploy/hostinger/reconcile-jefferson-etit.sh --apply"
  exit 0
fi

echo "=== 3. FRESH, VALIDATED BACKUP OF THE CURRENT POSTGRESQL ==="
install -d -m 700 /root/cop-portal-backups
backup_file="cop_portal_before_jefferson_etit_$(date -u +%Y%m%dT%H%M%SZ).dump"
docker run --rm \
  --env-file .env.vps \
  -e BACKUP_FILE="$backup_file" \
  -v /root/cop-portal-backups:/backup \
  postgres:17-alpine sh -ec '
    set -eu
    pg_dump --dbname="$DATABASE_URL" --schema=cop_portal \
      --format=custom --no-owner --no-acl --file="/backup/$BACKUP_FILE"
    test -s "/backup/$BACKUP_FILE"
    pg_restore --list "/backup/$BACKUP_FILE" >/dev/null
    echo "BACKUP_VALIDADO=$BACKUP_FILE"
  '
chmod 600 "/root/cop-portal-backups/$backup_file"
sha256sum "/root/cop-portal-backups/$backup_file"

echo "=== 4. REATTRIBUTE EXACT VERIFIED HISTORY IN ONE TRANSACTION ==="
docker exec -e PYTHONPATH=/app portal-indicadores-cop \
    python deploy/hostinger/reconcile-jefferson-etit.py --apply

echo "=== 5. POST-CHECK (NO DUPLICATE TRANSFERS) ==="
docker exec -e PYTHONPATH=/app portal-indicadores-cop \
    python deploy/hostinger/reconcile-jefferson-etit.py

echo "RECOVERY_COMPLETE. Backup: /root/cop-portal-backups/$backup_file"
echo "IMPORTANT: RAL/REC demand labels need the COMPLETE original XLSX re-import."
