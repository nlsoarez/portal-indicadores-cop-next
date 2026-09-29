from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.features.analytics.tips import build_tips
from src.ui.shared.freshness import render_indicator_freshness
from src.ui.shared.metrics import format_delta, format_metric, format_target


class AnalystShell:
    def __init__(self):
        self.dashboard = DashboardService()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        st.sidebar.markdown("<span class='cop-role-analyst'>ANALISTA</span>", unsafe_allow_html=True)
        st.sidebar.markdown(f"### {ctx.user.display_name}")
        segment = st.sidebar.selectbox(
            "Meu segmento", segments, format_func=lambda item: item.name, key="analyst_segment_selector"
        )
        switch_segment_state(st.session_state, segment.id)
        page = st.sidebar.radio(
            "Navegação", ["Meu desempenho", "Minha evolução", "Histórico"], label_visibility="collapsed"
        )

        st.markdown("<div class='cop-eyebrow'>Desempenho individual</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='cop-title'>Olá, {ctx.user.display_name}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='cop-subtitle'>Como estou performando e o que posso melhorar?</div>",
            unsafe_allow_html=True,
        )

        payload = self.dashboard.analyst_payload(ctx, segment.id)
        render_indicator_freshness(payload["freshness"])

        if page == "Meu desempenho":
            self._render_performance(payload)
        elif page == "Minha evolução":
            if payload["individual"]:
                st.dataframe(pd.DataFrame(payload["individual"]), use_container_width=True, hide_index=True)
            else:
                st.info("Ainda não há evolução disponível para este segmento.")
        else:
            if payload["summary"]:
                st.dataframe(pd.DataFrame(payload["summary"]), use_container_width=True, hide_index=True)
            else:
                st.info("Ainda não há histórico mensal processado.")

    def _render_performance(self, payload: dict) -> None:
        latest = _latest_by_indicator(payload["summary"])
        team_index = {
            (row["period"], row["indicator_key"]): row
            for row in payload["team_averages"]
        }

        if not latest:
            st.info("Ainda não há resultados individuais processados para este segmento.")
        else:
            cols = st.columns(min(3, len(latest)))
            for index, row in enumerate(latest):
                team = team_index.get((row["period"], row["indicator_key"]), {})
                value = float(row.get("value") or 0)
                unit = row.get("unit")
                team_avg = team.get("team_avg")
                delta = None if team_avg is None else format_delta(value - float(team_avg), unit)
                with cols[index % len(cols)]:
                    st.metric(row["name"], format_metric(value, unit), delta=delta)
                    target_label = format_target(row.get("target_value"), unit, row.get("direction"))
                    st.caption(f"{target_label} · Base {int(row.get('volume') or 0)} · {row['period']}")

        st.subheader("Dicas baseadas nos seus dados")
        for tip in build_tips(latest, payload["team_averages"]):
            st.markdown(f"<div class='cop-tip'>{tip}</div>", unsafe_allow_html=True)


def _latest_by_indicator(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row["indicator_key"])
        if key not in latest or str(row["period"]) > str(latest[key]["period"]):
            latest[key] = row
    return sorted(latest.values(), key=lambda row: str(row["name"]))
