from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
from src.features.analytics.tips import build_tips
from src.ui.shared.freshness import render_indicator_freshness
from src.ui.shared.metrics import format_metric, format_target


DIMENSION_LABELS = {
    "group": "Cluster",
    "service": "Serviço",
    "demand": "Demanda",
    "cause": "Causa",
    "cause_toa": "Causa TOA",
    "cause_sir": "Causa SIR",
    "area": "Área",
    "area_involved": "Área envolvida",
    "network": "Rede",
    "activity_type": "Tipo de atividade",
    "incident_type": "Tipo de incidente",
    "aging": "Faixa de tempo",
    "hour": "Hora",
    "base": "Base",
    "queue": "Fila",
    "queue_type": "Tipo de fila",
    "productivity_component": "Componente",
}

DETAIL_DIMENSIONS = {
    "res_etit_fibra_hfc": ("group", "service", "nature", "impact", "solution"),
    "res_etit_gpon": ("group", "service", "nature", "impact", "solution"),
    "emp_etit_event": ("group", "demand", "cause", "area"),
    "validacao_20m": ("group", "network", "activity_type", "incident_type", "aging"),
    "chat_10m": ("base", "queue", "queue_type", "hour"),
    "closing_assertiveness": ("group", "demand", "cause_toa", "cause_sir", "area_involved"),
    "toa_cancellation_rate": ("group", "network", "activity_type", "incident_type", "aging"),
    "productivity_avg_daily": ("productivity_component",),
}


class AnalystShell:
    def __init__(self):
        self.dashboard = DashboardService()

    def render(self, ctx: AccessContext, segments: list[Segment]) -> None:
        st.sidebar.markdown("<span class='cop-role-analyst'>ANALISTA</span>", unsafe_allow_html=True)
        st.sidebar.markdown(f"### {ctx.user.display_name}")
        segment = st.sidebar.selectbox(
            "Meu segmento", segments, format_func=lambda item: item.name, key="analyst_segment_selector"
        )
        switch_segment_state(st.session_state, segment.id)
        page = st.sidebar.radio(
            "Navegação", ["Meu desempenho", "Minha evolução", "Histórico"], label_visibility="collapsed"
        )

        st.markdown("<div class='cop-eyebrow'>Desempenho individual</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='cop-title'>Olá, {ctx.user.display_name}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='cop-subtitle'>Seus números, a referência da equipe e onde agir primeiro.</div>",
            unsafe_allow_html=True,
        )

        payload = self.dashboard.analyst_payload(ctx, segment.id)
        render_indicator_freshness(payload["freshness"])

        if page == "Meu desempenho":
            self._render_performance(payload)
        elif page == "Minha evolução":
            self._render_evolution(payload)
        else:
            self._render_history(payload)

    def _render_performance(self, payload: dict) -> None:
        latest = _latest_by_indicator(payload["summary"])
        team_index = {
            (str(row["period"]), str(row["indicator_key"])): row
            for row in payload["team_averages"]
        }

        if not latest:
            st.info("Ainda não há resultados individuais processados para este segmento.")
            return

        summary_tab, detail_tab = st.tabs(["Resumo", "Entenda seus números"])

        with summary_tab:
            cols = st.columns(min(3, len(latest)))
            for index, row in enumerate(latest):
                team = team_index.get((str(row["period"]), str(row["indicator_key"])), {})
                value = float(row.get("value") or 0)
                unit = row.get("unit")
                team_avg = team.get("team_avg")
                with cols[index % len(cols)]:
                    st.metric(row["name"], _format_ptbr_metric(value, unit))
                    st.markdown(f"**{_target_text(row)}**")
                    if team_avg is None:
                        st.markdown("**Média da equipe: ainda sem base suficiente**")
                        st.caption("Comparação com a equipe ainda indisponível.")
                    else:
                        team_value = float(team_avg)
                        st.markdown(f"**Média da equipe: {_format_ptbr_metric(team_value, unit)}**")
                        st.caption(_comparison_text(value, team_value, unit))
                    st.caption(f"Volume considerado: {int(row.get('volume') or 0)} · {row['period']}")

            st.subheader("Onde focar")
            for tip in build_tips(latest, payload["team_averages"]):
                st.markdown(f"<div class='cop-tip'>{tip}</div>", unsafe_allow_html=True)

        with detail_tab:
            options = {str(row["name"]): str(row["indicator_key"]) for row in latest}
            selected_name = st.selectbox("Indicador", list(options), key="analyst_detail_indicator")
            self._render_indicator_details(payload, options[selected_name], selected_name)

    def _render_evolution(self, payload: dict) -> None:
        individual = pd.DataFrame(payload.get("individual") or [])
        if individual.empty:
            st.info("Ainda não há evolução diária disponível para este segmento.")
            return

        options = {
            str(row["name"]): str(row["indicator_key"])
            for row in _latest_by_indicator(payload.get("summary") or [])
        }
        if not options:
            st.info("Ainda não há indicadores processados para exibir.")
            return

        selected_name = st.selectbox("Indicador", list(options), key="analyst_evolution_indicator")
        indicator_key = options[selected_name]

        mine = individual[individual["indicator_key"] == indicator_key].copy()
        team = pd.DataFrame(payload.get("team_daily") or [])
        if not team.empty:
            team = team[team["indicator_key"] == indicator_key][["period", "team_avg"]].copy()
        else:
            team = pd.DataFrame(columns=["period", "team_avg"])

        mine = mine[["period", "value", "volume"]].rename(
            columns={"period": "Data", "value": "Meu resultado", "volume": "Volume"}
        )
        merged = mine.merge(team.rename(columns={"period": "Data", "team_avg": "Média da equipe"}), on="Data", how="left")
        merged["Data"] = pd.to_datetime(merged["Data"], errors="coerce")
        merged = merged.dropna(subset=["Data"]).sort_values("Data")

        st.subheader(f"Evolução diária — {selected_name}")
        chart = merged.set_index("Data")[["Meu resultado", "Média da equipe"]]
        st.line_chart(chart, use_container_width=True)

        display = merged.copy()
        display["Data"] = display["Data"].dt.strftime("%d/%m/%Y")
        display["Meu resultado"] = display["Meu resultado"].map(lambda v: _format_ptbr_metric(float(v), _indicator_unit(payload, indicator_key)))
        display["Média da equipe"] = display["Média da equipe"].map(
            lambda v: "—" if pd.isna(v) else _format_ptbr_metric(float(v), _indicator_unit(payload, indicator_key))
        )
        st.dataframe(display, use_container_width=True, hide_index=True)

        self._render_indicator_details(payload, indicator_key, selected_name, compact=True)

    def _render_history(self, payload: dict) -> None:
        summary = pd.DataFrame(payload.get("summary") or [])
        if summary.empty:
            st.info("Ainda não há histórico mensal processado.")
            return

        teams = pd.DataFrame(payload.get("team_averages") or [])
        if teams.empty:
            teams = pd.DataFrame(columns=["period", "indicator_key", "team_avg"])

        history = summary.merge(
            teams[["period", "indicator_key", "team_avg"]],
            on=["period", "indicator_key"],
            how="left",
        )
        rows = []
        for _, row in history.iterrows():
            value = float(row.get("value") or 0)
            team_avg = row.get("team_avg")
            rows.append({
                "Período": str(row["period"]),
                "Indicador": str(row["name"]),
                "Meu resultado": _format_ptbr_metric(value, row.get("unit")),
                "Meta": _target_text(row),
                "Média da equipe": "—" if pd.isna(team_avg) else _format_ptbr_metric(float(team_avg), row.get("unit")),
                "Comparação": "—" if pd.isna(team_avg) else _comparison_text(value, float(team_avg), row.get("unit")),
                "Volume": int(row.get("volume") or 0),
            })

        st.subheader("Histórico mensal")
        st.caption("Somente seus resultados são exibidos. A equipe aparece apenas como média de referência.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    def _render_indicator_details(self, payload: dict, indicator_key: str, indicator_name: str, *, compact: bool = False) -> None:
        details = pd.DataFrame(payload.get("breakdowns") or [])
        if details.empty or "indicator_key" not in details.columns:
            st.info("O detalhamento desse indicador ainda não foi reprocessado com a nova estrutura.")
            return

        details = details[details["indicator_key"] == indicator_key].copy()
        if details.empty:
            st.info("Ainda não há detalhamento individual disponível para este indicador.")
            return

        latest_period = details["period"].dropna().astype(str).max()
        if latest_period:
            details = details[details["period"].astype(str) == latest_period].copy()

        overall = details[details["dimension"] == "overall"]
        if not overall.empty:
            total = int(overall["volume"].sum())
            successes = int(overall["successes"].sum())
            losses = int(overall["losses"].sum())
            tma = _weighted_seconds(overall, "tma_seconds")
            tmr = _weighted_seconds(overall, "tmr_seconds")
            cols = st.columns(4 if indicator_key != "toa_cancellation_rate" else 3)
            if indicator_key == "toa_cancellation_rate":
                cols[0].metric("Volume", total)
                cols[1].metric("Canceladas", losses)
                rate = (losses / total * 100) if total else 0.0
                cols[2].metric("Taxa de cancelamento", f"{rate:.1f}%".replace(".", ","))
            else:
                cols[0].metric("Volume", total)
                cols[1].metric("Aderentes", successes)
                cols[2].metric("Não aderentes", losses)
                if len(cols) > 3:
                    time_value = tmr if indicator_key == "validacao_20m" else tma
                    cols[3].metric("Tempo médio", _format_seconds(time_value))

        if indicator_key == "productivity_avg_daily":
            self._render_productivity_components(details)
            return

        self._render_loss_references(details, indicator_key)

        dimensions = DETAIL_DIMENSIONS.get(indicator_key, ())
        available = [dimension for dimension in dimensions if not details[details["dimension"] == dimension].empty]
        if not available:
            if not compact:
                st.caption("Não há outros recortes operacionais disponíveis nesta carga.")
            return

        st.markdown("#### Onde você ganha e onde precisa recuperar")
        for dimension in available:
            frame = details[details["dimension"] == dimension].copy()
            if frame.empty:
                continue
            label = DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title())
            frame = frame.sort_values(["losses", "volume"], ascending=[False, False])
            table = pd.DataFrame({
                label: frame["dimension_value"].astype(str),
                "Resultado": frame["value"].map(lambda v: f"{float(v):.1f}%".replace(".", ",")),
                "Volume": frame["volume"].astype(int),
                "Aderentes": frame["successes"].astype(int),
                "Não aderentes": frame["losses"].astype(int),
                "Tempo médio": [
                    _format_seconds(tmr if indicator_key == "validacao_20m" else tma)
                    for tma, tmr in zip(frame["tma_seconds"], frame["tmr_seconds"])
                ],
            })
            st.markdown(f"**{label}**")
            st.dataframe(table, use_container_width=True, hide_index=True)

    def _render_loss_references(self, details: pd.DataFrame, indicator_key: str) -> None:
        id_dimensions = ("activity_id",) if indicator_key in ("validacao_20m", "toa_cancellation_rate") else ("incident",)
        refs = details[details["dimension"].isin(id_dimensions)].copy()
        if refs.empty:
            return
        refs = refs[refs["losses"] > 0].copy()
        if refs.empty:
            st.success("Nenhuma ocorrência não aderente identificada nesta carga.")
            return

        refs = refs.sort_values(["day", "losses"], ascending=[False, False])
        title = "Tarefas canceladas para consulta" if indicator_key == "toa_cancellation_rate" else "Ocorrências não aderentes para consulta"
        st.markdown(f"#### {title}")
        table = pd.DataFrame({
            "Data": refs["day"].map(_format_date),
            "Identificador": refs["dimension_value"].astype(str),
            "Perdas": refs["losses"].astype(int),
        })
        st.dataframe(table, use_container_width=True, hide_index=True)

    def _render_productivity_components(self, details: pd.DataFrame) -> None:
        frame = details[details["dimension"] == "productivity_component"].copy()
        st.markdown("#### De onde vem sua produtividade")
        if frame.empty:
            st.info("Reprocesse a planilha de Produtividade para ver a composição do VOL_TOTAL.")
            return
        frame = frame.groupby("dimension_value", as_index=False)["volume"].sum().sort_values("volume", ascending=False)
        table = frame.rename(columns={"dimension_value": "Atividade", "volume": "Volume"})
        table["Volume"] = table["Volume"].astype(int)
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.caption("A produtividade diária vem do VOL_TOTAL; a tabela mostra quais tipos de atividade compõem esse volume.")

def _latest_by_indicator(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row["indicator_key"])
        if key not in latest or str(row["period"]) > str(latest[key]["period"]):
            latest[key] = row
    return sorted(latest.values(), key=lambda row: str(row["name"]))


def _indicator_unit(payload: dict, indicator_key: str) -> str | None:
    for row in payload.get("summary") or []:
        if str(row.get("indicator_key")) == indicator_key:
            return row.get("unit")
    return None


def _format_ptbr_metric(value: float, unit: str | None) -> str:
    formatted = format_metric(value, unit)
    if (unit or "percent").lower() == "percent":
        return formatted.replace(".", ",")
    return formatted


def _target_text(row: dict | pd.Series) -> str:
    target = row.get("target_value")
    direction = row.get("direction")
    unit = row.get("unit")
    return format_target(None if pd.isna(target) else target, unit, direction).replace(".", ",")


def _comparison_text(value: float, team_avg: float, unit: str | None) -> str:
    delta = value - team_avg
    if abs(delta) < 0.05:
        return "Você está praticamente na mesma média da equipe."
    direction = "acima" if delta > 0 else "abaixo"
    if (unit or "percent").lower() == "percent":
        amount = f"{abs(delta):.1f}".replace(".", ",")
        return f"Você está {amount} pontos percentuais {direction} da média da equipe."
    amount = f"{abs(delta):.1f}".replace(".", ",")
    return f"Você está {amount} {direction} da média da equipe."


def _weighted_seconds(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _format_seconds(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    seconds = max(int(round(float(value))), 0)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}min"
    return f"{minutes}min {seconds:02d}s"


def _format_date(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value or "")
    return parsed.strftime("%d/%m/%Y")
