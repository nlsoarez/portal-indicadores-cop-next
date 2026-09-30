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
from src.infrastructure.database import database_backend, database_is_persistent, persistence_diagnostics
from src.infrastructure.repositories import IndicatorRepository, UploadRepository, UserRepository
from src.ui.admin.certified_analysts import render_certified_analysts
from src.ui.admin.leaders_overview import render_leaders_overview
from src.ui.admin.dashboard_insights import render_dashboard_insights
from src.ui.shared.chrome import (
    render_dashboard_hero,
    render_page_header,
    render_sidebar_brand,
)
from src.ui.shared.chunked_upload import chunked_file_uploader, clear_chunked_upload
from src.ui.shared.freshness import render_indicator_freshness
from src.ui.shared.management_indicators import render_management_indicators
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
        render_sidebar_brand(
            role="admin",
            user_name=ctx.user.display_name,
        )

        nav_icons = {
            "Dashboard": "◉",
            "Indicadores": "▦",
            "Analista Certificado": "✓",
            "Analistas": "◎",
            "Líderes": "♛",
            "Uploads": "⇧",
            "Governança": "◇",
        }
        page = st.sidebar.radio(
            "Navegação",
            ["Dashboard", "Indicadores", "Analista Certificado", "Analistas", "Líderes", "Uploads", "Governança"],
            format_func=lambda item: f"{nav_icons.get(item, '•')}  {item}",
            label_visibility="collapsed",
        )

        st.sidebar.markdown("<div class='cop-sidebar-section'>CONTEXTO</div>", unsafe_allow_html=True)
        segment = st.sidebar.selectbox(
            "Segmento em foco",
            [None, *segments],
            index=0,
            format_func=lambda item: "Geral" if item is None else item.name,
            key="admin_scope_selector_v2",
        )
        segment_label = "Geral" if segment is None else segment.name
        switch_segment_state(st.session_state, 0 if segment is None else segment.id)
        scope_segments = segments if segment is None else [segment]

        if page == "Dashboard":
            render_page_header(
                title="Dashboard",
                subtitle="Leitura executiva da operação, pessoas e qualidade em um único fluxo.",
                eyebrow="Gestão operacional",
                badge=segment_label,
            )
            render_dashboard_hero(
                title="Performance que gera resultado.",
                subtitle="Acompanhe volume, qualidade, certificação e sinais de atenção sem perder contexto operacional.",
                kicker="Dados · Pessoas · Conexão",
            )
        elif page == "Indicadores":
            render_page_header(
                title="Indicadores",
                subtitle="Visões consolidadas, rankings, causas e recortes operacionais.",
                eyebrow="Performance operacional",
                badge=segment_label,
            )
        elif page == "Analista Certificado":
            render_page_header(
                title="Analista Certificado",
                subtitle="Certificação consolidada de Residencial e Empresarial com leitura rápida das exceções.",
                eyebrow="Qualidade e prontidão",
            )
        elif page == "Analistas":
            render_page_header(
                title="Analistas",
                subtitle="Aprofunde o desempenho individual sem perder a referência da equipe.",
                eyebrow="Gestão de pessoas",
                badge=segment_label,
            )
        elif page == "Líderes":
            render_page_header(
                title="Visão dos Líderes",
                subtitle="Compare produtividade, DPA, componentes e posição relativa de cada liderança.",
                eyebrow="Liderança operacional",
            )
        elif page == "Uploads":
            render_page_header(
                title="Atualização de dados",
                subtitle="Centralize o processamento das fontes oficiais e acompanhe a cobertura de cada carga.",
                eyebrow="Dados e integrações",
            )
        else:
            render_page_header(
                title="Governança do portal",
                subtitle="Acompanhe adoção, acessos, cobertura dos dados e histórico recente de atualizações.",
                eyebrow="Governança",
                badge=segment_label,
            )

        if page == "Dashboard":
            analysts, freshness, last_access, definitions = self._dashboard_scope(
                ctx,
                scope_segments,
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Analistas", len(analysts))
            c2.metric("Indicadores", len(definitions))
            c3.metric(
                "Já acessaram",
                sum(1 for row in last_access if row.get("last_access")),
            )
            c4.metric(
                "Fontes com dados",
                sum(1 for row in freshness if row.get("data_through")),
            )

            st.markdown("### Leitura da equipe")
            render_dashboard_insights(
                ctx,
                scope_segments,
                self.dashboard,
            )

            st.markdown("### Atualização dos dados")
            render_indicator_freshness(
                freshness,
                show_title=False,
                columns=3,
            )

            with st.expander("Acessos recentes", expanded=False):
                st.dataframe(
                    pd.DataFrame(last_access),
                    use_container_width=True,
                    hide_index=True,
                )

        elif page == "Indicadores":
            render_management_indicators(ctx, segments, self.dashboard)

        elif page == "Analista Certificado":
            render_certified_analysts(
                ctx,
                segments,
                self.dashboard,
                self.access,
            )

        elif page == "Analistas":
            analysis_segment = segment
            if analysis_segment is None:
                analysis_segment = st.selectbox(
                    "Segmento para análise individual",
                    segments,
                    format_func=lambda item: item.name,
                    key="admin_analyst_segment",
                )
            analysts = self.access.visible_users(ctx, analysis_segment.id)
            if not analysts:
                st.info("Nenhum analista cadastrado neste segmento.")
            else:
                target = st.selectbox(
                    "Analista",
                    analysts,
                    format_func=lambda user: f"{user.display_name} · {user.login}",
                    key=f"admin_analyst:{analysis_segment.id}",
                )
                render_person_performance(
                    ctx,
                    analysis_segment.id,
                    target,
                    self.dashboard,
                )

        elif page == "Líderes":
            render_leaders_overview(
                ctx,
                segments,
                self.dashboard,
                self.access,
                self.users,
            )

        elif page == "Uploads":
            self._render_uploads(ctx)

        else:
            self._render_governance(
                ctx,
                scope_segments,
            )

    def _dashboard_scope(
        self,
        ctx: AccessContext,
        segments: list[Segment],
    ) -> tuple[list, list[dict], list[dict], list[dict]]:
        analysts_by_id = {}
        freshness_by_key: dict[str, dict] = {}
        access_by_key: dict[str, dict] = {}
        definitions_by_key: dict[str, dict] = {}

        for scope in segments:
            for user in self.access.visible_users(ctx, scope.id):
                analysts_by_id[user.id] = user

            for row in self.indicators.freshness(scope.id):
                key = str(row.get("indicator_key") or row.get("name") or "")
                previous = freshness_by_key.get(key)
                if previous is None or str(row.get("data_through") or "") > str(previous.get("data_through") or ""):
                    freshness_by_key[key] = row

            for row in self.indicators.definitions(scope.id):
                key = str(row.get("indicator_key") or row.get("name") or "")
                definitions_by_key[key] = row

            for row in self.users.last_access_for_segment(scope.id):
                key = str(row.get("id") or row.get("login") or row.get("email") or row)
                previous = access_by_key.get(key)
                if previous is None or str(row.get("last_access") or "") > str(previous.get("last_access") or ""):
                    access_by_key[key] = row

        freshness = sorted(
            freshness_by_key.values(),
            key=lambda row: str(row.get("name") or row.get("indicator_key") or ""),
        )
        last_access = sorted(
            access_by_key.values(),
            key=lambda row: (
                str(row.get("last_access") or ""),
                str(row.get("full_name") or row.get("display_name") or row.get("login") or ""),
            ),
            reverse=True,
        )
        definitions = sorted(
            definitions_by_key.values(),
            key=lambda row: str(row.get("name") or row.get("indicator_key") or ""),
        )
        return list(analysts_by_id.values()), freshness, last_access, definitions

    def _render_uploads(self, ctx: AccessContext) -> None:
        st.markdown("#### Atualização das 7 fontes oficiais")
        st.caption(
            "Envie cada planilha uma única vez por atualização. O backend identifica os usuários "
            "e direciona os resultados aos segmentos correspondentes. Faça apenas um upload por vez."
        )

        if not database_is_persistent():
            diag = persistence_diagnostics()
            st.error(
                "BANCO TEMPORÁRIO: este deployment ainda está usando SQLite. "
                "Uploads e alterações persistentes estão bloqueados até o PostgreSQL estar conectado."
            )
            st.markdown("**Diagnóstico do deployment**")
            st.code(
                "Backend: {backend}\n"
                "DATABASE_URL detectada: {database_url}\n"
                "POSTGRES_URL detectada: {postgres_url}\n"
                "POSTGRES_URL_NON_POOLING detectada: {non_pooling}\n"
                "Ambiente Vercel: {vercel_env}\n"
                "Commit: {commit}".format(
                    backend=diag["backend"],
                    database_url="SIM" if diag["database_url_detected"] else "NÃO",
                    postgres_url="SIM" if diag["postgres_url_detected"] else "NÃO",
                    non_pooling="SIM" if diag["postgres_non_pooling_detected"] else "NÃO",
                    vercel_env=diag["vercel_env"] or "não informado",
                    commit=diag["commit"] or "não informado",
                )
            )
            st.info(
                "Vá em Vercel → Settings → Environment Variables e confirme que DATABASE_URL "
                "está habilitada para Production. Depois faça um novo Redeploy da produção."
            )
            return
        else:
            st.success(f"Banco persistente ativo: {database_backend().upper()}.")

        flash = st.session_state.get("_cop_upload_success")
        if isinstance(flash, dict):
            st.success(
                f"PROCESSAMENTO CONCLUÍDO — {flash.get('source', '')}\n\n"
                f"Arquivo: {flash.get('filename', '')}\n\n"
                f"{flash.get('summary', '')}"
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
                    st.success(
                        f"PROCESSADO · {latest['filename']} · {latest['created_at']} · "
                        f"por {latest['uploaded_by']}"
                    )
                else:
                    st.caption("Nenhum processamento registrado ainda.")

                upload_key = f"global-upload:{source.key}"
                uploaded = chunked_file_uploader(key=upload_key)

                if uploaded is not None:
                    size_mb = uploaded.size / (1024 * 1024)
                    st.caption(
                        f"Arquivo recebido: {uploaded.filename} · {size_mb:.1f} MB · pronto para processar."
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
                            uploaded.filename,
                            uploaded.getvalue(),
                        )
                    except (ImportValidationError, ValueError, PermissionError) as exc:
                        st.error(str(exc))
                    else:
                        summary = []
                        for slug, result in results:
                            date_label = datetime.fromisoformat(result.data_through).strftime("%d/%m/%Y")
                            summary.append(f"{slug}: {result.indicator_name} · dados até {date_label}")
                        st.session_state["_cop_upload_success"] = {
                            "source": source.label,
                            "filename": uploaded.filename,
                            "summary": " | ".join(summary),
                        }
                        clear_chunked_upload(upload_key)
                        st.rerun()
