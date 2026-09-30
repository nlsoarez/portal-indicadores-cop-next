from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.infrastructure.repositories import IndicatorRepository, UserRepository
from src.ui.shared.chrome import (
    render_dashboard_hero,
    render_page_header,
    render_sidebar_brand,
)
from src.ui.shared.freshness import render_indicator_freshness
from src.ui.shared.management_indicators import render_management_indicators
from src.ui.shared.person_performance import render_person_performance


class SubadminShell:
    def __init__(self):
        self.access = AccessService()
        self.dashboard = DashboardService(access=self.access)
        self.users = UserRepository()
        self.indicators = IndicatorRepository()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        render_sidebar_brand(
            role="subadmin",
            user_name=ctx.user.display_name,
        )
        segment = st.sidebar.selectbox(
            "Segmento em foco",
            segments,
            format_func=lambda item: item.name,
            key="subadmin_segment_selector",
        )
        switch_segment_state(st.session_state, segment.id)

        nav_icons = {
            "Dashboard": "◉",
            "Indicadores": "▦",
            "Analistas": "◎",
        }
        page = st.sidebar.radio(
            "Navegação",
            ["Dashboard", "Indicadores", "Analistas"],
            format_func=lambda item: f"{nav_icons.get(item, '•')}  {item}",
            label_visibility="collapsed",
        )

        if page == "Dashboard":
            render_page_header(
                title="Dashboard",
                subtitle="Resumo da equipe, cobertura dos dados e atividade recente.",
                eyebrow="Visão de liderança",
                badge=segment.name,
            )
            render_dashboard_hero(
                title="A equipe certa, com o contexto certo.",
                subtitle="Use o painel para identificar rapidamente cobertura, acesso e pontos que exigem investigação.",
                kicker="Liderança · Operação · Qualidade",
            )
        elif page == "Indicadores":
            render_page_header(
                title="Indicadores",
                subtitle="Visões consolidadas gerais, por setor e por analista.",
                eyebrow="Performance operacional",
                badge=segment.name,
            )
        else:
            render_page_header(
                title="Analistas",
                subtitle="Consulta individual dos analistas autorizados para sua liderança.",
                eyebrow="Gestão de pessoas",
                badge=segment.name,
            )

        if page == "Dashboard":
            analysts = self.access.visible_users(ctx, segment.id)
            freshness = self.indicators.freshness(segment.id)
            last_access = self.users.last_access_for_segment(segment.id)
            definitions = self.indicators.definitions(segment.id)

            c1, c2, c3 = st.columns(3)
            c1.metric("Analistas", len(analysts))
            c2.metric("Indicadores", len(definitions))
            c3.metric(
                "Já acessaram",
                sum(1 for row in last_access if row["last_access"]),
            )

            col_fresh, col_access = st.columns([1.15, .85])
            with col_fresh:
                with st.expander("Cobertura dos indicadores", expanded=True):
                    render_indicator_freshness(freshness)
            with col_access:
                with st.expander("Últimos acessos", expanded=True):
                    st.dataframe(
                        pd.DataFrame(last_access),
                        use_container_width=True,
                        hide_index=True,
                    )

        elif page == "Indicadores":
            render_management_indicators(ctx, segments, self.dashboard)

        elif page == "Analistas":
            analysts = self.access.visible_users(ctx, segment.id)
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
