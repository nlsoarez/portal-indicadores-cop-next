from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.infrastructure.repositories import IndicatorRepository, UploadRepository, UserRepository
from src.ui.shared.freshness import freshness_table_rows, render_indicator_freshness


class AdminShell:
    def __init__(self):
        self.access = AccessService()
        self.users = UserRepository()
        self.indicators = IndicatorRepository()
        self.uploads = UploadRepository()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        st.sidebar.markdown("ADMINISTRADOR")
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

        st.markdown("### Gestão operacional")
        st.title(segment.name)
        st.caption("Visão gerencial, comparação, anomalias e administração do segmento.")

        analysts = self.access.visible_users(ctx, segment.id)
        freshness = self.indicators.freshness(segment.id)

        if page == "Visão geral":
            c1, c2, c3 = st.columns(3)
            c1.metric("Pessoas no segmento", len(analysts))
            c2.metric("Indicadores configurados", len(self.indicators.definitions(segment.id)))
            last_access = self.users.last_access_for_segment(segment.id)
            accessed = sum(1 for row in last_access if row["last_access"])
            c3.metric("Usuários que já acessaram", accessed)
            render_indicator_freshness(freshness)
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
                st.markdown("#### Cobertura atual dos dados")
                st.dataframe(
                    pd.DataFrame(freshness_table_rows(freshness)),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Nenhum indicador foi configurado para este segmento ainda.")

        elif page == "Escala":
            st.info("A fundação de escala está criada no banco e será conectada ao importador na etapa de migração funcional.")

        elif page == "Uploads":
            st.markdown("#### Atualização dos dados")
            st.caption(
                "Ao processar uma planilha, o importador registra a data do envio e "
                "a maior data realmente encontrada para cada indicador."
            )
            if freshness:
                st.dataframe(
                    pd.DataFrame(freshness_table_rows(freshness)),
                    use_container_width=True,
                    hide_index=True,
                )
            recent = self.uploads.list_recent(segment.id)
            st.markdown("#### Últimos uploads")
            if recent:
                st.dataframe(pd.DataFrame(recent), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma planilha processada neste segmento ainda.")

        else:
            st.dataframe(
                pd.DataFrame(self.users.last_access_for_segment(segment.id)),
                use_container_width=True,
                hide_index=True,
            )
