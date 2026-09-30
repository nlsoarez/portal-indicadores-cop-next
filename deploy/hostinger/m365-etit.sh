#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/portal-indicadores-cop-next}"
EDGE_NETWORK="${EDGE_NETWORK:-evolution-hostinger_edge}"
LOCAL_OVERRIDE="${APP_DIR}/docker-compose.hostinger.yml"
REPO_OVERRIDE="${APP_DIR}/deploy/hostinger/docker-compose.hostinger.yml.example"

cd "${APP_DIR}"

if [[ -f "${LOCAL_OVERRIDE}" ]]; then
  HOST_OVERRIDE="${LOCAL_OVERRIDE}"
else
  HOST_OVERRIDE="${REPO_OVERRIDE}"
fi

[[ -f ".env.vps" ]] || {
  echo "ERRO: ${APP_DIR}/.env.vps não encontrado." >&2
  exit 1
}

docker network inspect "${EDGE_NETWORK}" >/dev/null 2>&1 || {
  echo "ERRO: rede Docker ${EDGE_NETWORK} não encontrada." >&2
  exit 1
}

COMPOSE=(
  docker compose
  -f docker-compose.vps.yml
  -f "${HOST_OVERRIDE}"
)

command_name="${1:-status}"
shift || true

case "${command_name}" in
  login|status|probe|sync)
    ;;
  *)
    echo "Uso: bash deploy/hostinger/m365-etit.sh {login|status|probe|sync} [--force]" >&2
    exit 2
    ;;
esac

"${COMPOSE[@]}" run --rm --no-deps portal   python -m src.integrations.m365_cli "${command_name}" "$@"
