from __future__ import annotations

from collections import defaultdict
from datetime import date

from src.features.ingestion.breakdowns import add_ratio, materialize, new_bucket
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.pivot_cache import iter_pivot_records

SOURCE_KEY = "closing_toa_sir"
REQUIRED = {
    "LOGIN_VALIDOU_FECHAMENTO", "TURNO", "ANOMES", "VOLUME",
    "FECHAMENTO_ASSERTIVO", "IN_REGIONAL", "DIA",
}
OPTIONAL = {"IN_GRUPO", "DEMANDA", "CAUSA_TOA", "CAUSA_SIR"}


def parse_closing_toa_sir(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    aggregates: dict[tuple[int, str, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
    breakdowns = new_bucket()
    latest_anomes = 0

    for record in iter_pivot_records(raw_bytes, required_fields=REQUIRED, optional_fields=OPTIONAL):
        login = str(record.get("LOGIN_VALIDOU_FECHAMENTO") or "").strip().upper()
        turn = str(record.get("TURNO") or "").strip()
        region = str(record.get("IN_REGIONAL") or "").strip()
        if not login or turn.upper() != "MADRUGADA" or region.upper() != "LESTE":
            continue
        try:
            anomes = int(float(record.get("ANOMES") or 0))
            day = int(float(record.get("DIA") or 0))
            volume = float(record.get("VOLUME") or 0)
            assertive = float(record.get("FECHAMENTO_ASSERTIVO") or 0)
        except (TypeError, ValueError):
            continue
        if anomes <= 0 or day <= 0 or volume <= 0:
            continue
        year, month = divmod(anomes, 100)
        try:
            period = date(year, month, day).isoformat()
        except ValueError:
            continue
        if login in allowed:
            latest_anomes = max(latest_anomes, anomes)
            aggregates[(anomes, login, day)][0] += assertive
            aggregates[(anomes, login, day)][1] += volume
            for dimension, dimension_value in (
                ("overall", "Total"), ("region", region), ("group", record.get("IN_GRUPO")), ("turn", turn),
                ("demand", record.get("DEMANDA")), ("cause_toa", record.get("CAUSA_TOA")),
                ("cause_sir", record.get("CAUSA_SIR")),
            ):
                add_ratio(breakdowns, anomes=anomes, scope="team", login=login, period=period,
                          dimension=dimension, dimension_value=dimension_value,
                          successes=assertive, volume=volume)
        else:
            add_ratio(breakdowns, anomes=anomes, scope="external", login=login, period=period,
                      dimension="external_hour", dimension_value="Madrugada",
                      successes=assertive, volume=volume)

    if latest_anomes <= 0:
        return ()

    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows: list[dict] = []
    year, month = divmod(latest_anomes, 100)
    for (anomes, login, day), (assertive, volume) in sorted(aggregates.items()):
        if anomes != latest_anomes or volume <= 0:
            continue
        try:
            period = date(year, month, day).isoformat()
        except ValueError:
            continue
        rows.append({
            "login": login, "period": period, "data_month": data_month,
            "value": round(assertive / volume * 100, 1), "volume": int(round(volume)),
        })
    if not rows:
        return ()
    return (
        ParsedIndicatorBatch(
            SOURCE_KEY, "closing_assertiveness", max(row["period"] for row in rows), tuple(rows),
            (data_month,), materialize(breakdowns, latest_anomes),
        ),
    )
