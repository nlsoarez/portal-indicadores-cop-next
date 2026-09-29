from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, iter_rows, normalize_login

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
    latest_anomes = 0
    optional = {COL_LOGIN_UNIFIED, COL_LOGIN_FO, COL_LOGIN_GPON}
    required = {COL_INDICATOR, COL_VOLUME, COL_VALUE, COL_REGIONAL, COL_DATE, COL_ANOMES}

    for row in iter_rows(
        raw_bytes,
        sheet_candidates=SHEET_CANDIDATES,
        header_row=1,
        required_headers=required,
        optional_headers=optional,
        required_any=(optional,),
    ):
        indicator = str(row.get(COL_INDICATOR) or "").strip().upper()
        if indicator not in INDICATORS:
            continue
        if str(row.get(COL_REGIONAL) or "").strip().upper() != "LESTE":
            continue
        login = normalize_login(row.get(COL_LOGIN_UNIFIED))
        if not login:
            login = normalize_login(row.get(COL_LOGIN_FO if indicator in HFC_INDICATORS else COL_LOGIN_GPON))
        if login not in allowed:
            continue
        anomes = as_int(row.get(COL_ANOMES))
        period = excel_date(row.get(COL_DATE))
        value = as_float(row.get(COL_VALUE), -1)
        volume = as_float(row.get(COL_VOLUME), 0)
        if anomes <= 0 or not period or value not in (0.0, 1.0) or volume <= 0:
            continue
        latest_anomes = max(latest_anomes, anomes)
        key = (anomes, INDICATORS[indicator], login, period)
        aggregates[key][0] += value * volume
        aggregates[key][1] += volume

    if latest_anomes <= 0:
        return ()

    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    batches: list[ParsedIndicatorBatch] = []
    for indicator_key in INDICATORS.values():
        rows = []
        for (anomes, key, login, period), (gain, volume) in sorted(aggregates.items()):
            if anomes != latest_anomes or key != indicator_key or volume <= 0:
                continue
            rows.append({"login": login, "period": period, "data_month": data_month, "value": round(gain / volume * 100, 1), "volume": int(round(volume))})
        if rows:
            batches.append(ParsedIndicatorBatch(SOURCE_KEY, indicator_key, max(r["period"] for r in rows), tuple(rows), (data_month,)))
    return tuple(batches)
