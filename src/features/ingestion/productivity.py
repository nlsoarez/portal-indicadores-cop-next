from __future__ import annotations

from collections import defaultdict

from src.features.ingestion.breakdowns import add_ratio, materialize, new_bucket
from src.features.ingestion.models import ParsedIndicatorBatch
from src.features.ingestion.xlsx_stream import as_float, as_int, excel_date, iter_rows, normalize_login

SOURCE_KEY = "productivity"
SHEET_CANDIDATES = ("Analítico Produtividade 2026", "Analítico Produtividade", "Produtividade")

PRODUCTIVITY_COMPONENTS = {
    "VOL_AB_NM": "Abertura New Monitor",
    "VOL_FE_NM": "Fechamento New Monitor",
    "VOL_FE_NM_MANOBRA": "Fechamento NM Manobra",
    "VOL_AB_SGO": "Abertura SGO",
    "VOL_TRAT_SGO": "Tratamento SGO",
    "VOL_AC_SGO": "Aceite SGO",
    "VOL_FE_SGO": "Fechamento SGO",
    "VOL_AB_OSS": "Abertura Remedy",
    "VOL_FE_OSS": "Fechamento OSS",
    "VOL_AC_OSS": "Aceite OSS",
    "VOL_RAL": "Tratativa RAL",
    "VOL_REC": "Tratativa REC",
    "VOL_AB_RAL": "Abertura RAL",
    "VOL_REMEDY_MOVEL": "Remedy Móvel",
    "VOL_TOA_PRIM_INT": "Primeira Interação TOA",
    "VOL_TOA_FORM": "Fechamento Tarefa TOA",
    "VOL_TELEFONIA_RECEBIDO": "Telefonia Recebido",
    "VOL_TELEFONIA_ATENDIDO": "Telefonia Atendido",
    "VOL_TELEFONIA_REALIZADO": "Ligações Realizadas",
}


def parse_productivity(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    required = {"USUARIO_LOGIN", "DATA", "ANOMES", "VOL_TOTAL"}
    aggregates: dict[tuple[int, str, str], float] = defaultdict(float)
    breakdowns = new_bucket()
    latest_anomes = 0

    for row in iter_rows(
        raw_bytes,
        sheet_candidates=SHEET_CANDIDATES,
        header_row=11,
        required_headers=required,
        optional_headers=set(PRODUCTIVITY_COMPONENTS),
    ):
        login = normalize_login(row.get("USUARIO_LOGIN"))
        if login not in allowed:
            continue
        anomes = as_int(row.get("ANOMES"))
        period = excel_date(row.get("DATA"))
        if anomes <= 0 or not period:
            continue

        total = as_float(row.get("VOL_TOTAL"), 0)
        latest_anomes = max(latest_anomes, anomes)
        aggregates[(anomes, login, period)] += total

        for column, label in PRODUCTIVITY_COMPONENTS.items():
            amount = as_float(row.get(column), 0)
            if amount <= 0:
                continue
            add_ratio(
                breakdowns,
                anomes=anomes,
                scope="team",
                login=login,
                period=period,
                dimension="productivity_component",
                dimension_value=label,
                successes=amount,
                volume=amount,
            )

    if latest_anomes <= 0:
        return ()

    data_month = f"{latest_anomes // 100:04d}-{latest_anomes % 100:02d}"
    rows = [
        {"login": login, "period": period, "data_month": data_month, "value": round(value, 1), "volume": 1}
        for (anomes, login, period), value in sorted(aggregates.items())
        if anomes == latest_anomes
    ]
    if not rows:
        return ()

    return (
        ParsedIndicatorBatch(
            SOURCE_KEY,
            "productivity_avg_daily",
            max(r["period"] for r in rows),
            tuple(rows),
            (data_month,),
            materialize(breakdowns, latest_anomes),
        ),
    )
