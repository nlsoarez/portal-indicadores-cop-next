from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext, Segment
from src.ui.shared.metrics import format_metric, format_target


_DIMENSION_LABELS = {
    "region": "Por região",
    "group": "Por grupo",
    "hour": "Por hora",
    "base": "Por base",
    "queue": "Por fila",
    "demand": "Por demanda",
    "type": "Por tipo",
    "cause": "Por causa",
}


def render_management_indicators(
    ctx: AccessContext,
    segments: list[Segment],
    dashboard: DashboardService,
) -> None:
    payload = dashboard.management_payload(ctx, [segment.id for segment in segments])
    segment_df = pd.DataFrame(payload["segment_summary"])
    analyst_df = pd.DataFrame(payload["analyst_summary"])
    breakdown_df = pd.DataFrame(payload["breakdowns"])
    external_df = pd.DataFrame(payload["external"])
    freshness_df = pd.DataFrame(payload["freshness"])

    st.markdown("### Indicadores consolidados")
    st.caption(
        "Resultado geral do indicador, setores aplicáveis e todos os analistas na mesma página. "
        "Os detalhamentos são apresentados em tabelas, sem gráficos."
    )

    if segment_df.empty:
        st.info("Ainda não há resultados processados para os indicadores.")
        return

    freshness_index = {
        str(row["indicator_key"]): row for row in freshness_df.to_dict("records")
    } if not freshness_df.empty else {}

    indicators = (
        segment_df[["indicator_key", "name"]]
        .drop_duplicates()
        .sort_values("name")
        .to_dict("records")
    )

    for indicator in indicators:
        indicator_key = str(indicator["indicator_key"])
        rows = segment_df[segment_df["indicator_key"] == indicator_key].copy()
        if rows.empty:
            continue
        first = rows.iloc[0]
        name = str(first["name"])
        unit = first.get("unit")
        direction = str(first.get("direction") or "higher_is_better")
        target = first.get("target_value")
        period = str(first.get("period") or "")
        total_volume = int(pd.to_numeric(rows["volume"], errors="coerce").fillna(0).sum())
        weighted = _weighted_value(rows)
        analysts = int(pd.to_numeric(rows["analysts"], errors="coerce").fillna(0).sum())
        fresh = freshness_index.get(indicator_key, {})

        with st.container(border=True):
            st.markdown(f"## {name}")
            update_label = fresh.get("data_through") or period or "—"
            st.caption(f"Competência: {period or '—'} · Dados até: {update_label}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Resultado", _fmt(weighted, unit))
            c2.metric("Meta", _target_value(target, unit))
            c3.metric("Base / volume", f"{total_volume:,}".replace(",", "."))
            c4.metric("Analistas", analysts)
            st.caption(format_target(None if pd.isna(target) else target, unit, direction))

            st.markdown("#### Resultado por setor")
            st.dataframe(_sector_table(rows, weighted, unit), use_container_width=True, hide_index=True)

            people = analyst_df[analyst_df["indicator_key"] == indicator_key].copy() if not analyst_df.empty else pd.DataFrame()
            if not people.empty:
                st.markdown("#### Todos os analistas")
                st.dataframe(
                    _analyst_table(people, direction, target, unit),
                    use_container_width=True,
                    hide_index=True,
                )

            details = breakdown_df[breakdown_df["indicator_key"] == indicator_key].copy() if not breakdown_df.empty else pd.DataFrame()
            if not details.empty:
                for dimension in ["region", "group", "hour", "base", "queue", "demand", "type", "cause"]:
                    part = details[details["dimension"] == dimension].copy()
                    if part.empty:
                        continue
                    st.markdown(f"#### {_DIMENSION_LABELS[dimension]}")
                    st.dataframe(
                        _breakdown_table(part, dimension, unit),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.caption(
                    "Região, horário e demais detalhamentos não existem nas cargas já persistidas. "
                    "Reprocesse a fonte após esta atualização para preencher esta seção."
                )

            if ctx.is_admin and not external_df.empty:
                ext = external_df[external_df["indicator_key"] == indicator_key].copy()
                if not ext.empty:
                    st.markdown("#### Fora da equipe · madrugada")
                    st.caption(
                        "Logins não pertencentes à equipe monitorada encontrados entre 22:00 e 05:59 "
                        "quando a fonte possui horário; fontes sem hora mostram o turno disponível."
                    )
                    st.dataframe(_external_table(ext, unit), use_container_width=True, hide_index=True)


def _weighted_value(rows: pd.DataFrame) -> float | None:
    values = pd.to_numeric(rows["value"], errors="coerce")
    volumes = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (volumes > 0)
    if not valid.any():
        return None
    return round(float((values[valid] * volumes[valid]).sum() / volumes[valid].sum()), 1)


def _fmt(value: float | None, unit) -> str:
    if value is None or pd.isna(value):
        return "—"
    return format_metric(float(value), unit)


def _target_value(target, unit) -> str:
    if target is None or pd.isna(target):
        return "—"
    return format_metric(float(target), unit)


def _sector_table(rows: pd.DataFrame, weighted: float | None, unit) -> pd.DataFrame:
    output = []
    if len(rows) > 1:
        output.append({
            "Setor": "Geral",
            "Resultado": _fmt(weighted, unit),
            "Base": int(pd.to_numeric(rows["volume"], errors="coerce").fillna(0).sum()),
            "Analistas": int(pd.to_numeric(rows["analysts"], errors="coerce").fillna(0).sum()),
        })
    for _, row in rows.sort_values("segment_name").iterrows():
        output.append({
            "Setor": row["segment_name"],
            "Resultado": _fmt(row.get("value"), unit),
            "Base": int(row.get("volume") or 0),
            "Analistas": int(row.get("analysts") or 0),
        })
    return pd.DataFrame(output)


def _analyst_table(rows: pd.DataFrame, direction: str, target, unit) -> pd.DataFrame:
    rows = rows.assign(_value_num=pd.to_numeric(rows["value"], errors="coerce"))
    rows = rows.sort_values("_value_num", ascending=(direction == "lower_is_better"))
    target_num = None if target is None or pd.isna(target) else float(target)
    output = []
    for _, row in rows.iterrows():
        value = None if pd.isna(row["_value_num"]) else float(row["_value_num"])
        gap = None if value is None or target_num is None else round(value - target_num, 1)
        output.append({
            "Analista": row["display_name"],
            "Matrícula": row["login"],
            "Setor": row["segment_name"],
            "Resultado": _fmt(value, unit),
            "Base": int(row.get("volume") or 0),
            "Dif. meta": _fmt(gap, unit) if gap is not None else "—",
        })
    return pd.DataFrame(output)


def _breakdown_table(rows: pd.DataFrame, dimension: str, unit) -> pd.DataFrame:
    label = {
        "region": "Região", "group": "Grupo", "hour": "Hora", "base": "Base",
        "queue": "Fila", "demand": "Demanda", "type": "Tipo", "cause": "Causa",
    }[dimension]
    if dimension == "hour":
        rows = rows.assign(_sort=pd.to_numeric(rows["dimension_value"], errors="coerce"))
        rows = rows.sort_values(["_sort", "segment_name"], na_position="last")
    else:
        rows = rows.sort_values(["dimension_value", "segment_name"])
    return pd.DataFrame([
        {
            "Setor": row["segment_name"],
            label: row["dimension_value"],
            "Resultado": _fmt(row.get("value"), unit),
            "Volume": int(row.get("volume") or 0),
            "Aderentes / ganhos": int(row.get("successes") or 0),
            "Perdas": int(row.get("losses") or 0),
        }
        for _, row in rows.iterrows()
    ])


def _external_table(rows: pd.DataFrame, unit) -> pd.DataFrame:
    rows = rows.assign(_hour_num=pd.to_numeric(rows["hour"], errors="coerce"))
    rows = rows.sort_values(["_hour_num", "login"], na_position="last")
    return pd.DataFrame([
        {
            "Login externo": row["login"],
            "Horário": row["hour"],
            "Resultado": _fmt(row.get("value"), unit),
            "Volume": int(row.get("volume") or 0),
            "Aderentes / ganhos": int(row.get("successes") or 0),
            "Perdas": int(row.get("losses") or 0),
        }
        for _, row in rows.iterrows()
    ])
