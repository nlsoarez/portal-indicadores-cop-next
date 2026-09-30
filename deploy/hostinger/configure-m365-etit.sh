#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/portal-indicadores-cop-next}"
ENV_FILE="${APP_DIR}/.env.vps"

OWNER_UPN="${M365_ETIT_OWNER_UPN:-fernando_pereiracunha@claro.com.br}"
RESIDENTIAL_PATH="${M365_ETIT_RESIDENTIAL_FOLDER_PATH:-Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Residencial/Novo BI}"
ENTERPRISE_PATH="${M365_ETIT_ENTERPRISE_FOLDER_PATH:-Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Empresarial/Novo BI}"

[[ -f "${ENV_FILE}" ]] || {
  echo "ERRO: ${ENV_FILE} não encontrado." >&2
  exit 1
}

upsert_env() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  awk -v k="${key}" -v v="${value}" '
    BEGIN { found=0 }
    index($0, k "=") == 1 {
      print k "=" v
      found=1
      next
    }
    { print }
    END {
      if (!found) print k "=" v
    }
  ' "${ENV_FILE}" > "${tmp}"
  cat "${tmp}" > "${ENV_FILE}"
  rm -f "${tmp}"
}

# Files.Read.All continua somente leitura e permite trabalhar com arquivos
# que a conta autenticada pode acessar, inclusive em OneDrive de outro usuário.
upsert_env "M365_SCOPES" "Files.Read.All"
upsert_env "M365_ETIT_RESIDENTIAL_OWNER_UPN" "${OWNER_UPN}"
upsert_env "M365_ETIT_RESIDENTIAL_FOLDER_PATH" "${RESIDENTIAL_PATH}"
upsert_env "M365_ETIT_ENTERPRISE_OWNER_UPN" "${OWNER_UPN}"
upsert_env "M365_ETIT_ENTERPRISE_FOLDER_PATH" "${ENTERPRISE_PATH}"

if [[ -n "${M365_TENANT_ID:-}" ]]; then
  upsert_env "M365_TENANT_ID" "${M365_TENANT_ID}"
fi

if [[ -n "${M365_CLIENT_ID:-}" ]]; then
  upsert_env "M365_CLIENT_ID" "${M365_CLIENT_ID}"
fi

chmod 0600 "${ENV_FILE}" || true

echo "Configuração do piloto ETIT aplicada em ${ENV_FILE}:"
echo "  Escopo: Files.Read.All"
echo "  Proprietário: ${OWNER_UPN}"
echo "  Residencial: ${RESIDENTIAL_PATH}"
echo "  Empresarial: ${ENTERPRISE_PATH}"

if ! grep -Eq '^M365_TENANT_ID=.+$' "${ENV_FILE}"; then
  echo
  echo "PENDENTE: M365_TENANT_ID ainda não configurado."
fi

if ! grep -Eq '^M365_CLIENT_ID=.+$' "${ENV_FILE}"; then
  echo "PENDENTE: M365_CLIENT_ID ainda não configurado."
fi

echo
echo "Próximo passo:"
echo "  bash deploy/hostinger/m365-etit.sh status"
echo "  bash deploy/hostinger/m365-etit.sh login"
echo "  bash deploy/hostinger/m365-etit.sh probe"
