from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from calendar import monthrange

from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.pivot_cache import iter_pivot_records

SOURCE_KEY = "dpa"
REQUIRED = {"USUARIO_LOGIN", "ANOMES", "TEMPO_USO_SEC", "HORARIO_JORNADA_SEC"}
OPTIONAL = {"DATA"}


def parse_dpa(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    aggregates: dict[tuple[int, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    latest_anomes = 0

    for record in iter_pivot_records(
        raw_bytes,
        required_fields=REQUIRED,
        optional_fields=OPTIONAL,
    ):
        login = str(record.get("USUARIO_LOGIN") or "").strip().upper()
        if login not in allowed:
            continue
        try:
            anomes = int(float(record.get("ANOMES") or 0))
        except (TypeError, ValueError):
            continue
        if anomes <= 0:
            continue
        latest_anomes = max(latest_anomes, anomes)
        period = _period(record.get("DATA"), anomes)
        try:
            usage = float(record.get("TEMPO_USO_SEC") or 0)
            journey = float(record.get("HORARIO_JORNADA_SEC") or 0)
        except (TypeError, ValueError):
            continue
        key = (anomes, login, period)
        aggregates[key][0] += usage
        aggregates[key][1] += journey

    if latest_anomes <= 0:
        return ()

    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows: list[dict] = []
    for (anomes, login, period), (usage, journey) in sorted(aggregates.items()):
        if anomes != latest_anomes or journey <= 0:
            continue
        rows.append(
            {
                "login": login,
                "period": period,
                "data_month": data_month,
                "value": round(usage / journey * 100, 1),
                "volume": int(round(journey)),
            }
        )
    if not rows:
        return ()

    data_through = max(row["period"] for row in rows)
    months = (data_month,)
    return (
        ParsedIndicatorBatch(SOURCE_KEY, "dpa_official", data_through, tuple(rows), months),
    )


def _period(value: object | None, anomes: int) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    if raw:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
        try:
            serial = float(raw)
            if serial > 1000:
                return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()
        except ValueError:
            pass
    year, month = divmod(anomes, 100)
    last_day = monthrange(year, month)[1]
    return date(year, month, last_day).isoformat()
