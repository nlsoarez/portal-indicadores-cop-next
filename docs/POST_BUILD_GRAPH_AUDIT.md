# Auditoria estrutural pós-build

> Método: grafo de imports extraído por AST como fallback Graphify-style. O CLI oficial do Graphify não foi executado neste runtime; este documento não é apresentado como saída oficial do Graphify.

## Resultado atual

- Módulos Python analisados: 53
- Relações internas de import: 89
- Ciclos detectados: 0

## Módulos de maior centralidade

- `src.infrastructure.repositories` — grau 10
- `src.ui.admin.shell` — grau 10
- `src.features.ingestion.models` — grau 9
- `src.domain.entities` — grau 9
- `src.features.ingestion.registry` — grau 9
- `src.application.upload_service` — grau 9
- `src.app` — grau 9
- `src.application.access_service` — grau 8
- `src.config.seed` — grau 8

## Caminho de ingestão

```text
AdminShell
  -> UploadProcessingService
     -> source_catalog (7 fontes)
     -> registry
        -> residential_indicators
        -> enterprise_indicators
        -> dpa
        -> productivity
        -> closing_toa_sir
        -> chat_toa
        -> toa_indicators
     -> IndicatorRepository
     -> IndicatorFreshnessService
```

## Avaliação

- Nenhum ciclo interno foi encontrado.
- Os parsers estão fora dos shells e separados por fonte.
- A UI administrativa não contém regras de cálculo dos indicadores.
- Autorização continua centralizada em `AccessService`.
- As fontes grandes usam módulos comuns de streaming/pivot, evitando duplicação de lógica de leitura.
- O módulo mais sensível a crescimento continua sendo `repositories.py`; uma próxima refatoração pode dividi-lo em repositórios por agregado sem alterar o contrato dos serviços.
