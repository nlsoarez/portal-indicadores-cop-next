# Auditoria estrutural pós-build

> Método: grafo de imports extraído por AST como fallback Graphify-style. O CLI oficial do Graphify não estava disponível no runtime; portanto este relatório não é apresentado como saída oficial do Graphify.

## Resultado

- Módulos analisados: 28
- Relações de import internas: 29
- Ciclos detectados: 0

## Módulos mais conectados

- `src.app` — grau 8 (entrada 0, saída 8)
- `src.infrastructure.repositories` — grau 7 (entrada 5, saída 2)
- `src.ui.analyst.shell` — grau 5 (entrada 1, saída 4)
- `src.ui.admin.shell` — grau 5 (entrada 1, saída 4)
- `src.domain.entities` — grau 5 (entrada 5, saída 0)
- `src.config.seed` — grau 5 (entrada 1, saída 4)
- `src.application.access_service` — grau 5 (entrada 3, saída 2)
- `src.application.dashboard_service` — grau 4 (entrada 1, saída 3)

## Avaliação

- Nenhuma dependência circular interna foi encontrada.
- A autorização está concentrada em `src.application.access_service`, enquanto persistência fica em `src.infrastructure.repositories`.
- As experiências admin/analista estão em shells separados; não há dependência entre `src.ui.admin` e `src.ui.analyst`.
- Regras específicas da Preventiva estão isoladas em `src.features.segments.preventiva` e não vazam para o domínio global.
- O próximo risco de acoplamento será a migração dos parsers legados; eles devem entrar como adapters por fonte, não dentro dos shells.
