# Diagnóstico estrutural — referência dashboard-indicadores-cop

> Método: análise Graphify-style via GitHub, porque o repositório privado não contém `graphify-out/graph.json` e o runtime local não possui acesso de rede para clonar o repositório nem o pacote Graphify instalado.

## System map

```text
Streamlit app.py
  -> auth.py -> storage.py -> Cloudflare R2/local
  -> access_control.py -> config.py (IDs/equipes hardcoded)
  -> source_selection.py -> session_state/uploaded_* bytes
  -> cached_processors.py -> processed_cache.py -> processors.py
  -> processors.py -> config.py (schemas, indicadores, metas, equipes)
  -> UI tabs/admin/analyst all rendered from app.py
```

## Relação solicitada

```text
Autenticação
  -> Perfil (resolve_access_profile)
  -> "Segmento"/setor (hardcoded em config.py + condicionais)
  -> Permissões (AccessProfile + filtros no app/processors)
  -> Dados (R2/local files + session_state)
  -> Indicadores (processors.py + config.py)
  -> Dashboard (app.py)
```

## Nós de maior conectividade

- `app.py`: supernó de UI, navegação, filtros, autorização operacional, parsing/cache e apresentação.
- `src/processors.py`: supernó de ingestão, normalização e métricas para múltiplas fontes.
- `src/config.py`: supernó de usuários, escopos, schemas de planilhas, indicadores, metas e cores.
- `src/auth.py`: autenticação e persistência de uploads/credenciais no mesmo módulo.

## Evidência

### EXTRACTED
- Perfis são derivados de matrículas e sets em `config.py`.
- `AccessProfile` resolve super-admin/coordenador/sub-admin e `team_ids` a partir de configuração estática.
- Credenciais são persistidas em `passwords.json`, com PBKDF2 e senha inicial padrão.
- Uploads são arquivos por chave fixa (`uploaded_*`) em R2/disco.
- A seleção de fontes depende do texto da aba atual.
- Admin e analista usam conjuntos de tabs diferentes dentro do mesmo `app.py`.
- Residencial possui função específica `filter_residential_by_logins(..., allowed_logins)` com fail-closed.

### INFERRED
- Adicionar novos segmentos tende a exigir novas constantes, novos mapas de equipe, novas condicionais e novas abas no supernó `app.py`.
- A autorização é mais difícil de auditar porque parte do escopo é resolvida no perfil e parte em filtros específicos de fonte.
- O modelo de arquivos é adequado como ingestão, mas não como fonte de identidade, autorização e relacionamentos multi-segmento.

### AMBIGUOUS
- O requisito-alvo cita QOE, porém o repositório analisado contém principalmente Residencial/Empresarial; por isso QOE foi criado apenas como segmento inativo nesta fundação.
- Não foi identificado schema relacional existente para usuários/segmentos; a nova base relacional é uma criação da nova arquitetura.
