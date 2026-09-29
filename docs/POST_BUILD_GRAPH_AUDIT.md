# Auditoria estrutural pós-build

> Método: grafo de imports extraído por AST como fallback Graphify-style. O CLI oficial do Graphify não estava disponível no runtime; portanto este relatório não é apresentado como saída oficial do Graphify.

## Resultado após migração de Chat e Validação

- Módulos analisados: 35
- Relações de import internas: 44
- Ciclos detectados: 0

## Módulos mais conectados

- `src.infrastructure.repositories` — grau 9 (entrada 7, saída 2)
- `src.app` — grau 8 (entrada 0, saída 8)
- `src.domain.entities` — grau 7 (entrada 7, saída 0)
- `src.application.access_service` — grau 7 (entrada 5, saída 2)
- `src.ui.admin.shell` — grau 7 (entrada 1, saída 6)
- `src.application.upload_service` — grau 7 (entrada 1, saída 6)
- `src.ui.analyst.shell` — grau 5 (entrada 1, saída 4)

## Novos caminhos relevantes

```text
AdminShell
  -> UploadProcessingService
     -> parser por fonte
        -> Chat TOA
        -> Indicadores TOA / Validação
     -> IndicatorRepository
        -> resultados diários por usuário
        -> resumo mensal ponderado
     -> IndicatorFreshnessService
        -> upload
        -> "dados até" por indicador

AnalystShell
  -> DashboardService
     -> dados individuais autorizados
     -> resumo mensal individual
     -> média agregada da equipe
     -> freshness
```

## Avaliação

- Nenhuma dependência circular interna foi encontrada.
- Chat e Validação foram isolados em adapters próprios em `src.features.ingestion`.
- Os parsers recebem apenas os logins autorizados do segmento; não possuem lista hardcoded da equipe.
- Reupload substitui apenas os meses presentes no arquivo para aquele indicador.
- A camada de leitura SQLite passou a fechar conexões explicitamente.
- Admin e analista continuam sem dependência direta entre seus shells.
- O próximo risco de centralidade está em `src.infrastructure.repositories`; novas fontes não devem adicionar regras de parsing nesse módulo.
