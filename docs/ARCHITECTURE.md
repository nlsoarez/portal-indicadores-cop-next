# Arquitetura proposta

## Princípio

O novo portal trata `Segment` como entidade, não como texto/filtro. Todos os acessos a dados individuais passam por `AccessService` antes de chegar aos repositórios.

```text
Login -> User -> Roles
              -> UserSegments -> Segment
                                -> IndicatorDefinitions
                                -> IndicatorResults
                                -> Uploads

Request -> AccessContext -> AccessService -> Repository -> Data
```

## Separação de experiência

- `AdminShell`: gestão total; único perfil com upload; consulta analistas e possui aba exclusiva para líderes.
- `SubadminShell`: visão de liderança somente leitura; consulta dados individuais dos analistas, sem upload e sem acesso aos dados individuais de outros líderes.
- `AnalystShell`: experiência individual; recebe apenas dados próprios e agregados da equipe.

## Regras centrais

1. Todo usuário, inclusive admin, precisa de membership explícito no segmento.
2. Analista não recebe entidade individual de outro usuário.
3. Média da equipe é calculada por agregação no repositório, sem expor linhas dos colegas.
4. Troca de segmento limpa estado/cache segmentado.
5. Identidade/roles/segmentos ficam em banco relacional; planilhas permanecem como fontes de ingestão.
6. Indicadores são definitions + results, permitindo variar por segmento sem criar colunas por segmento.\n7. Subadmins são persistidos fora da role `analyst`; seus resultados podem existir, mas não entram nas médias dos analistas.\n8. Upload é autorizado exclusivamente para `RoleCode.ADMIN` no backend.

## Fora de escopo

O portal não possui módulo de escala.

## Banco

Implementado inicialmente em SQLite por portabilidade local. O schema evita recursos exclusivos do SQLite e pode migrar para PostgreSQL posteriormente.
