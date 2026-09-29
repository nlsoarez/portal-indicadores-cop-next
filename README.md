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
- Testes de isolamento de dados e de contexto de segmento.
- **Sem GitHub Actions.** O repositório não usa `.github/workflows/`.

## Importante

Esta fundação ainda não migra os parsers e dashboards do portal legado. O próximo passo técnico é mover cada fonte de `src/processors.py` para adapters/features independentes e registrar os indicadores por segmento.

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
