# Portal de Indicadores COP — Next

Nova geração arquitetural do portal de indicadores, construída sem alterar o repositório de referência.

## O que já está implementado

- Modelo relacional: usuários, roles, segmentos, memberships, indicadores, resultados, escala, uploads e logs de acesso.
- Autorização server-side com fail-closed.
- `AdminShell` e `AnalystShell` visual e funcionalmente separados.
- Seletor de segmento para admin com limpeza de estado na troca.
- Preventiva cadastrada com Daniel, Rosana, Carlos e Maristella.
- Nome completo persistido e nome curto na interface.
- Senha inicial `claro123`, armazenada apenas como hash PBKDF2, com troca obrigatória.
- Último acesso disponível para administração.
- Estrutura para média de equipe sem expor linhas individuais dos colegas.
- **Cobertura dos dados por indicador:** cada processamento pode registrar a maior data real encontrada no arquivo (`data_through`), separada da data/hora do upload. Admin e analista visualizam "Dados até DD/MM/AAAA".
- Histórico do arquivo/fonte que originou a cobertura mais recente de cada indicador.
- Testes de isolamento de dados, contexto de segmento e atualização da cobertura dos indicadores.
- **Sem GitHub Actions.** O repositório não usa `.github/workflows/`.

## Contrato dos importadores

Quando um parser processar uma planilha, ele deve:

1. registrar o upload com `IndicatorFreshnessService.start_upload(...)`;
2. calcular a maior data válida realmente presente para cada indicador;
3. chamar `record_indicator_data_through(...)` para cada indicador processado.

A data exibida ao usuário é a cobertura real do indicador, não a data do envio do arquivo.

## Importante

A fundação de rastreamento já está pronta. Os parsers legados ainda precisam ser migrados por fonte/segmento para alimentar automaticamente resultados e cobertura.

## Rodar

```bash
python -m unittest discover -s tests -v
streamlit run app.py
```

Login inicial de administração: `ADMIN` / `claro123`.

Analistas Preventiva usam suas matrículas com a mesma senha inicial e são obrigados a alterá-la no primeiro acesso.

## Documentação

- `docs/GRAPHIFY_DIAGNOSIS.md`
- `docs/ARCHITECTURE.md`
- `docs/MIGRATION_INVENTORY.md`
- `docs/POST_BUILD_GRAPH_AUDIT.md`
