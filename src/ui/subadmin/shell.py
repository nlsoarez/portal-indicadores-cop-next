from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.infrastructure.repositories import IndicatorRepository, UserRepository
from src.ui.shared.freshness import freshness_table_rows, render_indicator_freshness
from src.ui.shared.person_performance import render_person_performance


class SubadminShell:
    def __init__(self):
        self.access = AccessService()
        self.dashboard = DashboardService(access=self.access)
        self.users = UserRepository()
        self.indicators = IndicatorRepository()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        st.sidebar.markdown("<span class='cop-role-subadmin'>SUBADMIN</span>", unsafe_allow_html=True)
        st.sidebar.markdown(f"### {ctx.user.display_name}")
        segment = st.sidebar.selectbox(
            "Segmento", segments, format_func=lambda item: item.name, key="subadmin_segment_selector"
        )
        switch_segment_state(st.session_state, segment.id)
        page = st.sidebar.radio(
            "Navegação", ["Visão geral", "Analistas", "Indicadores"], label_visibility="collapsed"
        )

        st.markdown("<div class='cop-eyebrow'>Visão de liderança</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='cop-title'>{segment.name}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='cop-subtitle'>Consulta gerencial dos analistas. Uploads são exclusivos do Admin.</div>",
            unsafe_allow_html=True,
        )

        analysts = self.access.visible_users(ctx, segment.id)
        freshness = self.indicators.freshness(segment.id)

        if page == "Visão geral":
            c1, c2 = st.columns(2)
            c1.metric("Analistas", len(analysts))
            c2.metric("Indicadores configurados", len(self.indicators.definitions(segment.id)))
            render_indicator_freshness(freshness)
            st.subheader("Último acesso dos analistas")
            st.dataframe(
                pd.DataFrame(self.users.last_access_for_segment(segment.id)),
                use_container_width=True,
                hide_index=True,
            )
        elif page == "Analistas":
            if not analysts:
                st.info("Nenhum analista cadastrado neste segmento.")
                return
            target = st.selectbox(
                "Analista",
                analysts,
                format_func=lambda user: f"{user.display_name} · {user.login}",
                key=f"subadmin_analyst:{segment.id}",
            )
            render_person_performance(ctx, segment.id, target, self.dashboard)
        else:
            definitions = self.indicators.definitions(segment.id)
            if definitions:
                st.dataframe(pd.DataFrame(definitions), use_container_width=True, hide_index=True)
                st.markdown("#### Cobertura atual dos dados")
                st.dataframe(
                    pd.DataFrame(freshness_table_rows(freshness)),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Nenhum indicador configurado para este segmento.")
