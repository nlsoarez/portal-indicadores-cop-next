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
