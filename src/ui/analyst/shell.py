from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.ui.shared.chrome import render_sidebar_brand
from src.ui.shared.freshness import render_indicator_freshness
from src.ui.shared.metrics import format_metric, format_target


DIMENSION_LABELS = {
    "group": "Cluster",
    "service": "Serviço",
    "demand": "Demanda",
    "cause": "Causa",
    "cause_toa": "Causa TOA",
    "cause_sir": "Causa SIR",
    "area": "Área",
    "area_involved": "Área envolvida",
    "network": "Rede",
    "activity_type": "Tipo de atividade",
    "incident_type": "Tipo de incidente",
    "aging": "Faixa de tempo",
    "hour": "Hora",
    "base": "Base",
    "queue": "Fila",
    "queue_type": "Tipo de fila",
    "productivity_component": "Componente",
    "nature": "Natureza",
    "impact": "Impacto",
    "solution": "Solução",
    "city": "Cidade",
    "technology": "Tecnologia",
    "type": "Tipo",
}

DETAIL_DIMENSIONS = {
    "res_etit_fibra_hfc": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "res_etit_gpon": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "res_assert_fibra_hfc": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "res_assert_gpon": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "emp_etit_event": ("demand", "type", "area", "cause", "group", "city"),
    "validacao_20m": ("group", "network", "activity_type", "incident_type", "aging"),
    "chat_10m": ("base", "queue_type", "queue", "hour"),
    "closing_assertiveness": ("demand", "cause_toa", "cause_sir", "area_involved", "group"),
    "toa_cancellation_rate": ("group", "network", "activity_type", "incident_type", "aging"),
    "productivity_avg_daily": ("productivity_component",),
}


INDICATOR_TAB_LABELS = {
    "res_assert_fibra_hfc": "📡 Assert. HFC",
    "res_assert_gpon": "📶 Assert. GPON",
    "chat_10m": "💬 Chat Livre",
    "dpa_official": "⏱️ DPA",
    "res_etit_fibra_hfc": "⚡ ETIT HFC",
    "res_etit_gpon": "🔎 ETIT GPON",
    "emp_etit_event": "⚡ ETIT Evento",
    "productivity_avg_daily": "📦 Produtividade",
    "validacao_20m": "✅ Tempo de Validação",
    "toa_cancellation_rate": "❌ Canceladas",
    "closing_assertiveness": "🌙 Fechamento",
}


class AnalystShell:
    def __init__(self):
        self.dashboard = DashboardService()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        render_sidebar_brand(
            role="analyst",
            user_name=ctx.user.display_name,
        )
        if len(segments) == 1:
            segment = segments[0]
            st.sidebar.caption(f"Segmento: {segment.name}")
        else:
            segment = st.sidebar.selectbox(
                "Meu segmento",
                segments,
                format_func=lambda item: item.name,
                key="analyst_segment_selector",
            )
        switch_segment_state(st.session_state, segment.id)

        payload = self.dashboard.analyst_payload(ctx, segment.id)
        latest = _latest_by_indicator(payload.get("summary") or [])

        _inject_analyst_styles()
        st.markdown("<div class='cop-analyst-shell'></div>", unsafe_allow_html=True)
        _render_identity_bar(
            ctx.user.full_name or ctx.user.display_name,
            segment.name,
            latest,
        )

        if segment.slug == "empresarial":
            enterprise_order = [
                ("productivity_avg_daily", "📦 Produtividade"),
                ("emp_etit_event", "⚡ ETIT Evento"),
                ("dpa_official", "⏱️ DPA"),
                ("validacao_20m", "✅ Tempo de Validação"),
                ("chat_10m", "💬 Chat Livre"),
                ("closing_assertiveness", "🌙 Fechamento"),
                ("toa_cancellation_rate", "❌ Canceladas"),
            ]
            latest_index = {
                str(row.get("indicator_key")): row
                for row in latest
            }

            labels = ["🏠 Resumo"]
            labels.extend(label for _, label in enterprise_order)
            labels.extend(["Analista certificado", "↺ Histórico"])
            tabs = st.tabs(labels)

            summary_tab = tabs[0]
            enterprise_tabs = tabs[1:1 + len(enterprise_order)]
            certified_tab = tabs[-2]
            history_tab = tabs[-1]

            with summary_tab:
                self._render_summary(payload, latest)
                with st.expander("Atualização dos meus indicadores", expanded=False):
                    render_indicator_freshness(
                        payload.get("freshness") or [],
                        compact=True,
                        show_title=False,
                        columns=3,
                    )

            team_index = _team_index(payload)
            for tab, (indicator_key, _) in zip(enterprise_tabs, enterprise_order):
                with tab:
                    row = latest_index.get(indicator_key)
                    if row is None:
                        st.info("Ainda não há dados processados para este indicador.")
                        continue
                    team = team_index.get(
                        (str(row.get("period")), indicator_key),
                        {},
                    )
                    self._render_indicator(payload, row, team)

            with certified_tab:
                self._render_enterprise_certification(payload, latest)

            with history_tab:
                self._render_history(payload)
            return

        if segment.slug == "residencial":
            latest_index = {
                str(row.get("indicator_key")): row
                for row in latest
            }
            summary_tab, indicators_tab, history_tab = st.tabs(
                [
                    "🏠 Resumo",
                    "📊 Indicadores",
                    "↺ Histórico",
                ]
            )

            with summary_tab:
                self._render_summary(payload, latest)
                with st.expander("Atualização dos meus indicadores", expanded=False):
                    render_indicator_freshness(
                        payload.get("freshness") or [],
                        compact=True,
                        show_title=False,
                        columns=3,
                    )

            with indicators_tab:
                # Abas fixas: não desaparecem quando uma fonte ainda não foi
                # processada no período. A ordem prioriza leitura operacional.
                residential_order = [
                    ("productivity_avg_daily", "📦 Produtividade"),
                    ("res_etit_fibra_hfc", "⚡ ETIT HFC"),
                    ("res_etit_gpon", "🔎 ETIT GPON"),
                    ("dpa_official", "⏱️ DPA"),
                    ("validacao_20m", "✅ Tempo de Validação"),
                    ("chat_10m", "💬 Chat Livre"),
                    ("res_assert_fibra_hfc", "📡 Assert. HFC"),
                    ("res_assert_gpon", "📶 Assert. GPON"),
                    ("toa_cancellation_rate", "❌ Canceladas"),
                ]

                sub_labels = [
                    label
                    for _, label in residential_order
                ]
                sub_labels.append("✅ Analista Certificado")
                sub_tabs = st.tabs(sub_labels)

                team_index = _team_index(payload)
                for tab, (indicator_key, _) in zip(
                    sub_tabs[:-1],
                    residential_order,
                ):
                    with tab:
                        row = latest_index.get(indicator_key)
                        if row is None:
                            st.info(
                                "Ainda não há dados processados para este indicador."
                            )
                            continue

                        team = team_index.get(
                            (str(row.get("period")), indicator_key),
                            {},
                        )
                        self._render_indicator(payload, row, team)

                with sub_tabs[-1]:
                    self._render_residential_certification(payload, latest)

            with history_tab:
                self._render_history(payload)
            return

        summary_tab, indicators_tab, history_tab = st.tabs(
            ["🏠 Resumo", "📊 Indicadores", "↺ Histórico"]
        )

        with summary_tab:
            self._render_summary(payload, latest)
            with st.expander("Atualização dos meus indicadores", expanded=False):
                render_indicator_freshness(
                    payload.get("freshness") or [],
                    compact=True,
                    show_title=False,
                    columns=3,
                )

        with indicators_tab:
            self._render_indicator_tabs(payload, latest)

        with history_tab:
            self._render_history(payload)

    def _render_enterprise_certification(
        self,
        payload: dict,
        latest: list[dict],
    ) -> None:
        latest_index = {
            str(row.get("indicator_key")): row
            for row in latest
        }
        etit = _number(
            (latest_index.get("emp_etit_event") or {}).get("value")
        )
        dpa = _number(
            (latest_index.get("dpa_official") or {}).get("value")
        )
        certification = _enterprise_certification_status(etit, dpa)

        st.markdown("### ✅ Analista Certificado")
        st.caption(
            "Status individual da certificação empresarial com base em "
            "ETIT por Evento e DPA."
        )

        _render_enterprise_certification_status(certification)

        cols = st.columns(2)
        with cols[0]:
            _render_enterprise_certification_metric(
                "ETIT POR EVENTO %",
                etit,
                "etit",
            )
        with cols[1]:
            _render_enterprise_certification_metric(
                "DPA INDIVIDUAL %",
                dpa,
                "dpa",
            )

        st.markdown("### 🧭 Leitura do seu desempenho")
        feedback = _build_analyst_performance_feedback(
            latest,
            _team_index(payload),
            payload.get("breakdowns") or [],
            payload.get("team_breakdowns") or [],
        )
        _render_performance_reading(feedback)

    def _render_residential_certification(
        self,
        payload: dict,
        latest: list[dict],
    ) -> None:
        latest_index = {
            str(row.get("indicator_key")): row
            for row in latest
        }

        etit_hfc = _number(
            (latest_index.get("res_etit_fibra_hfc") or {}).get("value")
        )
        dpa = _number(
            (latest_index.get("dpa_official") or {}).get("value")
        )
        assert_hfc = _number(
            (latest_index.get("res_assert_fibra_hfc") or {}).get("value")
        )
        assert_gpon = _number(
            (latest_index.get("res_assert_gpon") or {}).get("value")
        )
        assert_values = [
            value
            for value in (assert_hfc, assert_gpon)
            if value is not None
        ]
        assert_avg = (
            sum(assert_values) / len(assert_values)
            if assert_values
            else None
        )

        certification = _residential_certification_status(
            etit_hfc,
            dpa,
            assert_hfc,
            assert_gpon,
        )

        st.markdown(
            "### 🎯 Status de Certificação — ETIT Fibra HFC & DPA & Assertividade"
        )
        _render_residential_certification_status(certification)

        cols = st.columns(5)
        metrics = [
            ("ETIT FIBRA HFC %", etit_hfc, "etit"),
            ("DPA INDIVIDUAL %", dpa, "dpa"),
            ("ASSERT. FIBRA HFC %", assert_hfc, "assert"),
            ("ASSERT. GPON %", assert_gpon, "assert"),
            ("MÉDIA ASSERTIVIDADE %", assert_avg, "assert"),
        ]
        for column, (label, value, kind) in zip(cols, metrics):
            with column:
                _render_residential_certification_metric(
                    label,
                    value,
                    kind,
                )

        st.markdown("### 🧭 Leitura do seu desempenho")
        feedback = _build_analyst_performance_feedback(
            latest,
            _team_index(payload),
            payload.get("breakdowns") or [],
            payload.get("team_breakdowns") or [],
        )
        _render_performance_reading(feedback)

    def _render_summary(self, payload: dict, latest: list[dict]) -> None:
        if not latest:
            st.info("Ainda não há resultados individuais processados para este segmento.")
            return

        team_index = _team_index(payload)
        snapshot = _build_summary_snapshot(
            latest,
            team_index,
            payload.get("freshness") or [],
        )

        st.markdown("### Seu panorama")
        kpi_cols = st.columns(4)
        attention_count = max(snapshot["with_target"] - snapshot["met"], 0)
        kpis = [
            (
                "Indicadores acompanhados",
                str(snapshot["tracked"]),
                f"Dados atualizados até {snapshot['freshness_label']}",
                "neutral",
            ),
            (
                "Dentro da meta",
                (
                    f"{snapshot['met']}/{snapshot['with_target']}"
                    if snapshot["with_target"]
                    else "—"
                ),
                "Indicadores com meta configurada",
                "good" if snapshot["met"] == snapshot["with_target"] and snapshot["with_target"] else "neutral",
            ),
            (
                "Precisam de atenção",
                str(attention_count) if snapshot["with_target"] else "—",
                "Indicadores abaixo da meta",
                "attention" if attention_count else "good",
            ),
            (
                "Acima da equipe",
                (
                    f"{snapshot['above_team']}/{snapshot['with_team']}"
                    if snapshot["with_team"]
                    else "—"
                ),
                "Comparação com a média da equipe",
                "good" if snapshot["above_team"] else "neutral",
            ),
        ]
        for column, (label, value, context, tone) in zip(kpi_cols, kpis):
            with column:
                _render_summary_kpi(label, value, context, tone)

        _render_executive_summary(snapshot)

        st.markdown("### Leitura rápida")
        insight_cols = st.columns(2)
        with insight_cols[0]:
            _render_summary_insight(
                "Ponto forte",
                snapshot["best_title"],
                snapshot["best_text"],
                "good",
            )
        with insight_cols[1]:
            _render_summary_insight(
                "Prioridade",
                snapshot["attention_title"],
                snapshot["attention_text"],
                "attention",
            )

        st.markdown("### Minha situação")
        st.caption(
            "Veja rapidamente onde você está dentro da meta, como se compara com a equipe e onde concentrar atenção."
        )
        for start in range(0, len(latest), 3):
            cols = st.columns(3)
            for column, row in zip(cols, latest[start:start + 3]):
                key = str(row.get("indicator_key"))
                period = str(row.get("period"))
                team = team_index.get((period, key), {})
                with column:
                    _render_indicator_status_card(row, team)

    def _render_indicator_tabs(self, payload: dict, latest: list[dict]) -> None:
        if not latest:
            st.info("Ainda não há indicadores processados para este segmento.")
            return

        team_index = _team_index(payload)
        st.markdown("### Meus indicadores")
        st.caption(
            "Abra cada indicador para ver comparação com a equipe, foco de atuação, perdas e evolução recente."
        )

        labels = [
            _indicator_tab_label(str(row.get("indicator_key")), str(row.get("name") or "Indicador"))
            for row in latest
        ]
        tabs = st.tabs(labels)

        for tab, row in zip(tabs, latest):
            with tab:
                key = str(row.get("indicator_key"))
                team = team_index.get((str(row.get("period")), key), {})
                self._render_indicator(payload, row, team)

    def _render_indicator(self, payload: dict, row: dict, team: dict) -> None:
        indicator_key = str(row.get("indicator_key"))
        indicator_name = str(row.get("name") or indicator_key)
        unit = row.get("unit")
        direction = str(row.get("direction") or "higher_is_better")
        value = _number(row.get("value"))
        team_avg = _number(team.get("team_avg"))

        st.markdown(f"### {indicator_name}")

        details = _latest_indicator_rows(
            payload.get("breakdowns") or [],
            indicator_key,
        )
        team_details = _latest_indicator_rows(
            payload.get("team_breakdowns") or [],
            indicator_key,
        )

        if indicator_key == "toa_cancellation_rate":
            self._render_cancelled_tasks_view(
                payload,
                row,
                team,
                details,
                team_details,
            )
            return

        if indicator_key == "validacao_20m":
            self._render_validation_time_view(
                row,
                team,
                details,
            )
            return

        if indicator_key == "productivity_avg_daily":
            self._render_productivity_view(
                payload,
                row,
                team,
                details,
                team_details,
            )
            return

        if indicator_key == "closing_assertiveness":
            self._render_closing_header(row, team, details)
            self._render_closing_assertiveness(payload, details, team_details)
            return

        if indicator_key in {
            "res_assert_fibra_hfc",
            "res_assert_gpon",
        }:
            self._render_residential_assertiveness(
                payload,
                details,
                team_details,
                indicator_key,
            )
            return

        if indicator_key == "dpa_official":
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Meu resultado", _format_ptbr_metric(value, unit))
            c2.metric(
                "Média da equipe",
                "—" if team_avg is None else _format_ptbr_metric(team_avg, unit),
            )
            c3.metric(
                "Comparação",
                _comparison_label(value, team_avg, direction, unit),
            )
            c4.metric("Meta", _target_metric(row))
            self._render_dpa_recent_chart(payload)
            return

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Meu resultado", _format_ptbr_metric(value, unit))
        c2.metric(
            "Média da equipe",
            "—" if team_avg is None else _format_ptbr_metric(team_avg, unit),
        )
        c3.metric(
            "Comparação",
            _comparison_label(value, team_avg, direction, unit),
        )
        c4.metric("Meta", _target_metric(row))
        c5.metric("Meu volume", int(row.get("volume") or 0))

        if indicator_key == "chat_10m":
            self._render_chat_group_view(details, team_details)
            return

        if indicator_key in {
            "emp_etit_event",
            "res_etit_fibra_hfc",
            "res_etit_gpon",
        }:
            self._render_etit_operational(
                payload,
                details,
                team_details,
                indicator_key,
                unit,
            )
            return

        self._render_focus(details, team_details, indicator_key, direction)
        self._render_loss_references(details, indicator_key)
        self._render_full_detail(details, team_details, indicator_key, direction)
        self._render_recent_evolution(payload, indicator_key, unit)

    def _render_residential_assertiveness(
        self,
        payload: dict,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
        indicator_key: str,
    ) -> None:
        if details.empty:
            st.info(
                "Reprocesse a fonte de Indicadores Residencial para liberar "
                "a análise detalhada de assertividade."
            )
            return

        is_gpon = indicator_key == "res_assert_gpon"
        scoped_details = details.copy()

        if is_gpon:
            st.markdown("#### Consolidado por serviço GPON")
            service_table = _assertiveness_dimension_table(
                details,
                "service",
                "Serviço",
            )
            if service_table.empty:
                st.caption(
                    "A carga atual não possui Brownfield/Greenfield para este período."
                )
            else:
                st.dataframe(
                    service_table,
                    use_container_width=True,
                    hide_index=True,
                )
                available = [
                    str(value)
                    for value in service_table["Serviço"].dropna().tolist()
                    if str(value).strip()
                ]
                preferred = []
                canonical = {value.upper(): value for value in available}
                for service in ("BROWNFIELD", "GREENFIELD"):
                    if service in canonical:
                        preferred.append(canonical[service])
                extras = [
                    value
                    for value in available
                    if value.upper() not in {"BROWNFIELD", "GREENFIELD"}
                ]
                options = ["Todos", *preferred, *extras]
                service_choice = st.radio(
                    "🌿 Serviço",
                    options,
                    horizontal=True,
                    key=f"analyst_assert_service_{indicator_key}",
                )
                if service_choice != "Todos":
                    scoped_details = _assertiveness_service_scoped_details(
                        details,
                        service_choice,
                    )

        summary = _etit_operational_summary(scoped_details)
        st.markdown("#### Resumo operacional do período")

        first_row = [
            ("VOLUME", str(summary["volume"]), "neutral"),
            ("ASSERTIVOS", str(summary["successes"]), "good"),
            ("NÃO ASSERTIVOS", str(summary["losses"]), "bad"),
            ("ASSERTIVIDADE", _pct(summary["adherence"]), "good"),
            (
                "NÃO ASSERTIVIDADE",
                _pct(
                    None
                    if summary["adherence"] is None
                    else max(0.0, 100.0 - summary["adherence"])
                ),
                "bad",
            ),
        ]
        cols = st.columns(5)
        for column, (label, value, tone) in zip(cols, first_row):
            with column:
                _render_assertiveness_kpi(label, value, tone)

        second_row = [
            ("TMA MÉDIO", _format_duration(summary["tma_seconds"]), "team"),
            ("TMR MÉDIO", _format_duration(summary["tmr_seconds"]), "warning"),
        ]
        cols = st.columns(2)
        for column, (label, value, tone) in zip(cols, second_row):
            with column:
                _render_assertiveness_kpi(label, value, tone)

        left, right = st.columns(2, gap="large")
        with left:
            st.markdown("#### 🗺️ Por Grupo (IN_GRUPO) — Regional Leste")
            group_table = _assertiveness_dimension_table(
                scoped_details,
                "group",
                "IN_GRUPO",
            )
            if group_table.empty:
                st.caption("Sem dados por grupo no período.")
            else:
                st.dataframe(
                    group_table,
                    use_container_width=True,
                    hide_index=True,
                )

        with right:
            st.markdown("#### Por Natureza")
            nature_table = _assertiveness_dimension_table(
                scoped_details,
                "nature",
                "Natureza",
            )
            if nature_table.empty:
                st.caption("Sem dados por natureza no período.")
            else:
                st.dataframe(
                    nature_table,
                    use_container_width=True,
                    hide_index=True,
                )

        st.markdown("#### Por Impacto")
        impact_table = _assertiveness_dimension_table(
            scoped_details,
            "impact",
            "Impacto",
        )
        if impact_table.empty:
            st.caption("Sem dados por impacto no período.")
        else:
            st.dataframe(
                impact_table,
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("#### Top 15 Soluções")
        solution_table = _assertiveness_dimension_table(
            scoped_details,
            "solution",
            "Solução",
            top=15,
        )
        if solution_table.empty:
            st.caption("Sem dados de solução no período.")
        else:
            st.dataframe(
                solution_table,
                use_container_width=True,
                hide_index=True,
            )

        rows = _indicator_recent_rows(
            payload,
            indicator_key,
            limit=7,
            include_team=True,
        )
        st.markdown("#### Últimos dias")
        st.caption(
            "Evolução diária da assertividade, com animação e referência da equipe."
        )
        if not rows:
            st.caption("Sem histórico diário suficiente para exibir o gráfico.")
        else:
            _render_dual_percent_bar_chart(
                rows,
                chart_class="cop-assert-daily-chart",
                mine_label="Minha assert.",
                team_label="Equipe",
            )

    def _render_validation_time_view(
        self,
        row: dict,
        team: dict,
        details: pd.DataFrame,
    ) -> None:
        summary = _validation_time_user_summary(row, team, details)
        target = _number(row.get("target_value")) or 80.0

        primary = [
            ("TOTAL", _format_integer(summary["total"]), "neutral"),
            ("ADERENTES", _format_integer(summary["successes"]), "good"),
            ("NÃO ADERENTES", _format_integer(summary["losses"]), "bad"),
            (
                "ADERÊNCIA",
                _pct(summary["adherence"]),
                "good"
                if summary["adherence"] is not None
                and summary["adherence"] >= target
                else "attention",
            ),
        ]
        cols = st.columns(4)
        for column, (label, value, tone) in zip(cols, primary):
            with column:
                _render_validation_kpi(label, value, tone)

        secondary = [
            ("TMR MÉDIO (MIN)", _format_decimal(summary["tmr_minutes"]), "warning"),
            ("MÉDIA DA EQUIPE", _pct(summary["team_avg"]), "team"),
            ("META", f"≥ {_pct(target)}", "target"),
        ]
        cols = st.columns(3)
        for column, (label, value, tone) in zip(cols, secondary):
            with column:
                _render_validation_kpi(label, value, tone)

        st.markdown("#### 🗺️ Por Grupo (IN_GRUPO) — Regional Leste")
        group_table = _validation_group_table(details)
        if group_table.empty:
            st.caption("Sem dados por grupo disponíveis para este período.")
        else:
            st.dataframe(
                group_table,
                use_container_width=True,
                hide_index=True,
            )

    def _render_cancelled_tasks_view(
        self,
        payload: dict,
        row: dict,
        team: dict,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
    ) -> None:
        etit_base = _cancellation_etit_base_for_period(
            payload.get("summary") or [],
            str(row.get("period") or ""),
        )
        summary = _cancelled_tasks_user_summary(
            details,
            team_details,
            etit_volume=etit_base["volume"],
            target_pct=_number(row.get("target_value")) or 15.0,
        )

        cards = [
            (
                etit_base["label"],
                _format_integer(summary["etit_volume"]),
                "neutral",
            ),
            (
                "CANCELADAS (↓ MENOR MELHOR)",
                _format_integer(summary["cancelled"]),
                summary["tone"],
            ),
            (
                "% CANCELADAS DO ANALISTA",
                _pct(summary["analyst_pct"]),
                summary["tone"],
            ),
            (
                "META",
                f"≤ {_pct(summary['target_pct'])}",
                "target",
            ),
            (
                "MÉDIA CANCELADAS EQUIPE",
                _format_decimal(summary["team_average"]),
                "team",
            ),
        ]
        cols = st.columns(5)
        for column, (label, value, tone) in zip(cols, cards):
            with column:
                _render_cancelled_tasks_kpi(label, value, tone)

    def _render_closing_header(
        self,
        row: dict,
        team: dict,
        details: pd.DataFrame,
    ) -> None:
        value = _number(row.get("value"))
        team_avg = _number(team.get("team_avg"))
        target = _number(row.get("target_value"))
        volume = int(_number(row.get("volume")) or 0)
        if details.empty:
            losses = (
                0
                if value is None or volume <= 0
                else int(round(volume * max(100.0 - value, 0.0) / 100.0))
            )
        else:
            losses = _etit_operational_summary(details)["losses"]

        cards = [
            ("Meu resultado", _pct(value)),
            ("Média da equipe", _pct(team_avg)),
            (
                "Comparação",
                _comparison_label(
                    value,
                    team_avg,
                    "higher_is_better",
                    "percent",
                ),
            ),
            ("Meta", "—" if target is None else f"≥ {_pct(target)}"),
            ("Meu volume", str(volume)),
            ("Não aderentes", str(losses)),
        ]
        cols = st.columns(6)
        for column, (label, value_text) in zip(cols, cards):
            with column:
                st.metric(label, value_text)

    def _render_chat_group_view(
        self,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
    ) -> None:
        st.markdown("#### 🗺️ Por Grupo (IN_GRUPO)")
        group_table = _chat_group_table(details, team_details)
        if group_table.empty:
            st.caption(
                "Sem dados por grupo neste processamento. Reenvie a planilha de Chat "
                "para carregar o campo IN_GRUPO."
            )
            return
        st.dataframe(
            group_table,
            use_container_width=True,
            hide_index=True,
        )

    def _render_productivity_view(
        self,
        payload: dict,
        row: dict,
        team: dict,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
    ) -> None:
        summary = _productivity_user_summary(row, details, team, team_details)

        st.markdown("#### Visão rápida do período")
        cols = st.columns(3)
        cards = [
            (
                "VOLUME TOTAL",
                _format_integer(summary["volume_total"]),
                _comparison_context(
                    summary["volume_total"],
                    summary["team_volume_avg"],
                    "referência do setor",
                ),
                "box",
            ),
            (
                "MÉDIA POR DIA",
                _format_decimal(summary["daily_avg"]),
                _comparison_context(
                    summary["daily_avg"],
                    summary["team_daily_avg"],
                    "referência do setor",
                ),
                "chart",
            ),
            (
                "DIAS ATIVOS",
                str(summary["active_days"]),
                "Dias com produção no período",
                "calendar",
            ),
        ]
        for column, (label, value, context, icon) in zip(cols, cards):
            with column:
                _render_productivity_kpi(label, value, context, icon)

        st.markdown(
            _productivity_quick_read(summary),
            unsafe_allow_html=True,
        )

        st.markdown("#### Últimos dias")
        st.caption(
            "Volume diário comparado à média diária da equipe."
        )
        recent = _productivity_recent_rows(payload)
        if recent:
            _render_productivity_daily_chart(recent)
        else:
            st.caption("Sem histórico diário suficiente para exibir o gráfico.")

        st.markdown("#### Produção por atividade")
        activity = _productivity_activity_table(details)
        if activity.empty:
            st.caption("Sem detalhamento por atividade disponível no período.")
        else:
            st.dataframe(
                activity,
                use_container_width=True,
                hide_index=True,
            )

    def _render_dpa_recent_chart(self, payload: dict) -> None:
        rows = _dpa_recent_chart_rows(payload)
        st.markdown("#### Desempenho diário")
        st.caption(
            "Todos os dias disponíveis do período, exibindo apenas o seu DPA."
        )

        if not rows:
            st.caption("Sem histórico diário suficiente para exibir o gráfico.")
            return

        scale = _dpa_chart_scale(rows)
        items = []
        for index, row in enumerate(rows):
            my_value = _number(row.get("value"))
            my_width = (
                0.0
                if my_value is None
                else min(max(my_value / scale * 100, 0), 100)
            )
            delay = index * 0.045

            items.append(
                (
                    "<div class='cop-dpa-chart-row'>"
                    f"<div class='cop-dpa-chart-date'>{escape(str(row['date_label']))}</div>"
                    "<div class='cop-dpa-chart-bars'>"
                    "<div class='cop-dpa-chart-line cop-dpa-chart-line-single'>"
                    "<span class='cop-dpa-chart-series'>Meu DPA</span>"
                    "<div class='cop-dpa-chart-track'>"
                    f"<div class='cop-dpa-chart-bar cop-dpa-chart-mine' style='width:{my_width:.2f}%;animation-delay:{delay:.2f}s'></div>"
                    "</div>"
                    f"<strong>{escape(_pct(my_value))}</strong>"
                    "</div>"
                    "</div>"
                    "</div>"
                )
            )

        st.markdown(
            (
                "<section class='cop-dpa-chart'>"
                "<div class='cop-dpa-chart-scale'>"
                "<span>0%</span>"
                f"<span>Escala até {scale:.0f}%</span>"
                "</div>"
                + "".join(items)
                + "</section>"
            ),
            unsafe_allow_html=True,
        )

    def _render_etit_operational(
        self,
        payload: dict,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
        indicator_key: str,
        unit: str | None,
    ) -> None:
        if details.empty:
            st.info("Reprocesse a fonte do ETIT para liberar a análise operacional detalhada.")
            return

        summary = _etit_operational_summary(details)
        st.markdown("#### Resumo operacional do período")
        cols = st.columns(5)
        cards = [
            ("Eventos", str(summary["volume"])),
            ("Aderentes", str(summary["successes"])),
            ("Não aderentes", str(summary["losses"])),
            ("TMA médio", _format_duration(summary["tma_seconds"])),
            ("TMR médio", _format_duration(summary["tmr_seconds"])),
        ]
        for column, (label, value) in zip(cols, cards):
            with column:
                _render_etit_kpi(label, value)

        if indicator_key == "emp_etit_event":
            st.markdown("#### Meu desempenho por demanda — RAL e REC")
            demand_cards = _enterprise_etit_demand_cards(details, team_details)
            if demand_cards:
                cols = st.columns(2, gap="large")
                for column, item in zip(cols, demand_cards):
                    with column:
                        _render_enterprise_etit_demand_card(item)
                st.caption(
                    "Cada percentual considera somente os eventos da respectiva demanda. "
                    "A meta exibida no topo pertence ao ETIT consolidado."
                )
            else:
                st.caption("Sem detalhamento por RAL/REC disponível no período.")

            left, right = st.columns(2, gap="large")
            with left:
                st.markdown("#### Por Demanda (RAL/REC)")
                demand_table = _etit_dimension_table(
                    details,
                    team_details,
                    "demand",
                    "Demanda",
                    include_duration=True,
                )
                if demand_table.empty:
                    st.caption("Sem dados de RAL/REC no período.")
                else:
                    st.dataframe(
                        demand_table,
                        use_container_width=True,
                        hide_index=True,
                    )

            with right:
                st.markdown("#### Por Tipo")
                type_table = _etit_dimension_table(
                    details,
                    team_details,
                    "type",
                    "Tipo",
                )
                if type_table.empty:
                    st.caption("Sem dados por tipo no período.")
                else:
                    st.dataframe(
                        type_table,
                        use_container_width=True,
                        hide_index=True,
                    )
        else:
            service_title = (
                "#### Por Serviço — Brownfield / Greenfield"
                if indicator_key == "res_etit_gpon"
                else "#### Por Serviço"
            )
            st.markdown(service_title)
            service_table = _etit_dimension_table(
                details,
                team_details,
                "service",
                "Serviço",
                include_duration=True,
            )
            if service_table.empty:
                st.caption("Sem dados por serviço no período.")
            else:
                st.dataframe(
                    service_table,
                    use_container_width=True,
                    hide_index=True,
                )

            nature_table = _etit_dimension_table(
                details,
                team_details,
                "nature",
                "Natureza",
            )
            if not nature_table.empty:
                with st.expander("Ver distribuição por natureza", expanded=False):
                    st.dataframe(
                        nature_table,
                        use_container_width=True,
                        hide_index=True,
                    )

        left, right = st.columns(2, gap="large")
        with left:
            st.markdown("#### 🗺️ Por Grupo (IN_GRUPO) — Regional Leste")
            group_table = _etit_dimension_table(
                details,
                team_details,
                "group",
                "Grupo",
            )
            if group_table.empty:
                st.caption("Sem dados de grupo no período.")
            else:
                _render_etit_dimension_highlight(group_table, "Grupo")
                st.dataframe(
                    group_table,
                    use_container_width=True,
                    hide_index=True,
                )

        with right:
            st.markdown("#### 🕒 Por Turno")
            turn_table = _etit_dimension_table(
                details,
                team_details,
                "turn",
                "Turno",
            )
            if turn_table.empty:
                st.caption("Sem dados de turno no período.")
            else:
                st.dataframe(
                    turn_table,
                    use_container_width=True,
                    hide_index=True,
                )

        self._render_loss_references(details, indicator_key)
        self._render_etit_recent_chart(payload, indicator_key)

    def _render_etit_recent_chart(
        self,
        payload: dict,
        indicator_key: str,
    ) -> None:
        rows = _indicator_recent_rows(
            payload,
            indicator_key,
            limit=7,
            include_team=True,
        )
        st.markdown("#### Últimos dias")
        st.caption(
            "Evolução diária da aderência com animação e comparação com a média da equipe."
        )
        if not rows:
            st.caption("Sem histórico diário suficiente para exibir o gráfico.")
            return

        _render_dual_percent_bar_chart(
            rows,
            chart_class="cop-etit-daily-chart",
            mine_label="Meu ETIT",
            team_label="Equipe",
        )

    def _render_closing_assertiveness(
        self,
        payload: dict,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
    ) -> None:
        if details.empty:
            st.info("Reprocesse a fonte Fechamento TOA x SIR para liberar a análise detalhada.")
            return

        left, right = st.columns(2, gap="large")
        with left:
            st.markdown("#### ❌ Top Causas Não Assertivas — TOA")
            toa_causes = _closing_cause_table(
                details,
                "cause_toa",
                "Causa TOA",
            )
            if toa_causes.empty:
                st.caption("Sem causas TOA não assertivas no período.")
            else:
                st.dataframe(
                    toa_causes,
                    use_container_width=True,
                    hide_index=True,
                )

        with right:
            st.markdown("#### ❌ Top Causas Não Assertivas — SIR")
            sir_causes = _closing_cause_table(
                details,
                "cause_sir",
                "Causa SIR",
            )
            if sir_causes.empty:
                st.caption("Sem causas SIR não assertivas no período.")
            else:
                st.dataframe(
                    sir_causes,
                    use_container_width=True,
                    hide_index=True,
                )

        left, right = st.columns(2, gap="large")
        with left:
            st.markdown("#### 🗺️ Por Grupo (IN_GRUPO) — Regional Leste")
            group_table = _closing_dimension_table(
                details,
                team_details,
                "group",
                "Grupo",
            )
            if group_table.empty:
                st.caption("Sem dados de grupo disponíveis para este período.")
            else:
                _render_closing_dimension_highlight(group_table, "Grupo")
                st.dataframe(
                    group_table,
                    use_container_width=True,
                    hide_index=True,
                )

        with right:
            st.markdown("#### 📋 Por Tipo de Demanda")
            demand_table = _closing_dimension_table(
                details,
                team_details,
                "demand",
                "Demanda",
            )
            if demand_table.empty:
                st.caption("Sem dados de demanda disponíveis para este período.")
            else:
                st.dataframe(
                    demand_table,
                    use_container_width=True,
                    hide_index=True,
                )

        st.markdown("#### INC / ocorrências não aderentes para revisar")
        st.caption(
            "Lista completa das ocorrências não aderentes. A coluna Demanda identifica se o caso é RAL ou REC; "
            "o resultado do dia aparece na mesma linha para dar contexto."
        )
        review_rows = _closing_review_rows(details, payload)
        if review_rows:
            st.dataframe(
                pd.DataFrame(review_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("Nenhuma ocorrência não aderente foi encontrada no período.")

    def _render_ral_rec(self, details: pd.DataFrame, team_details: pd.DataFrame) -> None:
        mine = _dimension_rows(details, "demand")
        if mine.empty:
            return
        mine = mine[mine["dimension_value"].astype(str).str.upper().isin(("RAL", "REC"))].copy()
        if mine.empty:
            return

        team = _dimension_rows(team_details, "demand")
        st.markdown("#### RAL e REC")
        rows = []
        for demand in ("RAL", "REC"):
            part = mine[mine["dimension_value"].astype(str).str.upper() == demand]
            if part.empty:
                continue
            volume = int(pd.to_numeric(part["volume"], errors="coerce").fillna(0).sum())
            successes = int(pd.to_numeric(part["successes"], errors="coerce").fillna(0).sum())
            losses = int(pd.to_numeric(part["losses"], errors="coerce").fillna(0).sum())
            my_result = successes / volume * 100 if volume else None

            team_part = team[team["dimension_value"].astype(str).str.upper() == demand] if not team.empty else pd.DataFrame()
            team_avg = _weighted_team_avg(team_part)

            rows.append({
                "Demanda": demand,
                "Meu resultado": _pct(my_result),
                "Média da equipe": _pct(team_avg),
                "Comparação": _comparison_label(my_result, team_avg, "higher_is_better", "percent"),
                "Volume": volume,
                "Aderentes": successes,
                "Não aderentes": losses,
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    def _render_focus(
        self,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
        indicator_key: str,
        direction: str,
    ) -> None:
        if details.empty:
            st.info("Reprocesse a fonte para liberar o diagnóstico individual desse indicador.")
            return

        dimensions = DETAIL_DIMENSIONS.get(indicator_key, ())
        candidates = []
        for dimension in dimensions:
            mine = _dimension_rows(details, dimension)
            if mine.empty:
                continue
            for _, item in mine.iterrows():
                losses = int(item.get("losses") or 0)
                if losses <= 0:
                    continue
                value = _detail_value(item, indicator_key)
                team_avg = _team_value(team_details, dimension, str(item.get("dimension_value")), indicator_key)
                candidates.append({
                    "Foco": DIMENSION_LABELS.get(dimension, dimension),
                    "Onde": str(item.get("dimension_value") or "—"),
                    "Meu resultado": _format_ptbr_metric(value, "percent"),
                    "Média da equipe": "—" if team_avg is None else _format_ptbr_metric(team_avg, "percent"),
                    "Comparação": _comparison_label(value, team_avg, direction, "percent"),
                    "Volume": int(item.get("volume") or 0),
                    "Erros": losses,
                    "_losses": losses,
                    "_volume": int(item.get("volume") or 0),
                })

        st.markdown("#### Onde focar primeiro")
        if not candidates:
            st.success("Nenhuma concentração relevante de erro foi encontrada nos recortes disponíveis.")
            return

        candidates = sorted(candidates, key=lambda item: (item["_losses"], item["_volume"]), reverse=True)[:6]
        table = pd.DataFrame([{k: v for k, v in item.items() if not k.startswith("_")} for item in candidates])
        st.dataframe(table, use_container_width=True, hide_index=True)

    def _render_loss_references(self, details: pd.DataFrame, indicator_key: str) -> None:
        if details.empty:
            return
        dimensions = ("activity_id",) if indicator_key in ("validacao_20m", "toa_cancellation_rate") else ("incident",)
        refs = details[details["dimension"].isin(dimensions)].copy()
        if refs.empty:
            return
        refs["losses"] = pd.to_numeric(refs["losses"], errors="coerce").fillna(0)
        refs = refs[refs["losses"] > 0].copy()
        if refs.empty:
            return

        refs = refs.sort_values(["day", "losses"], ascending=[False, False])
        rows = []
        for _, item in refs.iterrows():
            raw = str(item.get("dimension_value") or "").strip()
            demand = ""
            identifier = raw
            if "|||" in raw:
                demand, identifier = raw.split("|||", 1)
            demand_label = demand or "—"
            if (
                not demand
                and indicator_key in {"res_etit_fibra_hfc", "res_etit_gpon"}
            ):
                demand_label = _residential_occurrence_type(identifier)

            rows.append({
                "Data": _format_date(item.get("day")),
                "Demanda": demand_label,
                "Identificador": identifier or "—",
                "Perdas": int(item.get("losses") or 0),
            })

        title = "INC / ocorrências para revisar"
        if indicator_key == "toa_cancellation_rate":
            title = "Tarefas canceladas para revisar"
        elif indicator_key == "validacao_20m":
            title = "Atividades fora da aderência para revisar"

        st.markdown(f"#### {title}")
        if indicator_key == "emp_etit_event":
            st.caption("Os RAL/REC não aderentes aparecem com o número da NOTA/INC para consulta no sistema.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    def _render_full_detail(
        self,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
        indicator_key: str,
        direction: str,
    ) -> None:
        if details.empty:
            return
        dimensions = [
            dimension
            for dimension in DETAIL_DIMENSIONS.get(indicator_key, ())
            if not _dimension_rows(details, dimension).empty
        ]
        if not dimensions:
            return

        with st.expander("Ver detalhamento completo", expanded=False):
            dimension = st.selectbox(
                "Analisar meus resultados por",
                dimensions,
                format_func=lambda value: DIMENSION_LABELS.get(value, value),
                key=f"analyst_dimension_{indicator_key}",
            )
            mine = _dimension_rows(details, dimension).copy()
            mine["losses"] = pd.to_numeric(mine["losses"], errors="coerce").fillna(0)
            mine["volume"] = pd.to_numeric(mine["volume"], errors="coerce").fillna(0)
            mine = mine.sort_values(["losses", "volume"], ascending=[False, False])

            rows = []
            for _, item in mine.iterrows():
                value = _detail_value(item, indicator_key)
                category = str(item.get("dimension_value") or "—")
                team_avg = _team_value(team_details, dimension, category, indicator_key)
                rows.append({
                    DIMENSION_LABELS.get(dimension, dimension): category,
                    "Meu resultado": _format_ptbr_metric(value, "percent"),
                    "Média da equipe": "—" if team_avg is None else _format_ptbr_metric(team_avg, "percent"),
                    "Comparação": _comparison_label(value, team_avg, direction, "percent"),
                    "Volume": int(item.get("volume") or 0),
                    "Erros": int(item.get("losses") or 0),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    def _render_recent_evolution(self, payload: dict, indicator_key: str, unit: str | None) -> None:
        individual = pd.DataFrame(payload.get("individual") or [])
        if individual.empty or "indicator_key" not in individual.columns:
            return
        mine = individual[individual["indicator_key"] == indicator_key].copy()
        if mine.empty:
            return

        team = pd.DataFrame(payload.get("team_daily") or [])
        if not team.empty and "indicator_key" in team.columns:
            team = team[team["indicator_key"] == indicator_key][["period", "team_avg"]].copy()
        else:
            team = pd.DataFrame(columns=["period", "team_avg"])

        mine = mine[["period", "value", "volume"]].rename(
            columns={"period": "Data", "value": "Meu resultado", "volume": "Volume"}
        )
        merged = mine.merge(
            team.rename(columns={"period": "Data", "team_avg": "Média da equipe"}),
            on="Data",
            how="left",
        )
        merged["Data"] = pd.to_datetime(merged["Data"], errors="coerce")
        merged = merged.dropna(subset=["Data"]).sort_values("Data", ascending=False).head(7)
        if merged.empty:
            return

        merged["Data"] = merged["Data"].dt.strftime("%d/%m/%Y")
        merged["Meu resultado"] = merged["Meu resultado"].map(
            lambda value: _format_ptbr_metric(_number(value), unit)
        )
        merged["Média da equipe"] = merged["Média da equipe"].map(
            lambda value: "—" if pd.isna(value) else _format_ptbr_metric(_number(value), unit)
        )
        st.markdown("#### Últimos dias")
        st.dataframe(merged, use_container_width=True, hide_index=True)

    def _render_history(self, payload: dict) -> None:
        summary = pd.DataFrame(payload.get("summary") or [])
        if summary.empty:
            st.info("Ainda não há histórico mensal processado.")
            return

        teams = pd.DataFrame(payload.get("team_averages") or [])
        if teams.empty:
            teams = pd.DataFrame(columns=["period", "indicator_key", "team_avg"])

        history = summary.merge(
            teams[["period", "indicator_key", "team_avg"]],
            on=["period", "indicator_key"],
            how="left",
        )
        rows = []
        for _, row in history.iterrows():
            value = _number(row.get("value"))
            team_avg = _number(row.get("team_avg"))
            rows.append({
                "Período": str(row.get("period")),
                "Indicador": str(row.get("name")),
                "Meu resultado": _format_ptbr_metric(value, row.get("unit")),
                "Média da equipe": "—" if team_avg is None else _format_ptbr_metric(team_avg, row.get("unit")),
                "Comparação": _comparison_label(
                    value,
                    team_avg,
                    str(row.get("direction") or "higher_is_better"),
                    row.get("unit"),
                ),
                "Meta": _target_text(row),
                "Volume": int(row.get("volume") or 0),
            })

        st.markdown("### Histórico mensal")
        st.caption("A equipe aparece somente como média agregada de referência.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _residential_occurrence_type(identifier: object | None) -> str:
    raw = str(identifier or "").strip().upper()
    if raw.startswith("INM"):
        return "Outage"
    return "Incidente"


def _residential_certification_status(
    etit_hfc: float | None,
    dpa: float | None,
    assert_hfc: float | None,
    assert_gpon: float | None,
) -> dict:
    assert_values = [
        value
        for value in (assert_hfc, assert_gpon)
        if value is not None
    ]
    assert_avg = (
        sum(assert_values) / len(assert_values)
        if assert_values
        else None
    )

    etit_ok = etit_hfc is None or etit_hfc >= 90.0
    dpa_ok = dpa is None or dpa >= 90.0
    dpa_alert = dpa is not None and 85.0 <= dpa < 90.0
    assert_ok = assert_avg is None or assert_avg >= 85.0

    missing: list[str] = []
    if etit_hfc is None:
        missing.append("ETIT Fibra HFC")
    if dpa is None:
        missing.append("DPA")
    if assert_avg is None:
        missing.append("Média Assertividade")

    if etit_ok and dpa_ok and assert_ok:
        status = "good"
        title = "✅ Você está certificando"
        message = (
            "ETIT Fibra HFC, DPA individual e média de Assertividade "
            "dentro das metas."
        )
    elif etit_ok and dpa_alert and assert_ok:
        status = "attention"
        title = "⚠️ Você está certificando"
        message = (
            "O DPA individual está em faixa de atenção "
            "(85% ≤ DPA < 90%); ETIT Fibra HFC e média de "
            "Assertividade permanecem dentro das metas."
        )
    else:
        status = "bad"
        title = "❌ Você NÃO está certificando"
        reasons: list[str] = []
        if etit_hfc is not None and etit_hfc < 90.0:
            reasons.append(
                f"ETIT Fibra HFC abaixo de 90% ({etit_hfc:.1f}%)"
            )
        if dpa is not None and dpa < 85.0:
            reasons.append(
                f"DPA individual abaixo de 85% ({dpa:.1f}%)"
            )
        if assert_avg is not None and assert_avg < 85.0:
            reasons.append(
                f"Média Assertividade abaixo de 85% ({assert_avg:.1f}%)"
            )
        message = (
            "Indicadores fora da meta — "
            + " · ".join(reasons)
            + "."
        )

    if missing:
        message += (
            f" Sem dados de {', '.join(missing)}; seguindo a regra do portal "
            "anterior, esses itens são considerados dentro da meta."
        )

    return {
        "status": status,
        "title": title,
        "message": message,
        "etit_hfc": etit_hfc,
        "dpa": dpa,
        "assert_hfc": assert_hfc,
        "assert_gpon": assert_gpon,
        "assert_avg": assert_avg,
    }


def _render_residential_certification_status(
    certification: dict,
) -> None:
    status = str(certification.get("status") or "neutral")
    st.markdown(
        (
            f"<section class='cop-user-cert-status cop-user-cert-{escape(status)}'>"
            "<div class='cop-user-cert-team'>EQUIPE NELSON (RESIDENCIAL)</div>"
            f"<div class='cop-user-cert-title'>{escape(str(certification.get('title') or '—'))}</div>"
            f"<div class='cop-user-cert-message'>{escape(str(certification.get('message') or ''))}</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def _render_residential_certification_metric(
    label: str,
    value: float | None,
    kind: str,
) -> None:
    if value is None:
        tone = "neutral"
    elif kind == "etit":
        tone = "good" if value >= 90.0 else "bad"
    elif kind == "dpa":
        tone = (
            "good"
            if value >= 90.0
            else "attention"
            if value >= 85.0
            else "bad"
        )
    else:
        tone = "good" if value >= 85.0 else "bad"

    st.markdown(
        (
            f"<article class='cop-user-cert-metric cop-user-cert-metric-{tone}'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape('—' if value is None else f'{value:.1f}'.replace('.', ','))}</strong>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _enterprise_certification_status(
    etit: float | None,
    dpa: float | None,
) -> dict:
    etit_ok = etit is None or etit >= 90.0
    dpa_ok = dpa is None or dpa >= 90.0
    dpa_alert = dpa is not None and 85.0 <= dpa < 90.0

    missing: list[str] = []
    if etit is None:
        missing.append("ETIT por Evento")
    if dpa is None:
        missing.append("DPA")

    if etit_ok and dpa_ok:
        status = "good"
        title = "✅ Você está certificando"
        message = "ETIT por Evento e DPA individual dentro da meta."
    elif etit_ok and dpa_alert:
        status = "attention"
        title = "⚠️ Você está certificando"
        message = (
            "ETIT por Evento dentro da meta; DPA individual em faixa de atenção "
            "(85% a 89,9%)."
        )
    else:
        status = "bad"
        title = "❌ Você não está certificando"
        reasons: list[str] = []
        if etit is not None and etit < 90.0:
            reasons.append(f"ETIT por Evento abaixo de 90% ({etit:.1f}%)")
        if dpa is not None and dpa < 85.0:
            reasons.append(f"DPA individual abaixo de 85% ({dpa:.1f}%)")
        message = " · ".join(reasons) or "Indicadores fora dos critérios de certificação."

    if missing:
        message += (
            f" Sem dados de {', '.join(missing)}; seguindo a regra atual do portal, "
            "esses itens não bloqueiam a certificação."
        )

    return {
        "status": status,
        "title": title,
        "message": message,
        "etit": etit,
        "dpa": dpa,
    }


def _render_enterprise_certification_status(certification: dict) -> None:
    status = str(certification.get("status") or "neutral")
    st.markdown(
        (
            f"<section class='cop-user-cert-status cop-user-cert-{escape(status)}'>"
            "<div class='cop-user-cert-team'>EQUIPE NELSON (EMPRESARIAL)</div>"
            f"<div class='cop-user-cert-title'>{escape(str(certification.get('title') or '—'))}</div>"
            f"<div class='cop-user-cert-message'>{escape(str(certification.get('message') or ''))}</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def _render_enterprise_certification_metric(
    label: str,
    value: float | None,
    kind: str,
) -> None:
    if value is None:
        tone = "neutral"
    elif kind == "etit":
        tone = "good" if value >= 90.0 else "bad"
    else:
        tone = "good" if value >= 90.0 else "attention" if value >= 85.0 else "bad"

    st.markdown(
        (
            f"<article class='cop-user-cert-metric cop-user-cert-metric-{tone}'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape('—' if value is None else f'{value:.1f}'.replace('.', ','))}</strong>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


_PERFORMANCE_THEMES = [
    {
        "key": "productivity",
        "strong": "produtividade alta e ritmo de entrega acima da média da equipe",
        "mixed": "produção em bom patamar, com espaço para ganhar regularidade",
        "attention": "o ritmo de produção indica espaço para ganhar consistência e previsibilidade nas entregas",
        "suggestion": "organizar a rotina de produção, com objetivos diários claros, para dar mais regularidade às entregas",
    },
    {
        "key": "quality",
        "strong": "boa qualidade operacional, sustentando a aderência nos processos críticos",
        "mixed": "qualidade operacional sólida na maior parte das frentes, com pontos a alinhar",
        "attention": "a aderência aos processos críticos pede atenção para sustentar a qualidade das tratativas",
        "suggestion": "revisar com a liderança os critérios de processo, usando casos reais como referência, para fortalecer a aderência",
    },
    {
        "key": "journey",
        "strong": "bom aproveitamento da jornada, com ocupação equilibrada ao longo do dia",
        "mixed": "aproveitamento da jornada razoável, com oscilações ao longo do dia",
        "attention": "o aproveitamento da jornada sugere necessidade de revisar gestão de tempo, pausas e priorização",
        "suggestion": "revisar a organização da jornada, pausas e priorização para recuperar previsibilidade na entrega",
    },
    {
        "key": "service",
        "strong": "agilidade no atendimento via chat, dentro dos tempos esperados",
        "mixed": "atendimento via chat em bom ritmo, com margem para ganhar agilidade",
        "attention": "o tempo de atendimento no chat aponta oportunidade de ganhar agilidade sem perder qualidade",
        "suggestion": "padronizar respostas frequentes e organizar os atendimentos simultâneos para ganhar agilidade no chat",
    },
    {
        "key": "control",
        "strong": "controle operacional consistente, com baixo retrabalho",
        "mixed": "controle operacional adequado, com algum retrabalho a observar",
        "attention": "o nível de retrabalho operacional pede acompanhamento para reduzir cancelamentos e reaberturas",
        "suggestion": "mapear os motivos mais frequentes de cancelamento para reduzir o retrabalho operacional",
    },
]


def _performance_theme(indicator_key: str) -> str | None:
    if indicator_key == "productivity_avg_daily":
        return "productivity"
    if indicator_key == "dpa_official":
        return "journey"
    if indicator_key == "chat_10m":
        return "service"
    if indicator_key == "toa_cancellation_rate":
        return "control"
    if indicator_key in {
        "emp_etit_event",
        "validacao_20m",
        "closing_assertiveness",
        "res_etit_fibra_hfc",
        "res_etit_gpon",
        "res_assert_fibra_hfc",
        "res_assert_gpon",
    }:
        return "quality"
    return None


def _performance_indicator_state(
    row: dict,
    team: dict,
    breakdowns: list[dict],
    team_breakdowns: list[dict],
    *,
    cancellation_etit_volume: float | None = None,
) -> str | None:
    """Classifica cada indicador como bom ou atenção.

    Mantém a mesma semântica da leitura qualitativa do dashboard legado:
    o estado "misto" nasce da combinação de indicadores bons e de atenção
    dentro de um mesmo tema, não de uma faixa intermediária de um indicador.
    """
    key = str(row.get("indicator_key") or "")
    value = _number(row.get("value"))
    if value is None:
        return None

    if key == "dpa_official":
        return "good" if value >= 90.0 else "attention"

    if key == "toa_cancellation_rate":
        details = _latest_indicator_rows(breakdowns, key)
        team_details = _latest_indicator_rows(team_breakdowns, key)
        summary = _cancelled_tasks_user_summary(
            details,
            team_details,
            etit_volume=cancellation_etit_volume,
            target_pct=_number(row.get("target_value")) or 15.0,
        )
        tone = str(summary.get("tone") or "neutral")
        if tone == "good":
            return "good"
        if tone in {"attention", "bad"}:
            return "attention"
        return None

    target = _number(row.get("target_value"))
    direction = str(row.get("direction") or "higher_is_better")
    if target is not None:
        return "good" if _meets_target(value, target, direction) else "attention"

    team_avg = _number(team.get("team_avg"))
    if team_avg is None:
        return None

    favorable = (
        value >= team_avg
        if direction != "lower_is_better"
        else value <= team_avg
    )
    return "good" if favorable else "attention"


def _build_analyst_performance_feedback(
    latest: list[dict],
    team_index: dict[tuple[str, str], dict],
    breakdowns: list[dict],
    team_breakdowns: list[dict],
) -> dict:
    aggregate: dict[str, dict[str, int]] = {}

    for row in latest:
        key = str(row.get("indicator_key") or "")
        theme = _performance_theme(key)
        if not theme:
            continue

        team = team_index.get((str(row.get("period")), key), {})
        cancellation_etit_volume = None
        if key == "toa_cancellation_rate":
            cancellation_etit_volume = _cancellation_etit_base_for_period(
                latest,
                str(row.get("period") or ""),
            )["volume"]

        state = _performance_indicator_state(
            row,
            team,
            breakdowns,
            team_breakdowns,
            cancellation_etit_volume=cancellation_etit_volume,
        )
        if state is None:
            continue

        counts = aggregate.setdefault(
            theme,
            {"good": 0, "mixed": 0, "attention": 0},
        )
        counts[state] += 1

    strong: list[dict] = []
    mixed: list[dict] = []
    attention: list[dict] = []

    for theme in _PERFORMANCE_THEMES:
        counts = aggregate.get(theme["key"])
        if not counts:
            continue
        if counts["attention"] == 0 and counts["mixed"] == 0:
            strong.append(theme)
        elif counts["good"] == 0 and counts["mixed"] == 0:
            attention.append(theme)
        else:
            mixed.append(theme)

    evaluated = len(strong) + len(mixed) + len(attention)
    to_improve = attention + mixed

    if evaluated == 0:
        summary = (
            "Ainda não há indicadores suficientes para uma leitura consolidada do seu "
            "desempenho neste período."
        )
    elif not to_improve:
        summary = (
            "Analista consistente, com desempenho equilibrado e sob controle em todas as "
            "frentes avaliadas — um período sólido do começo ao fim."
        )
    elif not strong and not mixed:
        summary = (
            "Período de ajustes: as principais frentes pedem atenção, mas o quadro é "
            "totalmente recuperável com foco em poucos pontos de cada vez."
        )
    else:
        summary = (
            "Analista com bons fundamentos e algumas frentes em desenvolvimento neste "
            "período — o equilíbrio está ao alcance com ajustes pontuais na rotina."
        )

    highlights = (
        [theme["strong"] for theme in strong]
        + [theme["mixed"] for theme in mixed]
    )[:3]
    if highlights:
        if len(highlights) == 1:
            point_strong = f"Analista que demonstra {highlights[0]}."
        else:
            first = highlights[0]
            remaining = highlights[1:]
            rest = (
                remaining[0]
                if len(remaining) == 1
                else ", ".join(remaining[:-1]) + " e " + remaining[-1]
            )
            point_strong = (
                f"Analista consistente, com {first}. Além disso, demonstra {rest}."
            )
    else:
        point_strong = (
            "Mesmo sem uma frente totalmente consolidada, há base para evoluir rápido: "
            "escolher um único foco por semana costuma destravar os demais indicadores."
        )

    if to_improve:
        point_attention = "; ".join(
            theme["attention"] for theme in to_improve
        ).capitalize() + "."
        suggestions = [theme["suggestion"] for theme in to_improve[:2]]
        suggestion = suggestions[0].capitalize()
        if len(suggestions) > 1:
            suggestion += f". Em paralelo, {suggestions[1]}"
        suggestion += "."
    else:
        point_attention = (
            "Nenhuma frente exige atenção neste período. O cuidado agora é manter a "
            "constância para preservar esse bom patamar."
        )
        suggestion = (
            "Seguir mantendo a rotina atual e compartilhar com a equipe o que está "
            "funcionando — isso fortalece o time e reforça a sua referência técnica."
        )

    return {
        "summary": summary,
        "point_strong": point_strong,
        "point_attention": point_attention,
        "suggestion": suggestion,
    }


def _render_performance_reading(feedback: dict) -> None:
    st.markdown(
        (
            "<section class='cop-user-reading-summary'>"
            f"{escape(str(feedback.get('summary') or ''))}"
            "</section>"
        ),
        unsafe_allow_html=True,
    )

    cols = st.columns(3, gap="large")
    cards = [
        (
            "✅ PONTO FORTE",
            str(feedback.get("point_strong") or ""),
            "good",
        ),
        (
            "⚠️ PONTO DE ATENÇÃO",
            str(feedback.get("point_attention") or ""),
            "attention",
        ),
        (
            "💡 SUGESTÃO",
            str(feedback.get("suggestion") or ""),
            "suggestion",
        ),
    ]
    for column, (label, text_value, tone) in zip(cols, cards):
        with column:
            st.markdown(
                (
                    f"<article class='cop-user-reading-card cop-user-reading-{tone}'>"
                    f"<div>{escape(label)}</div>"
                    f"<p>{escape(text_value)}</p>"
                    "</article>"
                ),
                unsafe_allow_html=True,
            )


def _validation_time_user_summary(
    row: dict,
    team: dict,
    details: pd.DataFrame,
) -> dict:
    overall = _dimension_rows(details, "overall")
    if overall.empty:
        total = float(_number(row.get("volume")) or 0)
        adherence = _number(row.get("value"))
        successes = (
            0.0
            if adherence is None or total <= 0
            else total * adherence / 100.0
        )
        losses = max(total - successes, 0.0)
        tmr_minutes = None
    else:
        total = float(
            pd.to_numeric(overall.get("volume"), errors="coerce").fillna(0).sum()
        )
        successes = float(
            pd.to_numeric(overall.get("successes"), errors="coerce").fillna(0).sum()
        )
        losses = float(
            pd.to_numeric(overall.get("losses"), errors="coerce").fillna(0).sum()
        )
        adherence = None if total <= 0 else successes / total * 100
        tmr_seconds = _weighted_breakdown_duration(overall, "tmr_seconds")
        tmr_minutes = None if tmr_seconds is None else tmr_seconds / 60.0

    return {
        "total": total,
        "successes": successes,
        "losses": losses,
        "adherence": adherence,
        "tmr_minutes": tmr_minutes,
        "team_avg": _number(team.get("team_avg")),
    }


def _validation_group_table(details: pd.DataFrame) -> pd.DataFrame:
    group = _dimension_rows(details, "group")
    if group.empty:
        return pd.DataFrame()

    records: list[dict] = []
    for raw_value, part in group.groupby("dimension_value", dropna=False):
        name = str(raw_value or "").strip()
        if not name:
            continue

        total = float(
            pd.to_numeric(part.get("volume"), errors="coerce").fillna(0).sum()
        )
        successes = float(
            pd.to_numeric(part.get("successes"), errors="coerce").fillna(0).sum()
        )
        adherence = None if total <= 0 else successes / total * 100
        tmr_seconds = _weighted_breakdown_duration(part, "tmr_seconds")
        tmr_minutes = None if tmr_seconds is None else tmr_seconds / 60.0

        records.append(
            {
                "Grupo": name,
                "Total": int(round(total)),
                "Aderentes": int(round(successes)),
                "Aderência %": _pct(adherence),
                "TMR (min)": _format_decimal(tmr_minutes),
                "_volume": total,
            }
        )

    if not records:
        return pd.DataFrame()

    return (
        pd.DataFrame(records)
        .sort_values(["_volume", "Grupo"], ascending=[False, True])
        .drop(columns=["_volume"])
        .reset_index(drop=True)
    )


def _render_validation_kpi(
    label: str,
    value: str,
    tone: str,
) -> None:
    safe_tone = (
        tone
        if tone in {"neutral", "good", "bad", "attention", "warning", "team", "target"}
        else "neutral"
    )
    st.markdown(
        (
            f"<article class='cop-validation-kpi cop-validation-{safe_tone}'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(value)}</strong>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _cancelled_tasks_user_summary(
    details: pd.DataFrame,
    team_details: pd.DataFrame,
    *,
    etit_volume: float | None = None,
    target_pct: float = 15.0,
) -> dict:
    overall = _dimension_rows(details, "overall")
    if overall.empty:
        cancelled = 0.0
    else:
        cancelled = float(
            pd.to_numeric(overall.get("losses"), errors="coerce")
            .fillna(0)
            .sum()
        )

    team_overall = _dimension_rows(team_details, "overall")
    team_average = None
    if not team_overall.empty:
        team_losses = float(
            pd.to_numeric(
                team_overall.get("team_losses"),
                errors="coerce",
            )
            .fillna(0)
            .sum()
        )
        analysts = pd.to_numeric(
            team_overall.get("team_analysts"),
            errors="coerce",
        ).fillna(0)
        analyst_count = float(analysts.max()) if not analysts.empty else 0.0
        if analyst_count > 0:
            team_average = team_losses / analyst_count

    # A taxa de cancelamento usa como denominador o volume total do ETIT por
    # Evento do mesmo analista/período. A planilha de Tarefas Canceladas contém
    # apenas as ocorrências de cancelamento e, portanto, não pode ser usada como
    # denominador da própria taxa.
    base_volume = _number(etit_volume)
    pct = (
        None
        if base_volume is None or base_volume <= 0
        else cancelled / base_volume * 100
    )
    target = float(target_pct)

    # Meta operacional oficial: até 15% de cancelamento. Quanto menor, melhor.
    tone = "neutral"
    if pct is not None:
        if pct <= target:
            tone = "good"
        elif pct <= target + 5:
            tone = "attention"
        else:
            tone = "bad"

    return {
        "cancelled": cancelled,
        "etit_volume": base_volume,
        "team_average": team_average,
        "analyst_pct": pct,
        "target_pct": target,
        "tone": tone,
    }


def _render_cancelled_tasks_kpi(
    label: str,
    value: str,
    tone: str,
) -> None:
    safe_tone = tone if tone in {"neutral", "good", "attention", "bad", "team", "target"} else "neutral"
    st.markdown(
        (
            f"<article class='cop-cancel-user-kpi cop-cancel-user-{safe_tone}'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(value)}</strong>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _productivity_user_summary(
    row: dict,
    details: pd.DataFrame,
    team: dict,
    team_details: pd.DataFrame,
) -> dict:
    daily_avg = _number(row.get("value")) or 0.0
    active_days = int(_number(row.get("volume")) or 0)

    total_rows = _dimension_rows(details, "productivity_total")
    if total_rows.empty:
        volume_total = daily_avg * active_days
    else:
        volume_total = float(
            pd.to_numeric(total_rows.get("successes"), errors="coerce")
            .fillna(0)
            .sum()
        )

    team_daily_avg = _number(team.get("team_avg"))
    team_total_rows = _dimension_rows(team_details, "productivity_total")
    team_volume_avg = None
    if not team_total_rows.empty:
        team_total = float(
            pd.to_numeric(
                team_total_rows.get("team_successes"),
                errors="coerce",
            )
            .fillna(0)
            .sum()
        )
        analysts = pd.to_numeric(
            team_total_rows.get("team_analysts"),
            errors="coerce",
        ).fillna(0)
        analyst_count = float(analysts.max()) if not analysts.empty else 0.0
        if analyst_count > 0:
            team_volume_avg = team_total / analyst_count

    return {
        "volume_total": volume_total,
        "daily_avg": daily_avg,
        "active_days": active_days,
        "team_volume_avg": team_volume_avg,
        "team_daily_avg": team_daily_avg,
    }


def _comparison_context(
    value: float | None,
    reference: float | None,
    reference_label: str,
) -> str:
    current = _number(value)
    baseline = _number(reference)
    if current is None or baseline is None or baseline == 0:
        return f"{reference_label.capitalize()} indisponível"

    difference = (current / baseline - 1.0) * 100
    direction = "acima" if difference >= 0 else "abaixo"
    return (
        f"{abs(difference):.0f}% {direction} da {reference_label}"
    )


def _productivity_quick_read(summary: dict) -> str:
    daily_avg = _number(summary.get("daily_avg"))
    team_daily_avg = _number(summary.get("team_daily_avg"))

    if (
        daily_avg is None
        or team_daily_avg is None
        or team_daily_avg <= 0
    ):
        text = (
            "A leitura comparativa ficará disponível quando houver referência "
            "suficiente da equipe para o período."
        )
        tone = "neutral"
    else:
        difference = (daily_avg / team_daily_avg - 1.0) * 100
        if difference >= 5:
            text = (
                "Seu ritmo diário está acima da referência do setor. "
                "O ponto principal é sustentar essa consistência ao longo do período."
            )
            tone = "good"
        elif difference <= -5:
            text = (
                "Seu principal ponto de atenção agora é recuperar o ritmo diário "
                "em relação à referência do setor."
            )
            tone = "attention"
        else:
            text = (
                "Seu ritmo diário está próximo da referência do setor. "
                "A prioridade é manter regularidade na produção."
            )
            tone = "neutral"

    return (
        f"<section class='cop-productivity-reading cop-productivity-reading-{tone}'>"
        "<div class='cop-productivity-reading-title'>🎯 Leitura rápida do período</div>"
        f"<div class='cop-productivity-reading-text'>{escape(text)}</div>"
        "</section>"
    )


def _productivity_activity_table(details: pd.DataFrame) -> pd.DataFrame:
    rows = _dimension_rows(details, "productivity_component")
    if rows.empty:
        return pd.DataFrame()

    frame = rows.copy()
    frame["successes"] = pd.to_numeric(
        frame.get("successes"),
        errors="coerce",
    ).fillna(0)
    grouped = (
        frame.groupby("dimension_value", dropna=False)["successes"]
        .sum()
        .reset_index()
        .rename(
            columns={
                "dimension_value": "Atividade",
                "successes": "Volume",
            }
        )
    )
    grouped["Atividade"] = grouped["Atividade"].fillna("").astype(str).str.strip()
    grouped = grouped[grouped["Atividade"].ne("")]
    if grouped.empty:
        return pd.DataFrame()

    grouped["Volume"] = grouped["Volume"].round().astype(int)
    return grouped.sort_values(
        ["Volume", "Atividade"],
        ascending=[False, True],
    ).reset_index(drop=True)


def _productivity_recent_rows(payload: dict) -> list[dict]:
    individual = pd.DataFrame(payload.get("individual") or [])
    if individual.empty or "indicator_key" not in individual.columns:
        return []

    mine = individual[
        individual["indicator_key"] == "productivity_avg_daily"
    ].copy()
    if mine.empty:
        return []

    team = pd.DataFrame(payload.get("team_daily") or [])
    if not team.empty and "indicator_key" in team.columns:
        team = team[
            team["indicator_key"] == "productivity_avg_daily"
        ][["period", "team_avg"]].copy()
    else:
        team = pd.DataFrame(columns=["period", "team_avg"])

    mine = mine[["period", "value"]].copy()
    merged = mine.merge(team, on="period", how="left")
    merged["period"] = pd.to_datetime(
        merged["period"],
        errors="coerce",
    )
    merged = (
        merged.dropna(subset=["period"])
        .sort_values("period", ascending=False)
        .head(7)
        .sort_values("period", ascending=True)
    )
    if merged.empty:
        return []

    return [
        {
            "date_label": item["period"].strftime("%d/%m"),
            "period": item["period"].date().isoformat(),
            "value": _number(item.get("value")),
            "team_avg": _number(item.get("team_avg")),
        }
        for _, item in merged.iterrows()
    ]


def _productivity_chart_scale(rows: list[dict]) -> float:
    values = [1.0]
    for row in rows:
        for key in ("value", "team_avg"):
            value = _number(row.get(key))
            if value is not None and value >= 0:
                values.append(value)
    maximum = max(values)
    step = 10 if maximum <= 100 else 20
    return float(((int(maximum) + step - 1) // step) * step)


def _render_productivity_daily_chart(rows: list[dict]) -> None:
    scale = _productivity_chart_scale(rows)
    items: list[str] = []

    for index, row in enumerate(rows):
        mine = _number(row.get("value"))
        team = _number(row.get("team_avg"))
        mine_width = (
            0.0
            if mine is None
            else min(max(mine / scale * 100, 0), 100)
        )
        team_width = (
            0.0
            if team is None
            else min(max(team / scale * 100, 0), 100)
        )
        delay = index * 0.06

        items.append(
            (
                "<div class='cop-productivity-chart-row'>"
                f"<div class='cop-productivity-chart-date'>{escape(str(row['date_label']))}</div>"
                "<div class='cop-productivity-chart-bars'>"
                "<div class='cop-productivity-chart-line'>"
                "<span class='cop-productivity-chart-series'>Meu volume</span>"
                "<div class='cop-productivity-chart-track'>"
                f"<div class='cop-productivity-chart-bar cop-productivity-chart-mine' style='width:{mine_width:.2f}%;animation-delay:{delay:.2f}s'></div>"
                "</div>"
                f"<strong>{escape(_format_decimal(mine))}</strong>"
                "</div>"
                "<div class='cop-productivity-chart-line'>"
                "<span class='cop-productivity-chart-series'>Equipe</span>"
                "<div class='cop-productivity-chart-track'>"
                f"<div class='cop-productivity-chart-bar cop-productivity-chart-team' style='width:{team_width:.2f}%;animation-delay:{delay + .08:.2f}s'></div>"
                "</div>"
                f"<strong>{escape(_format_decimal(team))}</strong>"
                "</div>"
                "</div>"
                "</div>"
            )
        )

    st.markdown(
        (
            "<section class='cop-productivity-chart'>"
            "<div class='cop-productivity-chart-scale'>"
            "<span>0</span>"
            f"<span>Escala até {int(scale)}</span>"
            "</div>"
            + "".join(items)
            + "</section>"
        ),
        unsafe_allow_html=True,
    )


def _render_productivity_kpi(
    label: str,
    value: str,
    context: str,
    icon: str,
) -> None:
    icons = {
        "box": "📦",
        "chart": "📈",
        "calendar": "🗓️",
    }
    st.markdown(
        (
            "<article class='cop-productivity-kpi'>"
            "<div class='cop-productivity-kpi-head'>"
            f"<span>{escape(label)}</span>"
            f"<b>{escape(icons.get(icon, '•'))}</b>"
            "</div>"
            f"<strong>{escape(value)}</strong>"
            f"<p>{escape(context)}</p>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _format_integer(value: float | None) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{int(round(number)):,}".replace(",", ".")


def _format_decimal(value: float | None) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{number:.1f}".replace(".", ",")


def _dpa_recent_chart_rows(payload: dict) -> list[dict]:
    individual = pd.DataFrame(payload.get("individual") or [])
    if individual.empty or "indicator_key" not in individual.columns:
        return []

    mine = individual[individual["indicator_key"] == "dpa_official"].copy()
    if mine.empty:
        return []

    if "data_month" in mine.columns:
        months = mine["data_month"].dropna().astype(str)
        if not months.empty:
            mine = mine[mine["data_month"].astype(str) == months.max()].copy()

    mine = mine[["period", "value"]].copy()
    mine["period"] = pd.to_datetime(mine["period"], errors="coerce")
    mine = mine.dropna(subset=["period"]).sort_values("period", ascending=True)
    if mine.empty:
        return []

    return [
        {
            "date_label": row["period"].strftime("%d/%m"),
            "period": row["period"].date().isoformat(),
            "value": _number(row.get("value")),
        }
        for _, row in mine.iterrows()
    ]


def _dpa_chart_scale(rows: list[dict]) -> float:
    values = [100.0]
    for row in rows:
        value = _number(row.get("value"))
        if value is not None and value >= 0:
            values.append(value)
    maximum = max(values)
    return float(((int(maximum) + 9) // 10) * 10)


def _indicator_recent_rows(
    payload: dict,
    indicator_key: str,
    *,
    limit: int | None = 7,
    include_team: bool = True,
) -> list[dict]:
    individual = pd.DataFrame(payload.get("individual") or [])
    if individual.empty or "indicator_key" not in individual.columns:
        return []

    mine = individual[individual["indicator_key"] == indicator_key].copy()
    if mine.empty:
        return []

    latest_month = None
    if "data_month" in mine.columns:
        months = mine["data_month"].dropna().astype(str)
        if not months.empty:
            latest_month = months.max()
            mine = mine[mine["data_month"].astype(str) == latest_month].copy()

    mine = mine[["period", "value"]].copy()

    if include_team:
        team = pd.DataFrame(payload.get("team_daily") or [])
        if not team.empty and "indicator_key" in team.columns:
            team = team[team["indicator_key"] == indicator_key].copy()
            if latest_month is not None and "data_month" in team.columns:
                team = team[team["data_month"].astype(str) == latest_month].copy()
            team = team[["period", "team_avg"]].copy()
        else:
            team = pd.DataFrame(columns=["period", "team_avg"])
        merged = mine.merge(team, on="period", how="left")
    else:
        merged = mine.copy()
        merged["team_avg"] = None

    merged["period"] = pd.to_datetime(merged["period"], errors="coerce")
    merged = merged.dropna(subset=["period"]).sort_values(
        "period",
        ascending=False,
    )
    if limit is not None:
        merged = merged.head(limit)
    merged = merged.sort_values("period", ascending=True)
    if merged.empty:
        return []

    return [
        {
            "date_label": row["period"].strftime("%d/%m"),
            "period": row["period"].date().isoformat(),
            "value": _number(row.get("value")),
            "team_avg": _number(row.get("team_avg")),
        }
        for _, row in merged.iterrows()
    ]


def _render_dual_percent_bar_chart(
    rows: list[dict],
    *,
    chart_class: str,
    mine_label: str,
    team_label: str,
) -> None:
    values = [100.0]
    for row in rows:
        for key in ("value", "team_avg"):
            value = _number(row.get(key))
            if value is not None and value >= 0:
                values.append(value)
    maximum = max(values)
    scale = float(((int(maximum) + 9) // 10) * 10)

    items: list[str] = []
    for index, row in enumerate(rows):
        mine = _number(row.get("value"))
        team = _number(row.get("team_avg"))
        mine_width = 0.0 if mine is None else min(max(mine / scale * 100, 0), 100)
        team_width = 0.0 if team is None else min(max(team / scale * 100, 0), 100)
        delay = index * 0.055

        items.append(
            (
                "<div class='cop-etit-chart-row'>"
                f"<div class='cop-etit-chart-date'>{escape(str(row['date_label']))}</div>"
                "<div class='cop-etit-chart-bars'>"
                "<div class='cop-etit-chart-line'>"
                f"<span class='cop-etit-chart-series'>{escape(mine_label)}</span>"
                "<div class='cop-etit-chart-track'>"
                f"<div class='cop-etit-chart-bar cop-etit-chart-mine' style='width:{mine_width:.2f}%;animation-delay:{delay:.2f}s'></div>"
                "</div>"
                f"<strong>{escape(_pct(mine))}</strong>"
                "</div>"
                "<div class='cop-etit-chart-line'>"
                f"<span class='cop-etit-chart-series'>{escape(team_label)}</span>"
                "<div class='cop-etit-chart-track'>"
                f"<div class='cop-etit-chart-bar cop-etit-chart-team' style='width:{team_width:.2f}%;animation-delay:{delay + .08:.2f}s'></div>"
                "</div>"
                f"<strong>{escape(_pct(team))}</strong>"
                "</div>"
                "</div>"
                "</div>"
            )
        )

    st.markdown(
        (
            f"<section class='{escape(chart_class)} cop-etit-chart'>"
            "<div class='cop-etit-chart-scale'>"
            "<span>0%</span>"
            f"<span>Escala até {scale:.0f}%</span>"
            "</div>"
            + "".join(items)
            + "</section>"
        ),
        unsafe_allow_html=True,
    )


def _chat_group_table(
    details: pd.DataFrame,
    team_details: pd.DataFrame,
) -> pd.DataFrame:
    group = _dimension_rows(details, "group")
    if group.empty:
        return pd.DataFrame()

    records: list[dict] = []
    for raw_value, part in group.groupby("dimension_value", dropna=False):
        name = str(raw_value or "").strip()
        if not name:
            continue

        volume = float(
            pd.to_numeric(part.get("volume"), errors="coerce").fillna(0).sum()
        )
        successes = float(
            pd.to_numeric(part.get("successes"), errors="coerce").fillna(0).sum()
        )
        losses = float(
            pd.to_numeric(part.get("losses"), errors="coerce").fillna(0).sum()
        )
        adherence = None if volume <= 0 else successes / volume * 100
        team_avg = _team_value(team_details, "group", name)

        records.append(
            {
                "Grupo": name,
                "Volume": int(round(volume)),
                "Aderentes": int(round(successes)),
                "Não aderentes": int(round(losses)),
                "Aderência %": _pct(adherence),
                "Média equipe %": _pct(team_avg),
                "_volume": volume,
            }
        )

    if not records:
        return pd.DataFrame()

    return (
        pd.DataFrame(records)
        .sort_values(["_volume", "Grupo"], ascending=[False, True])
        .drop(columns=["_volume"])
        .reset_index(drop=True)
    )


def _etit_operational_summary(details: pd.DataFrame) -> dict:
    overall = _dimension_rows(details, "overall")
    source = overall if not overall.empty else details

    volume = float(pd.to_numeric(source.get("volume"), errors="coerce").fillna(0).sum())
    successes = float(
        pd.to_numeric(source.get("successes"), errors="coerce").fillna(0).sum()
    )
    losses = float(
        pd.to_numeric(source.get("losses"), errors="coerce").fillna(0).sum()
    )

    return {
        "volume": int(round(volume)),
        "successes": int(round(successes)),
        "losses": int(round(losses)),
        "adherence": None if volume <= 0 else successes / volume * 100,
        "tma_seconds": _weighted_breakdown_duration(source, "tma_seconds"),
        "tmr_seconds": _weighted_breakdown_duration(source, "tmr_seconds"),
    }


def _weighted_breakdown_duration(
    frame: pd.DataFrame,
    column: str,
) -> float | None:
    if frame is None or frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce")
    weights = pd.to_numeric(frame.get("volume"), errors="coerce").fillna(0)
    valid = values.notna() & weights.gt(0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _format_duration(seconds: float | None) -> str:
    value = _number(seconds)
    if value is None or value < 0:
        return "—"
    total = int(round(value))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _assertiveness_dimension_table(
    details: pd.DataFrame,
    dimension: str,
    label: str,
    *,
    top: int | None = None,
) -> pd.DataFrame:
    rows = _dimension_rows(details, dimension)
    if rows.empty:
        return pd.DataFrame()

    records: list[dict] = []
    for raw_value, part in rows.groupby("dimension_value", dropna=False):
        value = str(raw_value or "").strip()
        if not value:
            continue

        volume = float(
            pd.to_numeric(part.get("volume"), errors="coerce").fillna(0).sum()
        )
        successes = float(
            pd.to_numeric(part.get("successes"), errors="coerce").fillna(0).sum()
        )
        losses = float(
            pd.to_numeric(part.get("losses"), errors="coerce").fillna(0).sum()
        )
        adherence = None if volume <= 0 else successes / volume * 100
        non_adherence = (
            None
            if adherence is None
            else max(0.0, 100.0 - adherence)
        )

        records.append(
            {
                label: value,
                "Volume": int(round(volume)),
                "Assertivos": int(round(successes)),
                "Não Assertivos": int(round(losses)),
                "Assertividade %": _pct(adherence),
                "Não Assertividade %": _pct(non_adherence),
                "_volume": volume,
                "_result": -1.0 if adherence is None else adherence,
            }
        )

    if not records:
        return pd.DataFrame()

    frame = pd.DataFrame(records).sort_values(
        ["_volume", "_result", label],
        ascending=[False, False, True],
    )
    if top is not None:
        frame = frame.head(top)

    return frame[
        [
            label,
            "Volume",
            "Assertivos",
            "Não Assertivos",
            "Assertividade %",
            "Não Assertividade %",
        ]
    ].reset_index(drop=True)


def _assertiveness_service_scoped_details(
    rows: pd.DataFrame,
    service: str,
) -> pd.DataFrame:
    if (
        rows is None
        or rows.empty
        or not {"dimension", "dimension_value"}.issubset(rows.columns)
    ):
        return pd.DataFrame()

    service_value = str(service or "").strip()
    if not service_value:
        return rows.copy()

    direct_service = rows[
        (rows["dimension"].astype(str) == "service")
        & (rows["dimension_value"].astype(str) == service_value)
    ].copy()

    composite = rows[
        rows["dimension"].astype(str).str.startswith("service__", na=False)
    ].copy()
    if composite.empty:
        return direct_service

    parts = composite["dimension_value"].astype(str).str.split(
        "|||",
        n=1,
        expand=True,
        regex=False,
    )
    if parts.shape[1] < 2:
        return direct_service

    mask = parts[0].astype(str) == service_value
    composite = composite[mask].copy()
    if composite.empty:
        return direct_service

    selected = composite["dimension_value"].astype(str).str.split(
        "|||",
        n=1,
        expand=True,
        regex=False,
    )
    composite["dimension_value"] = selected[1].values
    composite["dimension"] = composite["dimension"].astype(str).str.replace(
        r"^service__",
        "",
        regex=True,
    )

    return pd.concat(
        [direct_service, composite],
        ignore_index=True,
    )


def _render_assertiveness_kpi(
    label: str,
    value: str,
    tone: str,
) -> None:
    safe_tone = (
        tone
        if tone in {"neutral", "good", "bad", "warning", "team"}
        else "neutral"
    )
    st.markdown(
        (
            f"<article class='cop-assert-kpi cop-assert-{safe_tone}'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(value)}</strong>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _render_etit_kpi(label: str, value: str) -> None:
    st.markdown(
        (
            "<article class='cop-etit-user-kpi'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(value)}</strong>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _enterprise_etit_demand_cards(
    details: pd.DataFrame,
    team_details: pd.DataFrame,
) -> list[dict]:
    """Resumo individual de RAL/REC com referências agregadas da equipe."""
    mine = _dimension_rows(details, "demand")
    if mine.empty or "dimension_value" not in mine.columns:
        return []
    mine["dimension_value"] = (
        mine["dimension_value"].astype(str).str.upper().str.strip()
    )
    team = _dimension_rows(team_details, "demand")
    if not team.empty and "dimension_value" in team.columns:
        team["dimension_value"] = (
            team["dimension_value"].astype(str).str.upper().str.strip()
        )

    cards: list[dict] = []
    for demand_name in ("RAL", "REC"):
        part = mine[mine["dimension_value"] == demand_name]
        team_part = (
            team[team["dimension_value"] == demand_name]
            if not team.empty and "dimension_value" in team.columns
            else pd.DataFrame()
        )

        if part.empty:
            cards.append({"demand": demand_name, "has_data": False})
            continue

        volume = float(pd.to_numeric(part["volume"], errors="coerce").fillna(0).sum())
        successes = float(
            pd.to_numeric(part["successes"], errors="coerce").fillna(0).sum()
        )
        losses = float(pd.to_numeric(part["losses"], errors="coerce").fillna(0).sum())
        adherence = None if volume <= 0 else successes / volume * 100

        # Referência agregada da equipe; não expor dados de outros analistas.
        team_avg = _weighted_team_avg(team_part)
        avg_team_losses = None
        if not team_part.empty and {"team_losses", "team_analysts"}.issubset(team_part.columns):
            team_losses = float(
                pd.to_numeric(team_part["team_losses"], errors="coerce").fillna(0).sum()
            )
            analysts = pd.to_numeric(
                team_part["team_analysts"], errors="coerce"
            ).fillna(0)
            analyst_count = float(analysts.max()) if not analysts.empty else 0.0
            if analyst_count > 0:
                avg_team_losses = team_losses / analyst_count

        delta = None if adherence is None or team_avg is None else adherence - team_avg
        comparison_tone = (
            "neutral" if delta is None or abs(delta) < 0.05
            else "good" if delta > 0 else "attention"
        )
        cards.append(
            {
                "demand": demand_name,
                "has_data": True,
                "volume": int(round(volume)),
                "successes": int(round(successes)),
                "losses": int(round(losses)),
                "adherence": adherence,
                "team_avg": team_avg,
                "comparison": _comparison_label(
                    adherence, team_avg, "higher_is_better", "percent"
                ),
                "comparison_tone": comparison_tone,
                "tma_seconds": _weighted_breakdown_duration(part, "tma_seconds"),
                "tmr_seconds": _weighted_breakdown_duration(part, "tmr_seconds"),
                "avg_team_losses": avg_team_losses,
            }
        )
    return cards


def _render_enterprise_etit_demand_card(item: dict) -> None:
    demand = str(item.get("demand") or "")
    if demand not in {"RAL", "REC"}:
        return

    if not item.get("has_data"):
        st.markdown(
            (
                f"<article class='cop-etit-demand-panel cop-etit-demand-{demand.lower()}'>"
                f"<header><span>DEMANDA</span><strong>{demand}</strong></header>"
                "<p class='cop-etit-demand-empty'>Sem registros individuais para "
                "esta demanda no período.</p>"
                "</article>"
            ),
            unsafe_allow_html=True,
        )
        return

    tone = str(item.get("comparison_tone") or "neutral")
    if tone not in {"good", "attention", "neutral"}:
        tone = "neutral"
    avg_team_losses = _number(item.get("avg_team_losses"))
    avg_losses_label = (
        "—" if avg_team_losses is None
        else f"{avg_team_losses:.1f}".replace(".", ",")
    )
    metrics = (
        ("Média da equipe", _pct(_number(item.get("team_avg")))),
        ("Eventos", str(item.get("volume", 0))),
        ("Aderentes", str(item.get("successes", 0))),
        ("Não aderentes", str(item.get("losses", 0))),
        ("TMA médio", _format_duration(item.get("tma_seconds"))),
        ("TMR médio", _format_duration(item.get("tmr_seconds"))),
    )
    tiles = "".join(
        (
            "<div class='cop-etit-demand-tile'>"
            f"<span>{escape(label)}</span><strong>{escape(value)}</strong>"
            "</div>"
        )
        for label, value in metrics
    )
    st.markdown(
        (
            f"<article class='cop-etit-demand-panel cop-etit-demand-{demand.lower()}'>"
            f"<header><span>DEMANDA</span><strong>{demand}</strong></header>"
            "<div class='cop-etit-demand-result'>"
            "<div><span>Meu resultado</span>"
            f"<strong>{escape(_pct(_number(item.get('adherence'))))}</strong></div>"
            f"<em class='cop-etit-demand-comparison cop-etit-demand-{tone}'>"
            f"{escape(str(item.get('comparison') or '—'))}</em>"
            "</div>"
            f"<div class='cop-etit-demand-grid'>{tiles}</div>"
            "<footer>Média de não aderentes por analista na equipe: "
            f"<strong>{escape(avg_losses_label)}</strong></footer>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _etit_dimension_table(
    details: pd.DataFrame,
    team_details: pd.DataFrame,
    dimension: str,
    label: str,
    *,
    include_duration: bool = False,
) -> pd.DataFrame:
    mine = _dimension_rows(details, dimension)
    if mine.empty:
        return pd.DataFrame()

    team = _dimension_rows(team_details, dimension)
    records: list[dict] = []

    for raw_value, part in mine.groupby("dimension_value", dropna=False):
        value = str(raw_value or "").strip()
        if not value:
            continue

        volume = float(pd.to_numeric(part.get("volume"), errors="coerce").fillna(0).sum())
        successes = float(
            pd.to_numeric(part.get("successes"), errors="coerce").fillna(0).sum()
        )
        losses = float(
            pd.to_numeric(part.get("losses"), errors="coerce").fillna(0).sum()
        )
        adherence = None if volume <= 0 else successes / volume * 100

        team_avg = _team_value(team_details, dimension, value)
        row = {
            label: value,
            "Eventos": int(round(volume)),
            "Aderentes": int(round(successes)),
            "Não aderentes": int(round(losses)),
            "Aderência %": _pct(adherence),
            "Média equipe %": _pct(team_avg),
            "_result": -1.0 if adherence is None else float(adherence),
        }
        if include_duration:
            row["TMA"] = _format_duration(
                _weighted_breakdown_duration(part, "tma_seconds")
            )
            row["TMR"] = _format_duration(
                _weighted_breakdown_duration(part, "tmr_seconds")
            )
        records.append(row)

    if not records:
        return pd.DataFrame()

    table = pd.DataFrame(records).sort_values(
        ["Eventos", "_result", label],
        ascending=[False, False, True],
    )

    ordered = [label, "Eventos", "Aderentes", "Não aderentes"]
    if include_duration:
        ordered.extend(["TMA", "TMR"])
    ordered.extend(["Aderência %", "Média equipe %"])
    return table[ordered].reset_index(drop=True)


def _render_etit_dimension_highlight(
    table: pd.DataFrame,
    label: str,
) -> None:
    if table is None or table.empty or "Aderência %" not in table.columns:
        return

    scoring = table.copy()
    scoring["_score"] = (
        scoring["Aderência %"]
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    scoring["_score"] = pd.to_numeric(scoring["_score"], errors="coerce")
    scoring = scoring.dropna(subset=["_score"])
    if scoring.empty:
        return

    best = scoring.sort_values(
        ["_score", "Eventos"],
        ascending=[False, False],
    ).iloc[0]
    worst = scoring.sort_values(
        ["_score", "Eventos"],
        ascending=[True, False],
    ).iloc[0]
    st.caption(
        f"Melhor: {best[label]} ({best['Aderência %']}) · "
        f"Maior atenção: {worst[label]} ({worst['Aderência %']})"
    )


def _closing_demand_summary(
    details: pd.DataFrame,
    team_details: pd.DataFrame,
) -> list[dict]:
    mine = _dimension_rows(details, "demand")
    if mine.empty:
        return []

    mine["dimension_value"] = mine["dimension_value"].astype(str).str.upper().str.strip()
    mine = mine[mine["dimension_value"].isin(("RAL", "REC"))].copy()
    if mine.empty:
        return []

    team = _dimension_rows(team_details, "demand")
    if not team.empty:
        team["dimension_value"] = (
            team["dimension_value"].astype(str).str.upper().str.strip()
        )

    rows: list[dict] = []
    for demand in ("RAL", "REC"):
        part = mine[mine["dimension_value"] == demand]
        if part.empty:
            continue

        volume = int(pd.to_numeric(part["volume"], errors="coerce").fillna(0).sum())
        successes = int(
            pd.to_numeric(part["successes"], errors="coerce").fillna(0).sum()
        )
        losses = int(pd.to_numeric(part["losses"], errors="coerce").fillna(0).sum())
        my_result = successes / volume * 100 if volume else None

        team_part = (
            team[team["dimension_value"] == demand]
            if not team.empty
            else pd.DataFrame()
        )
        team_avg = _weighted_team_avg(team_part)
        rows.append(
            {
                "demand": demand,
                "volume": volume,
                "successes": successes,
                "losses": losses,
                "result": my_result,
                "team_avg": team_avg,
                "comparison": _comparison_label(
                    my_result,
                    team_avg,
                    "higher_is_better",
                    "percent",
                ),
            }
        )
    return rows


def _render_closing_demand_card(item: dict) -> None:
    demand = str(item.get("demand") or "—")
    result = _number(item.get("result"))
    team_avg = _number(item.get("team_avg"))
    losses = int(item.get("losses") or 0)
    tone = "good" if result is not None and result >= 80 else "attention"
    st.markdown(
        (
            f"<article class='cop-closing-demand cop-closing-demand-{tone}'>"
            "<div class='cop-closing-demand-head'>"
            f"<strong>{escape(demand)}</strong>"
            f"<span>{int(item.get('volume') or 0)} eventos</span>"
            "</div>"
            f"<div class='cop-closing-demand-value'>{escape(_pct(result))}</div>"
            "<div class='cop-closing-demand-grid'>"
            f"<div><small>Média da equipe</small><b>{escape(_pct(team_avg))}</b></div>"
            f"<div><small>Não aderentes</small><b>{losses}</b></div>"
            "</div>"
            f"<div class='cop-closing-demand-footer'>{escape(str(item.get('comparison') or '—'))}</div>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _closing_cause_summary(details: pd.DataFrame) -> list[dict]:
    labels = {
        "cause_toa": "Causa TOA",
        "cause_sir": "Causa SIR",
        "area_involved": "Área envolvida",
    }
    rows: list[dict] = []

    for dimension, label in labels.items():
        part = _dimension_rows(details, dimension)
        if part.empty:
            continue
        part = part.copy()
        part["losses"] = pd.to_numeric(part["losses"], errors="coerce").fillna(0)
        part = part[part["losses"] > 0]
        if part.empty:
            continue

        grouped = (
            part.groupby("dimension_value", dropna=False)["losses"]
            .sum()
            .reset_index()
        )
        for _, item in grouped.iterrows():
            reason = str(item.get("dimension_value") or "").strip()
            if not reason:
                continue
            rows.append(
                {
                    "Tipo": label,
                    "Motivo": reason,
                    "Não aderentes": int(item.get("losses") or 0),
                }
            )

    return sorted(
        rows,
        key=lambda item: (-int(item["Não aderentes"]), item["Tipo"], item["Motivo"]),
    )


def _closing_cause_table(
    details: pd.DataFrame,
    dimension: str,
    label: str,
    *,
    top: int = 10,
) -> pd.DataFrame:
    part = _dimension_rows(details, dimension)
    if part.empty:
        return pd.DataFrame()

    frame = part.copy()
    frame["losses"] = pd.to_numeric(frame["losses"], errors="coerce").fillna(0)
    frame = frame[frame["losses"] > 0]
    if frame.empty:
        return pd.DataFrame()

    grouped = (
        frame.groupby("dimension_value", dropna=False)["losses"]
        .sum()
        .reset_index()
        .rename(
            columns={
                "dimension_value": label,
                "losses": "Não Assertivos",
            }
        )
    )
    grouped[label] = grouped[label].fillna("").astype(str).str.strip()
    grouped = grouped[grouped[label].ne("")]
    if grouped.empty:
        return pd.DataFrame()

    grouped["Não Assertivos"] = grouped["Não Assertivos"].round().astype(int)
    return (
        grouped.sort_values(
            ["Não Assertivos", label],
            ascending=[False, True],
        )
        .head(top)
        .reset_index(drop=True)
    )


def _closing_dimension_table(
    details: pd.DataFrame,
    team_details: pd.DataFrame,
    dimension: str,
    label: str,
) -> pd.DataFrame:
    mine = _dimension_rows(details, dimension)
    if mine.empty:
        return pd.DataFrame()

    team = _dimension_rows(team_details, dimension)

    records: list[dict] = []
    for value, part in mine.groupby("dimension_value", dropna=False):
        name = str(value or "").strip()
        if not name:
            continue

        volume = int(pd.to_numeric(part["volume"], errors="coerce").fillna(0).sum())
        successes = int(
            pd.to_numeric(part["successes"], errors="coerce").fillna(0).sum()
        )
        losses = int(pd.to_numeric(part["losses"], errors="coerce").fillna(0).sum())
        result = successes / volume * 100 if volume else None

        if team.empty:
            team_avg = None
        else:
            team_part = team[
                team["dimension_value"].astype(str).str.strip() == name
            ]
            team_avg = _weighted_team_avg(team_part)

        records.append(
            {
                label: name,
                "Volume": volume,
                "Assertivos": successes,
                "Não aderentes": losses,
                "Meu resultado": _pct(result),
                "Média da equipe": _pct(team_avg),
                "_result": -1.0 if result is None else float(result),
            }
        )

    if not records:
        return pd.DataFrame()

    table = pd.DataFrame(records).sort_values(
        ["Volume", "_result", label],
        ascending=[False, False, True],
    )
    return table.drop(columns=["_result"]).reset_index(drop=True)


def _render_closing_dimension_highlight(
    table: pd.DataFrame,
    label: str,
) -> None:
    if table is None or table.empty or "Meu resultado" not in table.columns:
        return

    scoring = table.copy()
    scoring["_score"] = (
        scoring["Meu resultado"]
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    scoring["_score"] = pd.to_numeric(scoring["_score"], errors="coerce")
    scoring = scoring.dropna(subset=["_score"])
    if scoring.empty:
        return

    best = scoring.sort_values(
        ["_score", "Volume"],
        ascending=[False, False],
    ).iloc[0]
    worst = scoring.sort_values(
        ["_score", "Volume"],
        ascending=[True, False],
    ).iloc[0]

    st.caption(
        f"Melhor: {best[label]} ({best['Meu resultado']}) · "
        f"Maior atenção: {worst[label]} ({worst['Meu resultado']})"
    )


def _closing_review_rows(details: pd.DataFrame, payload: dict) -> list[dict]:
    refs = _dimension_rows(details, "incident")
    if refs.empty:
        return []

    refs = refs.copy()
    refs["losses"] = pd.to_numeric(refs["losses"], errors="coerce").fillna(0)
    refs = refs[refs["losses"] > 0].copy()
    if refs.empty:
        return []

    daily_index = _closing_daily_index(payload)
    rows: list[dict] = []

    for _, item in refs.sort_values(["day", "losses"], ascending=[False, False]).iterrows():
        day = str(item.get("day") or "")
        raw = str(item.get("dimension_value") or "").strip()
        demand = ""
        identifier = raw

        if "|||" in raw:
            demand, identifier = raw.split("|||", 1)
            demand = demand.strip().upper()
        else:
            demand = _closing_infer_demand_for_day(details, day)

        if demand not in {"RAL", "REC"}:
            demand = demand or "—"

        daily = daily_index.get(day, {})
        rows.append(
            {
                "Data": _format_date(day),
                "Demanda": demand,
                "INC / Identificador": identifier or "Sem identificador",
                "Resultado do dia": _format_ptbr_metric(
                    _number(daily.get("value")),
                    "percent",
                ),
                "Média da equipe no dia": (
                    "—"
                    if _number(daily.get("team_avg")) is None
                    else _format_ptbr_metric(
                        _number(daily.get("team_avg")),
                        "percent",
                    )
                ),
                "Não aderentes": int(item.get("losses") or 0),
            }
        )

    return rows


def _closing_daily_index(payload: dict) -> dict[str, dict]:
    individual = pd.DataFrame(payload.get("individual") or [])
    if individual.empty or "indicator_key" not in individual.columns:
        return {}

    mine = individual[individual["indicator_key"] == "closing_assertiveness"].copy()
    if mine.empty:
        return {}

    team = pd.DataFrame(payload.get("team_daily") or [])
    if not team.empty and "indicator_key" in team.columns:
        team = team[team["indicator_key"] == "closing_assertiveness"][
            ["period", "team_avg"]
        ].copy()
    else:
        team = pd.DataFrame(columns=["period", "team_avg"])

    mine = mine[["period", "value", "volume"]].copy()
    merged = mine.merge(team, on="period", how="left")

    output: dict[str, dict] = {}
    for _, row in merged.iterrows():
        period = str(row.get("period") or "")
        if period:
            output[period] = {
                "value": _number(row.get("value")),
                "team_avg": _number(row.get("team_avg")),
                "volume": int(row.get("volume") or 0),
            }
    return output


def _closing_infer_demand_for_day(details: pd.DataFrame, day: str) -> str:
    demand_rows = _dimension_rows(details, "demand")
    if demand_rows.empty:
        return ""

    same_day = demand_rows[demand_rows["day"].astype(str) == str(day)].copy()
    if same_day.empty:
        return ""

    same_day["losses"] = pd.to_numeric(
        same_day["losses"], errors="coerce"
    ).fillna(0)
    same_day = same_day[same_day["losses"] > 0]
    if same_day.empty:
        return ""

    positive_demands = {
        str(value).strip().upper()
        for value in same_day["dimension_value"].tolist()
        if str(value).strip().upper() in {"RAL", "REC"}
    }
    if len(positive_demands) == 1:
        return next(iter(positive_demands))
    return ""


def _indicator_volume_for_period(
    rows: list[dict],
    indicator_key: str,
    period: str,
) -> float | None:
    candidates = [
        row
        for row in rows or []
        if str(row.get("indicator_key") or "") == indicator_key
    ]
    if not candidates:
        return None

    exact = [
        row
        for row in candidates
        if str(row.get("period") or "") == str(period or "")
    ]
    selected = exact if exact else candidates
    selected = sorted(
        selected,
        key=lambda row: str(row.get("period") or ""),
        reverse=True,
    )
    return _number(selected[0].get("volume"))


def _cancellation_etit_base_for_period(
    rows: list[dict],
    period: str,
) -> dict:
    enterprise = _indicator_volume_for_period(
        rows,
        "emp_etit_event",
        period,
    )
    if enterprise is not None and enterprise > 0:
        return {
            "volume": enterprise,
            "label": "VOLUME ETIT",
            "source": "emp_etit_event",
        }

    hfc = _indicator_volume_for_period(
        rows,
        "res_etit_fibra_hfc",
        period,
    )
    gpon = _indicator_volume_for_period(
        rows,
        "res_etit_gpon",
        period,
    )
    residential_values = [
        value
        for value in (hfc, gpon)
        if value is not None and value > 0
    ]
    residential_total = (
        sum(residential_values)
        if residential_values
        else None
    )
    return {
        "volume": residential_total,
        "label": "VOLUME ETIT HFC + GPON",
        "source": "res_etit_hfc_gpon",
    }


def _team_index(payload: dict) -> dict[tuple[str, str], dict]:
    return {
        (str(row.get("period")), str(row.get("indicator_key"))): row
        for row in payload.get("team_averages") or []
    }


def _indicator_tab_label(indicator_key: str, name: str) -> str:
    return INDICATOR_TAB_LABELS.get(indicator_key, f"📊 {name}")


def _indicator_icon(indicator_key: str) -> str:
    label = INDICATOR_TAB_LABELS.get(indicator_key, "📊")
    return label.split(" ", 1)[0] if label else "📊"


def _period_label(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 6 and text.isdigit():
        months = (
            "Janeiro",
            "Fevereiro",
            "Março",
            "Abril",
            "Maio",
            "Junho",
            "Julho",
            "Agosto",
            "Setembro",
            "Outubro",
            "Novembro",
            "Dezembro",
        )
        month = int(text[4:6])
        if 1 <= month <= 12:
            return f"{months[month - 1]} {text[:4]}"
    return text or "Período atual"


def _render_identity_bar(
    display_name: str,
    segment_name: str,
    latest: list[dict],
) -> None:
    periods = [str(row.get("period") or "") for row in latest if row.get("period")]
    period = max(periods) if periods else ""
    person_name = _short_display_name(display_name)

    st.markdown(
        (
            "<section class='cop-analyst-identity'>"
            "<div class='cop-analyst-identity-main'>"
            "<div class='cop-analyst-eyebrow'>MEU PAINEL DE DESEMPENHO</div>"
            f"<h1>Olá, {escape(person_name)}.</h1>"
            "<p>Acompanhe seus resultados, entenda sua evolução e veja como você está "
            "em relação à referência da sua equipe.</p>"
            "<div class='cop-analyst-chips'>"
            f"<span>📅 {escape(_period_label(period))}</span>"
            f"<span>🏷️ {escape(segment_name)}</span>"
            "<span>📍 Regional Leste</span>"
            "</div>"
            "</div>"
            "<div class='cop-analyst-private'>🔒 Visão privada</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def _build_summary_snapshot(
    latest: list[dict],
    team_index: dict[tuple[str, str], dict],
    freshness: list[dict],
) -> dict:
    tracked = len(latest)
    with_target = 0
    met = 0
    with_team = 0
    above_team = 0
    best: tuple[float, dict, float] | None = None
    attention: tuple[float, dict, float | None] | None = None

    for row in latest:
        value = _number(row.get("value"))
        target = _number(row.get("target_value"))
        direction = str(row.get("direction") or "higher_is_better")
        key = str(row.get("indicator_key"))
        period = str(row.get("period"))
        team_avg = _number(team_index.get((period, key), {}).get("team_avg"))

        if value is not None and target is not None:
            with_target += 1
            if _meets_target(value, target, direction):
                met += 1
            else:
                shortfall = (
                    target - value
                    if direction != "lower_is_better"
                    else value - target
                )
                if attention is None or shortfall > attention[0]:
                    attention = (shortfall, row, team_avg)

        if value is not None and team_avg is not None:
            with_team += 1
            score = (
                value - team_avg
                if direction != "lower_is_better"
                else team_avg - value
            )
            if score >= 0:
                above_team += 1
            if best is None or score > best[0]:
                best = (score, row, team_avg)

    if attention is None:
        worst: tuple[float, dict, float] | None = None
        for row in latest:
            value = _number(row.get("value"))
            key = str(row.get("indicator_key"))
            period = str(row.get("period"))
            team_avg = _number(team_index.get((period, key), {}).get("team_avg"))
            if value is None or team_avg is None:
                continue
            direction = str(row.get("direction") or "higher_is_better")
            score = (
                value - team_avg
                if direction != "lower_is_better"
                else team_avg - value
            )
            if worst is None or score < worst[0]:
                worst = (score, row, team_avg)
        if worst is not None and worst[0] < 0:
            attention = (abs(worst[0]), worst[1], worst[2])

    freshness_dates = [
        pd.to_datetime(row.get("data_through"), errors="coerce")
        for row in freshness
        if row.get("data_through")
    ]
    freshness_dates = [value for value in freshness_dates if not pd.isna(value)]
    if freshness_dates:
        freshness_label = max(freshness_dates).strftime("%d/%m/%Y")
    else:
        periods = [str(row.get("period") or "") for row in latest if row.get("period")]
        freshness_label = _period_label(max(periods) if periods else "")

    if best is not None:
        best_score, best_row, best_team = best
        best_value = _number(best_row.get("value"))
        best_title = str(best_row.get("name") or best_row.get("indicator_key") or "Indicador")
        comparison = _comparison_label(
            best_value,
            best_team,
            str(best_row.get("direction") or "higher_is_better"),
            best_row.get("unit"),
        )
        prefix = "Destaque do período" if best_score >= 0 else "Melhor posição relativa"
        best_text = (
            f"{prefix}: {_format_ptbr_metric(best_value, best_row.get('unit'))} vs "
            f"{_format_ptbr_metric(best_team, best_row.get('unit'))} da equipe · "
            f"{comparison}."
        )
    else:
        best_title = "Comparação ainda indisponível"
        best_text = "Os próximos processamentos vão ampliar a comparação com a equipe."

    if attention is not None:
        _, attention_row, attention_team = attention
        attention_value = _number(attention_row.get("value"))
        attention_title = str(
            attention_row.get("name") or attention_row.get("indicator_key") or "Indicador"
        )
        comparison = _comparison_label(
            attention_value,
            attention_team,
            str(attention_row.get("direction") or "higher_is_better"),
            attention_row.get("unit"),
        )
        attention_text = (
            f"Resultado {_format_ptbr_metric(attention_value, attention_row.get('unit'))} · "
            f"{_target_text(attention_row)}"
        )
        if comparison == "Na média":
            attention_text += " · Na média da equipe."
        elif comparison != "—":
            attention_text += f" · {comparison} que a equipe."
    else:
        attention_title = "Nenhuma meta crítica"
        attention_text = (
            "Os indicadores com meta configurada estão dentro do esperado neste período."
        )

    return {
        "tracked": tracked,
        "with_target": with_target,
        "met": met,
        "with_team": with_team,
        "above_team": above_team,
        "freshness_label": freshness_label,
        "best_title": best_title,
        "best_text": best_text,
        "attention_title": attention_title,
        "attention_text": attention_text,
    }


def _meets_target(value: float, target: float, direction: str) -> bool:
    if direction == "lower_is_better":
        return value <= target
    return value >= target


def _short_display_name(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return "Analista"
    parts = text.split()
    if len(parts) <= 2:
        return text.upper()
    return f"{parts[0]} {parts[-1]}".upper()


def _render_executive_summary(snapshot: dict) -> None:
    tracked = int(snapshot.get("tracked") or 0)
    with_target = int(snapshot.get("with_target") or 0)
    met = int(snapshot.get("met") or 0)
    attention = max(with_target - met, 0)
    above = int(snapshot.get("above_team") or 0)
    with_team = int(snapshot.get("with_team") or 0)

    if with_target:
        target_text = f"{met} de {with_target} indicadores estão dentro da meta"
    else:
        target_text = "Ainda não há metas configuradas para os indicadores disponíveis"

    if with_team:
        team_text = f"{above} de {with_team} estão acima da média da equipe"
    else:
        team_text = "a comparação com a equipe ainda está sendo formada"

    tone = "good" if attention == 0 and with_target else "attention" if attention else "neutral"
    st.markdown(
        (
            f"<div class='cop-personal-executive cop-personal-executive-{tone}'>"
            "<div class='cop-personal-executive-label'>RESUMO EXECUTIVO</div>"
            f"<div class='cop-personal-executive-title'>{escape(target_text)}.</div>"
            f"<div class='cop-personal-executive-text'>No período, {escape(team_text)}. "
            f"Você possui {tracked} indicadores acompanhados.</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_summary_kpi(
    label: str,
    value: str,
    context: str,
    tone: str,
) -> None:
    tone_class = {
        "good": " cop-personal-kpi-good",
        "attention": " cop-personal-kpi-attention",
    }.get(tone, "")
    st.markdown(
        (
            f"<div class='cop-personal-kpi{tone_class}'>"
            f"<div class='cop-personal-kpi-label'>{escape(label)}</div>"
            f"<div class='cop-personal-kpi-value'>{escape(value)}</div>"
            f"<div class='cop-personal-kpi-context'>{escape(context)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_summary_insight(
    label: str,
    title: str,
    text: str,
    tone: str,
) -> None:
    st.markdown(
        (
            f"<div class='cop-personal-insight cop-personal-insight-{escape(tone)}'>"
            f"<div class='cop-personal-insight-label'>{escape(label)}</div>"
            f"<div class='cop-personal-insight-title'>{escape(title)}</div>"
            f"<div class='cop-personal-insight-text'>{escape(text)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_indicator_status_card(row: dict, team: dict) -> None:
    key = str(row.get("indicator_key"))
    name = str(row.get("name") or key)
    value = _number(row.get("value"))
    team_avg = _number(team.get("team_avg"))
    target = _number(row.get("target_value"))
    direction = str(row.get("direction") or "higher_is_better")
    unit = row.get("unit")

    if target is None or value is None:
        status = "Sem meta"
        status_class = "neutral"
    elif _meets_target(value, target, direction):
        status = "Dentro da meta"
        status_class = "good"
    else:
        status = "Atenção"
        status_class = "attention"

    comparison = _comparison_label(value, team_avg, direction, unit)
    team_text = "—" if team_avg is None else _format_ptbr_metric(team_avg, unit)
    volume = int(row.get("volume") or 0)
    volume_html = (
        ""
        if key == "dpa_official"
        else f"<span>Volume <b>{volume:,}</b></span>".replace(",", ".")
    )

    icon = _indicator_icon(key)

    st.markdown(
        (
            f"<article class='cop-personal-status-card cop-status-{status_class}'>"
            "<div class='cop-personal-status-head'>"
            "<div class='cop-personal-status-title'>"
            f"<span class='cop-personal-status-icon'>{escape(icon)}</span>"
            f"<strong>{escape(name)}</strong>"
            "</div>"
            f"<span class='cop-personal-status-pill'>{escape(status)}</span>"
            "</div>"
            f"<div class='cop-personal-status-value'>{escape(_format_ptbr_metric(value, unit))}</div>"
            "<div class='cop-personal-status-grid'>"
            "<div><small>Média da equipe</small>"
            f"<strong>{escape(team_text)}</strong></div>"
            "<div><small>Comparação</small>"
            f"<strong>{escape(comparison)}</strong></div>"
            "</div>"
            "<div class='cop-personal-status-footer'>"
            f"<span>{escape(_target_text(row))}</span>"
            f"{volume_html}"
            "</div>"
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def _inject_analyst_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-analyst-shell { height:0; overflow:hidden; }

        .cop-analyst-identity {
            position:relative;
            overflow:hidden;
            display:grid;
            grid-template-columns:minmax(0, 1fr) auto;
            align-items:start;
            gap:1.8rem;
            min-height:255px;
            padding:2.45rem 2.65rem;
            margin:.1rem 0 1.35rem;
            border:1px solid rgba(148,163,184,.16);
            border-radius:24px;
            background:
                radial-gradient(circle at 91% 8%, rgba(255,255,255,.08) 0 82px, transparent 83px),
                radial-gradient(circle at 80% 118%, rgba(237,28,36,.30), transparent 32%),
                linear-gradient(135deg, #111923 0%, #28171d 62%, #741019 100%);
            box-shadow:0 24px 58px rgba(0,0,0,.27);
        }
        .cop-analyst-identity::after {
            content:"";
            position:absolute;
            width:260px;
            height:260px;
            right:4%;
            bottom:-145px;
            border-radius:50%;
            background:rgba(237,28,36,.18);
        }
        .cop-analyst-identity-main {
            position:relative;
            z-index:2;
            max-width:980px;
        }
        .cop-analyst-eyebrow {
            color:#ff9aa1;
            font-size:.86rem;
            font-weight:900;
            letter-spacing:.13em;
            margin-bottom:1rem;
        }
        .cop-analyst-identity h1 {
            margin:0 !important;
            color:#fff !important;
            font-size:clamp(2.7rem, 4.2vw, 4.35rem) !important;
            line-height:1.05 !important;
            font-weight:900 !important;
            letter-spacing:-.045em !important;
        }
        .cop-analyst-identity p {
            max-width:840px;
            margin:1rem 0 0 !important;
            color:rgba(255,255,255,.82) !important;
            font-size:1.12rem !important;
            line-height:1.6 !important;
        }
        .cop-analyst-chips {
            display:flex;
            flex-wrap:wrap;
            gap:.62rem;
            margin-top:1.45rem;
        }
        .cop-analyst-chips span,
        .cop-analyst-private {
            display:inline-flex;
            align-items:center;
            gap:.35rem;
            border:1px solid rgba(255,255,255,.13);
            border-radius:999px;
            background:rgba(255,255,255,.08);
            color:#edf5fc;
            padding:.48rem .82rem;
            font-size:.83rem;
            font-weight:760;
        }
        .cop-analyst-private {
            position:relative;
            z-index:2;
            height:max-content;
            color:#bff4d7;
            background:rgba(39,174,96,.14);
            border-color:rgba(84,224,142,.25);
            white-space:nowrap;
        }

        .stApp:has(.cop-analyst-shell) .stTabs [data-baseweb="tab-list"] {
            gap:.42rem;
            overflow-x:auto;
            padding:.32rem;
            margin-bottom:1rem;
            border:1px solid rgba(148,163,184,.12);
            border-radius:14px;
            background:
                linear-gradient(180deg, rgba(11,25,42,.90), rgba(7,18,31,.94));
            box-shadow:
                inset 0 1px 0 rgba(255,255,255,.02),
                0 12px 28px rgba(0,0,0,.09);
        }
        .stApp:has(.cop-analyst-shell) .stTabs [data-baseweb="tab"] {
            min-height:46px;
            border:1px solid transparent !important;
            border-radius:10px;
            padding:.64rem .92rem;
            color:#8fa0b6;
            font-weight:760;
            white-space:nowrap;
            transition:
                color .18s ease,
                background .18s ease,
                border-color .18s ease,
                box-shadow .18s ease,
                transform .18s ease;
        }
        .stApp:has(.cop-analyst-shell) .stTabs [data-baseweb="tab"]:hover {
            color:#e8f2fb;
            background:rgba(255,255,255,.035);
            transform:translateY(-1px);
        }
        .stApp:has(.cop-analyst-shell) .stTabs [aria-selected="true"] {
            color:#fff !important;
            border-color:rgba(125,211,252,.18) !important;
            background:
                linear-gradient(135deg, rgba(22,52,79,.98), rgba(13,30,49,.98)) !important;
            box-shadow:
                0 8px 22px rgba(0,0,0,.18),
                inset 0 0 0 1px rgba(255,255,255,.025);
            transform:translateY(-1px);
        }
        .stApp:has(.cop-analyst-shell) .stTabs [aria-selected="true"]::after {
            background:linear-gradient(90deg, #ed1c24 0%, #ff5865 48%, #38bdf8 100%);
            box-shadow:0 0 16px rgba(56,189,248,.25);
        }

        /* Nested indicator tabs: visually subordinate to the primary navigation. */
        .stApp:has(.cop-analyst-shell) .stTabs .stTabs [data-baseweb="tab-list"] {
            padding:.18rem 0 .42rem;
            margin-top:.05rem;
            margin-bottom:.85rem;
            border:0;
            border-bottom:1px solid rgba(148,163,184,.12);
            border-radius:0;
            background:transparent;
            box-shadow:none;
        }
        .stApp:has(.cop-analyst-shell) .stTabs .stTabs [data-baseweb="tab"] {
            min-height:40px;
            padding:.5rem .76rem;
            border-radius:9px;
            font-size:.82rem;
            font-weight:720;
        }
        .stApp:has(.cop-analyst-shell) .stTabs .stTabs [aria-selected="true"] {
            color:#eaf7ff !important;
            border-color:rgba(56,189,248,.20) !important;
            background:rgba(56,189,248,.085) !important;
            box-shadow:
                0 6px 16px rgba(0,0,0,.12),
                inset 0 0 0 1px rgba(56,189,248,.04);
        }
        .stApp:has(.cop-analyst-shell) .stTabs .stTabs [aria-selected="true"]::after {
            background:linear-gradient(90deg, #38bdf8, #60a5fa);
            box-shadow:0 0 12px rgba(56,189,248,.32);
        }

        .cop-user-cert-status {
            margin:.2rem 0 .75rem;
            padding:1.3rem 1.45rem 1.2rem;
            border:1px solid rgba(148,163,184,.15);
            border-left:4px solid #64748b;
            border-radius:17px;
            background:linear-gradient(135deg, rgba(15,35,56,.95), rgba(9,22,37,.98));
            text-align:center;
            box-shadow:0 16px 34px rgba(0,0,0,.14);
        }
        .cop-user-cert-team {
            color:#8497ad;
            font-size:.67rem;
            font-weight:900;
            letter-spacing:.085em;
        }
        .cop-user-cert-title {
            margin-top:.38rem;
            color:#f6fbff;
            font-size:1.32rem;
            line-height:1.15;
            font-weight:900;
            letter-spacing:-.025em;
        }
        .cop-user-cert-message {
            margin-top:.42rem;
            color:#9fb0c2;
            font-size:.76rem;
            line-height:1.5;
        }
        .cop-user-cert-good {
            border-left-color:#31d58a;
        }
        .cop-user-cert-good .cop-user-cert-title {
            color:#65e3a5;
        }
        .cop-user-cert-attention {
            border-left-color:#f7b84b;
        }
        .cop-user-cert-attention .cop-user-cert-title {
            color:#ffc966;
        }
        .cop-user-cert-bad {
            border-left-color:#ff4d5f;
        }
        .cop-user-cert-bad .cop-user-cert-title {
            color:#ff6b79;
        }

        .cop-user-cert-metric {
            min-height:118px;
            padding:1rem 1.05rem;
            border:1px solid rgba(148,163,184,.15);
            border-left:4px solid #64748b;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.92), rgba(8,21,36,.98));
            text-align:center;
            box-shadow:0 14px 30px rgba(0,0,0,.13);
        }
        .cop-user-cert-metric span {
            display:block;
            color:#8fa0b6;
            font-size:.67rem;
            font-weight:900;
            letter-spacing:.075em;
        }
        .cop-user-cert-metric strong {
            display:block;
            margin-top:.7rem;
            color:#f7fbff;
            font-size:1.85rem;
            line-height:1;
            font-weight:900;
        }
        .cop-user-cert-metric-good {
            border-left-color:#31d58a;
        }
        .cop-user-cert-metric-good strong {
            color:#65e3a5;
        }
        .cop-user-cert-metric-attention {
            border-left-color:#f7b84b;
        }
        .cop-user-cert-metric-attention strong {
            color:#ffc966;
        }
        .cop-user-cert-metric-bad {
            border-left-color:#ff4d5f;
        }
        .cop-user-cert-metric-bad strong {
            color:#ff6b79;
        }

        .cop-user-reading-summary {
            margin:.25rem 0 .9rem;
            padding:1.05rem 1.2rem;
            border:1px solid rgba(148,163,184,.15);
            border-left:4px solid #64748b;
            border-radius:16px;
            background:linear-gradient(135deg, rgba(14,31,50,.92), rgba(9,22,37,.98));
            color:#dce7f2;
            font-size:.82rem;
            line-height:1.55;
            text-align:center;
        }
        .cop-user-reading-card {
            min-height:150px;
            padding:1.05rem 1.1rem;
            border:1px solid rgba(148,163,184,.15);
            border-left:4px solid #64748b;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.91), rgba(8,21,36,.98));
            box-shadow:0 14px 30px rgba(0,0,0,.12);
            text-align:center;
        }
        .cop-user-reading-card > div {
            font-size:.67rem;
            font-weight:900;
            letter-spacing:.075em;
        }
        .cop-user-reading-card p {
            margin:.75rem 0 0;
            color:#c7d4e2;
            font-size:.77rem;
            line-height:1.55;
        }
        .cop-user-reading-good {
            border-left-color:#31d58a;
        }
        .cop-user-reading-good > div {
            color:#65e3a5;
        }
        .cop-user-reading-attention {
            border-left-color:#f7b84b;
        }
        .cop-user-reading-attention > div {
            color:#ffc966;
        }
        .cop-user-reading-suggestion {
            border-left-color:#38bdf8;
        }
        .cop-user-reading-suggestion > div {
            color:#7dd3fc;
        }

        .cop-validation-kpi {
            min-height:116px;
            padding:1rem 1.05rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #64748b;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.92), rgba(8,21,36,.98));
            box-shadow:0 14px 30px rgba(0,0,0,.13);
        }
        .cop-validation-kpi span {
            display:block;
            color:#8fa0b6;
            font-size:.66rem;
            font-weight:900;
            letter-spacing:.075em;
            text-transform:uppercase;
        }
        .cop-validation-kpi strong {
            display:block;
            margin-top:.68rem;
            color:#f7fbff;
            font-size:1.72rem;
            line-height:1;
            font-weight:900;
            letter-spacing:-.035em;
        }
        .cop-validation-good {
            border-top-color:#31d58a;
        }
        .cop-validation-good strong {
            color:#65e3a5;
        }
        .cop-validation-bad {
            border-top-color:#ff4d5f;
        }
        .cop-validation-bad strong {
            color:#ff6b79;
        }
        .cop-validation-attention,
        .cop-validation-warning {
            border-top-color:#f7b84b;
        }
        .cop-validation-attention strong,
        .cop-validation-warning strong {
            color:#ffc966;
        }
        .cop-validation-team {
            border-top-color:#38bdf8;
        }
        .cop-validation-team strong {
            color:#7dd3fc;
        }
        .cop-validation-target {
            border-top-color:#a78bfa;
        }
        .cop-validation-target strong {
            color:#c4b5fd;
        }

        .cop-cancel-user-kpi {
            min-height:118px;
            padding:1rem 1.05rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #64748b;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.92), rgba(8,21,36,.98));
            box-shadow:0 14px 30px rgba(0,0,0,.13);
        }
        .cop-cancel-user-kpi span {
            display:block;
            color:#8fa0b6;
            font-size:.67rem;
            font-weight:900;
            letter-spacing:.075em;
            text-transform:uppercase;
        }
        .cop-cancel-user-kpi strong {
            display:block;
            margin-top:.72rem;
            color:#f7fbff;
            font-size:1.8rem;
            line-height:1;
            font-weight:900;
            letter-spacing:-.035em;
        }
        .cop-cancel-user-good {
            border-top-color:#31d58a;
        }
        .cop-cancel-user-good strong {
            color:#65e3a5;
        }
        .cop-cancel-user-attention {
            border-top-color:#f7b84b;
        }
        .cop-cancel-user-attention strong {
            color:#ffc966;
        }
        .cop-cancel-user-bad {
            border-top-color:#ff4d5f;
        }
        .cop-cancel-user-bad strong {
            color:#ff6b79;
        }
        .cop-cancel-user-team {
            border-top-color:#38bdf8;
        }
        .cop-cancel-user-team strong {
            color:#7dd3fc;
        }
        .cop-cancel-user-target {
            border-top-color:#a78bfa;
        }
        .cop-cancel-user-target strong {
            color:#c4b5fd;
        }

        .cop-productivity-kpi {
            min-height:132px;
            padding:1.05rem 1.1rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #38bdf8;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.92), rgba(8,21,36,.98));
            box-shadow:0 14px 30px rgba(0,0,0,.13);
        }
        .cop-productivity-kpi-head {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:.8rem;
        }
        .cop-productivity-kpi-head span {
            color:#8fa0b6;
            font-size:.67rem;
            font-weight:900;
            letter-spacing:.08em;
        }
        .cop-productivity-kpi-head b {
            font-size:1rem;
        }
        .cop-productivity-kpi > strong {
            display:block;
            margin-top:.72rem;
            color:#f7fbff;
            font-size:1.75rem;
            line-height:1;
            font-weight:900;
            letter-spacing:-.035em;
        }
        .cop-productivity-kpi p {
            margin:.58rem 0 0;
            color:#8fa0b6;
            font-size:.72rem;
            line-height:1.4;
        }
        .cop-productivity-reading {
            margin:1rem 0 1.4rem;
            padding:.95rem 1.05rem;
            border:1px solid rgba(148,163,184,.14);
            border-left:4px solid #64748b;
            border-radius:14px;
            background:linear-gradient(135deg, rgba(14,31,50,.90), rgba(9,22,37,.96));
        }
        .cop-productivity-reading-good {
            border-left-color:#31d58a;
        }
        .cop-productivity-reading-attention {
            border-left-color:#f7b84b;
        }
        .cop-productivity-reading-title {
            color:#f4f8fc;
            font-size:.76rem;
            font-weight:850;
        }
        .cop-productivity-reading-text {
            margin-top:.38rem;
            color:#a4b3c4;
            font-size:.77rem;
            line-height:1.5;
        }
        .cop-productivity-chart {
            margin:.35rem 0 1.25rem;
            padding:1rem 1.05rem .8rem;
            border:1px solid rgba(148,163,184,.15);
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.90), rgba(8,21,36,.97));
            box-shadow:0 14px 30px rgba(0,0,0,.12);
        }
        .cop-productivity-chart-scale {
            display:flex;
            justify-content:space-between;
            gap:1rem;
            margin-bottom:.65rem;
            color:#6f8196;
            font-size:.65rem;
        }
        .cop-productivity-chart-row {
            display:grid;
            grid-template-columns:72px minmax(0,1fr);
            gap:.8rem;
            align-items:center;
            padding:.72rem 0;
            border-top:1px solid rgba(148,163,184,.08);
        }
        .cop-productivity-chart-row:first-of-type {
            border-top:0;
        }
        .cop-productivity-chart-date {
            color:#dbe7f3;
            font-size:.78rem;
            font-weight:850;
        }
        .cop-productivity-chart-bars {
            display:grid;
            gap:.42rem;
        }
        .cop-productivity-chart-line {
            display:grid;
            grid-template-columns:84px minmax(0,1fr) 56px;
            gap:.6rem;
            align-items:center;
        }
        .cop-productivity-chart-series {
            color:#8395aa;
            font-size:.64rem;
            font-weight:750;
        }
        .cop-productivity-chart-line strong {
            color:#f4f8fc;
            font-size:.72rem;
            text-align:right;
        }
        .cop-productivity-chart-track {
            position:relative;
            height:10px;
            overflow:hidden;
            border-radius:999px;
            background:rgba(148,163,184,.10);
        }
        .cop-productivity-chart-bar {
            height:100%;
            border-radius:inherit;
            transform:scaleX(0);
            transform-origin:left center;
            animation:copProductivityBarGrow .78s cubic-bezier(.2,.75,.25,1) forwards;
        }
        .cop-productivity-chart-mine {
            background:linear-gradient(90deg, #38bdf8, #60a5fa);
        }
        .cop-productivity-chart-team {
            background:linear-gradient(90deg, #31d58a, #6ee7b7);
        }
        @keyframes copProductivityBarGrow {
            from { transform:scaleX(0); opacity:.35; }
            to { transform:scaleX(1); opacity:1; }
        }
        @media (prefers-reduced-motion: reduce) {
            .cop-productivity-chart-bar {
                animation:none;
                transform:scaleX(1);
            }
        }

        .cop-etit-chart {
            margin:.35rem 0 1.25rem;
            padding:1rem 1.05rem .8rem;
            border:1px solid rgba(148,163,184,.15);
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.90), rgba(8,21,36,.97));
            box-shadow:0 14px 30px rgba(0,0,0,.12);
        }
        .cop-etit-chart-scale {
            display:flex;
            justify-content:space-between;
            gap:1rem;
            margin-bottom:.65rem;
            color:#6f8196;
            font-size:.65rem;
        }
        .cop-etit-chart-row {
            display:grid;
            grid-template-columns:72px minmax(0,1fr);
            gap:.8rem;
            align-items:center;
            padding:.72rem 0;
            border-top:1px solid rgba(148,163,184,.08);
        }
        .cop-etit-chart-row:first-of-type {
            border-top:0;
        }
        .cop-etit-chart-date {
            color:#dbe7f3;
            font-size:.78rem;
            font-weight:850;
        }
        .cop-etit-chart-bars {
            display:grid;
            gap:.42rem;
        }
        .cop-etit-chart-line {
            display:grid;
            grid-template-columns:78px minmax(0,1fr) 56px;
            gap:.6rem;
            align-items:center;
        }
        .cop-etit-chart-series {
            color:#8395aa;
            font-size:.64rem;
            font-weight:750;
        }
        .cop-etit-chart-line strong {
            color:#f4f8fc;
            font-size:.72rem;
            text-align:right;
        }
        .cop-etit-chart-track {
            position:relative;
            height:10px;
            overflow:hidden;
            border-radius:999px;
            background:rgba(148,163,184,.10);
        }
        .cop-etit-chart-bar {
            height:100%;
            border-radius:inherit;
            transform:scaleX(0);
            transform-origin:left center;
            animation:copEtitBarGrow .78s cubic-bezier(.2,.75,.25,1) forwards;
        }
        .cop-etit-chart-mine {
            background:linear-gradient(90deg, #f97316, #fb923c);
        }
        .cop-etit-chart-team {
            background:linear-gradient(90deg, #38bdf8, #60a5fa);
        }
        @keyframes copEtitBarGrow {
            from { transform:scaleX(0); opacity:.35; }
            to { transform:scaleX(1); opacity:1; }
        }
        @media (prefers-reduced-motion: reduce) {
            .cop-etit-chart-bar {
                animation:none;
                transform:scaleX(1);
            }
        }

        .cop-dpa-chart {
            margin-top:.4rem;
            padding:1rem 1.05rem .8rem;
            border:1px solid rgba(148,163,184,.15);
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.90), rgba(8,21,36,.97));
            box-shadow:0 14px 30px rgba(0,0,0,.12);
        }
        .cop-dpa-chart-scale {
            display:flex;
            justify-content:space-between;
            gap:1rem;
            margin-bottom:.65rem;
            color:#6f8196;
            font-size:.65rem;
        }
        .cop-dpa-chart-row {
            display:grid;
            grid-template-columns:72px minmax(0,1fr);
            gap:.8rem;
            align-items:center;
            padding:.72rem 0;
            border-top:1px solid rgba(148,163,184,.08);
        }
        .cop-dpa-chart-row:first-of-type {
            border-top:0;
        }
        .cop-dpa-chart-date {
            color:#dbe7f3;
            font-size:.78rem;
            font-weight:850;
        }
        .cop-dpa-chart-bars {
            display:grid;
            gap:.42rem;
        }
        .cop-dpa-chart-line {
            display:grid;
            grid-template-columns:72px minmax(0,1fr) 56px;
            gap:.6rem;
            align-items:center;
        }
        .cop-dpa-chart-series {
            color:#8395aa;
            font-size:.64rem;
            font-weight:750;
        }
        .cop-dpa-chart-line strong {
            color:#f4f8fc;
            font-size:.72rem;
            text-align:right;
        }
        .cop-dpa-chart-track {
            position:relative;
            height:10px;
            overflow:hidden;
            border-radius:999px;
            background:rgba(148,163,184,.10);
        }
        .cop-dpa-chart-bar {
            height:100%;
            border-radius:inherit;
            transform:scaleX(0);
            transform-origin:left center;
            animation:copDpaBarGrow .78s cubic-bezier(.2,.75,.25,1) forwards;
        }
        .cop-dpa-chart-mine {
            background:linear-gradient(90deg, #38bdf8, #60a5fa);
        }
        .cop-dpa-chart-team {
            background:linear-gradient(90deg, #31d58a, #6ee7b7);
        }
        @keyframes copDpaBarGrow {
            from { transform:scaleX(0); opacity:.35; }
            to { transform:scaleX(1); opacity:1; }
        }
        @media (prefers-reduced-motion: reduce) {
            .cop-dpa-chart-bar {
                animation:none;
                transform:scaleX(1);
            }
        }

        .cop-assert-kpi {
            min-height:112px;
            padding:1rem 1.05rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #64748b;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.90), rgba(8,21,36,.97));
            box-shadow:0 14px 30px rgba(0,0,0,.13);
            text-align:center;
        }
        .cop-assert-kpi span {
            display:block;
            color:#8294aa;
            font-size:.66rem;
            font-weight:850;
            letter-spacing:.07em;
            text-transform:uppercase;
        }
        .cop-assert-kpi strong {
            display:block;
            margin-top:.6rem;
            color:#f7fbff;
            font-size:1.72rem;
            line-height:1;
            font-weight:900;
            letter-spacing:-.035em;
        }
        .cop-assert-good {
            border-top-color:#31d58a;
        }
        .cop-assert-good strong {
            color:#65e3a5;
        }
        .cop-assert-bad {
            border-top-color:#ff4d5f;
        }
        .cop-assert-bad strong {
            color:#ff6b79;
        }
        .cop-assert-warning {
            border-top-color:#f7b84b;
        }
        .cop-assert-warning strong {
            color:#ffc966;
        }
        .cop-assert-team {
            border-top-color:#38bdf8;
        }
        .cop-assert-team strong {
            color:#7dd3fc;
        }

        .cop-etit-user-kpi {
            min-height:112px;
            padding:1rem 1.05rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #38bdf8;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.90), rgba(8,21,36,.97));
            box-shadow:0 14px 30px rgba(0,0,0,.13);
        }
        .cop-etit-user-kpi span,
        .cop-etit-team-card span {
            display:block;
            color:#8294aa;
            font-size:.66rem;
            font-weight:850;
            letter-spacing:.07em;
            text-transform:uppercase;
        }
        .cop-etit-user-kpi strong {
            display:block;
            margin-top:.6rem;
            color:#f7fbff;
            font-size:1.7rem;
            line-height:1;
            font-weight:900;
            letter-spacing:-.035em;
        }
        .cop-etit-team-card {
            min-height:118px;
            padding:1rem 1.05rem;
            margin-bottom:.65rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #64748b;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.90), rgba(8,21,36,.97));
        }
        .cop-etit-team-card strong {
            display:block;
            margin-top:.62rem;
            color:#f5f9fd;
            font-size:1.75rem;
            line-height:1;
            font-weight:900;
            letter-spacing:-.035em;
        }
        .cop-etit-team-good {
            border-top-color:#31d58a;
        }
        .cop-etit-team-good strong {
            color:#65e3a5;
        }
        .cop-etit-team-attention {
            border-top-color:#f7b84b;
        }
        .cop-etit-team-attention strong {
            color:#ffc966;
        }

        /* ETIT Empresarial: leitura individual separada para RAL e REC */
        .cop-etit-demand-panel {
            min-height:388px;
            padding:1.15rem;
            margin-bottom:.9rem;
            border:1px solid rgba(148,163,184,.20);
            border-top:3px solid #38bdf8;
            border-radius:18px;
            background:linear-gradient(145deg, rgba(16,38,61,.96), rgba(7,19,33,.98));
            box-shadow:0 18px 35px rgba(0,0,0,.16);
        }
        .cop-etit-demand-rec { border-top-color:#a78bfa; }
        .cop-etit-demand-panel header {
            display:flex;
            justify-content:space-between;
            align-items:center;
            border-bottom:1px solid rgba(148,163,184,.13);
            padding-bottom:.7rem;
            margin-bottom:.85rem;
        }
        .cop-etit-demand-panel header span {
            font-size:.64rem;
            color:#9bacc0;
            font-weight:800;
            letter-spacing:.11em;
        }
        .cop-etit-demand-panel header strong {
            font-size:1.1rem;
            letter-spacing:.04em;
            color:#f4f8ff;
        }
        .cop-etit-demand-result {
            display:flex;
            align-items:end;
            justify-content:space-between;
            gap:.7rem;
            padding-bottom:1rem;
        }
        .cop-etit-demand-result div span,
        .cop-etit-demand-tile span {
            display:block;
            font-size:.7rem;
            color:#a8bbcf;
            margin-bottom:.25rem;
        }
        .cop-etit-demand-result div strong {
            display:block;
            color:#f9fbff;
            font-size:2.25rem;
            line-height:1.05;
            font-weight:900;
            letter-spacing:-.04em;
        }
        .cop-etit-demand-comparison {
            font-size:.72rem;
            font-weight:800;
            font-style:normal;
            border-radius:999px;
            padding:.4rem .65rem;
            white-space:nowrap;
            background:rgba(148,163,184,.15);
            color:#d6e0ea;
        }
        .cop-etit-demand-good { color:#6ee7b7; background:rgba(49,213,138,.11); }
        .cop-etit-demand-attention { color:#ffd179; background:rgba(247,184,75,.12); }
        .cop-etit-demand-grid {
            display:grid;
            grid-template-columns:repeat(3,minmax(0,1fr));
            gap:.55rem;
        }
        .cop-etit-demand-tile {
            border:1px solid rgba(148,163,184,.14);
            border-radius:12px;
            background:rgba(7,17,31,.63);
            min-width:0;
            padding:.7rem .6rem;
        }
        .cop-etit-demand-tile strong {
            color:#f5f8fd;
            font-weight:850;
            font-size:1.02rem;
            line-height:1.2;
            overflow-wrap:anywhere;
        }
        .cop-etit-demand-panel footer {
            margin-top:.75rem;
            padding-top:.7rem;
            border-top:1px solid rgba(148,163,184,.13);
            font-size:.71rem;
            color:#b6c6d8;
        }
        .cop-etit-demand-panel footer strong { color:#f7fbff; }
        .cop-etit-demand-empty {
            margin:1rem 0;
            color:#b6c6d8;
            font-size:.82rem;
        }
        @media (max-width: 1200px) {
            .cop-etit-demand-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .cop-etit-demand-result { align-items:start; flex-direction:column; }
        }

        .cop-personal-kpi {
            min-height:130px;
            padding:1rem 1.05rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #38bdf8;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.88), rgba(9,22,37,.96));
            box-shadow:0 14px 32px rgba(0,0,0,.14);
        }
        .cop-personal-kpi-good { border-top-color:#31d58a; }
        .cop-personal-kpi-attention { border-top-color:#f7b84b; }
        .cop-personal-kpi-label {
            color:#8fa0b6;
            font-size:.68rem;
            font-weight:850;
            letter-spacing:.08em;
            text-transform:uppercase;
        }
        .cop-personal-kpi-value {
            margin-top:.55rem;
            color:#f7fbff;
            font-size:1.8rem;
            line-height:1;
            font-weight:900;
            letter-spacing:-.04em;
        }
        .cop-personal-kpi-context {
            margin-top:.55rem;
            color:#8294aa;
            font-size:.72rem;
            line-height:1.35;
        }

        .cop-personal-executive {
            margin:1.15rem 0 1.35rem;
            padding:1rem 1.15rem;
            border:1px solid rgba(148,163,184,.14);
            border-left:4px solid #64748b;
            border-radius:14px;
            background:linear-gradient(135deg, rgba(14,31,50,.90), rgba(9,22,37,.96));
        }
        .cop-personal-executive-good { border-left-color:#31d58a; }
        .cop-personal-executive-attention { border-left-color:#f7b84b; }
        .cop-personal-executive-label {
            color:#7dd3fc;
            font-size:.64rem;
            font-weight:850;
            letter-spacing:.10em;
        }
        .cop-personal-executive-title {
            margin-top:.32rem;
            color:#f8fbff;
            font-size:1rem;
            font-weight:850;
        }
        .cop-personal-executive-text {
            margin-top:.28rem;
            color:#9aacbf;
            font-size:.78rem;
            line-height:1.45;
        }

        .cop-personal-insight {
            min-height:122px;
            padding:1rem 1.1rem;
            border:1px solid rgba(148,163,184,.14);
            border-left:4px solid;
            border-radius:15px;
            background:rgba(12,28,46,.84);
        }
        .cop-personal-insight-good { border-left-color:#31d58a; }
        .cop-personal-insight-attention { border-left-color:#f7b84b; }
        .cop-personal-insight-label {
            color:#8294aa;
            font-size:.66rem;
            font-weight:850;
            letter-spacing:.08em;
            text-transform:uppercase;
        }
        .cop-personal-insight-title {
            margin-top:.35rem;
            color:#f6fbff;
            font-size:1rem;
            font-weight:850;
        }
        .cop-personal-insight-text {
            margin-top:.4rem;
            color:#a8b7c8;
            font-size:.78rem;
            line-height:1.45;
        }

        .cop-personal-status-card {
            min-height:230px;
            margin-bottom:12px;
            padding:1rem 1.05rem;
            border:1px solid rgba(148,163,184,.15);
            border-top:3px solid #64748b;
            border-radius:16px;
            background:linear-gradient(180deg, rgba(16,38,61,.90), rgba(8,21,36,.97));
            box-shadow:0 14px 30px rgba(0,0,0,.13);
        }
        .cop-status-good { border-top-color:#31d58a; }
        .cop-status-attention { border-top-color:#f7b84b; }
        .cop-personal-status-head {
            min-height:44px;
            display:flex;
            justify-content:space-between;
            gap:.65rem;
            align-items:flex-start;
            color:#dce8f4;
            font-size:.76rem;
            font-weight:800;
            line-height:1.35;
        }
        .cop-personal-status-title {
            display:flex;
            align-items:flex-start;
            gap:.55rem;
            min-width:0;
        }
        .cop-personal-status-title strong {
            color:#eaf2fa;
            font-size:.78rem;
            line-height:1.35;
        }
        .cop-personal-status-icon {
            flex:0 0 auto;
            font-size:1rem;
            line-height:1.1;
        }
        .cop-personal-status-pill {
            flex:0 0 auto;
            padding:.26rem .52rem;
            border-radius:999px;
            color:#cbd7e4;
            background:rgba(148,163,184,.10);
            border:1px solid rgba(148,163,184,.15);
            font-size:.60rem;
            font-weight:800;
        }
        .cop-status-good .cop-personal-status-pill {
            color:#8af0bd;
            background:rgba(49,213,138,.09);
            border-color:rgba(49,213,138,.20);
        }
        .cop-status-attention .cop-personal-status-pill {
            color:#ffd183;
            background:rgba(247,184,75,.09);
            border-color:rgba(247,184,75,.22);
        }
        .cop-personal-status-value {
            margin-top:.45rem;
            color:#fff;
            font-size:1.85rem;
            font-weight:900;
            letter-spacing:-.045em;
        }
        .cop-personal-status-grid {
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:.55rem;
            margin-top:.8rem;
        }
        .cop-personal-status-grid > div {
            padding:.6rem .65rem;
            border-radius:10px;
            background:rgba(255,255,255,.035);
            border:1px solid rgba(148,163,184,.10);
        }
        .cop-personal-status-grid small {
            display:block;
            color:#73859a;
            font-size:.60rem;
            text-transform:uppercase;
            letter-spacing:.06em;
        }
        .cop-personal-status-grid strong {
            display:block;
            margin-top:.22rem;
            color:#dfe9f4;
            font-size:.75rem;
        }
        .cop-personal-status-footer {
            display:flex;
            justify-content:space-between;
            gap:.5rem;
            flex-wrap:wrap;
            margin-top:.75rem;
            padding-top:.65rem;
            border-top:1px solid rgba(148,163,184,.10);
            color:#8294aa;
            font-size:.67rem;
        }
        .cop-personal-status-footer b { color:#b9c8d7; }

        @media (max-width: 900px) {
            .cop-analyst-identity {
                min-height:auto;
                padding:1.35rem;
                display:block;
            }
            .cop-analyst-private {
                margin-top:1rem;
                width:max-content;
            }
            .cop-analyst-identity h1 {
                font-size:2.25rem !important;
            }
            .cop-analyst-identity p {
                font-size:.96rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _latest_by_indicator(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("indicator_key"))
        if key not in latest or str(row.get("period")) > str(latest[key].get("period")):
            latest[key] = row
    return sorted(latest.values(), key=lambda row: str(row.get("name") or ""))


def _latest_indicator_rows(rows: list[dict], indicator_key: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows or [])
    if frame.empty or "indicator_key" not in frame.columns:
        return pd.DataFrame()
    frame = frame[frame["indicator_key"].astype(str) == indicator_key].copy()
    if frame.empty:
        return frame
    if "period" in frame.columns:
        latest_period = frame["period"].dropna().astype(str).max()
        frame = frame[frame["period"].astype(str) == latest_period].copy()
    return frame


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None or frame.empty or "dimension" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["dimension"].astype(str) == dimension].copy()


def _detail_value(row: pd.Series, indicator_key: str) -> float | None:
    if indicator_key == "toa_cancellation_rate":
        volume = _number(row.get("volume"))
        losses = _number(row.get("losses"))
        if volume is None or volume <= 0 or losses is None:
            return None
        return losses / volume * 100
    return _number(row.get("value"))


def _team_value(
    team_details: pd.DataFrame,
    dimension: str,
    value: str,
    indicator_key: str | None = None,
) -> float | None:
    rows = _dimension_rows(team_details, dimension)
    if rows.empty or "dimension_value" not in rows.columns:
        return None
    rows = rows[rows["dimension_value"].astype(str) == str(value)]
    if rows.empty:
        return None
    if indicator_key == "toa_cancellation_rate":
        volumes = pd.to_numeric(rows["team_volume"], errors="coerce").fillna(0)
        losses = pd.to_numeric(rows["team_losses"], errors="coerce").fillna(0)
        total_volume = float(volumes.sum())
        return None if total_volume <= 0 else float(losses.sum()) / total_volume * 100
    return _weighted_team_avg(rows)


def _weighted_team_avg(rows: pd.DataFrame) -> float | None:
    if rows is None or rows.empty:
        return None
    if "team_avg" not in rows.columns:
        return None
    values = pd.to_numeric(rows["team_avg"], errors="coerce")
    weights = pd.to_numeric(rows.get("team_volume"), errors="coerce").fillna(0)
    valid = values.notna() & weights.gt(0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _target_metric(row: dict | pd.Series) -> str:
    target = row.get("target_value")
    if target is None or pd.isna(target):
        return "—"
    return _format_ptbr_metric(float(target), row.get("unit"))


def _target_text(row: dict | pd.Series) -> str:
    target = row.get("target_value")
    direction = row.get("direction")
    unit = row.get("unit")
    return format_target(None if target is None or pd.isna(target) else target, unit, direction).replace(".", ",")


def _comparison_label(
    value: float | None,
    team_avg: float | None,
    direction: str,
    unit: str | None,
) -> str:
    if value is None or team_avg is None:
        return "—"
    delta = value - team_avg
    if abs(delta) < 0.05:
        return "Na média"

    favorable = delta > 0 if direction != "lower_is_better" else delta < 0
    label = "melhor" if favorable else "pior"
    if (unit or "percent").lower() == "percent":
        amount = f"{abs(delta):.1f}".replace(".", ",")
        return f"{amount} pp {label}"
    amount = f"{abs(delta):.1f}".replace(".", ",")
    return f"{amount} {label}"


def _format_ptbr_metric(value: float | None, unit: str | None) -> str:
    if value is None:
        return "—"
    formatted = format_metric(value, unit)
    if (unit or "percent").lower() == "percent":
        return formatted.replace(".", ",")
    return formatted


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%".replace(".", ",")


def _number(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_date(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value or "")
    return parsed.strftime("%d/%m/%Y")
