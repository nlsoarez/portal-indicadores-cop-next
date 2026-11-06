#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/portal-indicadores-cop-next}"
BRANCH="${1:-security/guardian-fixes-20260930}"
EXPECTED_COMMIT="${2:-${VALIDATE_COMMIT:-}}"

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
  printf '\nERRO: %s\n' "$*" >&2
  exit 1
}

[[ -d "${APP_DIR}/.git" ]] || fail "Repositório não encontrado em ${APP_DIR}"
[[ "${EXPECTED_COMMIT}" =~ ^[0-9a-fA-F]{40}$ ]] \
  || fail "Informe o SHA completo aprovado como segundo argumento ou VALIDATE_COMMIT."

command -v git >/dev/null 2>&1 || fail "git não encontrado"
command -v docker >/dev/null 2>&1 || fail "docker não encontrado"

cd "${APP_DIR}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "Há alterações locais rastreadas no checkout principal."
fi

log "Buscando origin/${BRANCH}"
git fetch --prune origin "${BRANCH}"
TARGET_COMMIT="$(git rev-parse "origin/${BRANCH}")"

if [[ "${TARGET_COMMIT,,}" != "${EXPECTED_COMMIT,,}" ]]; then
  fail "O HEAD remoto não corresponde ao SHA aprovado."
fi

SHORT_SHA="${EXPECTED_COMMIT:0:12}"
WORKTREE="$(mktemp -d "/tmp/portal-security-${SHORT_SHA}-XXXXXX")"
IMAGE="portal-security-validation:${SHORT_SHA}"

cleanup() {
  set +e
  docker image rm -f "${IMAGE}" >/dev/null 2>&1 || true
  git -C "${APP_DIR}" worktree remove --force "${WORKTREE}" >/dev/null 2>&1 || true
  rm -rf "${WORKTREE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "Criando worktree isolado em ${WORKTREE}"
rm -rf "${WORKTREE}"
git worktree add --detach "${WORKTREE}" "${EXPECTED_COMMIT}"

log "Construindo imagem temporária ${IMAGE}"
docker build --pull -f "${WORKTREE}/Dockerfile.vps" -t "${IMAGE}" "${WORKTREE}"

log "Validando sintaxe Python"
docker run --rm \
  -e DATABASE_URL= \
  -e POSTGRES_URL= \
  -e POSTGRES_URL_NON_POOLING= \
  -e COP_DB_AUTO_MIGRATE=1 \
  "${IMAGE}" python -m compileall -q /app

log "Executando suíte completa em SQLite isolado"
docker run --rm \
  -e DATABASE_URL= \
  -e POSTGRES_URL= \
  -e POSTGRES_URL_NON_POOLING= \
  -e COP_DB_AUTO_MIGRATE=1 \
  -e COP_PORTAL_DB=/tmp/security-validation.db \
  "${IMAGE}" python -m unittest discover -s tests -p 'test_*.py'

printf '\nVALIDAÇÃO CONCLUÍDA\n'
printf 'Branch: %s\n' "${BRANCH}"
printf 'Commit: %s\n' "${EXPECTED_COMMIT}"
printf 'Produção alterada: NÃO\n'
