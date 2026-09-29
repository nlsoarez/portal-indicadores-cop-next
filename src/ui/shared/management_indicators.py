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
    "region": "Macro regional",
    "group": "Cluster / regional",
    "city": "Cidade",
    "uf": "UF",
    "technology": "Tecnologia",
    "area": "Área envolvida",
    "symptom": "Sintoma",
    "tool": "Ferramenta de abertura",
    "closure": "Fechamento",
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
    "group",
    "city",
    "uf",
    "region",
    "technology",
    "turn",
    "hour",
    "demand",
    "type",
    "area",
    "cause",
    "network",
    "activity_type",
    "aging",
    "base",
    "queue_type",
    "queue",
    "nature",
    "symptom",
    "tool",
    "closure",
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


MANAGEMENT_DIMENSIONS = {
    "res_etit_fibra_hfc": ("service", "group", "city", "technology", "nature", "impact", "solution", "hour"),
    "res_etit_gpon": ("service", "group", "city", "technology", "nature", "impact", "solution", "hour"),
    "res_assert_fibra_hfc": ("service", "group", "city", "technology", "nature", "impact", "solution", "hour"),
    "res_assert_gpon": ("service", "group", "city", "technology", "nature", "impact", "solution", "hour"),
    "emp_etit_event": ("demand", "type", "area", "cause", "group", "city", "hour"),
    "validacao_20m": ("group", "network", "activity_type", "aging", "hour"),
    "toa_cancellation_rate": ("group", "network", "activity_type", "aging", "hour"),
    "closing_assertiveness": ("demand", "cause_toa", "cause_sir", "group", "hour"),
    "chat_10m": ("base", "queue_type", "queue", "hour"),
    "dpa_official": (),
    "productivity_avg_daily": (),
}

TEAM_AVERAGE_SPLITS = {
    "emp_etit_event": ("demand", ("RAL", "REC")),
    "res_etit_fibra_hfc": ("service", ("BROWNFIELD", "GREENFIELD")),
    "res_etit_gpon": ("service", ("BROWNFIELD", "GREENFIELD")),
}


FRAME_SCHEMAS = {
    "segment_summary": (
        "period", "segment_id", "segment_slug", "segment_name", "indicator_key", "name",
        "target_value", "direction", "unit", "value", "volume", "analysts",
    ),
    "analyst_summary": (
        "period", "segment_id", "segment_slug", "segment_name", "indicator_key", "name",
        "target_value", "direction", "unit", "user_id", "login", "display_name", "value", "volume",
    ),
    "analyst_metrics": (
        "period", "segment_id", "segment_slug", "segment_name", "indicator_key", "login",
        "volume", "successes", "losses", "tma_seconds", "tmr_seconds",
    ),
    "analyst_breakdowns": (
        "period", "segment_id", "segment_slug", "segment_name", "indicator_key", "name",
        "login", "dimension", "dimension_value", "value", "volume", "successes", "losses",
    ),
    "daily_summary": (
        "period", "data_month", "segment_id", "segment_slug", "segment_name",
        "indicator_key", "name", "unit", "value", "volume",
    ),
    "breakdowns": (
        "period", "segment_id", "segment_slug", "segment_name", "indicator_key", "name",
        "dimension", "dimension_value", "value", "volume", "successes", "losses",
        "tma_seconds", "tmr_seconds",
    ),
    "external": (
        "period", "indicator_key", "name", "login", "hour", "value", "volume",
        "successes", "losses", "tma_seconds", "tmr_seconds",
    ),
    "freshness": ("indicator_key", "name", "data_through", "refreshed_at"),
}


def render_management_indicators(
    ctx: AccessContext,
    segments: list[Segment],
    dashboard: DashboardService,
) -> None:
    payload = dashboard.management_payload(ctx, [segment.id for segment in segments])
    segment_df = _payload_frame(payload, "segment_summary")
    analyst_df = _payload_frame(payload, "analyst_summary")
    analyst_metrics_df = _payload_frame(payload, "analyst_metrics")
    analyst_breakdowns_df = _payload_frame(payload, "analyst_breakdowns")
    daily_df = _payload_frame(payload, "daily_summary")
    breakdown_df = _payload_frame(payload, "breakdowns")
    external_df = _payload_frame(payload, "external")
    freshness_df = _payload_frame(payload, "freshness")

    st.markdown("### Visão gerencial dos indicadores")
    st.caption(
        "Cada fonte possui sua própria aba. Dentro dela, os indicadores ficam separados e "
        "com resumo, analistas e cortes operacionais em tabelas — sem gráficos."
    )

    if segment_df.empty:
        st.info("Ainda não há resultados processados para os indicadores.")
        return

    freshness_index = {
        str(row.get("indicator_key")): row
        for row in freshness_df.to_dict("records")
        if row.get("indicator_key") not in (None, "")
    } if not freshness_df.empty else {}

    available = set(segment_df["indicator_key"].dropna().astype(str))
    groups = [
        (label, tuple(key for key in keys if key in available))
        for label, keys in SOURCE_GROUPS
    ]
    groups = [(label, keys) for label, keys in groups if keys]
    known_keys = {key for _, keys in SOURCE_GROUPS for key in keys}
    unknown_keys = tuple(sorted(available - known_keys))
    if unknown_keys:
        groups.append(("Outros indicadores", unknown_keys))
    if not groups:
        st.info("Há resultados no banco, mas nenhum indicador reconhecido para exibição.")
        return

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
                analyst_breakdowns_df=analyst_breakdowns_df,
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
    analyst_breakdowns_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    breakdown_df: pd.DataFrame,
    external_df: pd.DataFrame,
    freshness_index: dict[str, dict],
) -> None:
    st.markdown(f"## {source_label}")

    if len(indicator_keys) == 1:
        _render_indicator(
            indicator_keys[0],
            ctx=ctx,
            segment_df=segment_df,
            analyst_df=analyst_df,
            analyst_metrics_df=analyst_metrics_df,
            analyst_breakdowns_df=analyst_breakdowns_df,
            daily_df=daily_df,
            breakdown_df=breakdown_df,
            external_df=external_df,
            freshness_index=freshness_index,
        )
        return

    indicator_names = []
    visible_keys = []
    for key in indicator_keys:
        rows = _indicator_frame(segment_df, key)
        if rows.empty:
            continue
        indicator_names.append(str(rows.iloc[0].get("name") or key))
        visible_keys.append(key)

    if not visible_keys:
        st.info("Nenhum indicador desta fonte possui dados na competência atual.")
        return

    indicator_tabs = st.tabs(indicator_names)
    for indicator_tab, key in zip(indicator_tabs, visible_keys):
        with indicator_tab:
            _render_indicator(
                key,
                ctx=ctx,
                segment_df=segment_df,
                analyst_df=analyst_df,
                analyst_metrics_df=analyst_metrics_df,
                analyst_breakdowns_df=analyst_breakdowns_df,
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
    analyst_breakdowns_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    breakdown_df: pd.DataFrame,
    external_df: pd.DataFrame,
    freshness_index: dict[str, dict],
) -> None:
    rows = _indicator_frame(segment_df, indicator_key)
    if rows.empty:
        return

    first = rows.iloc[0]
    name = str(first.get("name") or indicator_key)
    unit = first.get("unit")
    direction = str(first.get("direction") or "higher_is_better")
    target = first.get("target_value")
    period = str(first.get("period") or "")
    fresh = freshness_index.get(indicator_key, {})

    details = _indicator_frame(breakdown_df, indicator_key)
    detail = _overall_detail(breakdown_df, indicator_key)
    people = _indicator_frame(analyst_df, indicator_key)
    metrics = _indicator_frame(analyst_metrics_df, indicator_key)
    analyst_breakdowns = _indicator_frame(analyst_breakdowns_df, indicator_key)
    daily = _indicator_frame(daily_df, indicator_key)
    ext = _indicator_frame(external_df, indicator_key) if ctx.is_admin else external_df.iloc[0:0].copy()

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

    summary_tab, diagnostic_tab, analysts_tab = st.tabs(
        ["Resumo executivo", "Diagnóstico", "Analistas"]
    )

    with summary_tab:
        _render_executive_summary(
            indicator_key=indicator_key,
            rows=rows,
            people=people,
            analyst_breakdowns=analyst_breakdowns,
            details=details,
            target=target,
            direction=direction,
        )

    with diagnostic_tab:
        _render_diagnostic(
            indicator_key=indicator_key,
            rows=rows,
            details=details,
            daily=daily,
            external=ext,
        )

    with analysts_tab:
        _render_analysts_compact(
            people,
            metrics,
            indicator_key=indicator_key,
            direction=direction,
            target=target,
            unit=unit,
        )


def _render_executive_summary(
    *,
    indicator_key: str,
    rows: pd.DataFrame,
    people: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
    details: pd.DataFrame,
    target,
    direction: str,
) -> None:
    if len(rows) > 1:
        st.markdown("#### Resultado por setor")
        st.dataframe(
            _sector_table(rows, indicator_key, pd.DataFrame(), target=target, direction=direction),
            use_container_width=True,
            hide_index=True,
        )
    else:
        segment_name = str(rows.iloc[0].get("segment_name") or "—")
        st.caption(f"Setor: {segment_name}")

    _render_team_average_panel(
        indicator_key=indicator_key,
        people=people,
        analyst_breakdowns=analyst_breakdowns,
    )
    _render_management_focus(
        indicator_key=indicator_key,
        details=details,
        target=target,
        direction=direction,
    )


def _render_team_average_panel(
    *,
    indicator_key: str,
    people: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
) -> None:
    config = TEAM_AVERAGE_SPLITS.get(indicator_key)
    if not config or people.empty or analyst_breakdowns.empty:
        return

    dimension, preferred = config
    rows = _dimension_rows(analyst_breakdowns, dimension)
    if rows.empty:
        return

    universe = sorted(
        login for login in people.get("login", pd.Series(dtype="object")).dropna().astype(str).unique()
        if login.strip()
    )
    if not universe:
        return

    available_values = [str(value) for value in rows["dimension_value"].dropna().unique() if str(value).strip()]
    if not available_values:
        return

    upper_map = {value.upper(): value for value in available_values}
    categories = [upper_map[value] for value in preferred if value in upper_map]
    if not categories:
        volume_by_value = (
            rows.assign(_volume=pd.to_numeric(rows["volume"], errors="coerce").fillna(0))
            .groupby("dimension_value")["_volume"]
            .sum()
            .sort_values(ascending=False)
        )
        categories = [str(value) for value in volume_by_value.head(2).index]
    categories = categories[:2]
    if not categories:
        return

    stats = []
    for category in categories:
        part = rows[rows["dimension_value"].astype(str) == category].copy()
        grouped = part.groupby("login", dropna=False).agg(
            successes=("successes", "sum"),
            losses=("losses", "sum"),
            volume=("volume", "sum"),
        )
        grouped = grouped.reindex(universe, fill_value=0)
        total_volume = float(pd.to_numeric(grouped["volume"], errors="coerce").fillna(0).sum())
        total_successes = float(pd.to_numeric(grouped["successes"], errors="coerce").fillna(0).sum())
        adherence = None if total_volume <= 0 else total_successes / total_volume * 100
        stats.append({
            "category": category,
            "avg_successes": float(pd.to_numeric(grouped["successes"], errors="coerce").fillna(0).mean()),
            "avg_losses": float(pd.to_numeric(grouped["losses"], errors="coerce").fillna(0).mean()),
            "adherence": adherence,
        })

    title = " e ".join(item["category"] for item in stats)
    st.markdown(f"#### Média da equipe por analista — {title}")
    st.caption("Média absoluta por analista; a aderência total da categoria aparece abaixo de cada valor.")

    cards = []
    for item in stats:
        cards.append((f"{item['category']} · aderentes", item["avg_successes"], item["adherence"]))
    for item in stats:
        cards.append((f"{item['category']} · não aderentes", item["avg_losses"], item["adherence"]))

    columns = st.columns(len(cards))
    for column, (label, value, adherence) in zip(columns, cards):
        with column:
            st.metric(label, f"{value:.1f}")
            if adherence is not None:
                st.caption(f"Aderência da categoria: {adherence:.1f}%")


def _render_management_focus(
    *,
    indicator_key: str,
    details: pd.DataFrame,
    target,
    direction: str,
) -> None:
    if details.empty:
        return

    dimensions = MANAGEMENT_DIMENSIONS.get(indicator_key, ())
    usable = _dimensions_rows(details, dimensions)
    usable = _exclude_dimension_prefix(usable, "service__")
    if usable.empty:
        return

    if usable["segment_name"].nunique(dropna=True) > 1:
        usable = _aggregate_breakdown_rows(usable)
    if usable.empty:
        return

    priorities: list[dict] = []
    strengths: list[dict] = []

    for dimension in dimensions:
        part = _dimension_rows(usable, dimension)
        if part.empty:
            continue

        part = part.copy()
        part["_volume"] = pd.to_numeric(part["volume"], errors="coerce").fillna(0)
        part["_successes"] = pd.to_numeric(part["successes"], errors="coerce").fillna(0)
        part["_losses"] = pd.to_numeric(part["losses"], errors="coerce").fillna(0)
        part["_result"] = part.apply(lambda row: _manager_result(indicator_key, row), axis=1)
        part = part[part["_volume"] > 0]
        if part.empty:
            continue

        min_volume = max(3.0, float(part["_volume"].sum()) * 0.02)
        relevant = part[part["_volume"] >= min_volume].copy()
        if relevant.empty:
            relevant = part.copy()

        worst = relevant.sort_values(
            ["_losses", "_volume"], ascending=[False, False]
        ).iloc[0]
        if float(worst["_losses"]) > 0:
            priorities.append(_focus_row(dimension, worst, indicator_key, target, direction, "losses"))

        if indicator_key == "toa_cancellation_rate":
            best = relevant.sort_values(
                ["_result", "_volume"], ascending=[True, False], na_position="last"
            ).iloc[0]
        else:
            best = relevant.sort_values(
                ["_result", "_volume"], ascending=[False, False], na_position="last"
            ).iloc[0]
        strengths.append(_focus_row(dimension, best, indicator_key, target, direction, "successes"))

    priorities = sorted(priorities, key=lambda row: row["_sort"], reverse=True)[:5]
    strengths = sorted(strengths, key=lambda row: row["_sort"], reverse=True)[:5]

    if not priorities and not strengths:
        return

    st.markdown("#### Leitura de gestão")
    left, right = st.columns(2)
    with left:
        st.markdown("**Prioridades para recuperar**")
        if priorities:
            st.dataframe(
                pd.DataFrame([{k: v for k, v in row.items() if not k.startswith("_")} for row in priorities]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Nenhuma concentração relevante de perdas encontrada.")
    with right:
        st.markdown("**Pontos para manter**")
        if strengths:
            st.dataframe(
                pd.DataFrame([{k: v for k, v in row.items() if not k.startswith("_")} for row in strengths]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Ainda não há base suficiente para destacar pontos fortes.")


def _focus_row(
    dimension: str,
    row: pd.Series,
    indicator_key: str,
    target,
    direction: str,
    sort_by: str,
) -> dict:
    result = _manager_result(indicator_key, row)
    gap = _goal_gap(result, target, direction)
    item = {
        "Foco": DIMENSION_LABELS.get(dimension, dimension),
        "Onde": str(row.get("dimension_value") or "—"),
        "Resultado": _pct(result),
        "Volume": _int(row.get("volume")),
    }
    if sort_by == "losses":
        item["Perdas"] = _int(row.get("losses"))
        item["_sort"] = float(_number(row.get("losses")) or 0)
    else:
        item["Ganhos"] = _int(row.get("successes"))
        item["_sort"] = float(_number(row.get("successes")) or 0)
    if gap is not None:
        item["Gap meta"] = f"{gap:+.1f} pp"
    return item


def _manager_result(indicator_key: str, row: pd.Series) -> float | None:
    volume = _number(row.get("volume"))
    if indicator_key == "toa_cancellation_rate":
        losses = _number(row.get("losses"))
        if volume is None or volume <= 0 or losses is None:
            return None
        return losses / volume * 100
    return _number(row.get("value"))


def _goal_gap(value, target, direction: str) -> float | None:
    value_num = _number(value)
    target_num = _number(target)
    if value_num is None or target_num is None:
        return None
    if direction == "lower_is_better":
        return target_num - value_num
    return value_num - target_num


def _render_diagnostic(
    *,
    indicator_key: str,
    rows: pd.DataFrame,
    details: pd.DataFrame,
    daily: pd.DataFrame,
    external: pd.DataFrame,
) -> None:
    segment_names = _segment_names(rows)
    scope_options = ["Geral", *segment_names] if len(segment_names) > 1 else (segment_names or ["Geral"])

    c1, c2 = st.columns(2)
    with c1:
        scope = st.selectbox(
            "Setor",
            scope_options,
            key=f"diag_scope_{indicator_key}",
        )

    scoped = _scope_frame(details, scope)

    service_values = []
    if not scoped.empty:
        service_rows = _dimension_rows(scoped, "service")
        service_values = sorted(
            str(value) for value in service_rows["dimension_value"].dropna().unique()
            if str(value).strip()
        )
    has_service_context = (
        len(service_values) > 1
        and not scoped.empty
        and scoped["dimension"].astype(str).str.startswith("service__", na=False).any()
    )

    service_choice = "Todos"
    if has_service_context:
        with c2:
            service_choice = st.selectbox(
                "Serviço",
                ["Todos", *service_values],
                key=f"diag_service_{indicator_key}_{scope}",
            )
    else:
        with c2:
            st.caption("Use o recorte abaixo para localizar concentração de volume, perdas e aderência.")

    if service_choice != "Todos":
        scoped = _service_scoped_details(scoped, service_choice)
    else:
        scoped = _exclude_dimension_prefix(scoped, "service__")

    if scope == "Geral" and not scoped.empty:
        scoped = _aggregate_breakdown_rows(scoped)

    preferred_dimensions = MANAGEMENT_DIMENSIONS.get(indicator_key, ())
    available_dimensions = [
        dimension for dimension in preferred_dimensions
        if not _dimension_rows(scoped, dimension).empty
    ]

    choices: list[tuple[str, str]] = [
        (DIMENSION_LABELS.get(dimension, dimension), dimension)
        for dimension in available_dimensions
    ]

    scoped_daily = _scope_frame(daily, scope)
    if scope == "Geral" and not scoped_daily.empty:
        scoped_daily = _aggregate_daily_rows(scoped_daily)
    if not scoped_daily.empty:
        choices.append(("Evolução diária", "__daily__"))
    if not external.empty:
        choices.append(("Fora da equipe · madrugada", "__external__"))

    if not choices:
        st.info(
            "Ainda não há detalhamento operacional nesta carga. Reprocesse a fonte para preencher "
            "cluster, cidade, serviço, causas, horários e demais cortes disponíveis."
        )
        return

    labels = [label for label, _ in choices]
    selected_label = st.selectbox(
        "Analisar por",
        labels,
        key=f"diag_dimension_{indicator_key}_{scope}_{service_choice}",
    )
    selected = next(value for label, value in choices if label == selected_label)

    if selected == "__daily__":
        table = _daily_table(scoped_daily, indicator_key)
    elif selected == "__external__":
        table = _external_table(external, indicator_key)
    else:
        part = _dimension_rows(scoped, selected)
        table = _breakdown_table(part, selected, indicator_key)

    if table.empty:
        st.info("Sem dados para este recorte.")
        return

    st.caption("Ordenação prioriza concentração de perdas e volume; horários permanecem em ordem cronológica.")
    st.dataframe(table, use_container_width=True, hide_index=True)


def _render_analysts_compact(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    *,
    indicator_key: str,
    direction: str,
    target,
    unit,
) -> None:
    if people.empty:
        st.info("Nenhum analista com resultado para a competência atual.")
        return

    segment_names = _segment_names(people)
    if len(segment_names) > 1:
        scope = st.selectbox(
            "Setor",
            ["Todos", *segment_names],
            key=f"analyst_scope_{indicator_key}",
        )
    else:
        scope = segment_names[0] if segment_names else "Todos"

    scoped_people = people.copy() if scope == "Todos" else _scope_frame(people, scope)
    scoped_metrics = metrics.copy() if scope == "Todos" else _scope_frame(metrics, scope)

    st.dataframe(
        _analyst_table(
            scoped_people,
            scoped_metrics,
            indicator_key=indicator_key,
            direction=direction,
            target=target,
            unit=unit,
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_operational_details(
    details: pd.DataFrame,
    indicator_key: str,
    indicator_rows: pd.DataFrame,
) -> None:
    segment_names = _segment_names(indicator_rows)
    scopes = ["Geral", *segment_names] if len(segment_names) > 1 else (segment_names or ["Geral"])
    scope_tabs = st.tabs(scopes)

    for scope_tab, scope in zip(scope_tabs, scopes):
        with scope_tab:
            scoped = _scope_frame(details, scope)
            if scoped.empty:
                st.info("Sem detalhamento para este setor.")
                continue

            service_rows = _dimension_rows(scoped, "service")
            service_values = sorted(service_rows["dimension_value"].dropna().astype(str).unique())
            service_choice = "Todos"
            if len(service_values) > 1:
                service_choice = st.radio(
                    "Serviço",
                    ["Todos", *service_values],
                    horizontal=True,
                    key=f"mgmt_service_{indicator_key}_{scope}",
                )

            if service_choice != "Todos":
                scoped = _service_scoped_details(scoped, service_choice)
                st.caption(f"Cortes abaixo filtrados para o serviço: {service_choice}")
            else:
                scoped = _exclude_dimension_prefix(scoped, "service__")

            if scope == "Geral":
                scoped = _aggregate_breakdown_rows(scoped)

            categories = (
                (
                    "Cobertura",
                    ("service", "group", "city", "uf", "region", "technology", "network", "base"),
                ),
                (
                    "Causas e perfil",
                    (
                        "demand", "type", "area", "cause", "activity_type", "aging",
                        "nature", "symptom", "tool", "closure", "impact", "solution",
                        "cause_toa", "cause_sir",
                    ),
                ),
                ("Filas", ("queue_type", "queue")),
            )
            available_categories = [
                (label, tuple(dim for dim in dims if not _dimension_rows(scoped, dim).empty))
                for label, dims in categories
            ]
            available_categories = [(label, dims) for label, dims in available_categories if dims]
            if not available_categories:
                st.info("Não há cortes operacionais adicionais para este indicador.")
                continue

            category_tabs = st.tabs([label for label, _ in available_categories])
            for category_tab, (_, dimensions) in zip(category_tabs, available_categories):
                with category_tab:
                    dimension_tabs = st.tabs([DIMENSION_LABELS.get(dimension, dimension) for dimension in dimensions])
                    for dimension_tab, dimension in zip(dimension_tabs, dimensions):
                        with dimension_tab:
                            part = _dimension_rows(scoped, dimension)
                            st.dataframe(
                                _breakdown_table(part, dimension, indicator_key),
                                use_container_width=True,
                                hide_index=True,
                            )


def _render_time_details(
    details: pd.DataFrame,
    daily: pd.DataFrame,
    indicator_key: str,
    indicator_rows: pd.DataFrame,
) -> None:
    segment_names = _segment_names(indicator_rows)
    scopes = ["Geral", *segment_names] if len(segment_names) > 1 else (segment_names or ["Geral"])
    scope_tabs = st.tabs(scopes)

    for scope_tab, scope in zip(scope_tabs, scopes):
        with scope_tab:
            scoped_details = _scope_frame(details, scope)
            scoped_daily = _scope_frame(daily, scope)

            scoped_details = _dimensions_rows(scoped_details, ("turn", "hour"))
            if scope == "Geral" and not scoped_details.empty:
                scoped_details = _aggregate_breakdown_rows(scoped_details)
            if scope == "Geral" and not scoped_daily.empty:
                scoped_daily = _aggregate_daily_rows(scoped_daily)

            blocks = []
            if not _dimension_rows(scoped_details, "turn").empty:
                blocks.append(("Turno", "turn"))
            if not _dimension_rows(scoped_details, "hour").empty:
                blocks.append(("Hora", "hour"))
            if not scoped_daily.empty:
                blocks.append(("Evolução diária", "daily"))

            if not blocks:
                st.info("Esta fonte não possui recorte temporal disponível na competência atual.")
                continue

            detail_tabs = st.tabs([label for label, _ in blocks])
            for detail_tab, (_, kind) in zip(detail_tabs, blocks):
                with detail_tab:
                    if kind == "daily":
                        st.dataframe(
                            _daily_table(scoped_daily, indicator_key),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        part = _dimension_rows(scoped_details, kind)
                        st.dataframe(
                            _breakdown_table(part, kind, indicator_key),
                            use_container_width=True,
                            hide_index=True,
                        )


def _segment_names(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty or "segment_name" not in frame.columns:
        return []
    return sorted(
        value for value in frame["segment_name"].dropna().astype(str).unique()
        if value.strip()
    )


def _payload_frame(payload: dict, key: str) -> pd.DataFrame:
    """Cria DataFrame com schema estável mesmo quando o payload vem vazio/parcial."""
    columns = FRAME_SCHEMAS[key]
    records = payload.get(key) or []
    frame = pd.DataFrame(records)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.Series(index=frame.index, dtype="object")
    return frame.loc[:, list(dict.fromkeys([*frame.columns, *columns]))]


def _indicator_frame(frame: pd.DataFrame, indicator_key: str) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if frame.empty:
        return frame.copy()
    if "indicator_key" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame["indicator_key"] == indicator_key].copy()


def _scope_frame(frame: pd.DataFrame, scope: str) -> pd.DataFrame:
    """Filtra por setor preservando o schema, inclusive para cargas legadas/vazias."""
    if frame is None:
        return pd.DataFrame()
    if frame.empty or scope == "Geral":
        return frame.copy()
    if "segment_name" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame["segment_name"] == scope].copy()


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if frame.empty or "dimension" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame["dimension"] == dimension].copy()


def _dimensions_rows(frame: pd.DataFrame, dimensions: tuple[str, ...]) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if frame.empty or "dimension" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame["dimension"].isin(dimensions)].copy()


def _exclude_dimension_prefix(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if frame.empty or "dimension" not in frame.columns:
        return frame.copy()
    return frame[~frame["dimension"].astype(str).str.startswith(prefix, na=False)].copy()


def _render_analyst_details(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    *,
    indicator_key: str,
    direction: str,
    target,
    unit,
) -> None:
    if people.empty:
        st.info("Nenhum analista com resultado para a competência atual.")
        return

    segment_names = _segment_names(people)
    scopes = ["Todos", *segment_names] if len(segment_names) > 1 else (segment_names or ["Todos"])
    scope_tabs = st.tabs(scopes)
    for scope_tab, scope in zip(scope_tabs, scopes):
        with scope_tab:
            scoped_people = people.copy() if scope == "Todos" else people[people["segment_name"] == scope].copy()
            scoped_metrics = metrics.copy()
            if scope != "Todos" and not scoped_metrics.empty and "segment_name" in scoped_metrics.columns:
                scoped_metrics = scoped_metrics[scoped_metrics["segment_name"] == scope].copy()
            st.dataframe(
                _analyst_table(
                    scoped_people,
                    scoped_metrics,
                    indicator_key=indicator_key,
                    direction=direction,
                    target=target,
                    unit=unit,
                ),
                use_container_width=True,
                hide_index=True,
            )


def _service_scoped_details(rows: pd.DataFrame, service: str) -> pd.DataFrame:
    if rows is None or rows.empty or not {"dimension", "dimension_value"}.issubset(rows.columns):
        return rows.iloc[0:0].copy() if rows is not None else pd.DataFrame()
    direct_service = rows[
        (rows["dimension"] == "service")
        & (rows["dimension_value"].astype(str) == service)
    ].copy()

    composite = rows[rows["dimension"].astype(str).str.startswith("service__", na=False)].copy()
    if composite.empty:
        return direct_service

    split_values = composite["dimension_value"].astype(str).str.split("|||", n=1, expand=True, regex=False)
    if split_values.shape[1] < 2:
        return direct_service
    composite = composite[split_values[0] == service].copy()
    if composite.empty:
        return direct_service

    selected_values = composite["dimension_value"].astype(str).str.split("|||", n=1, expand=True, regex=False)
    composite["dimension_value"] = selected_values[1].values
    composite["dimension"] = composite["dimension"].astype(str).str.replace(
        r"^service__", "", regex=True
    )
    return pd.concat([direct_service, composite], ignore_index=True)


def _aggregate_breakdown_rows(rows: pd.DataFrame) -> pd.DataFrame:
    required = {"dimension", "dimension_value", "volume", "successes", "losses"}
    if rows is None or rows.empty:
        return rows.copy() if rows is not None else pd.DataFrame()
    if not required.issubset(rows.columns):
        return rows.iloc[0:0].copy()
    records = []
    for (dimension, dimension_value), part in rows.groupby(
        ["dimension", "dimension_value"], dropna=False
    ):
        volume = pd.to_numeric(part["volume"], errors="coerce").fillna(0)
        successes = pd.to_numeric(part["successes"], errors="coerce").fillna(0)
        losses = pd.to_numeric(part["losses"], errors="coerce").fillna(0)
        total_volume = float(volume.sum())
        total_successes = float(successes.sum())
        total_losses = float(losses.sum())

        def weighted_average(column: str):
            if column not in part.columns:
                return None
            values = pd.to_numeric(part[column], errors="coerce")
            valid = values.notna() & volume.gt(0)
            if not valid.any():
                return None
            weights = volume[valid]
            return float((values[valid] * weights).sum() / weights.sum())

        first = part.iloc[0]
        records.append({
            "period": first.get("period"),
            "segment_id": 0,
            "segment_slug": "geral",
            "segment_name": "Geral",
            "indicator_key": first.get("indicator_key"),
            "name": first.get("name"),
            "dimension": dimension,
            "dimension_value": dimension_value,
            "value": None if total_volume <= 0 else round(total_successes / total_volume * 100, 1),
            "volume": total_volume,
            "successes": total_successes,
            "losses": total_losses,
            "tma_seconds": weighted_average("tma_seconds"),
            "tmr_seconds": weighted_average("tmr_seconds"),
        })
    return pd.DataFrame(records)


def _aggregate_daily_rows(rows: pd.DataFrame) -> pd.DataFrame:
    required = {"period", "value", "volume"}
    if rows is None or rows.empty:
        return rows.copy() if rows is not None else pd.DataFrame()
    if not required.issubset(rows.columns):
        return rows.iloc[0:0].copy()
    records = []
    for period, part in rows.groupby("period", dropna=False):
        volume = pd.to_numeric(part["volume"], errors="coerce").fillna(0)
        values = pd.to_numeric(part["value"], errors="coerce")
        valid = values.notna() & volume.gt(0)
        total_volume = float(volume.sum())
        value = None
        if valid.any() and float(volume[valid].sum()) > 0:
            value = float((values[valid] * volume[valid]).sum() / volume[valid].sum())
        first = part.iloc[0]
        records.append({
            "period": period,
            "data_month": first.get("data_month"),
            "segment_id": 0,
            "segment_slug": "geral",
            "segment_name": "Geral",
            "indicator_key": first.get("indicator_key"),
            "name": first.get("name"),
            "unit": first.get("unit"),
            "value": value,
            "volume": total_volume,
        })
    return pd.DataFrame(records)


def _render_gain_loss_summary(details: pd.DataFrame, indicator_key: str) -> None:
    required = {"dimension", "volume", "successes", "losses"}
    if (
        details is None
        or details.empty
        or not required.issubset(details.columns)
        or indicator_key in {"dpa_official", "productivity_avg_daily"}
    ):
        return
    usable = details[
        ~details["dimension"].isin(("overall", "turn", "hour"))
        & ~details["dimension"].astype(str).str.startswith("service__", na=False)
    ].copy()
    if usable.empty:
        return
    usable = _aggregate_breakdown_rows(usable)
    if usable.empty:
        return

    losses = pd.to_numeric(usable["losses"], errors="coerce").fillna(0)
    successes = pd.to_numeric(usable["successes"], errors="coerce").fillna(0)
    candidates = []
    if losses.max() > 0:
        for _, row in usable.assign(_metric=losses).sort_values("_metric", ascending=False).head(5).iterrows():
            candidates.append(("Mais perdas", row))
    if successes.max() > 0:
        for _, row in usable.assign(_metric=successes).sort_values("_metric", ascending=False).head(5).iterrows():
            candidates.append(("Mais ganhos", row))
    if not candidates:
        return

    output = []
    seen = set()
    for kind, row in candidates:
        dimension = str(row["dimension"])
        value = str(row["dimension_value"])
        key = (kind, dimension, value)
        if key in seen:
            continue
        seen.add(key)
        volume = _int(row.get("volume"))
        success = _int(row.get("successes"))
        loss = _int(row.get("losses"))
        result = None if volume <= 0 else success / volume * 100
        output.append({
            "Leitura": kind,
            "Corte": DIMENSION_LABELS.get(dimension, dimension),
            "Valor": value,
            "Volume": volume,
            "Ganhos / aderentes": success,
            "Perdas / não aderentes": loss,
            "Resultado": _pct(result),
        })
    if output:
        st.markdown("#### Onde mais ganha e onde mais perde")
        st.dataframe(pd.DataFrame(output), use_container_width=True, hide_index=True)

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
        merge_keys = [col for col in ("login", "segment_id") if col in available and col in rows.columns]
        if merge_keys:
            metric_frame = metrics[available].drop_duplicates(subset=merge_keys)
            rows = rows.merge(metric_frame, on=merge_keys, how="left")

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
    label = DIMENSION_LABELS.get(dimension, str(dimension).replace("_", " ").title())
    if rows is None or rows.empty:
        return pd.DataFrame()
    required = {"dimension_value", "volume", "successes", "losses", "value"}
    if not required.issubset(rows.columns):
        return pd.DataFrame()
    rows = rows.copy()
    if "segment_name" not in rows.columns:
        rows["segment_name"] = "Geral"

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
    if rows is None or rows.empty or not {"period", "value", "volume"}.issubset(rows.columns):
        return pd.DataFrame()
    rows = rows.copy()
    if "segment_name" not in rows.columns:
        rows["segment_name"] = "Geral"
    rows = rows.sort_values(["period", "segment_name"])
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
    required = {"hour", "login", "volume", "successes", "losses", "value"}
    if rows is None or rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame()
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
    required = {"indicator_key", "dimension", "volume", "successes", "losses"}
    if breakdown_df is None or breakdown_df.empty or not required.issubset(breakdown_df.columns):
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
    if rows is None or rows.empty or column not in rows.columns or "volume" not in rows.columns:
        return None
    values = pd.to_numeric(rows[column], errors="coerce")
    weights = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (weights > 0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _weighted_value(rows: pd.DataFrame) -> float | None:
    if rows is None or rows.empty or not {"value", "volume"}.issubset(rows.columns):
        return None
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
