from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.features.analytics.tips import build_tips


class AnalystShell:
    def __init__(self):
        self.dashboard = DashboardService()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        st.sidebar.markdown("<span class='cop-role-analyst'>ANALISTA</span>", unsafe_allow_html=True)
        st.sidebar.markdown(f"### {ctx.user.display_name}")
        segment = st.sidebar.selectbox(
            "Meu segmento",
            segments,
            format_func=lambda item: item.name,
            key="analyst_segment_selector",
        )
        switch_segment_state(st.session_state, segment.id)
        page = st.sidebar.radio(
            "Navegação",
            ["Meu desempenho", "Minha evolução", "Minha escala", "Histórico"],
            label_visibility="collapsed",
        )

        st.markdown("<div class='cop-eyebrow'>Desempenho individual</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='cop-title'>Olá, {ctx.user.display_name}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='cop-subtitle'>Como estou performando e o que posso melhorar?</div>",
            unsafe_allow_html=True,
        )

        payload = self.dashboard.analyst_payload(ctx, segment.id)
        if page == "Meu desempenho":
            if payload["individual"]:
                st.dataframe(pd.DataFrame(payload["individual"]), use_container_width=True, hide_index=True)
            else:
                st.info("Ainda não há resultados individuais processados para este segmento.")
            st.subheader("Dicas baseadas nos seus dados")
            for tip in build_tips(payload["individual"], payload["team_averages"]):
                st.markdown(f"<div class='cop-tip'>{tip}</div>", unsafe_allow_html=True)
        elif page == "Minha evolução":
            st.dataframe(pd.DataFrame(payload["individual"]), use_container_width=True, hide_index=True)
        elif page == "Minha escala":
            if payload["scale"]:
                st.dataframe(pd.DataFrame(payload["scale"]), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma escala importada para você neste segmento.")
        else:
            st.dataframe(pd.DataFrame(payload["individual"]), use_container_width=True, hide_index=True)
