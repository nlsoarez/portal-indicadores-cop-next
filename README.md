# Portal de Indicadores COP — Next

Nova geração do Portal de Indicadores COP, construída sem alterar o repositório legado de referência.

## Perfis de acesso

- **Admin** — gestão total e **único perfil autorizado a fazer upload/processamento das planilhas**.
- **Subadmin** — Bruno (`N5619600`), Leandro (`N6088107`), Kelly (`N5923221`) e Marley (`N0238475`). Possuem visão gerencial dos analistas, sem upload.
- **Analista** — visualiza somente seus próprios dados individuais e agregados permitidos da equipe.
- Líderes/Subadmins não aparecem na lista de analistas comuns.
- O Admin possui a aba **Líderes** para consultar indicadores, evolução, histórico e último acesso dos quatro líderes.
- Resultados dos líderes são persistidos quando aparecem nas fontes, mas **não entram nas médias dos analistas**.

## Segmentos e pessoas

- **Preventiva:** Daniel (`N5604148`), Rosana (`N5941223`), Carlos (`N0158974`) e Maristella (`N5577565`).
- Maristella pertence somente à Preventiva.
- **Residencial:** inclui Marcelo de Souza Almeida (`F104752`) e a equipe residencial migrada do portal legado.
- **Empresarial:** equipe empresarial migrada do portal legado.
- Bruno e Leandro têm seus indicadores próprios associados ao Empresarial; Kelly e Marley ao Residencial. Como Subadmins, os quatro continuam podendo consultar os segmentos ativos autorizados.

## Sete fontes oficiais de upload

O Admin atualiza o portal em um painel global. Cada arquivo é enviado **uma única vez**, independentemente do segmento atualmente selecionado:

1. **Analítico Indicadores Residencial**
2. **Analítico Empresarial**
3. **Ocupação DPA 2026**
4. **Produtividade COP Rede 2026 — Analítico**
5. **Fechamento TOA x SIR**
6. **Analítico TOA Chat**
7. **Analítico Indicadores TOA**

As sete fontes possuem adapter funcional. O backend identifica os usuários autorizados e direciona os resultados aos segmentos correspondentes.

## Indicadores atualmente processados

### Residencial

- ETIT Fibra HFC
- ETIT GPON
- Assertividade Acionamento Fibra HFC
- Assertividade Acionamento GPON
- DPA Oficial
- Produtividade média diária
- Assertividade Fechamento TOA x SIR

### Empresarial

- ETIT por Evento
- DPA Oficial
- Produtividade média diária
- Assertividade Fechamento TOA x SIR

### Preventiva

- Chat 10 min — meta 75%
- Tempo de Validação do Formulário — meta 80%
- Taxa de Tarefas Canceladas
- DPA Oficial
- Produtividade média diária
- Assertividade Fechamento TOA x SIR quando houver dados dos usuários do segmento

## Regras de ingestão

- A maior data real encontrada em cada indicador alimenta **Dados até DD/MM/AAAA**.
- O mês de competência da fonte (`ANOMES`) é persistido separadamente da data real do evento. Isso evita atribuir ao mês anterior um evento que pertence ao fechamento do mês atual.
- Reupload de uma mesma competência substitui aquele mês/indicador, evitando duplicação.
- Médias mensais são ponderadas pelo volume quando o indicador possui volume operacional.
- DPA e Fechamento TOA x SIR são lidos do **pivot cache** interno dos arquivos, sem depender do estado visual dos filtros do Excel.
- Planilhas grandes são processadas em streaming de XML para evitar carregar worksheets de centenas de MB inteiros em memória.
- Chat TOA é filtrado pelas matrículas do segmento; não há filtro fixo por nome de fila, porque as filas reais da Preventiva incluem QOE.

## Banco e segurança

- Usuários, roles, segmentos, memberships, indicadores, resultados, uploads, cobertura dos dados e logs de acesso ficam no banco relacional. Em Vercel, configure `DATABASE_URL` para PostgreSQL persistente; SQLite fica apenas como fallback local/teste.
- Existe uma separação entre segmento que o usuário pode **consultar** e segmento em que seu próprio **desempenho** deve ser contabilizado.
- Senha inicial `claro123`, persistida somente como hash PBKDF2, com troca obrigatória no primeiro acesso.
- Autorização é validada no backend (`AccessService`); esconder um controle na interface não é usado como proteção de acesso.
- O portal **não possui módulo de escala**.
- O projeto **não usa GitHub Actions** e não possui `.github/workflows/`.

## Testes

A suíte cobre isolamento de usuários, hierarquia Admin/Subadmin/Analista, ausência de escala, roteamento de segmentos, freshness, catálogo das sete fontes e parsers das fontes oficiais.

```bash
python -m unittest discover -s tests -v
streamlit run app.py
```

## Documentação

- `docs/ARCHITECTURE.md`
- `docs/MIGRATION_INVENTORY.md`
- `docs/POST_BUILD_GRAPH_AUDIT.md`
- `docs/GRAPHIFY_DIAGNOSIS.md`


## Deploy no Vercel

Este repositório já existe no GitHub. Não use o fluxo **Clone** / **Deploy Button**, pois ele tenta criar outro repositório.

No Vercel:
1. Abra **Add New → Project**.
2. Em **Import Git Repository**, selecione `nlsoarez/portal-indicadores-cop-next`.
3. Use o time **Neural Lab**.
4. Mantenha a branch `main` e a raiz do projeto em `./`.
5. O Vercel detectará o `Dockerfile.vercel` na raiz e fará o build do container.
6. Clique em **Deploy**.

A integração Git do Vercel publica novos pushes diretamente, sem GitHub Actions.


### Persistência no Vercel

O container do Vercel não deve usar SQLite em `/tmp` como banco definitivo. O portal aceita, em ordem:

1. `DATABASE_URL`
2. `POSTGRES_URL`
3. `POSTGRES_URL_NON_POOLING`
4. SQLite via `COP_PORTAL_DB` apenas como fallback

Para uso real, conecte um PostgreSQL/Neon ao projeto no Vercel e disponibilize `DATABASE_URL` para Production e Preview. O schema é criado automaticamente na inicialização.

As planilhas Excel originais **não são arquivadas permanentemente** pelo portal. Elas são remontadas temporariamente durante o upload, processadas e removidas. O banco persiste os resultados normalizados, metadados do upload, cobertura dos indicadores, usuários, senhas e logs. Se for necessário manter cópia dos arquivos-fonte para auditoria, deve ser adicionada uma camada de object storage.


### Supabase dedicado

- Projeto: `portal-indicadores-cop`
- Project ref: `zuxdjfirvltktqsbvvlf`
- Região: `sa-east-1` (São Paulo)
- Schema da aplicação: `cop_portal`
- O schema não é usado pela Data API pública do portal; `anon` e `authenticated` não recebem privilégios nas tabelas.
- Em produção no Vercel, configure a URI PostgreSQL do **Transaction pooler** como `DATABASE_URL`.
- O driver `psycopg` roda com prepared statements desativados para compatibilidade com Supavisor em transaction mode.
