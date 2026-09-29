from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UploadSource:
    key: str
    label: str
    filename_hint: str
    description: str
    target_segment_slugs: tuple[str, ...]
    adapter_key: str

    @property
    def implemented(self) -> bool:
        return True


UPLOAD_SOURCES: tuple[UploadSource, ...] = (
    UploadSource(
        "residential_indicators",
        "Indicadores Residencial",
        "Analítico Indicadores Residencial",
        "ETIT Fibra HFC, ETIT GPON e assertividade de acionamento.",
        ("residencial",),
        "residential_indicators",
    ),
    UploadSource(
        "enterprise_indicators",
        "Indicadores Empresarial",
        "Analítico Empresarial",
        "ETIT por Evento do segmento Empresarial.",
        ("empresarial",),
        "enterprise_indicators",
    ),
    UploadSource(
        "dpa",
        "Ocupação DPA",
        "Ocupação DPA 2026",
        "DPA oficial extraído do pivot cache da planilha.",
        ("residencial", "empresarial", "preventiva"),
        "dpa",
    ),
    UploadSource(
        "productivity",
        "Produtividade COP Rede",
        "Produtividade COP Rede 2026 - Analítico",
        "Volume diário de produtividade por usuário.",
        ("residencial", "empresarial", "preventiva"),
        "productivity",
    ),
    UploadSource(
        "closing_toa_sir",
        "Fechamento TOA x SIR",
        "Fechamento TOA x SIR",
        "Assertividade de fechamento TOA x SIR no turno Madrugada/Leste.",
        ("residencial", "empresarial", "preventiva"),
        "closing_toa_sir",
    ),
    UploadSource(
        "chat_toa",
        "Chat TOA",
        "Analítico TOA Chat",
        "Aderência do indicador Chat 10 min.",
        ("preventiva",),
        "chat_toa",
    ),
    UploadSource(
        "toa_indicators",
        "Indicadores TOA",
        "Analitico Indicadores TOA",
        "Tempo de Validação do Formulário e Tarefas Canceladas.",
        ("preventiva",),
        "toa_indicators",
    ),
)

UPLOAD_SOURCE_BY_KEY = {source.key: source for source in UPLOAD_SOURCES}
