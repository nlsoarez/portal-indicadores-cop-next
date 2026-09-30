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

## Deploy

Na VPS:

```bash
cd /opt/portal-indicadores-cop-next
chmod +x deploy/hostinger/deploy.sh deploy/hostinger/check.sh
./deploy/hostinger/deploy.sh feat/admin-etit-operational-view
```

Depois que esta feature estiver incorporada à `main`:

```bash
./deploy/hostinger/deploy.sh main
```

O deploy executa:

1. valida `.env.vps` e `DATABASE_URL`;
2. valida a rede Docker usada pelo Caddy;
3. busca a branch no GitHub;
4. usa exatamente o commit remoto da branch;
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
DATABASE_URL=postgresql://...
DB_POOL_MAX_SIZE=8
PORTAL_PORT=8501
```

Não faça commit da URI real do banco nem de senhas.


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
M365_ETIT_RESIDENTIAL_OWNER_UPN=fernando_pereiracunha@claro.com.br
M365_ETIT_RESIDENTIAL_FOLDER_PATH=Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Residencial/Novo BI
M365_ETIT_ENTERPRISE_OWNER_UPN=fernando_pereiracunha@claro.com.br
M365_ETIT_ENTERPRISE_FOLDER_PATH=Indicadores_COP_Rede/ICG_COPREDE_MDU/ICG_COPREDE/Analítico Empresarial/Novo BI
```

Como alternativas, cada fonte também aceita `DRIVE_ID/FOLDER_ID` ou a URL compartilhada original.

A App Registration do Microsoft Entra precisa permitir **public client flows/device code**.
Não é necessário client secret para este piloto.

### Primeiro login

Após o deploy:

```bash
cd /opt/portal-indicadores-cop-next
bash deploy/hostinger/m365-etit.sh login
```

O comando mostra uma URL e um código Microsoft. Abra a URL em um navegador, informe o código e faça
login com uma conta corporativa que tenha acesso às duas pastas.

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

O instalador usa 05:15 no timezone do servidor por padrão:

```bash
bash deploy/hostinger/install-m365-etit-cron.sh
```

Para outro horário:

```bash
SYNC_HOUR=6 SYNC_MINUTE=30 bash deploy/hostinger/install-m365-etit-cron.sh
```

Log:

```text
/var/log/portal-m365-etit.log
```

O upload manual permanece disponível como contingência.
