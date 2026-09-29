from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.application.upload_service import UploadProcessingService
from src.domain.entities import AccessContext, Segment
from src.features.ingestion.excel import ImportValidationError
from src.features.ingestion.source_catalog import UPLOAD_SOURCES
from src.infrastructure.repositories import IndicatorRepository, UploadRepository, UserRepository
from src.ui.shared.freshness import freshness_table_rows, render_indicator_freshness
from src.ui.shared.person_performance import render_person_performance


class AdminShell:
    def __init__(self):
        self.access = AccessService()
        self.users = UserRepository()
        self.indicators = IndicatorRepository()
        self.dashboard = DashboardService(access=self.access, indicators=self.indicators)
        self.uploads = UploadRepository()
        self.processing = UploadProcessingService(
            access=self.access,
            users=self.users,
            indicators=self.indicators,
        )

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        st.sidebar.markdown("<span class='cop-role-admin'>ADMIN</span>", unsafe_allow_html=True)
        st.sidebar.markdown(f"### {ctx.user.display_name}")
        segment = st.sidebar.selectbox(
            "Segmento", segments, format_func=lambda item: item.name, key="admin_segment_selector"
        )
        switch_segment_state(st.session_state, segment.id)
        page = st.sidebar.radio(
            "Navegação",
            ["Visão geral", "Analistas", "Líderes", "Indicadores", "Uploads", "Auditoria"],
            label_visibility="collapsed",
        )

        st.markdown("<div class='cop-eyebrow'>Gestão operacional</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='cop-title'>{segment.name}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='cop-subtitle'>Visão gerencial, indicadores e administração do portal.</div>",
            unsafe_allow_html=True,
        )

        analysts = self.access.visible_users(ctx, segment.id)
        freshness = self.indicators.freshness(segment.id)

        if page == "Visão geral":
            c1, c2, c3 = st.columns(3)
            c1.metric("Analistas", len(analysts))
            c2.metric("Indicadores configurados", len(self.indicators.definitions(segment.id)))
            last_access = self.users.last_access_for_segment(segment.id)
            c3.metric("Analistas que já acessaram", sum(1 for row in last_access if row["last_access"]))
            render_indicator_freshness(freshness)
            st.subheader("Acompanhamento da equipe")
            st.dataframe(pd.DataFrame(last_access), use_container_width=True, hide_index=True)

        elif page == "Analistas":
            if not analysts:
                st.info("Nenhum analista cadastrado neste segmento.")
            else:
                target = st.selectbox(
                    "Analista",
                    analysts,
                    format_func=lambda user: f"{user.display_name} · {user.login}",
                    key=f"admin_analyst:{segment.id}",
                )
                render_person_performance(ctx, segment.id, target, self.dashboard)

        elif page == "Líderes":
            leaders = self.access.visible_subadmins(ctx)
            st.caption("Área exclusiva do Admin. Líderes não aparecem na lista de analistas.")
            if not leaders:
                st.info("Nenhum líder cadastrado.")
            else:
                leader = st.selectbox(
                    "Líder",
                    leaders,
                    format_func=lambda user: f"{user.display_name} · {user.login}",
                    key="admin_leader",
                )
                performance_segments = self.users.performance_segments_for_user(leader.id)
                if not performance_segments:
                    st.info("Este líder ainda não possui segmento operacional para indicadores.")
                else:
                    perf_segment = performance_segments[0]
                    st.caption(f"Indicadores operacionais: {perf_segment.name}")
                    render_person_performance(
                        ctx,
                        perf_segment.id,
                        leader,
                        self.dashboard,
                        comparison_label="vs média dos analistas",
                    )
                access_rows = self.users.last_access_for_subadmins()
                current = next((row for row in access_rows if int(row["id"]) == leader.id), None)
                if current:
                    st.caption(f"Último acesso: {current.get('last_access') or 'Nunca acessou'}")

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

        elif page == "Uploads":
            self._render_uploads(ctx)

        else:
            st.dataframe(
                pd.DataFrame(self.users.last_access_for_segment(segment.id)),
                use_container_width=True,
                hide_index=True,
            )

    def _render_uploads(self, ctx: AccessContext) -> None:
        st.markdown("#### Atualização das 7 fontes oficiais")
        st.caption(
            "Envie cada planilha uma única vez por atualização. O backend identifica os usuários "
            "e direciona os resultados aos segmentos correspondentes."
        )
        latest_by_source = self.uploads.latest_by_source()
        c1, c2 = st.columns(2)
        c1.metric("Fontes oficiais", len(UPLOAD_SOURCES))
        c2.metric("Integrações ativas", f"{len(UPLOAD_SOURCES)}/{len(UPLOAD_SOURCES)}")

        for source in UPLOAD_SOURCES:
            latest = latest_by_source.get(source.key)
            with st.expander(f"{source.label} · Integrada", expanded=False):
                st.caption(source.description)
                st.markdown(f"**Arquivo esperado:** {source.filename_hint}.xlsx")
                if latest:
                    st.caption(
                        f"Último processamento: {latest['filename']} · {latest['created_at']} · "
                        f"por {latest['uploaded_by']}"
                    )
                else:
                    st.caption("Nenhum processamento registrado ainda.")

                uploaded = st.file_uploader(
                    f"Selecionar {source.label}",
                    type=["xlsx", "xls"],
                    key=f"global-upload:{source.key}",
                    label_visibility="collapsed",
                )
                if st.button(
                    f"Processar {source.label}",
                    type="primary",
                    use_container_width=True,
                    disabled=uploaded is None,
                    key=f"global-process:{source.key}",
                ):
                    try:
                        results = self.processing.process_global_source(
                            ctx,
                            source.key,
                            uploaded.name,
                            uploaded.getvalue(),
                        )
                    except (ImportValidationError, ValueError, PermissionError) as exc:
                        st.error(str(exc))
                    else:
                        summary = []
                        for slug, result in results:
                            date_label = datetime.fromisoformat(result.data_through).strftime("%d/%m/%Y")
                            summary.append(f"{slug}: {result.indicator_name} · dados até {date_label}")
                        st.success("Processamento concluído — " + " | ".join(summary))
                        st.rerun()
