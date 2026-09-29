from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.features.ingestion.chat_toa import parse_chat_toa
from src.features.ingestion.closing_toa_sir import parse_closing_toa_sir
from src.features.ingestion.dpa import parse_dpa
from src.features.ingestion.enterprise_indicators import parse_enterprise_indicators
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.productivity import parse_productivity
from src.features.ingestion.residential_indicators import parse_residential_indicators
from src.features.ingestion.toa_indicators import parse_toa_indicators, parse_toa_validation

Parser = Callable[[bytes, set[str]], tuple[ParsedIndicatorBatch, ...]]


@dataclass(frozen=True)
class SourceAdapter:
    key: str
    label: str
    indicator_keys: tuple[str, ...]
    parser: Parser


def _single(parser: Callable[[bytes, set[str]], ParsedIndicatorBatch]) -> Parser:
    def wrapped(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
        return (parser(raw_bytes, allowed_logins),)
    return wrapped


SOURCE_ADAPTERS: dict[str, SourceAdapter] = {
    "chat_toa": SourceAdapter(
        key="chat_toa",
        label="Chat TOA",
        indicator_keys=("chat_10m",),
        parser=_single(parse_chat_toa),
    ),
    # Chave mantida para compatibilidade com testes/rotas anteriores.
    "toa_validation": SourceAdapter(
        key="toa_validation",
        label="Indicadores TOA — Tempo de Validação",
        indicator_keys=("validacao_20m",),
        parser=_single(parse_toa_validation),
    ),
    "toa_indicators": SourceAdapter(
        key="toa_indicators",
        label="Indicadores TOA",
        indicator_keys=("validacao_20m", "toa_cancellation_rate"),
        parser=parse_toa_indicators,
    ),
    "residential_indicators": SourceAdapter(
        key="residential_indicators",
        label="Indicadores Residencial",
        indicator_keys=(
            "res_etit_fibra_hfc",
            "res_etit_gpon",
            "res_assert_fibra_hfc",
            "res_assert_gpon",
        ),
        parser=parse_residential_indicators,
    ),
    "enterprise_indicators": SourceAdapter(
        key="enterprise_indicators",
        label="Indicadores Empresarial",
        indicator_keys=("emp_etit_event",),
        parser=parse_enterprise_indicators,
    ),
    "productivity": SourceAdapter(
        key="productivity",
        label="Produtividade COP Rede",
        indicator_keys=("productivity_avg_daily",),
        parser=parse_productivity,
    ),
    "dpa": SourceAdapter(
        key="dpa",
        label="Ocupação DPA",
        indicator_keys=("dpa_official",),
        parser=parse_dpa,
    ),
    "closing_toa_sir": SourceAdapter(
        key="closing_toa_sir",
        label="Fechamento TOA x SIR",
        indicator_keys=("closing_assertiveness",),
        parser=parse_closing_toa_sir,
    ),
}
