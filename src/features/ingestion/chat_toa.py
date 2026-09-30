from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.breakdowns import add_ratio, is_night, materialize, minutes_to_seconds, new_bucket
from src.features.ingestion.excel import ImportValidationError
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, excel_hour, iter_rows, normalize_login

SOURCE_KEY = "chat_toa"
INDICATOR_KEY = "chat_10m"
SHEET_CANDIDATES = ("Analítico CHAT TOA", "Analitico CHAT TOA", "CHAT TOA")


def parse_chat_toa(raw_bytes: bytes, allowed_logins: set[str]) -> ParsedIndicatorBatch:
    allowed = {login.strip().upper() for login in allowed_logins}
    required = {"FECHAMENTO_COPREDE_LOGIN_ANALISTA", "ABERTURA_ANOMES", "INDICADOR_TMA_DENTRO", "CHAT_INICIO"}
    optional = {
        "ABERTURA_HORA", "FECHAMENTO_COPREDE_BASE_ANALISTA",
        "FECHAMENTO_FILA", "FECHAMENTO_TIPO_FILA", "MINUTOS_TMA",
        "IN_GRUPO",
    }
    aggregates: dict[tuple[int, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    breakdowns = new_bucket()
    latest_anomes = 0

    for row in iter_rows(
        raw_bytes,
        sheet_candidates=SHEET_CANDIDATES,
        header_row=4,
        required_headers=required,
        optional_headers=optional,
    ):
        login = normalize_login(row.get("FECHAMENTO_COPREDE_LOGIN_ANALISTA"))
        if not login:
            continue
        anomes = as_int(row.get("ABERTURA_ANOMES"))
        period = excel_date(row.get("CHAT_INICIO"))
        indicator = as_float(row.get("INDICADOR_TMA_DENTRO"), -1)
        if anomes <= 0 or not period or indicator not in (0.0, 1.0):
            continue

        hour_num = as_int(row.get("ABERTURA_HORA"), -1)
        hour = hour_num if 0 <= hour_num <= 23 else excel_hour(row.get("CHAT_INICIO"))
        tma_seconds = minutes_to_seconds(row.get("MINUTOS_TMA"))

        if login in allowed:
            latest_anomes = max(latest_anomes, anomes)
            aggregates[(anomes, login, period)][0] += indicator
            aggregates[(anomes, login, period)][1] += 1
            for dimension, dimension_value in (
                ("overall", "Total"),
                ("group", row.get("IN_GRUPO")),
                ("hour", hour),
                ("base", row.get("FECHAMENTO_COPREDE_BASE_ANALISTA")),
                ("queue", row.get("FECHAMENTO_FILA")),
                ("queue_type", row.get("FECHAMENTO_TIPO_FILA")),
            ):
                add_ratio(
                    breakdowns,
                    anomes=anomes,
                    scope="team",
                    login=login,
                    period=period,
                    dimension=dimension,
                    dimension_value=dimension_value,
                    successes=indicator,
                    volume=1,
                    tma_seconds=tma_seconds,
                )
        elif is_night(hour):
            add_ratio(
                breakdowns,
                anomes=anomes,
                scope="external",
                login=login,
                period=period,
                dimension="external_hour",
                dimension_value=hour if hour is not None else "Madrugada",
                successes=indicator,
                volume=1,
                tma_seconds=tma_seconds,
            )

    if latest_anomes <= 0:
        raise ImportValidationError("O arquivo de Chat TOA não possui dados dos usuários deste segmento.")

    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows = []
    for (anomes, login, period), (adherent, volume) in sorted(aggregates.items()):
        if anomes == latest_anomes and volume > 0:
            rows.append({
                "login": login,
                "period": period,
                "data_month": data_month,
                "value": round(adherent / volume * 100, 1),
                "volume": int(volume),
            })
    if not rows:
        raise ImportValidationError("O arquivo de Chat TOA não possui dados dos usuários deste segmento.")

    return ParsedIndicatorBatch(
        SOURCE_KEY,
        INDICATOR_KEY,
        max(r["period"] for r in rows),
        tuple(rows),
        (data_month,),
        materialize(breakdowns, latest_anomes),
    )
