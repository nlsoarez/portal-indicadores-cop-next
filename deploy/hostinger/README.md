# Deploy Hostinger — Portal Indicadores COP

Este diretório contém o fluxo de deploy para a VPS Hostinger já existente.

## Ambiente atual

- Aplicação: `/opt/portal-indicadores-cop-next`
- Container: `portal-indicadores-cop`
- Porta local: `127.0.0.1:8501`
- Reverse proxy: Caddy
- Rede compartilhada com o Caddy: `evolution-hostinger_edge`
- URL pública: `https://portal-indicadores.179-198-124-8.sslip.io`
- Banco: PostgreSQL/Supabase via `.env.vps`

O script não instala Docker, não altera firewall e não reescreve o Caddy. Esses componentes já existem na VPS.

## Validação isolada antes do deploy

Use o validador de segurança para construir e testar o commit sem trocar o checkout
principal e sem subir o container de produção:

```bash
cd /opt/portal-indicadores-cop-next
chmod +x deploy/hostinger/validate-security.sh
./deploy/hostinger/validate-security.sh security/guardian-fixes-20260930 <SHA_COMPLETO_APROVADO>
```

O script:
- confirma que o SHA é exatamente o HEAD remoto aprovado;
- cria um `git worktree` temporário;
- constrói uma imagem Docker temporária;
- executa `compileall`;
- executa toda a suíte `unittest` com URLs PostgreSQL zeradas e SQLite temporário;
- remove worktree e imagem ao terminar;
- não executa `docker compose up` e não altera o container ativo.

## Deploy

Na VPS:

```bash
cd /opt/portal-indicadores-cop-next
chmod +x deploy/hostinger/deploy.sh deploy/hostinger/check.sh
./deploy/hostinger/deploy.sh feat/admin-etit-operational-view <SHA_COMPLETO_APROVADO>
```

Depois que esta feature estiver incorporada à `main`:

```bash
./deploy/hostinger/deploy.sh main <SHA_COMPLETO_APROVADO>
```

O deploy executa:

1. valida `.env.vps` e `DATABASE_URL`;
2. valida a rede Docker usada pelo Caddy;
3. busca a branch no GitHub;
4. compara o HEAD remoto com o SHA completo informado pelo operador e aborta se houver divergência;
5. valida o Compose;
6. faz o build da imagem;
7. sobe o container;
8. aguarda o healthcheck do Streamlit;
9. testa o endpoint público;
10. se o container novo não ficar saudável, tenta voltar ao commit anterior.

## Verificação

```bash
cd /opt/portal-indicadores-cop-next
./deploy/hostinger/check.sh
```

## Compose Hostinger

O deploy prefere o arquivo local existente:

```text
/opt/portal-indicadores-cop-next/docker-compose.hostinger.yml
```

Se ele não existir, usa automaticamente:

```text
deploy/hostinger/docker-compose.hostinger.yml.example
```

Esse override conecta o portal à rede `evolution-hostinger_edge`, permitindo ao Caddy encaminhar:

```text
portal-indicadores.179-198-124-8.sslip.io
    -> portal-indicadores-cop:8501
```

## Variáveis

O arquivo `.env.vps` deve continuar fora do Git. Exemplo mínimo:

```env
DATABASE_URL=postgresql://cop_portal_app.PROJECT_REF:...
DATABASE_ADMIN_URL=postgresql://postgres.PROJECT_REF:...
COP_DB_AUTO_MIGRATE=0
DB_POOL_MAX_SIZE=8
PORTAL_PORT=8501
# Obrigatório somente para o primeiro ADMIN de um banco PostgreSQL novo:
COP_ADMIN_BOOTSTRAP_PASSWORD=...
```

Não faça commit da URI real do banco nem de senhas.

### Papel PostgreSQL de runtime

O processo web não deve operar como `postgres`.

#### Rollout seguro em duas etapas

O banco atual precisa receber primeiro as novas estruturas de autenticação antes de o papel restrito ser usado.

**Etapa 1 — atualizar schema mantendo a credencial atual**
1. faça deploy do código com o `DATABASE_URL` administrativo atual e `COP_DB_AUTO_MIGRATE=1`;
2. valide que foram criados `users.auth_version` e `auth_throttle`;
3. confirme login, reset de senha e healthcheck.

**Etapa 2 — reduzir privilégios**
1. revise e execute `deploy/supabase/runtime-role.sql.example`;
2. defina a senha do `cop_portal_app` fora do Git;
3. configure `DATABASE_URL` com esse papel;
4. configure `DATABASE_ADMIN_URL` apenas para migração;
5. defina `COP_DB_AUTO_MIGRATE=0`;
6. faça novo deploy usando SHA aprovado e valide novamente.

Antes de ativar o modo separado:

1. revise `deploy/supabase/runtime-role.sql.example`;
2. crie `cop_portal_app` no Supabase com senha forte gerada fora do Git;
3. configure `DATABASE_URL` com esse papel;
4. mantenha `DATABASE_ADMIN_URL` restrita ao deploy;
5. defina `COP_DB_AUTO_MIGRATE=0`.

Quando esse modo está ativo, `deploy.sh` executa `python -m src.infrastructure.migrate`
com a credencial administrativa antes de iniciar o portal. O processo web apenas valida que o
schema já existe e opera com DML de runtime.


## Piloto Microsoft 365 — ETIT Residencial e Empresarial

O piloto verifica diariamente as pastas oficiais de ETIT via Microsoft Graph. Ele não depende de manter
uma aba do SharePoint aberta no navegador. O fluxo usa autenticação delegada com device code e persiste
o cache de token em um volume Docker privado.

### Variáveis obrigatórias

O piloto prefere localizar as pastas pelo proprietário e caminho interno do OneDrive,
evitando depender da API de links compartilhados. Isso permite trabalhar somente com
permissões de leitura.

Na VPS, execute primeiro:

```bash
cd /opt/portal-indicadores-cop-next
bash deploy/hostinger/configure-m365-etit.sh
```

O helper configura as duas pastas usadas neste piloto:

- `Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Residencial/Novo BI`
- `Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Empresarial/Novo BI`

e grava `M365_SCOPES=Files.Read.All`.

Ainda é necessário informar em `.env.vps`:

```env
M365_TENANT_ID=...
M365_CLIENT_ID=...
M365_SCOPES=Files.Read.All
M365_TOKEN_CACHE_KEY=...
M365_ETIT_RESIDENTIAL_OWNER_UPN=fernando_pereiracunha@claro.com.br
M365_ETIT_RESIDENTIAL_FOLDER_PATH=Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Residencial/Novo BI
M365_ETIT_ENTERPRISE_OWNER_UPN=fernando_pereiracunha@claro.com.br
M365_ETIT_ENTERPRISE_FOLDER_PATH=Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Empresarial/Novo BI
```

Como alternativas, cada fonte também aceita `DRIVE_ID/FOLDER_ID` ou a URL compartilhada original.

A App Registration do Microsoft Entra precisa permitir **public client flows/device code**.
Não é necessário client secret para este piloto.

### Criar a App Registration

No Microsoft Entra, use uma aplicação dedicada ao piloto:

1. **App registrations → New registration**.
2. Nome sugerido: `Portal Indicadores COP - ETIT`.
3. Tipos de conta: somente contas deste diretório organizacional (single tenant).
4. Não configure Redirect URI.
5. Em **Authentication**, habilite **Allow public client flows**.
6. Em **API permissions**, adicione **Microsoft Graph → Delegated permissions → Files.Read.All**.
7. Em **Overview**, copie **Directory (tenant) ID** e **Application (client) ID** para `.env.vps`.

A permissão delegada `Files.Read.All` é somente leitura. Ela não exige consentimento
administrativo por definição do Microsoft Graph, mas uma política corporativa do tenant pode
bloquear consentimento pelo próprio usuário; nesse caso, TI precisa aprovar a aplicação.

### Primeiro login

Após o deploy:

```bash
cd /opt/portal-indicadores-cop-next
bash deploy/hostinger/m365-etit.sh login
```

Antes do primeiro login, configure `M365_TOKEN_CACHE_KEY` como uma chave Fernet gerada fora do Git.
O cache MSAL existente em texto será migrado para conteúdo criptografado na primeira renovação/login
com a chave configurada.

O comando mostra uma URL e um código Microsoft. Abra a URL em um navegador, informe o código e faça
login com uma conta corporativa dedicada ao portal e que tenha acesso apenas ao necessário para o piloto.

### Validar sem processar

```bash
bash deploy/hostinger/m365-etit.sh probe
```

O retorno deve identificar:

- `Analítico Indicadores Residencial - YYYYMM.xlsx`
- `Analítico Empresarial - YYYYMM.xlsx`

### Sincronizar

```bash
bash deploy/hostinger/m365-etit.sh sync
```

Somente arquivos alterados são baixados e enviados ao pipeline de ingestão já existente. Para forçar
um reprocessamento:

```bash
bash deploy/hostinger/m365-etit.sh sync --force
```

### Agendar 1 vez por dia

O instalador usa 18:30 (America/Sao_Paulo) por padrão, para capturar atualizações feitas ao longo do expediente:

```bash
bash deploy/hostinger/install-m365-etit-cron.sh
```

O cron é instalado de forma independente do timezone configurado na VPS: ele avalia o relógio
de `America/Sao_Paulo` antes de executar o sincronismo. Isso evita deslocamento de horário em
hosts configurados em UTC e também evita depender do suporte do daemon a `CRON_TZ`.

Para outro horário:

```bash
SYNC_HOUR=6 SYNC_MINUTE=30 bash deploy/hostinger/install-m365-etit-cron.sh
```

Use `bash deploy/hostinger/check.sh` para comparar o horário do host, o horário de São Paulo e
confirmar a entrada instalada em `/etc/cron.d/portal-indicadores-m365-etit`.

Log:

```text
/var/log/portal-m365-etit.log
```

O upload manual permanece disponível como contingência.
