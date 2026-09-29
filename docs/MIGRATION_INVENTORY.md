# Inventário de migração

## Migrado

### Identidade e autorização

- User / Role / Segment / UserSegment.
- `user_performance_segments` para separar visibilidade de desempenho.
- Admin, Subadmin e Analista.
- Último acesso.
- Isolamento server-side.

### Pessoas

- Preventiva com Daniel, Rosana, Carlos e Maristella.
- Maristella removida do Residencial.
- Marcelo de Souza Almeida (`F104752`) no Residencial.
- Bruno, Leandro, Kelly e Marley convertidos para Subadmin.
- Equipes comuns Residencial e Empresarial migradas do legado.

### Sete fontes oficiais

- Indicadores Residencial → 4 indicadores.
- Indicadores Empresarial → ETIT por Evento.
- Ocupação DPA → DPA Oficial via pivot cache.
- Produtividade COP Rede → produtividade média diária.
- Fechamento TOA x SIR → assertividade via pivot cache.
- Chat TOA → Chat 10 min.
- Indicadores TOA → Tempo de Validação + Tarefas Canceladas.

### Infraestrutura funcional

- Catálogo global de fontes.
- Upload único por fonte, independente do segmento selecionado.
- Streaming de XLSX para arquivos grandes.
- Batches múltiplos por arquivo.
- Resultado diário + competência mensal.
- Freshness / “Dados até”.
- Reupload sem duplicação.
- Separação de resultados dos líderes das médias dos analistas.

## Descartado

- Escala: fora do escopo deste portal.
- Listas hardcoded dentro dos parsers como regra de autorização.
- Upload permitido a líderes/subadmins.
- Condicionais de segurança implementadas apenas na UI.
- Dependência do estado visual de filtros/slicers do Excel para DPA e Fechamento.
- Filtro fixo `RJO` no Chat TOA, incompatível com as filas QOE reais da Preventiva.

## Ainda pendente antes de produção

- Escolher persistência definitiva para hospedagem (SQLite persistente versus PostgreSQL/Supabase).
- Implantar o portal em um ambiente acessível aos usuários.
- Validar visualmente a experiência com os três perfis no navegador publicado.
- Refinar dashboards/gráficos além das tabelas e KPIs já existentes.
