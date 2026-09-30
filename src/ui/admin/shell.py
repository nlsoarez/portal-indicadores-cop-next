from __future__ import annotations

from datetime import datetime

import secrets
import string

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.auth_service import AuthService
from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.application.upload_service import UploadProcessingService
from src.domain.entities import AccessContext, Segment
from src.features.ingestion.excel import ImportValidationError
from src.features.ingestion.source_catalog import UPLOAD_SOURCES
from src.infrastructure.database import database_backend, database_is_persistent, persistence_diagnostics
from src.infrastructure.repositories import IndicatorRepository, UploadRepository, UserRepository
from src.integrations.m365_etit import EtitM365Pilot
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

def _format_timestamp(value) -> str:
    if not value:
        return "Nunca"
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return str(value)
    try:
        parsed = parsed.tz_convert("America/Sao_Paulo")
    except TypeError:
        pass
    return parsed.strftime("%d/%m/%Y %H:%M")


def _format_date(value) -> str:
    if not value:
        return "—"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%d/%m/%Y")

def _temporary_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password)
        ):
            return password


class AdminShell:
    def __init__(self):
        self.users = UserRepository()
        self.access = AccessService(self.users)
        self.auth = AuthService(users=self.users)
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
            st.caption(
                "Compare produtividade, ocupação e componentes operacionais para localizar "
                "forças e sinais de atenção sem perder a referência do setor."
            )
            render_dashboard_insights(
                ctx,
                scope_segments,
                self.dashboard,
            )

            st.markdown("### Atualização dos dados")
            st.caption(
                "Veja até quando cada fonte está atualizada antes de interpretar variações "
                "ou cobrar resultado da equipe."
            )
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

    def _render_governance(
        self,
        ctx: AccessContext,
        segments: list[Segment],
    ) -> None:
        access_rows: list[dict] = []
        freshness_rows: list[dict] = []

        for scope in segments:
            for row in self.users.last_access_for_segment(scope.id):
                access_rows.append(
                    {
                        "Analista": row.get("display_name") or row.get("login") or "—",
                        "Login": row.get("login") or "—",
                        "Segmento": scope.name,
                        "Último acesso": _format_timestamp(row.get("last_access")),
                        "_has_access": bool(row.get("last_access")),
                    }
                )

            for row in self.indicators.freshness(scope.id):
                freshness_rows.append(
                    {
                        "Indicador": row.get("name") or row.get("indicator_key") or "—",
                        "Segmento": scope.name,
                        "Dados até": _format_date(row.get("data_through")),
                        "Fonte": row.get("source_key") or "—",
                        "Arquivo": row.get("filename") or "—",
                        "_has_data": bool(row.get("data_through")),
                    }
                )

        analysts_count = len(access_rows)
        accessed_count = sum(1 for row in access_rows if row["_has_access"])
        never_accessed = analysts_count - accessed_count
        indicators_without_data = sum(1 for row in freshness_rows if not row["_has_data"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Analistas ativos", analysts_count)
        c2.metric("Já acessaram", accessed_count)
        c3.metric("Nunca acessaram", never_accessed)
        c4.metric("Indicadores sem dados", indicators_without_data)
        st.markdown("### Gerenciamento de acesso")
        with st.container(border=True):
            accounts = self.users.list_manageable_accounts()
            allowed_segments = {scope.name for scope in segments}
            scoped_accounts = [
                account
                for account in accounts
                if account.get("role_code") == "subadmin"
                or allowed_segments.intersection(account.get("segments") or [])
            ]

            if not scoped_accounts:
                st.info("Nenhum usuário ativo disponível para gerenciamento neste contexto.")
            else:
                target = st.selectbox(
                    "Usuário",
                    scoped_accounts,
                    format_func=lambda item: (
                        f"{item['display_name']} · {item['login']} · "
                        f"{'Liderança' if item['role_code'] == 'subadmin' else 'Analista'}"
                    ),
                    key="admin_password_reset_user",
                )
                st.caption(
                    "O reset gera uma senha temporária segura. No próximo login, "
                    "o usuário será obrigado a cadastrar uma nova senha."
                )

                if st.button(
                    "Resetar senha",
                    type="primary",
                    use_container_width=False,
                    key="admin_password_reset_button",
                ):
                    temporary_password = _temporary_password()
                    try:
                        self.auth.reset_password_as_admin(
                            ctx,
                            int(target["id"]),
                            temporary_password,
                        )
                    except (ValueError, PermissionError) as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["_cop_password_reset_result"] = {
                            "user_id": int(target["id"]),
                            "display_name": target["display_name"],
                            "login": target["login"],
                            "password": temporary_password,
                        }

                reset_result = st.session_state.get("_cop_password_reset_result")
                if (
                    isinstance(reset_result, dict)
                    and int(reset_result.get("user_id", -1)) != int(target["id"])
                ):
                    st.session_state.pop("_cop_password_reset_result", None)
                    reset_result = None

                if (
                    isinstance(reset_result, dict)
                    and int(reset_result.get("user_id", -1)) == int(target["id"])
                ):
                    st.success(
                        f"Senha de {reset_result['display_name']} ({reset_result['login']}) resetada."
                    )
                    st.markdown("**Senha temporária:**")
                    st.code(str(reset_result["password"]), language=None)
                    st.warning(
                        "Copie a senha agora e envie ao usuário por um canal seguro. "
                        "Ela deixará de ser exibida quando outro usuário for selecionado ou a sessão for encerrada."
                    )

        st.markdown("### Adoção da equipe")
        if access_rows:
            access_frame = pd.DataFrame(access_rows)
            access_frame["Status"] = access_frame["_has_access"].map(
                {True: "Já acessou", False: "Nunca acessou"}
            )
            access_frame = access_frame[
                ["Analista", "Login", "Segmento", "Status", "Último acesso"]
            ].sort_values(["Status", "Segmento", "Analista"])
            st.dataframe(access_frame, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum analista ativo no contexto selecionado.")

        leaders_access = self.users.last_access_for_subadmins()
        if leaders_access:
            with st.expander("Acesso das lideranças", expanded=False):
                leader_frame = pd.DataFrame(
                    [
                        {
                            "Líder": row.get("display_name") or row.get("login") or "—",
                            "Login": row.get("login") or "—",
                            "Último acesso": _format_timestamp(row.get("last_access")),
                            "Status": "Já acessou" if row.get("last_access") else "Nunca acessou",
                        }
                        for row in leaders_access
                    ]
                )
                st.dataframe(leader_frame, use_container_width=True, hide_index=True)

        st.markdown("### Cobertura dos indicadores")
        if freshness_rows:
            freshness_frame = pd.DataFrame(freshness_rows)
            freshness_frame["Status"] = freshness_frame["_has_data"].map(
                {True: "Com dados", False: "Sem dados"}
            )
            freshness_frame = freshness_frame[
                ["Indicador", "Segmento", "Status", "Dados até", "Fonte", "Arquivo"]
            ].sort_values(["Status", "Segmento", "Indicador"])
            st.dataframe(freshness_frame, use_container_width=True, hide_index=True)

        st.markdown("### Últimas atualizações")
        recent_uploads: list[dict] = []
        source_labels = {source.key: source.label for source in UPLOAD_SOURCES}
        for scope in segments:
            for row in self.uploads.list_recent(scope.id, limit=8):
                recent_uploads.append(
                    {
                        "Fonte": source_labels.get(
                            str(row.get("source_key") or ""),
                            row.get("source_key") or "—",
                        ),
                        "Segmento": scope.name,
                        "Arquivo": row.get("filename") or "—",
                        "Enviado por": row.get("uploaded_by") or "—",
                        "Processado em": _format_timestamp(row.get("created_at")),
                        "_sort": str(row.get("created_at") or ""),
                    }
                )

        if recent_uploads:
            upload_frame = pd.DataFrame(recent_uploads).sort_values(
                "_sort", ascending=False
            ).head(12)
            st.dataframe(
                upload_frame[
                    ["Fonte", "Segmento", "Arquivo", "Enviado por", "Processado em"]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Nenhum upload registrado no contexto selecionado.")

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

        st.markdown("#### Piloto automático — ETIT Microsoft 365")
        st.caption(
            "Residencial e Empresarial podem ser verificados diretamente no Microsoft 365. "
            "O sincronismo só baixa e reprocessa quando o arquivo remoto muda."
        )
        pilot = EtitM365Pilot()
        pilot_status = pilot.status()
        source_status = pilot_status.get("sources") or {}
        source_config = pilot_status.get("source_configuration") or {}

        p1, p2, p3 = st.columns(3)
        p1.metric(
            "Configuração Graph",
            "OK" if pilot_status.get("configured") else "Pendente",
        )
        p2.metric(
            "Autenticação Microsoft 365",
            "Conectada" if pilot_status.get("authenticated") else "Pendente",
        )
        configured_sources = sum(
            1
            for row in source_config.values()
            if isinstance(row, dict) and row.get("configured")
        )
        p3.metric("Fontes piloto configuradas", f"{configured_sources}/2")

        pilot_rows = []
        for key, label in (
            ("residential_indicators", "ETIT Residencial"),
            ("enterprise_indicators", "ETIT Empresarial"),
        ):
            config_row = source_config.get(key) or {}
            state_row = source_status.get(key) or {}
            remote = state_row.get("remote") or {}
            pilot_rows.append(
                {
                    "Fonte": label,
                    "Configuração": "OK" if config_row.get("configured") else "Pendente",
                    "Status": state_row.get("status") or "Ainda não verificado",
                    "Arquivo remoto": remote.get("name") or "—",
                    "Competência": remote.get("competence") or "—",
                    "Modificado em": _format_timestamp(remote.get("last_modified")),
                    "Último sync": _format_timestamp(state_row.get("last_synced_at")),
                    "Erro": state_row.get("last_error") or "—",
                }
            )
        st.dataframe(
            pd.DataFrame(pilot_rows),
            use_container_width=True,
            hide_index=True,
        )

        if not pilot_status.get("configured"):
            st.info(
                "Configure M365_TENANT_ID e M365_CLIENT_ID em .env.vps. "
                "Os links das pastas ETIT também precisam estar nas variáveis "
                "M365_ETIT_RESIDENTIAL_URL e M365_ETIT_ENTERPRISE_URL."
            )
        elif not pilot_status.get("authenticated"):
            st.warning(
                "A configuração existe, mas falta autenticar a conta Microsoft 365. "
                "No servidor execute: bash deploy/hostinger/m365-etit.sh login"
            )
        else:
            b1, b2 = st.columns(2)
            with b1:
                if st.button(
                    "Verificar Microsoft 365 agora",
                    use_container_width=True,
                    key="m365_etit_probe",
                ):
                    with st.spinner("Consultando pastas ETIT no Microsoft 365..."):
                        try:
                            result = pilot.probe()
                        except Exception as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["_cop_m365_probe_result"] = result
                            st.rerun()
            with b2:
                if st.button(
                    "Sincronizar ETIT agora",
                    type="primary",
                    use_container_width=True,
                    key="m365_etit_sync",
                ):
                    with st.spinner("Verificando e processando ETIT alterado..."):
                        try:
                            result = pilot.sync(
                                processing=self.processing,
                                ctx=ctx,
                            )
                        except Exception as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["_cop_m365_sync_result"] = result
                            st.rerun()

        probe_flash = st.session_state.pop("_cop_m365_probe_result", None)
        if isinstance(probe_flash, dict):
            checked = probe_flash.get("checked_at")
            st.success(
                "Verificação Microsoft 365 concluída"
                + (f" em {_format_timestamp(checked)}." if checked else ".")
            )

        sync_flash = st.session_state.pop("_cop_m365_sync_result", None)
        if isinstance(sync_flash, dict):
            statuses = [
                str(row.get("status") or "")
                for row in (sync_flash.get("sources") or {}).values()
                if isinstance(row, dict)
            ]
            updated = sum(1 for value in statuses if value == "updated")
            unchanged = sum(1 for value in statuses if value == "unchanged")
            errors = sum(1 for value in statuses if value == "error")
            if errors:
                st.warning(
                    f"Sincronismo concluído com {errors} erro(s), "
                    f"{updated} atualização(ões) e {unchanged} fonte(s) sem mudança."
                )
            else:
                st.success(
                    f"Sincronismo concluído: {updated} atualização(ões) e "
                    f"{unchanged} fonte(s) sem mudança."
                )

        st.divider()

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

        for start in range(0, len(UPLOAD_SOURCES), 2):
            cols = st.columns(2, gap="large")
            for column, source in zip(cols, UPLOAD_SOURCES[start:start + 2]):
                with column:
                    self._render_upload_source_card(
                        ctx,
                        source,
                        latest_by_source.get(source.key),
                    )

    def _render_upload_source_card(self, ctx: AccessContext, source, latest: dict | None) -> None:
        with st.container(border=True):
            st.markdown(f"#### {source.label}")
            st.caption(source.description)
            st.markdown(f"**Arquivo esperado:** {source.filename_hint}.xlsx")

            if latest:
                st.caption(
                    f"Último processamento: {_format_timestamp(latest.get('created_at'))} · "
                    f"{latest.get('uploaded_by') or '—'} · {latest.get('filename') or '—'}"
                )
            else:
                st.caption("Ainda não há processamento registrado para esta fonte.")

            upload_key = f"global-upload:{source.key}"
            uploaded = chunked_file_uploader(key=upload_key)

            if uploaded is not None:
                size_mb = uploaded.size / (1024 * 1024)
                st.success(f"{uploaded.filename} · {size_mb:.1f} MB · pronto para processar.")

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
