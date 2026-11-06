"""Operational COP receipt delay for ETIT FIBRA HFC (Regional Leste).

Counts unique outages arriving at COP between 22:00 and 05:59:59.
Delay = DT_INICIO_CHEGOU_COP_FO - DT_INICIO_SISTEMA.
Independent of ETIT adherence and of the assigned analyst's team.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.features.ingestion.breakdowns import add_ratio, materialize, new_bucket
from src.features.ingestion.xlsx_stream import as_int

_SCOPE_LOGIN = "__COP_HFC_ARRIVAL__"
_BR_TZ = ZoneInfo("America/Sao_Paulo")


def parse_source_datetime(value: object | None) -> datetime | None:
    """Parse original source's local timestamp, preserving date across midnight.

    Date-only values cannot be used to decide whether arrival was on shift.
    Excel numeric serials are supported, with fractional-day time preserved.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(_BR_TZ).replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return None

    raw = str(value).strip()
    if not raw or raw.upper() in {"NONE", "NAN", "NAT"}:
        return None
    if ":" in raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(_BR_TZ).replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
        for fmt in (
            "%d/%m/%Y %H:%M:%S.%f", "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        ):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None

    try:
        serial = float(raw)
    except (ValueError, OverflowError):
        return None
    if not 1000 < serial < 1000000 or abs(serial - round(serial)) < 1e-10:
        return None
    try:
        return datetime(1899, 12, 30) + timedelta(days=serial)
    except (OverflowError, ValueError):
        return None


def in_night_arrival(value: datetime) -> bool:
    """Business time window is the COP arrival clock, not outage start."""
    return value.hour >= 22 or value.hour <= 5


@dataclass(frozen=True)
class _Arrival:
    group: str
    started: datetime | None
    received: datetime
    conflict: bool = False


class HFCCopArrival:
    def __init__(self) -> None:
        self._events: dict[tuple[int, str], _Arrival] = {}
        self._missing_id_seq = 0

    def add(self, row: dict) -> None:
        anomes = as_int(row.get("ANOMES"))
        if anomes <= 0:
            return
        received = parse_source_datetime(row.get("DT_INICIO_CHEGOU_COP_FO"))
        if received is None or not in_night_arrival(received):
            return
        started = parse_source_datetime(row.get("DT_INICIO_SISTEMA"))
        group = str(row.get("IN_GRUPO") or "").strip().upper() or "SEM GRUPO"
        event_id = str(row.get("ID_MOSTRA") or "").strip().upper()
        if not event_id:
            # Missing ID cannot be de-duplicated. Count as a non-valid pair;
            # never silently treat an unidentifiable row as a unique outage.
            self._missing_id_seq += 1
            event_id = f"__SEM_ID__{self._missing_id_seq}"
            started = None
        key = (anomes, event_id)
        candidate = _Arrival(group, started, received)
        previous = self._events.get(key)
        if previous is None:
            self._events[key] = candidate
        elif previous != candidate:
            # Conflicting data for one outage: count once, but do not
            # assert an average for an ambiguous timeline.
            self._events[key] = _Arrival(
                previous.group, None, previous.received, conflict=True
            )

    def to_breakdowns(self, latest_anomes: int) -> tuple[dict, ...]:
        bucket = new_bucket()
        for (anomes, _), record in self._events.items():
            if anomes != latest_anomes:
                continue
            delay = (
                (record.received - record.started).total_seconds()
                if record.started is not None and not record.conflict else None
            )
            valid = delay is not None and delay >= 0
            for dimension, value in (
                ("cop_arrival_overall", "Total"),
                ("cop_arrival_group", record.group),
            ):
                add_ratio(
                    bucket,
                    anomes=anomes,
                    scope="operational",
                    login=_SCOPE_LOGIN,
                    period=record.received.date().isoformat(),
                    dimension=dimension,
                    dimension_value=value,
                    successes=1 if valid else 0,
                    volume=1,
                    tma_seconds=delay if valid else None,
                )
        return materialize(bucket, latest_anomes)
