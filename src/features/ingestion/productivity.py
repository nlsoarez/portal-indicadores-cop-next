from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, iter_rows, normalize_login

SOURCE_KEY = "productivity"
SHEET_CANDIDATES = ("Analítico Produtividade 2026", "Analítico Produtividade", "Produtividade")


def parse_productivity(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    required = {"USUARIO_LOGIN", "DATA", "ANOMES", "VOL_TOTAL"}
    aggregates: dict[tuple[int, str, str], float] = defaultdict(float)
    latest_anomes = 0
    for row in iter_rows(raw_bytes, sheet_candidates=SHEET_CANDIDATES, header_row=11, required_headers=required):
        login = normalize_login(row.get("USUARIO_LOGIN"))
        if login not in allowed:
            continue
        anomes = as_int(row.get("ANOMES")); period = excel_date(row.get("DATA"))
        if anomes <= 0 or not period:
            continue
        latest_anomes = max(latest_anomes, anomes)
        aggregates[(anomes, login, period)] += as_float(row.get("VOL_TOTAL"), 0)
    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows = [
        {"login": login, "period": period, "data_month": data_month, "value": round(value, 1), "volume": 1}
        for (anomes, login, period), value in sorted(aggregates.items())
        if anomes == latest_anomes
    ]
    if not rows:
        return ()
    return (ParsedIndicatorBatch(SOURCE_KEY, "productivity_avg_daily", max(r["period"] for r in rows), tuple(rows), (data_month,)),)
