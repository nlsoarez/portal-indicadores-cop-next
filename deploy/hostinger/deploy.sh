#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/portal-indicadores-cop-next}"
BRANCH="${1:-${DEPLOY_BRANCH:-feat/admin-etit-operational-view}}"
EXPECTED_COMMIT="${2:-${DEPLOY_COMMIT:-}}"
PUBLIC_URL="${PUBLIC_URL:-https://portal-indicadores.179-198-124-8.sslip.io}"
PORTAL_PORT="${PORTAL_PORT:-8501}"
EDGE_NETWORK="${EDGE_NETWORK:-evolution-hostinger_edge}"
LOCAL_OVERRIDE="${APP_DIR}/docker-compose.hostinger.yml"
REPO_OVERRIDE="${APP_DIR}/deploy/hostinger/docker-compose.hostinger.yml.example"
ENV_FILE="${APP_DIR}/.env.vps"
HEALTH_PATH="/_stcore/health"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
  printf '\nERRO: %s\n' "$*" >&2
  exit 1
}

[[ -d "${APP_DIR}/.git" ]] || fail "Repositório não encontrado em ${APP_DIR}"
cd "${APP_DIR}"

[[ "${EXPECTED_COMMIT}" =~ ^[0-9a-fA-F]{40}$ ]] \
  || fail "Informe o SHA completo aprovado como segundo argumento ou DEPLOY_COMMIT."

command -v git >/dev/null 2>&1 || fail "git não encontrado"
command -v docker >/dev/null 2>&1 || fail "docker não encontrado"
docker compose version >/dev/null 2>&1 || fail "docker compose não disponível"

[[ -f "${ENV_FILE}" ]] || fail "Arquivo ${ENV_FILE} não existe"
grep -Eq '^[[:space:]]*DATABASE_URL=.+' "${ENV_FILE}" \
  || fail "DATABASE_URL não configurada em ${ENV_FILE}"

docker network inspect "${EDGE_NETWORK}" >/dev/null 2>&1 \
  || fail "Rede Docker externa ${EDGE_NETWORK} não existe"

if [[ -f "${LOCAL_OVERRIDE}" ]]; then
  HOST_OVERRIDE="${LOCAL_OVERRIDE}"
else
  [[ -f "${REPO_OVERRIDE}" ]] || fail "Override Hostinger não encontrado"
  HOST_OVERRIDE="${REPO_OVERRIDE}"
fi

COMPOSE=(
  docker compose
  -f docker-compose.vps.yml
  -f "${HOST_OVERRIDE}"
)

if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "Há alterações locais rastreadas no repositório. Preserve ou descarte antes do deploy."
fi

PREVIOUS_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"

log "Buscando branch origin/${BRANCH}"
git fetch --prune origin "${BRANCH}"

TARGET_COMMIT="$(git rev-parse "origin/${BRANCH}")"
log "Commit alvo da branch: ${TARGET_COMMIT}"
log "Commit aprovado: ${EXPECTED_COMMIT}"

if [[ "${TARGET_COMMIT,,}" != "${EXPECTED_COMMIT,,}" ]]; then
  fail "A branch mudou ou o SHA informado não corresponde ao HEAD remoto. Revise antes de publicar."
fi

log "Validando Docker Compose"
"${COMPOSE[@]}" config --quiet

log "Posicionando checkout no commit alvo"
git switch --detach "${TARGET_COMMIT}"

rollback() {
  local reason="$1"
  printf '\nDEPLOY FALHOU: %s\n' "${reason}" >&2
  "${COMPOSE[@]}" logs --tail=160 portal || true

  if [[ -n "${PREVIOUS_COMMIT}" && "${PREVIOUS_COMMIT}" != "${TARGET_COMMIT}" ]]; then
    log "Executando rollback para ${PREVIOUS_COMMIT}"
    git switch --detach "${PREVIOUS_COMMIT}"
    "${COMPOSE[@]}" build
    "${COMPOSE[@]}" up -d --remove-orphans
    sleep 5

    if curl -fsS --max-time 5 "http://127.0.0.1:${PORTAL_PORT}${HEALTH_PATH}" >/dev/null; then
      log "Rollback concluído e aplicação anterior saudável"
    else
      printf '\nATENÇÃO: rollback executado, mas o healthcheck local ainda falhou.\n' >&2
      "${COMPOSE[@]}" logs --tail=160 portal || true
    fi
  fi
  exit 1
}

trap 'rollback "erro inesperado na linha $LINENO"' ERR

log "Construindo imagem"
"${COMPOSE[@]}" build --pull portal

log "Validando sintaxe Python da imagem"
"${COMPOSE[@]}" run --rm --no-deps portal python -m compileall -q /app

if grep -Eqi '^[[:space:]]*COP_DB_AUTO_MIGRATE=(0|false|no|off)[[:space:]]*$' "${ENV_FILE}"; then
  grep -Eq '^[[:space:]]*DATABASE_ADMIN_URL=.+' "${ENV_FILE}" \
    || fail "COP_DB_AUTO_MIGRATE está desabilitado, mas DATABASE_ADMIN_URL não foi configurada."
  log "Executando migração de schema e seed com credencial administrativa separada"
  "${COMPOSE[@]}" run --rm --no-deps portal python -m src.infrastructure.migrate
fi

log "Subindo container"
"${COMPOSE[@]}" up -d --remove-orphans portal

trap - ERR

log "Aguardando healthcheck local"
deadline=$((SECONDS + HEALTH_TIMEOUT))
healthy=0
while (( SECONDS < deadline )); do
  container_status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' portal-indicadores-cop 2>/dev/null || true)"
  if [[ "${container_status}" == "healthy" ]] \
      && curl -fsS --max-time 5 "http://127.0.0.1:${PORTAL_PORT}${HEALTH_PATH}" >/dev/null; then
    healthy=1
    break
  fi
  sleep 3
done

if [[ "${healthy}" -ne 1 ]]; then
  rollback "healthcheck não ficou saudável em ${HEALTH_TIMEOUT}s"
fi

log "Container saudável"
"${COMPOSE[@]}" ps

log "Verificando URL pública"
if curl -fsS --max-time 12 "${PUBLIC_URL}${HEALTH_PATH}" >/dev/null; then
  printf 'HTTPS OK: %s%s\n' "${PUBLIC_URL}" "${HEALTH_PATH}"
else
  printf 'ATENÇÃO: aplicação local está saudável, mas a URL pública não respondeu ao healthcheck.\n' >&2
  printf 'Verifique Caddy e a rota para portal-indicadores-cop:8501.\n' >&2
fi

printf '\nDEPLOY CONCLUÍDO\n'
printf 'Branch: %s\n' "${BRANCH}"
printf 'Commit: %s\n' "${TARGET_COMMIT}"
printf 'URL: %s\n' "${PUBLIC_URL}"
