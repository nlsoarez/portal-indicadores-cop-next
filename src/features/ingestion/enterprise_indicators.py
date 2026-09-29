from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, iter_rows, normalize_login

SOURCE_KEY = "enterprise_indicators"
SHEET_CANDIDATES = ("Empresarial", "ETIT", "Analítico", "Analitico")


def parse_enterprise_indicators(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    required = {"INDICADOR_NOME", "LOGIN_ACIONAMENTO", "VOLUME", "INDICADOR", "IN_REGIONAL", "DT_INICIO", "ANOMES"}
    aggregates: dict[tuple[int, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    latest_anomes = 0
    for row in iter_rows(raw_bytes, sheet_candidates=SHEET_CANDIDATES, header_row=1, required_headers=required):
        if str(row.get("INDICADOR_NOME") or "").strip().upper() != "ETIT POR EVENTO":
            continue
        if str(row.get("IN_REGIONAL") or "").strip().upper() != "LESTE":
            continue
        login = normalize_login(row.get("LOGIN_ACIONAMENTO"))
        if login not in allowed:
            continue
        anomes = as_int(row.get("ANOMES")); period = excel_date(row.get("DT_INICIO"))
        indicator = as_float(row.get("INDICADOR"), -1); volume = as_float(row.get("VOLUME"), 0)
        if anomes <= 0 or not period or indicator not in (0.0, 1.0) or volume <= 0:
            continue
        latest_anomes = max(latest_anomes, anomes)
        aggregates[(anomes, login, period)][0] += indicator * volume
        aggregates[(anomes, login, period)][1] += volume
    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows = []
    for (anomes, login, period), (gain, volume) in sorted(aggregates.items()):
        if anomes == latest_anomes and volume > 0:
            rows.append({"login": login, "period": period, "data_month": data_month, "value": round(gain / volume * 100, 1), "volume": int(round(volume))})
    if not rows:
        return ()
    return (ParsedIndicatorBatch(SOURCE_KEY, "emp_etit_event", max(r["period"] for r in rows), tuple(rows), (data_month,)),)
