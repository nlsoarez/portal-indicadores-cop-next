from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.breakdowns import add_ratio, is_night, materialize, new_bucket
from src.features.ingestion.excel import ImportValidationError
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, excel_hour, iter_rows, normalize_login

SOURCE_KEY = "toa_indicators"
SHEET_CANDIDATES = ("TOA", "Planilha1", "Sheet1", "Analitico", "Analítico", "INDICADORES")
SPECS = {
    "TEMPO DE VALIDAÇÃO DO FORMULÁRIO": "validacao_20m",
    "TAREFAS CANCELADAS": "toa_cancellation_rate",
}


def parse_toa_indicators(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    required = {"INDICADOR_NOME", "LOGIN", "INDICADOR", "ANOMES", "IN_REGIONAL", "DATA"}
    optional = {"IN_GRUPO", "DT_INICIO_FORM", "DT_CANCELAMENTO", "TURNO", "REDE", "TIPO_ATIVIDADE"}
    aggregates: dict[tuple[int, str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    breakdowns_by_indicator = {key: new_bucket() for key in SPECS.values()}
    latest_anomes = 0
    for row in iter_rows(raw_bytes, sheet_candidates=SHEET_CANDIDATES, header_row=1, required_headers=required, optional_headers=optional):
        source_name = str(row.get("INDICADOR_NOME") or "").strip().upper()
        indicator_key = SPECS.get(source_name)
        region = str(row.get("IN_REGIONAL") or "").strip()
        if not indicator_key or region.upper() != "LESTE":
            continue
        login = normalize_login(row.get("LOGIN"))
        if not login:
            continue
        anomes = as_int(row.get("ANOMES"))
        period = excel_date(row.get("DATA"))
        metric = as_float(row.get("INDICADOR"), -1)
        if anomes <= 0 or not period or metric not in (0.0, 1.0):
            continue
        source_time = row.get("DT_CANCELAMENTO") if indicator_key == "toa_cancellation_rate" else row.get("DT_INICIO_FORM")
        hour = excel_hour(source_time)
        if hour is None:
            hour = excel_hour(row.get("DATA"))
        turn = row.get("TURNO")
        bucket = breakdowns_by_indicator[indicator_key]
        if login in allowed:
            latest_anomes = max(latest_anomes, anomes)
            aggregates[(anomes, indicator_key, login, period)][0] += metric
            aggregates[(anomes, indicator_key, login, period)][1] += 1
            for dimension, dimension_value in (
                ("region", region), ("group", row.get("IN_GRUPO")), ("hour", hour),
                ("network", row.get("REDE")), ("activity_type", row.get("TIPO_ATIVIDADE")),
            ):
                add_ratio(bucket, anomes=anomes, scope="team", login=login, period=period,
                          dimension=dimension, dimension_value=dimension_value,
                          successes=metric, volume=1)
        elif is_night(hour, turn):
            add_ratio(bucket, anomes=anomes, scope="external", login=login, period=period,
                      dimension="external_hour", dimension_value=hour if hour is not None else "Madrugada",
                      successes=metric, volume=1)
    if latest_anomes <= 0:
        return ()
    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    batches = []
    for indicator_key in SPECS.values():
        rows = []
        for (anomes, key, login, period), (metric, volume) in sorted(aggregates.items()):
            if anomes == latest_anomes and key == indicator_key and volume > 0:
                rows.append({"login": login, "period": period, "data_month": data_month, "value": round(metric / volume * 100, 1), "volume": int(volume)})
        if rows:
            batches.append(
                ParsedIndicatorBatch(
                    SOURCE_KEY, indicator_key, max(r["period"] for r in rows), tuple(rows),
                    (data_month,), materialize(breakdowns_by_indicator[indicator_key], latest_anomes),
                )
            )
    return tuple(batches)


def parse_toa_validation(raw_bytes: bytes, allowed_logins: set[str]) -> ParsedIndicatorBatch:
    for batch in parse_toa_indicators(raw_bytes, allowed_logins):
        if batch.indicator_key == "validacao_20m":
            return batch
    raise ImportValidationError("O arquivo não contém dados válidos de Tempo de Validação do Formulário.")
