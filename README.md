# Portal de Indicadores COP — Next

Nova geração arquitetural do portal de indicadores, construída sem alterar o repositório de referência.

## O que já está implementado

- Modelo relacional: usuários, roles, segmentos, memberships, indicadores, resultados, uploads e logs de acesso.
- Autorização server-side com fail-closed.
- `AdminShell` e `AnalystShell` visual e funcionalmente separados.
- Seletor de segmento para admin com limpeza de estado na troca.
- Preventiva cadastrada com Daniel, Rosana, Carlos e Maristella.
- Nome completo persistido e nome curto na interface.
- Senha inicial `claro123`, armazenada apenas como hash PBKDF2, com troca obrigatória.
- Último acesso disponível para administração.
- Estrutura para média de equipe sem expor linhas individuais dos colegas.
- **Cobertura dos dados por indicador:** cada processamento registra a maior data real encontrada no arquivo (`data_through`), separada da data/hora do upload. Admin e analista visualizam "Dados até DD/MM/AAAA".
- Histórico do arquivo/fonte que originou a cobertura mais recente de cada indicador.
- Testes de isolamento de dados, contexto de segmento e atualização da cobertura dos indicadores.
- **Sem GitHub Actions.** O repositório não usa `.github/workflows/`.

Este portal não possui módulo de escala.

## Fontes já migradas

### Preventiva

- **Chat 10 min** — fonte Chat TOA, meta 75%, leitura de `INDICADOR_TMA_DENTRO`, filtro RJO, mês mais recente e membership do segmento.
- **Tempo de Validação do Formulário** — fonte Indicadores TOA, meta 80%, `INDICADOR=1` como aderente, Regional Leste, mês mais recente e membership do segmento.
- Resultados são persistidos por dia/analista.
- Reupload do mesmo mês substitui aquele mês em vez de duplicar resultados.
- A visão do analista consolida o mês ponderando aderência pelo volume e compara com a média da equipe.

## Contrato dos importadores

Quando um parser processar uma planilha, ele deve:

1. registrar o upload com `IndicatorFreshnessService.start_upload(...)`;
2. calcular a maior data válida realmente presente para cada indicador;
3. chamar `record_indicator_data_through(...)` para cada indicador processado.

A data exibida ao usuário é a cobertura real do indicador, não a data do envio do arquivo.

## Importante

A fundação de rastreamento e os parsers de Chat/Validação da Preventiva já estão integrados. As demais fontes do portal legado ainda devem ser migradas por adapters independentes.

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
