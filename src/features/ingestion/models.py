from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedIndicatorBatch:
    source_key: str
    indicator_key: str
    data_through: str
    rows: tuple[dict, ...]
    months: tuple[str, ...]
    breakdowns: tuple[dict, ...] = ()

    @property
    def analyst_count(self) -> int:
        return len({str(row["login"]).upper() for row in self.rows})

    @property
    def total_volume(self) -> int:
        return sum(int(row.get("volume", 0) or 0) for row in self.rows)
