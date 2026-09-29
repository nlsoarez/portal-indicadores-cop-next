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

SOURCE_KEY = "enterprise_indicators"
SHEET_CANDIDATES = ("Empresarial", "ETIT", "Analítico", "Analitico")


def parse_enterprise_indicators(raw_bytes: bytes, allowed_logins: set[str]) -> tuple[ParsedIndicatorBatch, ...]:
    allowed = {login.strip().upper() for login in allowed_logins}
    required = {"INDICADOR_NOME", "LOGIN_ACIONAMENTO", "VOLUME", "INDICADOR", "IN_REGIONAL", "DT_INICIO", "ANOMES"}
    optional = {
        "DT_ACIONAMENTO", "IN_GRUPO", "IN_CIDADE_UF", "IN_UF", "TURNO",
        "DEMANDA", "TIPO", "AREA_ENVOLVIDA", "CAUSA", "TMA", "TMR", "NOTA",
        "ID_ATIVIDADE", "ID_MOSTRA", "INCIDENTE", "ID_INCIDENTE", "NUMERO_INCIDENTE",
    }
    aggregates: dict[tuple[int, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    breakdowns = new_bucket()
    latest_anomes = 0

    for row in iter_rows(
        raw_bytes,
        sheet_candidates=SHEET_CANDIDATES,
        header_row=1,
        required_headers=required,
        optional_headers=optional,
    ):
        if str(row.get("INDICADOR_NOME") or "").strip().upper() != "ETIT POR EVENTO":
            continue
        region = str(row.get("IN_REGIONAL") or "").strip()
        if region.upper() != "LESTE":
            continue
        login = normalize_login(row.get("LOGIN_ACIONAMENTO"))
        if not login:
            continue
        anomes = as_int(row.get("ANOMES"))
        period = excel_date(row.get("DT_INICIO"))
        indicator = as_float(row.get("INDICADOR"), -1)
        volume = as_float(row.get("VOLUME"), 0)
        if anomes <= 0 or not period or indicator not in (0.0, 1.0) or volume <= 0:
            continue

        success = indicator * volume
        hour = excel_hour(row.get("DT_ACIONAMENTO"))
        if hour is None:
            hour = excel_hour(row.get("DT_INICIO"))
        turn = str(row.get("TURNO") or "").strip() or turn_from_hour(hour)
        tma_seconds = decimal_hours_to_seconds(row.get("TMA"))
        tmr_seconds = decimal_hours_to_seconds(row.get("TMR"))
        incident_id = next(
            (
                row.get(key)
                for key in ("NOTA", "ID_ATIVIDADE", "ID_MOSTRA", "INCIDENTE", "ID_INCIDENTE", "NUMERO_INCIDENTE")
                if row.get(key)
            ),
            None,
        )

        if login in allowed:
            latest_anomes = max(latest_anomes, anomes)
            aggregates[(anomes, login, period)][0] += success
            aggregates[(anomes, login, period)][1] += volume
            for dimension, dimension_value in (
                ("overall", "Total"),
                ("region", region),
                ("group", row.get("IN_GRUPO")),
                ("city", row.get("IN_CIDADE_UF")),
                ("uf", row.get("IN_UF")),
                ("hour", hour),
                ("turn", turn),
                ("demand", row.get("DEMANDA")),
                ("type", row.get("TIPO")),
                ("area", row.get("AREA_ENVOLVIDA")),
                ("cause", row.get("CAUSA")),
            ):
                add_ratio(
                    breakdowns,
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

            if incident_id and success < volume:
                add_ratio(
                    breakdowns,
                    anomes=anomes,
                    scope="team",
                    login=login,
                    period=period,
                    dimension="incident",
                    dimension_value=_incident_reference(row.get("DEMANDA"), incident_id),
                    successes=success,
                    volume=volume,
                    tma_seconds=tma_seconds,
                    tmr_seconds=tmr_seconds,
                )
        elif is_night(hour, turn):
            add_ratio(
                breakdowns,
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
    rows = []
    for (anomes, login, period), (gain, volume) in sorted(aggregates.items()):
        if anomes == latest_anomes and volume > 0:
            rows.append({
                "login": login,
                "period": period,
                "data_month": data_month,
                "value": round(gain / volume * 100, 1),
                "volume": int(round(volume)),
            })
    if not rows:
        return ()
    return (
        ParsedIndicatorBatch(
            SOURCE_KEY,
            "emp_etit_event",
            max(r["period"] for r in rows),
            tuple(rows),
            (data_month,),
            materialize(breakdowns, latest_anomes),
        ),
    )


def _incident_reference(demand: object | None, incident_id: object) -> str:
    demand_value = str(demand or "").strip().upper()
    incident_value = str(incident_id or "").strip()
    if demand_value:
        return f"{demand_value}|||{incident_value}"
    return incident_value
