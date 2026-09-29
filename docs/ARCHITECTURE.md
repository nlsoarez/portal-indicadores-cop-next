# Arquitetura

## Princípio

`Segment` é uma entidade persistida. Autorização, escopo de leitura e escopo de desempenho são resolvidos no backend antes de os dados chegarem à interface.

```text
Login -> User -> Role
              -> UserSegments (segmentos que pode consultar)
              -> UserPerformanceSegments (onde seu próprio KPI é contabilizado)

AdminShell ------> UploadProcessingService ----> Source Registry ----> 7 adapters
     |                       |                         |
     |                       |                         +-> XLSX streaming / pivot cache
     |                       +-> IndicatorRepository
     |                       +-> IndicatorFreshnessService
     |
     +-> Analistas / Líderes / Indicadores / Uploads / Auditoria

SubadminShell ---> AccessService ---> dados individuais dos analistas (somente leitura)
AnalystShell ----> AccessService ---> somente o próprio usuário
```

## Perfis

- `admin`: visão total; único perfil com upload.
- `subadmin`: líderes; leitura gerencial dos analistas; sem upload; não consulta dados individuais de outro líder.
- `analyst`: somente dados próprios.

Os quatro líderes são removidos da role `analyst`, portanto não aparecem nas listas ou médias dos usuários comuns.

## Ingestão

O catálogo `src.features.ingestion.source_catalog` define exatamente as sete fontes oficiais. `UploadProcessingService.process_global_source()` recebe o arquivo uma vez, calcula a união das matrículas elegíveis, executa o parser uma única vez e distribui os batches aos segmentos correspondentes.

Cada adapter retorna um ou mais `ParsedIndicatorBatch`. Um mesmo arquivo pode alimentar vários indicadores, como:

- Indicadores Residencial → quatro indicadores;
- Indicadores TOA → Validação + Tarefas Canceladas.

Arquivos XLSX grandes usam leitura streaming em `xlsx_stream.py`. DPA e Fechamento TOA x SIR usam `pivot_cache.py`.

## Persistência temporal

`indicator_results` guarda:

- `period`: data real do evento, usada para evolução diária;
- `data_month`: mês de competência da fonte, usado para consolidação/reupload mensal.

Isso é necessário porque uma fonte de setembro pode conter evento real de 31/08.

## Regras centrais

1. Upload só é aceito quando `ctx.is_admin` no backend.
2. Analista não recebe registro individual de outro analista.
3. Subadmin recebe registros individuais apenas de analistas.
4. Admin pode consultar analistas e líderes dentro do escopo de desempenho correspondente.
5. Médias de equipe incluem somente role `analyst`.
6. Resultados dos líderes são persistidos, mas não contaminam a média dos analistas.
7. Troca de segmento limpa estado segmentado da UI.
8. Reupload substitui somente a competência afetada para o indicador.
9. `indicator_freshness` registra a maior data real processada, separada da data do upload.
10. Não existe módulo de escala.
11. Não há GitHub Actions.

## Banco

A fundação atual usa SQLite com migrações aditivas de colunas para manter compatibilidade com bases já criadas. Antes de uma implantação multi-instância/efêmera, a persistência deve ser avaliada para PostgreSQL/Supabase ou armazenamento equivalente.
