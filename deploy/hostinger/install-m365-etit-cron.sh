#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/portal-indicadores-cop-next}"
SYNC_HOUR="${SYNC_HOUR:-5}"
SYNC_MINUTE="${SYNC_MINUTE:-15}"
CRON_FILE="/etc/cron.d/portal-indicadores-m365-etit"
LOG_FILE="${M365_SYNC_LOG:-/var/log/portal-m365-etit.log}"
LOCK_FILE="${M365_SYNC_LOCK:-/var/lock/portal-m365-etit.lock}"

[[ "${EUID}" -eq 0 ]] || {
  echo "ERRO: execute como root para instalar o cron." >&2
  exit 1
}

cat > "${CRON_FILE}" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
CRON_TZ=America/Sao_Paulo
TZ=America/Sao_Paulo
${SYNC_MINUTE} ${SYNC_HOUR} * * * root flock -n ${LOCK_FILE} bash -lc 'cd ${APP_DIR} && bash deploy/hostinger/m365-etit.sh sync' >> ${LOG_FILE} 2>&1
EOF

chmod 0644 "${CRON_FILE}"
touch "${LOG_FILE}"
chmod 0640 "${LOG_FILE}"

echo "Agendamento instalado:"
cat "${CRON_FILE}"
echo
echo "Log: ${LOG_FILE}"
echo "Lock: ${LOCK_FILE}"
echo "Timezone do agendamento: America/Sao_Paulo."
