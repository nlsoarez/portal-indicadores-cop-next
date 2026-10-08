from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.infrastructure.repositories import UserRepository
from src.ui.analyst.shell import AnalystShell
from src.ui.shared.chrome import render_page_header, render_sidebar_brand
from src.ui.shared.management_indicators import render_management_indicators
from src.ui.shared.metrics import format_metric, format_target
from src.ui.shared.person_performance import render_person_performance


def _operational_segment(
    ctx: AccessContext,
    segments: list[Segment],
    users: UserRepository,
    access: AccessService,
) -> Segment:
    """Restrict leaders to the one segment assigned to their performance."""
    if not ctx.is_subadmin or ctx.is_admin:
        raise PermissionError("A visão de liderança exige perfil de líder")
    assigned = {row.id for row in users.performance_segments_for_user(ctx.user.id)}
    permitted = [row for row in segments if row.id in assigned]
    if len(permitted) != 1:
        raise PermissionError("O líder deve possuir exatamente um segmento operacional")
    access.assert_segment_access(ctx, permitted[0].id)
    return permitted[0]


def _team_snapshot(summary_rows: list[dict], analyst_count: int) -> dict:
    """Metas comparadas apenas com o consolidado da equipe no último período."""
    frame = pd.DataFrame(summary_rows)
    if frame.empty:
        return {
            "analysts": analyst_count, "indicators": 0,
            "with_target": 0, "met": 0, "attention": 0,
            "rows": [],
        }

    # A consulta já devolve a última competência de cada indicador.
    # Esta proteção mantém uma única linha por indicador se houver duplicatas.
    frame["period"] = frame["period"].fillna("").astype(str)
    frame = frame.sort_values("period").drop_duplicates("indicator_key", keep="last")
    rows = frame.to_dict("records")

    assessed = 0
    met = 0
    for row in rows:
        value = _safe_number(row.get("value"))
        target = _safe_number(row.get("target_value"))
        row["status"] = None
        if value is None or target is None:
            continue
        assessed += 1
        direction = str(row.get("direction") or "higher_is_better")
        passed = value <= target if direction == "lower_is_better" else value >= target
        row["status"] = "Dentro da meta" if passed else "Fora da meta"
        met += int(passed)

    return {
        "analysts": analyst_count,
        "indicators": len(rows),
        "with_target": assessed,
        "met": met,
        "attention": assessed - met,
        "rows": sorted(rows, key=lambda row: str(row.get("name") or "")),
    }


def _safe_number(value) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
        return parsed if pd.notna(parsed) else None
    except (ValueError, TypeError):
        return None


def _format_team_value(value: float | None, unit: str | None) -> str:
    if value is None:
        return "—"
    formatted = format_metric(value, unit)
    if (unit or "percent").lower() == "percent":
        return formatted.replace(".", ",")
    return formatted


def _team_ranking(summary_rows: list[dict], analyst_rows: list[dict], indicator_key: str) -> pd.DataFrame:
    """Ranking restricted to the indicator and competence shown to the leader."""
    source = next(
        (row for row in summary_rows if str(row.get("indicator_key")) == indicator_key),
        None,
    )
    if not source:
        return pd.DataFrame()
    period = str(source.get("period") or "")
    rows = [
        row for row in analyst_rows
        if str(row.get("indicator_key")) == indicator_key
        and str(row.get("period") or "") == period
    ]
    if not rows:
        return pd.DataFrame()
    descending = str(source.get("direction") or "higher_is_better") != "lower_is_better"
    ranking = pd.DataFrame(rows)
    ranking["value"] = pd.to_numeric(ranking["value"], errors="coerce")
    ranking = ranking.sort_values(
        ["value", "display_name"], ascending=[not descending, True], na_position="last"
    )
    unit = source.get("unit")
    return pd.DataFrame(
        [
            {
                "Analista": row["display_name"],
                "Login": row["login"],
                "Resultado": _format_team_value(_safe_number(row["value"]), unit),
                "Base": int(row.get("volume") or 0),
            }
            for _, row in ranking.iterrows()
        ]
    )


class SubadminShell:
    def __init__(self):
        self.access = AccessService()
        self.dashboard = DashboardService(access=self.access)
        self.users = UserRepository()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        segment = _operational_segment(ctx, segments, self.users, self.access)
        render_sidebar_brand(
            role="subadmin",
            user_name=ctx.user.display_name,
            segment_name=segment.name,
        )
        st.sidebar.caption(f"Setor de responsabilidade: {segment.name}")
        switch_segment_state(st.session_state, segment.id)

        page = st.sidebar.radio(
            "Visão",
            ["Meu Dashboard", "Minha Equipe"],
            format_func=lambda value: {
                "Meu Dashboard": "◎  Meu Dashboard",
                "Minha Equipe": "▦  Minha Equipe",
            }[value],
            key="leader_workspace_v2",
        )

        if page == "Meu Dashboard":
            render_page_header(
                title="Meu Dashboard",
                subtitle="Seus resultados, metas, produtividade e evolução individual.",
                eyebrow="Meu desempenho",
                badge=segment.name,
            )
            # Reuse the fully featured personal analyst dashboard.
            # Its data source remains the authenticated leader's user ID.
            AnalystShell().render(ctx, [segment], embedded=True)
            return

        render_page_header(
            title="Minha Equipe",
            subtitle="Indicadores consolidados e acompanhamento dos analistas do seu setor.",
            eyebrow="Visão de liderança",
            badge=segment.name,
        )
        section = st.radio(
            "Explorar equipe",
            ["Visão geral", "Indicadores", "Analistas", "Qualidade dos dados"],
            horizontal=True,
            label_visibility="collapsed",
            key="leader_team_section_v2",
        )

        if section == "Indicadores":
            render_management_indicators(ctx, [segment], self.dashboard)
        elif section == "Analistas":
            self._render_analysts(ctx, segment)
        elif section == "Qualidade dos dados":
            self._render_quality(ctx, segment)
        else:
            self._render_team_overview(ctx, segment)

    def _render_team_overview(self, ctx: AccessContext, segment: Segment) -> None:
        analysts = self.access.visible_users(ctx, segment.id)
        payload = self.dashboard.management_payload(ctx, [segment.id])
        snapshot = _team_snapshot(payload.get("segment_summary") or [], len(analysts))

        a, b, c, d = st.columns(4)
        a.metric("Analistas da equipe", snapshot["analysts"])
        b.metric("Indicadores com dados", snapshot["indicators"])
        c.metric(
            "Indicadores na meta",
            f'{snapshot["met"]}/{snapshot["with_target"]}'
            if snapshot["with_target"] else "—",
        )
        d.metric(
            "Fora da meta",
            snapshot["attention"] if snapshot["with_target"] else "—",
        )

        st.markdown("### Resultados consolidados")
        st.caption(
            "Cada indicador utiliza sua própria competência mais recente. "
            "A média considera os analistas do setor, sem incluir os líderes."
        )
        rows = snapshot["rows"]
        if not rows:
            st.info("Ainda não há indicadores processados para esta equipe.")
            return

        for start in range(0, len(rows), 3):
            cols = st.columns(3)
            for col, row in zip(cols, rows[start:start + 3]):
                with col:
                    value = _safe_number(row.get("value"))
                    unit = row.get("unit")
                    st.metric(
                        str(row.get("name") or row.get("indicator_key") or "Indicador"),
                        _format_team_value(value, unit),
                    )
                    target = _safe_number(row.get("target_value"))
                    st.caption(
                        (format_target(target, unit, row.get("direction")).replace(".", ",")
                         if target is not None else "Sem meta configurada")
                        + f" · {row.get('period') or 'Período não informado'}"
                    )

        st.markdown("### Resultado por analista")
        options = {str(row["indicator_key"]): row for row in rows}
        selected = st.selectbox(
            "Indicador para comparar a equipe",
            list(options),
            format_func=lambda key: str(options[key].get("name") or key),
            key=f"leader_team_ranking:{segment.id}",
        )
        table = _team_ranking(
            rows, payload.get("analyst_summary") or [], selected
        )
        if table.empty:
            st.info("Sem dados individuais disponíveis para a competência selecionada.")
        else:
            st.dataframe(table, use_container_width=True, hide_index=True)

    def _render_quality(self, ctx: AccessContext, segment: Segment) -> None:
        report = self.dashboard.leader_quality_report(ctx, segment.id)
        st.markdown("### Confiabilidade dos dados de ETIT e Canceladas")
        st.caption(
            "Auditoria informativa: identifica falta de base e volumes reduzidos. "
            "Não modifica cargas, metas nem indicadores. "
            "Outros líderes não aparecem individualmente nesta visão."
        )
        month = report["period"]
        if not month:
            st.info("Não há competência identificada para as fontes monitoradas.")
            return
        st.caption(f"Competência analisada: {month}")
        cols = st.columns(4)
        cols[0].metric("Bases incompatíveis", report["incompatible"])
        cols[1].metric("Amostras ETIT reduzidas", report["small_samples"])
        cols[2].metric("Sem eventos ETIT", report["without_etit"])
        cols[3].metric("Sem alerta", report["no_alert"])

        st.markdown("#### Pendências e cobertura por pessoa")
        data = pd.DataFrame(report["people"])
        if not data.empty:
            view = data.rename(
                columns={
                    "name": "Nome",
                    "login": "Login",
                    "role": "Perfil",
                    "month": "Competência",
                    "cancelled": "Canceladas",
                    "cancelled_records": "Registros na fonte",
                    "etit_volume": "Eventos ETIT",
                    "status": "Situação",
                    "reason": "Diagnóstico",
                    "action": "Ação sugerida",
                }
            )
            cols_to_show = [
                "Nome", "Login", "Perfil", "Competência", "Eventos ETIT",
                "Canceladas", "Registros na fonte", "Situação",
                "Diagnóstico", "Ação sugerida",
            ]
            st.dataframe(
                view[cols_to_show],
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("#### Origem e atualização das informações")
        provenance = pd.DataFrame(report["sources"])
        if provenance.empty:
            st.warning("Nenhuma fonte ETIT ou Canceladas cadastrada para o setor.")
        else:
            fields = {
                "name": "Indicador",
                "data_through": "Dados até",
                "filename": "Arquivo recebido",
                "uploaded_at": "Carregado em",
            }
            for col in fields:
                if col not in provenance.columns:
                    provenance[col] = None
            st.dataframe(
                provenance[list(fields)].rename(columns=fields),
                use_container_width=True,
                hide_index=True,
            )

        st.info(
            "Critério informativo de amostra reduzida: menos de 10 eventos ETIT "
            "no mês. Não é meta de desempenho. Ausência de ETIT pode ser normal "
            "para quem não atuou nesse fluxo e exige conferência da escala. "
            "A taxa de Canceladas só é calculada com denominador ETIT "
            "compatível na mesma competência."
        )

    def _render_analysts(self, ctx: AccessContext, segment: Segment) -> None:
        analysts = self.access.visible_users(ctx, segment.id)
        if not analysts:
            st.info("Nenhum analista ativo cadastrado neste setor.")
            return

        target = st.selectbox(
            "Analista",
            analysts,
            format_func=lambda user: f"{user.display_name} · {user.login}",
            key=f"leader_analyst:{segment.id}",
        )
        render_person_performance(ctx, segment.id, target, self.dashboard)
