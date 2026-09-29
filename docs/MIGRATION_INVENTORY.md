# Inventário funcional

## MANTER

- Processamento de planilhas em Python.
- Cache de processamento por conteúdo/versão.
- Carregamento seletivo de fontes conforme necessidade.
- Tratamento de múltiplos schemas de origem quando já testado.
- Testes existentes dos parsers e semântica dos indicadores.
- Conceito de senha inicial com troca obrigatória, mantendo apenas hashes.

## REFATORAR

- `app.py`: quebrar em shells e features por domínio.
- `processors.py`: dividir por fonte/indicador e separar parsing de autorização.
- `config.py`: remover usuários, memberships e permissões; manter apenas configuração técnica de fontes/indicadores.
- `auth.py`: separar autenticação, upload e persistência.
- Escopos de coordenadores/matrículas: migrar para tabelas `users`, `roles`, `segments`, `user_segments`.
- Tabs baseadas em texto: migrar para rotas/feature registry.
- Uploads globais por chave fixa: escopar por `segment_id` e fonte.

## DESCARTAR

- Regras de acesso implementadas apenas por visibilidade de UI.
- Condicionais específicas de usuário dentro da composição visual.
- Listas hardcoded de equipe como fonte de verdade de autorização.
- Acoplamento de cores/labels de indicadores ao mesmo módulo que define equipe/permissões.
- Scripts de patch ad-hoc como parte da arquitetura de produção.

## NOVO

- `Segment` como entidade persistida.
- `user_segments` e roles persistidos.
- `AdminShell` e `AnalystShell` distintos.
- Auditoria/último acesso.
- `indicator_definitions` e `indicator_results` por segmento.
- Escala por usuário + segmento + dia.
- Estado de UI segment-scoped com limpeza na troca de segmento.
- Preventiva com Daniel, Rosana, Carlos e Maristella.
- Testes server-side de isolamento entre analistas.
