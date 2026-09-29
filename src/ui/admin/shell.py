from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.segment_context import switch_segment_state
from src.application.upload_service import UploadProcessingService
from src.domain.entities import AccessContext, Segment
from src.features.ingestion.excel import ImportValidationError
from src.infrastructure.repositories import IndicatorRepository, UploadRepository, UserRepository
from src.ui.shared.freshness import freshness_table_rows, render_indicator_freshness


SOURCE_OPTIONS = {
    "Chat TOA — Chat 10 min": "chat_toa",
    "Indicadores TOA — Tempo de Validação": "toa_validation",
}


class AdminShell:
    def __init__(self):
        self.access = AccessService()
        self.users = UserRepository()
        self.indicators = IndicatorRepository()
        self.uploads = UploadRepository()
        self.processing = UploadProcessingService(
            access=self.access,
            users=self.users,
            indicators=self.indicators,
        )

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
            self._render_uploads(ctx, segment)

        else:
            st.dataframe(
                pd.DataFrame(self.users.last_access_for_segment(segment.id)),
                use_container_width=True,
                hide_index=True,
            )

    def _render_uploads(self, ctx: AccessContext, segment: Segment) -> None:
        st.markdown("#### Importar planilha")
        st.caption(
            "O processamento usa a maior data real presente na planilha para atualizar o campo 'Dados até'. "
            "Reenvios do mesmo mês substituem somente aquele mês e não duplicam resultados."
        )

        source_label = st.selectbox("Fonte", tuple(SOURCE_OPTIONS), key=f"source:{segment.id}")
        source_key = SOURCE_OPTIONS[source_label]
        uploaded = st.file_uploader(
            "Planilha",
            type=["xlsx", "xls"],
            key=f"upload:{segment.id}:{source_key}",
        )
        if st.button(
            "Processar planilha",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
            key=f"process:{segment.id}:{source_key}",
        ):
            try:
                result = self.processing.process(
                    ctx,
                    segment.id,
                    source_key,
                    uploaded.name,
                    uploaded.getvalue(),
                )
            except (ImportValidationError, ValueError, PermissionError) as exc:
                st.error(str(exc))
            else:
                date_label = datetime.fromisoformat(result.data_through).strftime("%d/%m/%Y")
                st.success(
                    f"{result.indicator_name} processado: {result.total_volume} registros, "
                    f"{result.analyst_count} analistas, dados até {date_label}."
                )
                st.rerun()

        freshness = self.indicators.freshness(segment.id)
        st.markdown("#### Atualização dos dados")
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
