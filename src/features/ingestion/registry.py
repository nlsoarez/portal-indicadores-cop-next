from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.features.ingestion.chat_toa import parse_chat_toa
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.toa_validation import parse_toa_validation


Parser = Callable[[bytes, set[str]], ParsedIndicatorBatch]


@dataclass(frozen=True)
class SourceAdapter:
    key: str
    label: str
    indicator_key: str
    parser: Parser


SOURCE_ADAPTERS: dict[str, SourceAdapter] = {
    "chat_toa": SourceAdapter(
        key="chat_toa",
        label="Chat TOA — Chat 10 min",
        indicator_key="chat_10m",
        parser=parse_chat_toa,
    ),
    "toa_validation": SourceAdapter(
        key="toa_validation",
        label="Indicadores TOA — Tempo de Validação",
        indicator_key="validacao_20m",
        parser=parse_toa_validation,
    ),
    "toa_indicators": SourceAdapter(
        key="toa_indicators",
        label="Indicadores TOA",
        indicator_key="validacao_20m",
        parser=parse_toa_validation,
    ),
}


def sources_for_indicator_keys(indicator_keys: set[str]) -> tuple[SourceAdapter, ...]:
    return tuple(
        source
        for source in SOURCE_ADAPTERS.values()
        if source.indicator_key in indicator_keys
    )
