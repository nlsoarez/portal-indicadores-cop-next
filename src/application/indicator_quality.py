"""Conferência de cobertura ETIT e consistência de tarefas canceladas.

Os avisos são diagnósticos, não novas metas operacionais.
As taxas oficiais permanecem calculadas pelo serviço de indicadores.
"""
from __future__ import annotations

ETIT_SMALL_SAMPLE_THRESHOLD = 10


def classify_etit_quality(
    stats: dict | None,
    *,
    threshold: int = ETIT_SMALL_SAMPLE_THRESHOLD,
) -> dict:
    """Evaluate only one person/segment/month, without guessing missing data."""
    item = stats or {}
    cancelled = int(item.get("cancelled") or 0)
    etit = int(item.get("etit_volume") or 0)
    records = int(item.get("source_volume") or 0)

    if records > 0 and etit <= 0:
        return {
            "status": "Incompatível",
            "severity": "critical",
            "reason": "Canceladas sem base ETIT na competência",
            "action": "Conferir cobertura ETIT do login e período; não calcular taxa.",
        }
    if records > 0 and cancelled > etit:
        return {
            "status": "Incompatível",
            "severity": "critical",
            "reason": "Cancelamentos superiores ao volume ETIT",
            "action": "Reconciliar origem ETIT e cancelamentos antes de calcular taxa.",
        }
    if etit <= 0:
        return {
            "status": "Sem ETIT",
            "severity": "info",
            "reason": "Nenhum evento ETIT identificado na competência",
            "action": "Confirmar se o usuário deveria constar na fonte ETIT.",
        }
    if etit < threshold:
        return {
            "status": "Amostra reduzida",
            "severity": "warning",
            "reason": f"ETIT com menos de {threshold} eventos",
            "action": "Interpretar a aderência com cautela; conferir a cobertura da origem.",
        }
    return {
        "status": "Sem alerta",
        "severity": "ok",
        "reason": "Bases ETIT e canceladas sem inconsistência detectada",
        "action": "Nenhuma ação necessária nesta verificação.",
    }


def build_leader_quality_report(
    *,
    segment_id: int,
    month: str,
    current_leader: dict,
    analysts: list[dict],
    stats: dict,
    source_rows: list[dict],
) -> dict:
    """Restrict person-level details to own leader and analysts of their team."""
    people = [
        {
            "id": int(current_leader["id"]),
            "login": str(current_leader["login"]),
            "name": str(current_leader["name"]),
            "role": "Líder (meu resultado)",
        },
    ]
    people.extend(
        {
            "id": int(user["id"]),
            "login": str(user["login"]),
            "name": str(user["name"]),
            "role": "Analista",
        }
        for user in analysts
        if int(user["id"]) != int(current_leader["id"])
    )
    result = []
    for person in people:
        measure = stats.get((segment_id, person["id"], month))
        observed = measure or {}
        quality = classify_etit_quality(measure)
        result.append({
            "name": person["name"],
            "login": person["login"],
            "role": person["role"],
            "month": month,
            "cancelled": int(observed.get("cancelled") or 0),
            "cancelled_records": int(observed.get("source_volume") or 0),
            "etit_volume": int(observed.get("etit_volume") or 0),
            **quality,
        })
    result.sort(
        key=lambda row: (
            {"critical": 0, "warning": 1, "info": 2, "ok": 3}[row["severity"]],
            0 if row["role"].startswith("Líder") else 1,
            row["name"].casefold(),
        )
    )
    source_months = sorted({
        str(source["data_through"])[:7]
        for source in source_rows if source.get("data_through")
    })
    return {
        "period": month,
        "people": result,
        "sources": source_rows,
        "source_months": source_months,
        "sources_out_of_sync": len(source_months) > 1,
        "incompatible": sum(x["severity"] == "critical" for x in result),
        "small_samples": sum(x["severity"] == "warning" for x in result),
        "without_etit": sum(x["severity"] == "info" for x in result),
        "no_alert": sum(x["severity"] == "ok" for x in result),
    }
