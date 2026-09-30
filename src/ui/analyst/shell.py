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
    "chat_10m": "💬 Chat",
    "dpa_official": "⏱️ DPA",
    "res_etit_fibra_hfc": "⚡ ETIT HFC",
    "res_etit_gpon": "🔎 ETIT GPON",
    "emp_etit_event": "⚡ ETIT Evento",
    "productivity_avg_daily": "📦 Produtividade",
    "validacao_20m": "✅ Validação",
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
        else:
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

        details = _latest_indicator_rows(payload.get("breakdowns") or [], indicator_key)
        team_details = _latest_indicator_rows(payload.get("team_breakdowns") or [], indicator_key)

        # Chat TOA: visão intencionalmente enxuta. Os cinco cards acima são
        # suficientes para a leitura operacional do analista; removemos
        # tabelas, diagnósticos, perdas e evolução para evitar ruído.
        if indicator_key == "chat_10m":
            return

        if indicator_key == "closing_assertiveness":
            self._render_closing_assertiveness(payload, details, team_details)
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

        if indicator_key == "dpa_official":
            self._render_dpa_recent_chart(payload)
            return

        self._render_focus(details, team_details, indicator_key, direction)
        self._render_loss_references(details, indicator_key)
        self._render_full_detail(details, team_details, indicator_key, direction)
        self._render_recent_evolution(payload, indicator_key, unit)

    def _render_dpa_recent_chart(self, payload: dict) -> None:
        rows = _dpa_recent_chart_rows(payload)
        st.markdown("#### Últimos dias")
        st.caption(
            "DPA diário do analista comparado à média diária da equipe. "
            "As barras são exibidas em ordem cronológica."
        )

        if not rows:
            st.caption("Sem histórico diário suficiente para exibir o gráfico.")
            return

        scale = _dpa_chart_scale(rows)
        items = []
        for index, row in enumerate(rows):
            my_value = _number(row.get("value"))
            team_value = _number(row.get("team_avg"))
            my_width = 0.0 if my_value is None else min(max(my_value / scale * 100, 0), 100)
            team_width = (
                0.0
                if team_value is None
                else min(max(team_value / scale * 100, 0), 100)
            )
            delay = index * 0.06

            items.append(
                (
                    "<div class='cop-dpa-chart-row'>"
                    f"<div class='cop-dpa-chart-date'>{escape(str(row['date_label']))}</div>"
                    "<div class='cop-dpa-chart-bars'>"
                    "<div class='cop-dpa-chart-line'>"
                    "<span class='cop-dpa-chart-series'>Meu DPA</span>"
                    "<div class='cop-dpa-chart-track'>"
                    f"<div class='cop-dpa-chart-bar cop-dpa-chart-mine' style='width:{my_width:.2f}%;animation-delay:{delay:.2f}s'></div>"
                    "</div>"
                    f"<strong>{escape(_pct(my_value))}</strong>"
                    "</div>"
                    "<div class='cop-dpa-chart-line'>"
                    "<span class='cop-dpa-chart-series'>Equipe</span>"
                    "<div class='cop-dpa-chart-track'>"
                    f"<div class='cop-dpa-chart-bar cop-dpa-chart-team' style='width:{team_width:.2f}%;animation-delay:{delay + .08:.2f}s'></div>"
                    "</div>"
                    f"<strong>{escape(_pct(team_value))}</strong>"
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
        cols = st.columns(4)
        cards = [
            ("Eventos", str(summary["volume"])),
            ("Aderentes", str(summary["successes"])),
            ("TMA médio", _format_duration(summary["tma_seconds"])),
            ("TMR médio", _format_duration(summary["tmr_seconds"])),
        ]
        for column, (label, value) in zip(cols, cards):
            with column:
                _render_etit_kpi(label, value)

        if indicator_key == "emp_etit_event":
            st.markdown("#### Aderentes e não aderentes — RAL e REC")
            team_demand = _etit_team_demand_cards(team_details)
            if team_demand:
                cols = st.columns(len(team_demand))
                for column, item in zip(cols, team_demand):
                    with column:
                        _render_etit_team_card(item)

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
        self._render_recent_evolution(payload, indicator_key, unit)

    def _render_closing_assertiveness(
        self,
        payload: dict,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
    ) -> None:
        if details.empty:
            st.info("Reprocesse a fonte Fechamento TOA x SIR para liberar a análise detalhada.")
            return

        st.markdown("#### Leitura por demanda")
        st.caption(
            "RAL e REC são consolidados no período para evitar repetições por dia ou por ocorrência."
        )
        demand_rows = _closing_demand_summary(details, team_details)
        if demand_rows:
            cols = st.columns(min(2, len(demand_rows)))
            for column, item in zip(cols, demand_rows):
                with column:
                    _render_closing_demand_card(item)
        else:
            st.caption("Não há recorte RAL/REC disponível para este período.")

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
            rows.append({
                "Data": _format_date(item.get("day")),
                "Demanda": demand or "—",
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


def _dpa_recent_chart_rows(payload: dict) -> list[dict]:
    individual = pd.DataFrame(payload.get("individual") or [])
    if individual.empty or "indicator_key" not in individual.columns:
        return []

    mine = individual[individual["indicator_key"] == "dpa_official"].copy()
    if mine.empty:
        return []

    team = pd.DataFrame(payload.get("team_daily") or [])
    if not team.empty and "indicator_key" in team.columns:
        team = team[team["indicator_key"] == "dpa_official"][
            ["period", "team_avg"]
        ].copy()
    else:
        team = pd.DataFrame(columns=["period", "team_avg"])

    mine = mine[["period", "value"]].copy()
    merged = mine.merge(team, on="period", how="left")
    merged["period"] = pd.to_datetime(merged["period"], errors="coerce")
    merged = (
        merged.dropna(subset=["period"])
        .sort_values("period", ascending=False)
        .head(7)
        .sort_values("period", ascending=True)
    )
    if merged.empty:
        return []

    rows: list[dict] = []
    for _, row in merged.iterrows():
        rows.append(
            {
                "date_label": row["period"].strftime("%d/%m"),
                "period": row["period"].date().isoformat(),
                "value": _number(row.get("value")),
                "team_avg": _number(row.get("team_avg")),
            }
        )
    return rows


def _dpa_chart_scale(rows: list[dict]) -> float:
    values = [100.0]
    for row in rows:
        for key in ("value", "team_avg"):
            value = _number(row.get(key))
            if value is not None and value >= 0:
                values.append(value)
    maximum = max(values)
    return float(((int(maximum) + 9) // 10) * 10)


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


def _etit_team_demand_cards(team_details: pd.DataFrame) -> list[dict]:
    demand = _dimension_rows(team_details, "demand")
    if demand.empty:
        return []

    demand = demand.copy()
    demand["dimension_value"] = (
        demand["dimension_value"].astype(str).str.upper().str.strip()
    )
    cards: list[dict] = []
    for demand_name in ("RAL", "REC"):
        part = demand[demand["dimension_value"] == demand_name]
        if part.empty:
            continue

        volume = float(
            pd.to_numeric(part.get("team_volume"), errors="coerce").fillna(0).sum()
        )
        successes = float(
            pd.to_numeric(part.get("team_successes"), errors="coerce").fillna(0).sum()
        )
        losses = float(
            pd.to_numeric(part.get("team_losses"), errors="coerce").fillna(0).sum()
        )
        analysts_series = pd.to_numeric(
            part.get("team_analysts"),
            errors="coerce",
        ).fillna(0)
        analysts = float(analysts_series.max()) if not analysts_series.empty else 0.0

        adherence = None if volume <= 0 else successes / volume * 100
        avg_losses = None if analysts <= 0 else losses / analysts
        cards.extend(
            [
                {
                    "label": f"% {demand_name} Ader. (média equipe)",
                    "value": _pct(adherence),
                    "tone": "good" if adherence is not None and adherence >= 90 else "neutral",
                },
                {
                    "label": f"{demand_name} N. Ader. (média equipe)",
                    "value": "—" if avg_losses is None else f"{avg_losses:.1f}".replace(".", ","),
                    "tone": "attention" if avg_losses is not None and avg_losses > 0 else "neutral",
                },
            ]
        )
    return cards


def _render_etit_team_card(item: dict) -> None:
    tone = str(item.get("tone") or "neutral")
    st.markdown(
        (
            f"<article class='cop-etit-team-card cop-etit-team-{escape(tone)}'>"
            f"<span>{escape(str(item.get('label') or ''))}</span>"
            f"<strong>{escape(str(item.get('value') or '—'))}</strong>"
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
            padding:.3rem;
            margin-bottom:.85rem;
            border:1px solid rgba(148,163,184,.13);
            border-radius:14px;
            background:rgba(8,20,34,.78);
        }
        .stApp:has(.cop-analyst-shell) .stTabs [data-baseweb="tab"] {
            min-height:48px;
            border-radius:11px;
            padding:.68rem 1rem;
            color:#91a2b7;
            font-weight:750;
            white-space:nowrap;
        }
        .stApp:has(.cop-analyst-shell) .stTabs [aria-selected="true"] {
            color:#fff !important;
            border:1px solid rgba(237,28,36,.28);
            border-bottom:1px solid rgba(237,28,36,.28) !important;
            background:linear-gradient(135deg, rgba(237,28,36,.18), rgba(59,130,246,.08));
            box-shadow:inset 3px 0 0 #ed1c24;
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
