from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.infrastructure.repositories import IndicatorRepository, UserRepository


class AdminShell:
    def __init__(self):
        self.access = AccessService()
        self.users = UserRepository()
        self.indicators = IndicatorRepository()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        st.sidebar.markdown("<span class='cop-role-admin'>ADMINISTRADOR</span>", unsafe_allow_html=True)
        st.sidebar.markdown(f"### {ctx.user.display_name}")
        segment = st.sidebar.selectbox(
            "Segmento",
            segments,
            format_func=lambda item: item.name,
            key="admin_segment_selector",
        )
        switch_segment_state(st.session_state, segment.id)
        page = st.sidebar.radio(
            "Navegação",
            ["Visão geral", "Analistas", "Indicadores", "Escala", "Uploads", "Auditoria"],
            label_visibility="collapsed",
        )

        st.markdown("<div class='cop-eyebrow'>Gestão operacional</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='cop-title'>{segment.name}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='cop-subtitle'>Visão gerencial, comparação, anomalias e administração do segmento.</div>",
            unsafe_allow_html=True,
        )

        analysts = self.access.visible_users(ctx, segment.id)
        if page == "Visão geral":
            c1, c2, c3 = st.columns(3)
            c1.metric("Pessoas no segmento", len(analysts))
            c2.metric("Indicadores configurados", len(self.indicators.definitions(segment.id)))
            last_access = self.users.last_access_for_segment(segment.id)
            accessed = sum(1 for row in last_access if row["last_access"])
            c3.metric("Usuários que já acessaram", accessed)
            st.subheader("Acompanhamento da equipe")
            st.dataframe(pd.DataFrame(last_access), use_container_width=True, hide_index=True)
        elif page == "Analistas":
            st.dataframe(
                pd.DataFrame(
                    [{"login": u.login, "nome": u.display_name, "nome_completo": u.full_name} for u in analysts]
                ),
                use_container_width=True,
                hide_index=True,
            )
        elif page == "Indicadores":
            definitions = self.indicators.definitions(segment.id)
            if definitions:
                st.dataframe(pd.DataFrame(definitions), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum indicador foi configurado para este segmento ainda.")
        elif page == "Escala":
            st.info("A fundação de escala está criada no banco e será conectada ao importador na etapa de migração funcional.")
        elif page == "Uploads":
            st.info("Uploads são segmentados por `segment_id`. O importador legado ainda não foi migrado nesta fundação.")
        else:
            st.dataframe(pd.DataFrame(self.users.last_access_for_segment(segment.id)), use_container_width=True, hide_index=True)
