#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/portal-indicadores-cop-next}"
SYNC_HOUR="${SYNC_HOUR:-18}"
SYNC_MINUTE="${SYNC_MINUTE:-30}"
CRON_FILE="/etc/cron.d/portal-indicadores-m365-etit"
LOG_FILE="${M365_SYNC_LOG:-/var/log/portal-m365-etit.log}"
LOCK_FILE="${M365_SYNC_LOCK:-/var/lock/portal-m365-etit.lock}"

[[ "${EUID}" -eq 0 ]] || {
  echo "ERRO: execute como root para instalar o cron." >&2
  exit 1
}

if ! [[ "${SYNC_HOUR}" =~ ^([01]?[0-9]|2[0-3])$ ]]; then
  echo "ERRO: SYNC_HOUR deve estar entre 0 e 23." >&2
  exit 1
fi

if ! [[ "${SYNC_MINUTE}" =~ ^([0-5]?[0-9])$ ]]; then
  echo "ERRO: SYNC_MINUTE deve estar entre 0 e 59." >&2
  exit 1
fi

hour_num=$((10#${SYNC_HOUR}))
minute_num=$((10#${SYNC_MINUTE}))
printf -v SYNC_TIME '%02d:%02d' "${hour_num}" "${minute_num}"

cat > "${CRON_FILE}" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TZ=America/Sao_Paulo
# O cron é avaliado a cada minuto e só executa o sync quando o relógio de
# America/Sao_Paulo coincide com ${SYNC_TIME}. Isso evita depender do fuso
# configurado no host ou do suporte do daemon a CRON_TZ.
* * * * * root [ "\$(TZ=America/Sao_Paulo date +\%H:\%M)" = "${SYNC_TIME}" ] && flock -n "${LOCK_FILE}" bash -lc 'cd "${APP_DIR}" && bash deploy/hostinger/m365-etit.sh sync' >> "${LOG_FILE}" 2>&1
EOF

chmod 0644 "${CRON_FILE}"
touch "${LOG_FILE}"
chmod 0640 "${LOG_FILE}"

echo "Agendamento instalado:"
cat "${CRON_FILE}"
echo
echo "Execução efetiva: diariamente às ${SYNC_TIME} America/Sao_Paulo."
echo "A checagem do horário é independente do timezone configurado na VPS."
echo "Log: ${LOG_FILE}"
echo "Lock: ${LOCK_FILE}"
