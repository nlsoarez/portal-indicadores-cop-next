from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UploadSource:
    key: str
    label: str
    filename_hint: str
    description: str
    target_segment_slugs: tuple[str, ...]
    adapter_key: str | None
    integration_note: str | None = None

    @property
    def implemented(self) -> bool:
        return self.adapter_key is not None


UPLOAD_SOURCES: tuple[UploadSource, ...] = (
    UploadSource(
        key="residential_indicators",
        label="Indicadores Residencial",
        filename_hint="Analítico Indicadores Residencial",
        description="Indicadores operacionais do segmento Residencial.",
        target_segment_slugs=("residencial",),
        adapter_key=None,
        integration_note="Schema real validado; adapter funcional será migrado do legado.",
    ),
    UploadSource(
        key="enterprise_indicators",
        label="Indicadores Empresarial",
        filename_hint="Analítico Empresarial",
        description="ETIT por evento e indicadores do segmento Empresarial.",
        target_segment_slugs=("empresarial",),
        adapter_key=None,
        integration_note="Schema real validado; adapter funcional será migrado do legado.",
    ),
    UploadSource(
        key="dpa",
        label="Ocupação DPA",
        filename_hint="Ocupação DPA 2026",
        description="Ocupação DPA por analista.",
        target_segment_slugs=("residencial", "empresarial", "preventiva"),
        adapter_key=None,
        integration_note="Fonte baseada em pivot cache; parser do legado será isolado em adapter próprio.",
    ),
    UploadSource(
        key="productivity",
        label="Produtividade COP Rede",
        filename_hint="Produtividade COP Rede 2026 - Analítico",
        description="Volumes e produtividade diária dos usuários.",
        target_segment_slugs=("residencial", "empresarial", "preventiva"),
        adapter_key=None,
        integration_note="Header real identificado na linha 11; integração funcional pendente.",
    ),
    UploadSource(
        key="closing_toa_sir",
        label="Fechamento TOA x SIR",
        filename_hint="Fechamento TOA x SIR",
        description="Assertividade de fechamento TOA x SIR.",
        target_segment_slugs=("residencial", "empresarial", "preventiva"),
        adapter_key=None,
        integration_note="Fonte baseada em pivot cache; parser será migrado sem depender das tabelas visíveis.",
    ),
    UploadSource(
        key="chat_toa",
        label="Chat TOA",
        filename_hint="Analítico TOA Chat",
        description="Aderência do indicador Chat 10 min.",
        target_segment_slugs=("preventiva",),
        adapter_key="chat_toa",
    ),
    UploadSource(
        key="toa_indicators",
        label="Indicadores TOA",
        filename_hint="Analitico Indicadores TOA",
        description="Indicadores TOA, incluindo Tempo de Validação do Formulário.",
        target_segment_slugs=("preventiva",),
        adapter_key="toa_indicators",
        integration_note="Tempo de Validação já funcional; demais métricas do mesmo arquivo serão adicionadas no adapter.",
    ),
)

UPLOAD_SOURCE_BY_KEY = {source.key: source for source in UPLOAD_SOURCES}
