from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.excel import ImportValidationError
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, iter_rows, normalize_login

SOURCE_KEY = "chat_toa"
INDICATOR_KEY = "chat_10m"
SHEET_CANDIDATES = ("Analítico CHAT TOA", "Analitico CHAT TOA", "CHAT TOA")


def parse_chat_toa(raw_bytes: bytes, allowed_logins: set[str]) -> ParsedIndicatorBatch:
    allowed = {login.strip().upper() for login in allowed_logins}
    required = {"FECHAMENTO_COPREDE_LOGIN_ANALISTA", "ABERTURA_ANOMES", "INDICADOR_TMA_DENTRO", "CHAT_INICIO"}
    aggregates: dict[tuple[int, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    latest_anomes = 0
    for row in iter_rows(raw_bytes, sheet_candidates=SHEET_CANDIDATES, header_row=4, required_headers=required):
        login = normalize_login(row.get("FECHAMENTO_COPREDE_LOGIN_ANALISTA"))
        if login not in allowed:
            continue
        anomes = as_int(row.get("ABERTURA_ANOMES")); period = excel_date(row.get("CHAT_INICIO")); indicator = as_float(row.get("INDICADOR_TMA_DENTRO"), -1)
        if anomes <= 0 or not period or indicator not in (0.0, 1.0):
            continue
        latest_anomes = max(latest_anomes, anomes)
        aggregates[(anomes, login, period)][0] += indicator
        aggregates[(anomes, login, period)][1] += 1
    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows = []
    for (anomes, login, period), (adherent, volume) in sorted(aggregates.items()):
        if anomes == latest_anomes and volume > 0:
            rows.append({"login": login, "period": period, "data_month": data_month, "value": round(adherent / volume * 100, 1), "volume": int(volume)})
    if not rows:
        raise ImportValidationError("O arquivo de Chat TOA não possui dados dos usuários deste segmento.")
    return ParsedIndicatorBatch(SOURCE_KEY, INDICATOR_KEY, max(r["period"] for r in rows), tuple(rows), (data_month,))
