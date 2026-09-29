from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext, Segment
from src.ui.shared.metrics import format_metric, format_target


SOURCE_GROUPS = (
    (
        "Indicadores Residencial",
        (
            "res_etit_fibra_hfc",
            "res_etit_gpon",
            "res_assert_fibra_hfc",
            "res_assert_gpon",
        ),
    ),
    ("ETIT Empresarial", ("emp_etit_event",)),
    ("Indicadores TOA", ("toa_cancellation_rate", "validacao_20m")),
    ("Ocupação DPA", ("dpa_official",)),
    ("Fechamento TOA x SIR", ("closing_assertiveness",)),
    ("Chat TOA", ("chat_10m",)),
    ("Produtividade", ("productivity_avg_daily",)),
)

DIMENSION_LABELS = {
    "service": "Serviço",
    "turn": "Turno",
    "region": "Região",
    "group": "Grupo",
    "hour": "Hora",
    "base": "Base",
    "queue": "Fila",
    "queue_type": "Tipo de fila",
    "demand": "Demanda",
    "type": "Tipo",
    "cause": "Causa",
    "nature": "Natureza",
    "solution": "Solução",
    "impact": "Impacto",
    "network": "Rede",
    "activity_type": "Tipo de atividade",
    "aging": "Aging",
    "cause_toa": "Causa TOA",
    "cause_sir": "Causa SIR",
}

DIMENSION_ORDER = (
    "service",
    "turn",
    "group",
    "region",
    "hour",
    "demand",
    "type",
    "cause",
    "network",
    "activity_type",
    "aging",
    "base",
    "queue_type",
    "queue",
    "nature",
    "impact",
    "solution",
    "cause_toa",
    "cause_sir",
)

ADHERENCE_KEYS = {
    "res_etit_fibra_hfc",
    "res_etit_gpon",
    "res_assert_fibra_hfc",
    "res_assert_gpon",
    "emp_etit_event",
    "validacao_20m",
    "chat_10m",
    "closing_assertiveness",
}


def render_management_indicators(
    ctx: AccessContext,
    segments: list[Segment],
    dashboard: DashboardService,
) -> None:
    payload = dashboard.management_payload(ctx, [segment.id for segment in segments])
    segment_df = pd.DataFrame(payload["segment_summary"])
    analyst_df = pd.DataFrame(payload["analyst_summary"])
    analyst_metrics_df = pd.DataFrame(payload.get("analyst_metrics", []))
    daily_df = pd.DataFrame(payload.get("daily_summary", []))
    breakdown_df = pd.DataFrame(payload["breakdowns"])
    external_df = pd.DataFrame(payload["external"])
    freshness_df = pd.DataFrame(payload["freshness"])

    st.markdown("### Visão gerencial dos indicadores")
    st.caption(
        "Cada fonte possui sua própria aba. Dentro dela, os indicadores ficam separados e "
        "com resumo, analistas e cortes operacionais em tabelas — sem gráficos."
    )

    if segment_df.empty:
        st.info("Ainda não há resultados processados para os indicadores.")
        return

    freshness_index = {
        str(row["indicator_key"]): row
        for row in freshness_df.to_dict("records")
    } if not freshness_df.empty else {}

    available = set(segment_df["indicator_key"].astype(str))
    groups = [
        (label, tuple(key for key in keys if key in available))
        for label, keys in SOURCE_GROUPS
    ]
    groups = [(label, keys) for label, keys in groups if keys]

    tabs = st.tabs([label for label, _ in groups])
    for source_tab, (source_label, keys) in zip(tabs, groups):
        with source_tab:
            _render_source(
                source_label=source_label,
                indicator_keys=keys,
                ctx=ctx,
                segment_df=segment_df,
                analyst_df=analyst_df,
                analyst_metrics_df=analyst_metrics_df,
                daily_df=daily_df,
                breakdown_df=breakdown_df,
                external_df=external_df,
                freshness_index=freshness_index,
            )


def _render_source(
    *,
    source_label: str,
    indicator_keys: tuple[str, ...],
    ctx: AccessContext,
    segment_df: pd.DataFrame,
    analyst_df: pd.DataFrame,
    analyst_metrics_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    breakdown_df: pd.DataFrame,
    external_df: pd.DataFrame,
    freshness_index: dict[str, dict],
) -> None:
    st.markdown(f"## {source_label}")
    st.markdown("#### Resumo por indicador")

    cols = st.columns(min(4, len(indicator_keys)))
    for index, key in enumerate(indicator_keys):
        rows = segment_df[segment_df["indicator_key"] == key]
        if rows.empty:
            continue
        first = rows.iloc[0]
        value = _weighted_value(rows)
        detail = _overall_detail(breakdown_df, key)
        with cols[index % len(cols)]:
            with st.container(border=True):
                st.caption(str(first["name"]))
                st.metric("Resultado", _fmt(value, first.get("unit")))
                if detail:
                    st.caption(
                        f"{_int(detail['volume'])} registros · "
                        f"{_int(detail['successes'])} ganhos/aderentes · "
                        f"{_int(detail['losses'])} perdas"
                    )
                else:
                    st.caption(
                        f"Base {_int(pd.to_numeric(rows['volume'], errors='coerce').fillna(0).sum())} · "
                        f"{_int(pd.to_numeric(rows['analysts'], errors='coerce').fillna(0).sum())} analistas"
                    )

    if len(indicator_keys) == 1:
        _render_indicator(
            indicator_keys[0],
            ctx=ctx,
            segment_df=segment_df,
            analyst_df=analyst_df,
            analyst_metrics_df=analyst_metrics_df,
            daily_df=daily_df,
            breakdown_df=breakdown_df,
            external_df=external_df,
            freshness_index=freshness_index,
        )
        return

    indicator_names = [
        str(segment_df[segment_df["indicator_key"] == key].iloc[0]["name"])
        for key in indicator_keys
    ]
    indicator_tabs = st.tabs(indicator_names)
    for indicator_tab, key in zip(indicator_tabs, indicator_keys):
        with indicator_tab:
            _render_indicator(
                key,
                ctx=ctx,
                segment_df=segment_df,
                analyst_df=analyst_df,
                analyst_metrics_df=analyst_metrics_df,
                daily_df=daily_df,
                breakdown_df=breakdown_df,
                external_df=external_df,
                freshness_index=freshness_index,
            )


def _render_indicator(
    indicator_key: str,
    *,
    ctx: AccessContext,
    segment_df: pd.DataFrame,
    analyst_df: pd.DataFrame,
    analyst_metrics_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    breakdown_df: pd.DataFrame,
    external_df: pd.DataFrame,
    freshness_index: dict[str, dict],
) -> None:
    rows = segment_df[segment_df["indicator_key"] == indicator_key].copy()
    if rows.empty:
        return

    first = rows.iloc[0]
    name = str(first["name"])
    unit = first.get("unit")
    direction = str(first.get("direction") or "higher_is_better")
    target = first.get("target_value")
    period = str(first.get("period") or "")
    fresh = freshness_index.get(indicator_key, {})
    detail = _overall_detail(breakdown_df, indicator_key)

    st.markdown(f"### {name}")
    st.caption(
        f"Competência: {period or '—'} · "
        f"Dados até: {fresh.get('data_through') or period or '—'}"
    )

    _render_kpis(
        indicator_key=indicator_key,
        rows=rows,
        detail=detail,
        unit=unit,
        target=target,
        direction=direction,
    )

    if len(rows) > 1:
        st.markdown("#### Resultado por setor")
        st.dataframe(
            _sector_table(rows, indicator_key, breakdown_df),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption(f"Setor: {rows.iloc[0]['segment_name']}")

    people = analyst_df[analyst_df["indicator_key"] == indicator_key].copy()
    metrics = (
        analyst_metrics_df[analyst_metrics_df["indicator_key"] == indicator_key].copy()
        if not analyst_metrics_df.empty
        else pd.DataFrame()
    )
    if not people.empty:
        st.markdown("#### Resultado por analista")
        st.dataframe(
            _analyst_table(
                people,
                metrics,
                indicator_key=indicator_key,
                direction=direction,
                target=target,
                unit=unit,
            ),
            use_container_width=True,
            hide_index=True,
        )

    details = (
        breakdown_df[breakdown_df["indicator_key"] == indicator_key].copy()
        if not breakdown_df.empty
        else pd.DataFrame()
    )

    rendered_detail = False
    if not details.empty:
        for dimension in DIMENSION_ORDER:
            part = details[details["dimension"] == dimension].copy()
            if part.empty:
                continue
            rendered_detail = True
            label = DIMENSION_LABELS[dimension]
            st.markdown(f"#### Por {label.lower()}")
            st.dataframe(
                _breakdown_table(part, dimension, indicator_key),
                use_container_width=True,
                hide_index=True,
            )

    daily = (
        daily_df[daily_df["indicator_key"] == indicator_key].copy()
        if not daily_df.empty
        else pd.DataFrame()
    )
    if not daily.empty:
        st.markdown("#### Evolução diária")
        st.dataframe(
            _daily_table(daily, indicator_key),
            use_container_width=True,
            hide_index=True,
        )

    if not rendered_detail:
        st.info(
            "Os dados consolidados e por analista já estão disponíveis. "
            "Reprocesse esta fonte para preencher serviço, turno, grupo, hora, "
            "TMA/TMR e demais cortes do analítico."
        )

    if ctx.is_admin and not external_df.empty:
        ext = external_df[external_df["indicator_key"] == indicator_key].copy()
        if not ext.empty:
            st.markdown("#### Fora da equipe · madrugada")
            st.caption(
                "Logins fora da equipe encontrados entre 22:00 e 05:59 "
                "quando a fonte possui horário."
            )
            st.dataframe(
                _external_table(ext, indicator_key),
                use_container_width=True,
                hide_index=True,
            )


def _render_kpis(
    *,
    indicator_key: str,
    rows: pd.DataFrame,
    detail: dict | None,
    unit,
    target,
    direction: str,
) -> None:
    result = _weighted_value(rows)
    analysts = _int(pd.to_numeric(rows["analysts"], errors="coerce").fillna(0).sum())
    raw_volume = float(pd.to_numeric(rows["volume"], errors="coerce").fillna(0).sum())

    if indicator_key == "dpa_official":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("DPA", _fmt(result, unit))
        c2.metric("Meta", _target_value(target, unit))
        c3.metric("Jornada acumulada", _format_hours(raw_volume))
        c4.metric("Analistas", analysts)
        st.caption(format_target(None if pd.isna(target) else target, unit, direction))
        return

    if indicator_key == "productivity_avg_daily":
        c1, c2, c3 = st.columns(3)
        c1.metric("Média diária", _fmt(result, unit))
        c2.metric("Analistas", analysts)
        c3.metric("Pontos analista/dia", _int(raw_volume))
        return

    if indicator_key == "toa_cancellation_rate":
        total = _int(detail["volume"]) if detail else _int(raw_volume)
        not_cancelled = _int(detail["successes"]) if detail else None
        cancelled = _int(detail["losses"]) if detail else None
        rate = None if total <= 0 or cancelled is None else cancelled / total * 100
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", total)
        c2.metric("Canceladas", cancelled if cancelled is not None else "—")
        c3.metric("Não canceladas", not_cancelled if not_cancelled is not None else "—")
        c4.metric("Taxa de cancelamento", _pct(rate))
        if detail and _number(detail.get("tmr_seconds")) is not None:
            st.metric("TMR médio", _duration(detail.get("tmr_seconds")))
        return

    if indicator_key in ADHERENCE_KEYS:
        total = _int(detail["volume"]) if detail else _int(raw_volume)
        successes = _int(detail["successes"]) if detail else None
        losses = _int(detail["losses"]) if detail else None
        adherence = None if total <= 0 or successes is None else successes / total * 100
        non_adherence = None if total <= 0 or losses is None else losses / total * 100
        success_label = "Assertivos" if indicator_key == "closing_assertiveness" else "Aderentes"
        loss_label = "Não assertivos" if indicator_key == "closing_assertiveness" else "Não aderentes"
        result_label = "Assertividade" if indicator_key == "closing_assertiveness" else "Aderência"

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Volume", total)
        c2.metric(success_label, successes if successes is not None else "—")
        c3.metric(loss_label, losses if losses is not None else "—")
        c4.metric(result_label, _pct(adherence if adherence is not None else result))
        c5.metric("Não aderência", _pct(non_adherence))

        durations = []
        if detail and _number(detail.get("tma_seconds")) is not None:
            durations.append(("TMA médio", _duration(detail.get("tma_seconds"))))
        if detail and _number(detail.get("tmr_seconds")) is not None:
            durations.append(("TMR médio", _duration(detail.get("tmr_seconds"))))
        if durations:
            cols = st.columns(len(durations))
            for col, (label, value) in zip(cols, durations):
                col.metric(label, value)

        if target is not None and not pd.isna(target):
            st.caption(format_target(float(target), unit, direction))
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Resultado", _fmt(result, unit))
    c2.metric("Meta", _target_value(target, unit))
    c3.metric("Base / volume", _int(raw_volume))
    c4.metric("Analistas", analysts)


def _sector_table(rows: pd.DataFrame, indicator_key: str, breakdown_df: pd.DataFrame) -> pd.DataFrame:
    output = []
    overall = _weighted_value(rows)
    total_volume = float(pd.to_numeric(rows["volume"], errors="coerce").fillna(0).sum())
    output.append({
        "Setor": "Geral",
        "Resultado": _format_indicator_result(indicator_key, overall),
        "Base": _format_base(indicator_key, total_volume),
        "Analistas": _int(pd.to_numeric(rows["analysts"], errors="coerce").fillna(0).sum()),
    })
    for _, row in rows.sort_values("segment_name").iterrows():
        output.append({
            "Setor": row["segment_name"],
            "Resultado": _format_indicator_result(indicator_key, row.get("value")),
            "Base": _format_base(indicator_key, row.get("volume")),
            "Analistas": _int(row.get("analysts")),
        })
    return pd.DataFrame(output)


def _analyst_table(
    rows: pd.DataFrame,
    metrics: pd.DataFrame,
    *,
    indicator_key: str,
    direction: str,
    target,
    unit,
) -> pd.DataFrame:
    rows = rows.copy()
    if not metrics.empty:
        metric_cols = [
            "login", "segment_id", "successes", "losses",
            "tma_seconds", "tmr_seconds",
        ]
        available = [col for col in metric_cols if col in metrics.columns]
        rows = rows.merge(
            metrics[available],
            on=[col for col in ("login", "segment_id") if col in available],
            how="left",
        )

    rows["_value_num"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows.sort_values("_value_num", ascending=(direction == "lower_is_better"))
    target_num = None if target is None or pd.isna(target) else float(target)

    output = []
    for rank, (_, row) in enumerate(rows.iterrows(), start=1):
        value = _number(row.get("_value_num"))
        item = {
            "#": rank,
            "Analista": row["display_name"],
            "Matrícula": row["login"],
            "Setor": row["segment_name"],
        }

        if indicator_key == "dpa_official":
            item["DPA"] = _pct(value)
            item["Jornada"] = _format_hours(row.get("volume"))
        elif indicator_key == "productivity_avg_daily":
            item["Média diária"] = _fmt(value, unit)
            item["Dias"] = _int(row.get("volume"))
        elif indicator_key == "toa_cancellation_rate":
            item["Volume"] = _int(row.get("volume"))
            item["Canceladas"] = _int(row.get("losses")) if not pd.isna(row.get("losses")) else "—"
            item["Não canceladas"] = _int(row.get("successes")) if not pd.isna(row.get("successes")) else "—"
            item["Taxa cancelamento"] = _pct(value)
            if _number(row.get("tmr_seconds")) is not None:
                item["TMR médio"] = _duration(row.get("tmr_seconds"))
        else:
            item["Volume"] = _int(row.get("volume"))
            if "successes" in row and not pd.isna(row.get("successes")):
                success_label = "Assertivos" if indicator_key == "closing_assertiveness" else "Aderentes"
                loss_label = "Não assertivos" if indicator_key == "closing_assertiveness" else "Não aderentes"
                item[success_label] = _int(row.get("successes"))
                item[loss_label] = _int(row.get("losses"))
            item["Resultado"] = _fmt(value, unit)
            if value is not None and target_num is not None:
                item["Dif. meta"] = _fmt(round(value - target_num, 1), unit)
            if _number(row.get("tma_seconds")) is not None:
                item["TMA médio"] = _duration(row.get("tma_seconds"))
            if _number(row.get("tmr_seconds")) is not None:
                item["TMR médio"] = _duration(row.get("tmr_seconds"))

        output.append(item)

    return pd.DataFrame(output)


def _breakdown_table(rows: pd.DataFrame, dimension: str, indicator_key: str) -> pd.DataFrame:
    label = DIMENSION_LABELS[dimension]
    rows = rows.copy()

    if dimension == "hour":
        rows["_sort"] = pd.to_numeric(rows["dimension_value"], errors="coerce")
        rows = rows.sort_values(["_sort", "segment_name"], na_position="last")
    else:
        rows = rows.sort_values(["volume", "dimension_value"], ascending=[False, True])

    if dimension == "solution":
        rows = rows.head(15)

    output = []
    for _, row in rows.iterrows():
        item = {}
        if rows["segment_name"].nunique() > 1:
            item["Setor"] = row["segment_name"]
        item[label] = row["dimension_value"]

        volume = _int(row.get("volume"))
        successes = _int(row.get("successes"))
        losses = _int(row.get("losses"))
        value = _number(row.get("value"))

        if indicator_key == "toa_cancellation_rate":
            item["Volume"] = volume
            item["Não canceladas"] = successes
            item["Canceladas"] = losses
            item["Cancelamento %"] = _pct(None if volume <= 0 else losses / volume * 100)
        elif indicator_key == "dpa_official":
            item["DPA"] = _pct(value)
            item["Jornada"] = _format_hours(volume)
        else:
            item["Volume"] = volume
            item["Aderentes / ganhos"] = successes
            item["Não aderentes / perdas"] = losses
            item["Aderência %"] = _pct(value)
            item["Não aderência %"] = _pct(None if volume <= 0 else losses / volume * 100)

        if _number(row.get("tma_seconds")) is not None:
            item["TMA médio"] = _duration(row.get("tma_seconds"))
        if _number(row.get("tmr_seconds")) is not None:
            item["TMR médio"] = _duration(row.get("tmr_seconds"))

        output.append(item)

    return pd.DataFrame(output)


def _daily_table(rows: pd.DataFrame, indicator_key: str) -> pd.DataFrame:
    rows = rows.copy().sort_values(["period", "segment_name"])
    output = []
    for _, row in rows.iterrows():
        item = {
            "Data": row["period"],
            "Resultado": _format_indicator_result(indicator_key, row.get("value")),
            "Base": _format_base(indicator_key, row.get("volume")),
        }
        if rows["segment_name"].nunique() > 1:
            item["Setor"] = row["segment_name"]
        output.append(item)
    return pd.DataFrame(output)


def _external_table(rows: pd.DataFrame, indicator_key: str) -> pd.DataFrame:
    rows = rows.copy()
    rows["_hour_num"] = pd.to_numeric(rows["hour"], errors="coerce")
    rows = rows.sort_values(["_hour_num", "login"], na_position="last")

    output = []
    for _, row in rows.iterrows():
        volume = _int(row.get("volume"))
        successes = _int(row.get("successes"))
        losses = _int(row.get("losses"))
        item = {
            "Login externo": row["login"],
            "Horário": row["hour"],
            "Volume": volume,
        }
        if indicator_key == "toa_cancellation_rate":
            item["Não canceladas"] = successes
            item["Canceladas"] = losses
            item["Cancelamento %"] = _pct(None if volume <= 0 else losses / volume * 100)
        elif indicator_key == "dpa_official":
            item["DPA"] = _pct(row.get("value"))
        else:
            item["Ganhos / aderentes"] = successes
            item["Perdas"] = losses
            item["Resultado"] = _pct(row.get("value"))
        if _number(row.get("tma_seconds")) is not None:
            item["TMA médio"] = _duration(row.get("tma_seconds"))
        if _number(row.get("tmr_seconds")) is not None:
            item["TMR médio"] = _duration(row.get("tmr_seconds"))
        output.append(item)
    return pd.DataFrame(output)


def _overall_detail(breakdown_df: pd.DataFrame, indicator_key: str) -> dict | None:
    if breakdown_df.empty:
        return None
    rows = breakdown_df[
        (breakdown_df["indicator_key"] == indicator_key)
        & (breakdown_df["dimension"] == "overall")
    ].copy()
    if rows.empty:
        return None

    volume = float(pd.to_numeric(rows["volume"], errors="coerce").fillna(0).sum())
    successes = float(pd.to_numeric(rows["successes"], errors="coerce").fillna(0).sum())
    losses = float(pd.to_numeric(rows["losses"], errors="coerce").fillna(0).sum())

    return {
        "volume": volume,
        "successes": successes,
        "losses": losses,
        "tma_seconds": _weighted_duration(rows, "tma_seconds"),
        "tmr_seconds": _weighted_duration(rows, "tmr_seconds"),
    }


def _weighted_duration(rows: pd.DataFrame, column: str) -> float | None:
    if column not in rows.columns:
        return None
    values = pd.to_numeric(rows[column], errors="coerce")
    weights = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (weights > 0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _weighted_value(rows: pd.DataFrame) -> float | None:
    values = pd.to_numeric(rows["value"], errors="coerce")
    volumes = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (volumes > 0)
    if not valid.any():
        return None
    return round(float((values[valid] * volumes[valid]).sum() / volumes[valid].sum()), 1)


def _format_indicator_result(indicator_key: str, value) -> str:
    if indicator_key == "productivity_avg_daily":
        return _fmt(value, "number")
    return _pct(value)


def _format_base(indicator_key: str, value) -> str | int:
    if indicator_key == "dpa_official":
        return _format_hours(value)
    return _int(value)


def _fmt(value, unit) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return format_metric(number, unit)


def _pct(value) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.1f}%"


def _target_value(target, unit) -> str:
    number = _number(target)
    return "—" if number is None else format_metric(number, unit)


def _duration(seconds) -> str:
    number = _number(seconds)
    if number is None or number < 0:
        return "—"
    total = int(round(number))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_hours(seconds) -> str:
    number = _number(seconds)
    if number is None:
        return "—"
    return f"{number / 3600:.1f} h"


def _int(value) -> int:
    number = _number(value)
    return 0 if number is None else int(round(number))


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number
