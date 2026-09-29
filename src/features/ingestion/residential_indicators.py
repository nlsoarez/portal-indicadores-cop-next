from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.breakdowns import (
    add_ratio,
    decimal_hours_to_seconds,
    is_night,
    materialize,
    new_bucket,
    turn_from_hour,
)
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, excel_hour, iter_rows, normalize_login

SOURCE_KEY = "residential_indicators"
SHEET_CANDIDATES = ("Analitico", "Analítico", "Residencial", "Sheet1")
COL_INDICATOR = "INDICADOR_NOME_ICG"
COL_VOLUME = "VOLUME"
COL_VALUE = "INDICADOR"
COL_REGIONAL = "IN_REGIONAL"
COL_DATE = "DT_INICIO"
COL_ANOMES = "ANOMES"
COL_LOGIN_UNIFIED = "LOGIN_PRIMEIRO_ACIONAMENTO"
COL_LOGIN_FO = "LOGIN_PRIMEIRO_ACIONAMENTO_FO"
COL_LOGIN_GPON = "LOGIN_PRIMEIRO_ACIONAMENTO_GPON"
INDICATORS = {
    "ETIT FIBRA HFC": "res_etit_fibra_hfc",
    "ETIT GPON": "res_etit_gpon",
    "ASSERTIVIDADE ACIONAMENTO FIBRA HFC": "res_assert_fibra_hfc",
    "ASSERTIVIDADE ACIONAMENTO GPON": "res_assert_gpon",
}
HFC_INDICATORS = {"ETIT FIBRA HFC", "ASSERTIVIDADE ACIONAMENTO FIBRA HFC"}


def parse_residential_indicators(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    aggregates: dict[tuple[int, str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    breakdowns_by_indicator = {key: new_bucket() for key in INDICATORS.values()}
    latest_anomes = 0
    optional = {
        COL_LOGIN_UNIFIED, COL_LOGIN_FO, COL_LOGIN_GPON,
        "IN_GRUPO", "IN_CIDADE_UF", "IN_UF", "TURNO", "TECNOLOGIA",
        "SERVICO", "NATUREZA", "SINTOMA", "FERRAMENTA_ABERTURA",
        "FECHAMENTO", "SOLUCAO", "IMPACTO", "TMA", "TMR", "ID_MOSTRA",
    }
    required = {COL_INDICATOR, COL_VOLUME, COL_VALUE, COL_REGIONAL, COL_DATE, COL_ANOMES}

    for row in iter_rows(
        raw_bytes,
        sheet_candidates=SHEET_CANDIDATES,
        header_row=1,
        required_headers=required,
        optional_headers=optional,
        required_any=({COL_LOGIN_UNIFIED, COL_LOGIN_FO, COL_LOGIN_GPON},),
    ):
        indicator = str(row.get(COL_INDICATOR) or "").strip().upper()
        indicator_key = INDICATORS.get(indicator)
        if not indicator_key:
            continue
        region = str(row.get(COL_REGIONAL) or "").strip()
        if region.upper() != "LESTE":
            continue

        primary_login_col = COL_LOGIN_FO if indicator in HFC_INDICATORS else COL_LOGIN_GPON
        login = normalize_login(row.get(primary_login_col))
        if not login:
            login = normalize_login(row.get(COL_LOGIN_UNIFIED))
        if not login:
            continue

        anomes = as_int(row.get(COL_ANOMES))
        period = excel_date(row.get(COL_DATE))
        metric = as_float(row.get(COL_VALUE), -1)
        volume = as_float(row.get(COL_VOLUME), 0)
        if anomes <= 0 or not period or metric not in (0.0, 1.0) or volume <= 0:
            continue

        success = metric * volume
        hour = excel_hour(row.get(COL_DATE))
        turn = str(row.get("TURNO") or "").strip() or turn_from_hour(hour)
        service = row.get("SERVICO")
        tma_seconds = decimal_hours_to_seconds(row.get("TMA"))
        tmr_seconds = decimal_hours_to_seconds(row.get("TMR"))
        bucket = breakdowns_by_indicator[indicator_key]

        if login in allowed:
            latest_anomes = max(latest_anomes, anomes)
            key = (anomes, indicator_key, login, period)
            aggregates[key][0] += success
            aggregates[key][1] += volume
            dimensions = (
                ("overall", "Total"),
                ("incident", row.get("ID_MOSTRA")),
                ("region", region),
                ("group", row.get("IN_GRUPO")),
                ("city", row.get("IN_CIDADE_UF")),
                ("uf", row.get("IN_UF")),
                ("turn", turn),
                ("hour", hour),
                ("technology", row.get("TECNOLOGIA")),
                ("service", service),
                ("nature", row.get("NATUREZA")),
                ("symptom", row.get("SINTOMA")),
                ("tool", row.get("FERRAMENTA_ABERTURA")),
                ("closure", row.get("FECHAMENTO")),
                ("solution", row.get("SOLUCAO")),
                ("impact", row.get("IMPACTO")),
            )
            for dimension, dimension_value in dimensions:
                add_ratio(
                    bucket,
                    anomes=anomes,
                    scope="team",
                    login=login,
                    period=period,
                    dimension=dimension,
                    dimension_value=dimension_value,
                    successes=success,
                    volume=volume,
                    tma_seconds=tma_seconds,
                    tmr_seconds=tmr_seconds,
                )
                if dimension != "service":
                    scoped_value = _compound(service, dimension_value)
                    if scoped_value:
                        add_ratio(
                            bucket,
                            anomes=anomes,
                            scope="team",
                            login=login,
                            period=period,
                            dimension=f"service__{dimension}",
                            dimension_value=scoped_value,
                            successes=success,
                            volume=volume,
                            tma_seconds=tma_seconds,
                            tmr_seconds=tmr_seconds,
                        )
        elif is_night(hour, turn):
            add_ratio(
                bucket,
                anomes=anomes,
                scope="external",
                login=login,
                period=period,
                dimension="external_hour",
                dimension_value=hour if hour is not None else "Madrugada",
                successes=success,
                volume=volume,
                tma_seconds=tma_seconds,
                tmr_seconds=tmr_seconds,
            )

    if latest_anomes <= 0:
        return ()

    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    batches: list[ParsedIndicatorBatch] = []
    for indicator_key in INDICATORS.values():
        rows = []
        for (anomes, key, login, period), (gain, volume) in sorted(aggregates.items()):
            if anomes != latest_anomes or key != indicator_key or volume <= 0:
                continue
            rows.append({
                "login": login,
                "period": period,
                "data_month": data_month,
                "value": round(gain / volume * 100, 1),
                "volume": int(round(volume)),
            })
        if rows:
            batches.append(
                ParsedIndicatorBatch(
                    SOURCE_KEY,
                    indicator_key,
                    max(r["period"] for r in rows),
                    tuple(rows),
                    (data_month,),
                    materialize(breakdowns_by_indicator[indicator_key], latest_anomes),
                )
            )
    return tuple(batches)


def _compound(left: object | None, right: object | None) -> str | None:
    left_value = str(left or "").strip()
    right_value = str(right or "").strip()
    if not left_value or not right_value:
        return None
    return f"{left_value}|||{right_value}"
