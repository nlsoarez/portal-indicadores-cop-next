#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/portal-indicadores-cop-next}"
PUBLIC_URL="${PUBLIC_URL:-https://portal-indicadores.179-198-124-8.sslip.io}"
PORTAL_PORT="${PORTAL_PORT:-8501}"
EDGE_NETWORK="${EDGE_NETWORK:-evolution-hostinger_edge}"
LOCAL_OVERRIDE="${APP_DIR}/docker-compose.hostinger.yml"
REPO_OVERRIDE="${APP_DIR}/deploy/hostinger/docker-compose.hostinger.yml.example"

cd "${APP_DIR}"

if [[ -f "${LOCAL_OVERRIDE}" ]]; then
  HOST_OVERRIDE="${LOCAL_OVERRIDE}"
else
  HOST_OVERRIDE="${REPO_OVERRIDE}"
fi

COMPOSE=(
  docker compose
  -f docker-compose.vps.yml
  -f "${HOST_OVERRIDE}"
)

printf '=== Git ===\n'
git rev-parse --short HEAD
git status --short --branch || true

printf '\n=== Docker Compose ===\n'
"${COMPOSE[@]}" ps

printf '\n=== Container health ===\n'
docker inspect -f 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' portal-indicadores-cop

printf '\n=== Rede do Caddy ===\n'
docker network inspect "${EDGE_NETWORK}" --format '{{range .Containers}}{{.Name}} {{end}}' | tr ' ' '\n' | grep -E 'portal-indicadores-cop|caddy' || true

printf '\n=== Health local ===\n'
curl -fsS --max-time 5 "http://127.0.0.1:${PORTAL_PORT}/_stcore/health"
printf '\n'

printf '\n=== Health público ===\n'
curl -fsS --max-time 12 "${PUBLIC_URL}/_stcore/health"
printf '\n'

printf '\n=== Últimos logs ===\n'
"${COMPOSE[@]}" logs --tail=80 portal
