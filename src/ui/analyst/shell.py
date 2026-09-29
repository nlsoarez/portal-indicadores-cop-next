from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.application.segment_context import switch_segment_state
from src.domain.entities import AccessContext, Segment
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
    "nature": "Natureza",
    "impact": "Impacto",
    "solution": "Solução",
    "city": "Cidade",
    "technology": "Tecnologia",
    "type": "Tipo",
}

DETAIL_DIMENSIONS = {
    "res_etit_fibra_hfc": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "res_etit_gpon": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "res_assert_fibra_hfc": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "res_assert_gpon": ("service", "group", "city", "technology", "nature", "impact", "solution"),
    "emp_etit_event": ("demand", "type", "area", "cause", "group", "city"),
    "validacao_20m": ("group", "network", "activity_type", "incident_type", "aging"),
    "chat_10m": ("base", "queue_type", "queue", "hour"),
    "closing_assertiveness": ("demand", "cause_toa", "cause_sir", "area_involved", "group"),
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
            "Meu segmento",
            segments,
            format_func=lambda item: item.name,
            key="analyst_segment_selector",
        )
        switch_segment_state(st.session_state, segment.id)
        page = st.sidebar.radio(
            "Navegação",
            ["Meu painel", "Histórico"],
            label_visibility="collapsed",
        )

        st.markdown("<div class='cop-eyebrow'>Desempenho individual</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='cop-title'>Olá, {ctx.user.display_name}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='cop-subtitle'>Somente seus resultados e médias agregadas da equipe. "
            "Nenhum número individual de outro analista é exibido.</div>",
            unsafe_allow_html=True,
        )

        payload = self.dashboard.analyst_payload(ctx, segment.id)
        render_indicator_freshness(payload.get("freshness") or [])

        if page == "Meu painel":
            self._render_panel(payload)
        else:
            self._render_history(payload)

    def _render_panel(self, payload: dict) -> None:
        latest = _latest_by_indicator(payload.get("summary") or [])
        if not latest:
            st.info("Ainda não há resultados individuais processados para este segmento.")
            return

        team_index = {
            (str(row.get("period")), str(row.get("indicator_key"))): row
            for row in payload.get("team_averages") or []
        }

        st.markdown("### Minha situação")
        overview_rows = []
        for row in latest:
            period = str(row.get("period"))
            key = str(row.get("indicator_key"))
            team = team_index.get((period, key), {})
            value = _number(row.get("value"))
            team_avg = _number(team.get("team_avg"))
            overview_rows.append({
                "Indicador": str(row.get("name") or key),
                "Meu resultado": _format_ptbr_metric(value, row.get("unit")),
                "Média da equipe": "—" if team_avg is None else _format_ptbr_metric(team_avg, row.get("unit")),
                "Comparação": _comparison_label(value, team_avg, str(row.get("direction") or "higher_is_better"), row.get("unit")),
                "Meta": _target_text(row),
                "Volume": int(row.get("volume") or 0),
            })
        st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)

        options = {str(row.get("name") or row.get("indicator_key")): str(row.get("indicator_key")) for row in latest}
        selected_name = st.selectbox("Analisar indicador", list(options), key="analyst_indicator_focus")
        indicator_key = options[selected_name]
        row = next(item for item in latest if str(item.get("indicator_key")) == indicator_key)
        team = team_index.get((str(row.get("period")), indicator_key), {})
        self._render_indicator(payload, row, team)

    def _render_indicator(self, payload: dict, row: dict, team: dict) -> None:
        indicator_key = str(row.get("indicator_key"))
        indicator_name = str(row.get("name") or indicator_key)
        unit = row.get("unit")
        direction = str(row.get("direction") or "higher_is_better")
        value = _number(row.get("value"))
        team_avg = _number(team.get("team_avg"))

        st.markdown(f"### {indicator_name}")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Meu resultado", _format_ptbr_metric(value, unit))
        c2.metric("Média da equipe", "—" if team_avg is None else _format_ptbr_metric(team_avg, unit))
        c3.metric("Comparação", _comparison_label(value, team_avg, direction, unit))
        c4.metric("Meta", _target_metric(row))
        c5.metric("Meu volume", int(row.get("volume") or 0))

        details = _latest_indicator_rows(payload.get("breakdowns") or [], indicator_key)
        team_details = _latest_indicator_rows(payload.get("team_breakdowns") or [], indicator_key)

        if indicator_key == "emp_etit_event":
            self._render_ral_rec(details, team_details)

        self._render_focus(details, team_details, indicator_key, direction)
        self._render_loss_references(details, indicator_key)
        self._render_full_detail(details, team_details, indicator_key, direction)
        self._render_recent_evolution(payload, indicator_key, unit)

    def _render_ral_rec(self, details: pd.DataFrame, team_details: pd.DataFrame) -> None:
        mine = _dimension_rows(details, "demand")
        if mine.empty:
            return
        mine = mine[mine["dimension_value"].astype(str).str.upper().isin(("RAL", "REC"))].copy()
        if mine.empty:
            return

        team = _dimension_rows(team_details, "demand")
        st.markdown("#### RAL e REC")
        rows = []
        for demand in ("RAL", "REC"):
            part = mine[mine["dimension_value"].astype(str).str.upper() == demand]
            if part.empty:
                continue
            volume = int(pd.to_numeric(part["volume"], errors="coerce").fillna(0).sum())
            successes = int(pd.to_numeric(part["successes"], errors="coerce").fillna(0).sum())
            losses = int(pd.to_numeric(part["losses"], errors="coerce").fillna(0).sum())
            my_result = successes / volume * 100 if volume else None

            team_part = team[team["dimension_value"].astype(str).str.upper() == demand] if not team.empty else pd.DataFrame()
            team_avg = _weighted_team_avg(team_part)

            rows.append({
                "Demanda": demand,
                "Meu resultado": _pct(my_result),
                "Média da equipe": _pct(team_avg),
                "Comparação": _comparison_label(my_result, team_avg, "higher_is_better", "percent"),
                "Volume": volume,
                "Aderentes": successes,
                "Não aderentes": losses,
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    def _render_focus(
        self,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
        indicator_key: str,
        direction: str,
    ) -> None:
        if details.empty:
            st.info("Reprocesse a fonte para liberar o diagnóstico individual desse indicador.")
            return

        dimensions = DETAIL_DIMENSIONS.get(indicator_key, ())
        candidates = []
        for dimension in dimensions:
            mine = _dimension_rows(details, dimension)
            if mine.empty:
                continue
            for _, item in mine.iterrows():
                losses = int(item.get("losses") or 0)
                if losses <= 0:
                    continue
                value = _number(item.get("value"))
                team_avg = _team_value(team_details, dimension, str(item.get("dimension_value")))
                candidates.append({
                    "Foco": DIMENSION_LABELS.get(dimension, dimension),
                    "Onde": str(item.get("dimension_value") or "—"),
                    "Meu resultado": _format_ptbr_metric(value, "percent"),
                    "Média da equipe": "—" if team_avg is None else _format_ptbr_metric(team_avg, "percent"),
                    "Comparação": _comparison_label(value, team_avg, direction, "percent"),
                    "Volume": int(item.get("volume") or 0),
                    "Erros": losses,
                    "_losses": losses,
                    "_volume": int(item.get("volume") or 0),
                })

        st.markdown("#### Onde focar primeiro")
        if not candidates:
            st.success("Nenhuma concentração relevante de erro foi encontrada nos recortes disponíveis.")
            return

        candidates = sorted(candidates, key=lambda item: (item["_losses"], item["_volume"]), reverse=True)[:6]
        table = pd.DataFrame([{k: v for k, v in item.items() if not k.startswith("_")} for item in candidates])
        st.dataframe(table, use_container_width=True, hide_index=True)

    def _render_loss_references(self, details: pd.DataFrame, indicator_key: str) -> None:
        if details.empty:
            return
        dimensions = ("activity_id",) if indicator_key in ("validacao_20m", "toa_cancellation_rate") else ("incident",)
        refs = details[details["dimension"].isin(dimensions)].copy()
        if refs.empty:
            return
        refs["losses"] = pd.to_numeric(refs["losses"], errors="coerce").fillna(0)
        refs = refs[refs["losses"] > 0].copy()
        if refs.empty:
            return

        refs = refs.sort_values(["day", "losses"], ascending=[False, False])
        rows = []
        for _, item in refs.iterrows():
            raw = str(item.get("dimension_value") or "").strip()
            demand = ""
            identifier = raw
            if "|||" in raw:
                demand, identifier = raw.split("|||", 1)
            rows.append({
                "Data": _format_date(item.get("day")),
                "Demanda": demand or "—",
                "Identificador": identifier or "—",
                "Perdas": int(item.get("losses") or 0),
            })

        title = "INC / ocorrências para revisar"
        if indicator_key == "toa_cancellation_rate":
            title = "Tarefas canceladas para revisar"
        elif indicator_key == "validacao_20m":
            title = "Atividades fora da aderência para revisar"

        st.markdown(f"#### {title}")
        if indicator_key == "emp_etit_event":
            st.caption("Os RAL/REC não aderentes aparecem com o número da NOTA/INC para consulta no sistema.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    def _render_full_detail(
        self,
        details: pd.DataFrame,
        team_details: pd.DataFrame,
        indicator_key: str,
        direction: str,
    ) -> None:
        if details.empty:
            return
        dimensions = [
            dimension
            for dimension in DETAIL_DIMENSIONS.get(indicator_key, ())
            if not _dimension_rows(details, dimension).empty
        ]
        if not dimensions:
            return

        with st.expander("Ver detalhamento completo", expanded=False):
            dimension = st.selectbox(
                "Analisar meus resultados por",
                dimensions,
                format_func=lambda value: DIMENSION_LABELS.get(value, value),
                key=f"analyst_dimension_{indicator_key}",
            )
            mine = _dimension_rows(details, dimension).copy()
            mine["losses"] = pd.to_numeric(mine["losses"], errors="coerce").fillna(0)
            mine["volume"] = pd.to_numeric(mine["volume"], errors="coerce").fillna(0)
            mine = mine.sort_values(["losses", "volume"], ascending=[False, False])

            rows = []
            for _, item in mine.iterrows():
                value = _number(item.get("value"))
                category = str(item.get("dimension_value") or "—")
                team_avg = _team_value(team_details, dimension, category)
                rows.append({
                    DIMENSION_LABELS.get(dimension, dimension): category,
                    "Meu resultado": _format_ptbr_metric(value, "percent"),
                    "Média da equipe": "—" if team_avg is None else _format_ptbr_metric(team_avg, "percent"),
                    "Comparação": _comparison_label(value, team_avg, direction, "percent"),
                    "Volume": int(item.get("volume") or 0),
                    "Erros": int(item.get("losses") or 0),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    def _render_recent_evolution(self, payload: dict, indicator_key: str, unit: str | None) -> None:
        individual = pd.DataFrame(payload.get("individual") or [])
        if individual.empty or "indicator_key" not in individual.columns:
            return
        mine = individual[individual["indicator_key"] == indicator_key].copy()
        if mine.empty:
            return

        team = pd.DataFrame(payload.get("team_daily") or [])
        if not team.empty and "indicator_key" in team.columns:
            team = team[team["indicator_key"] == indicator_key][["period", "team_avg"]].copy()
        else:
            team = pd.DataFrame(columns=["period", "team_avg"])

        mine = mine[["period", "value", "volume"]].rename(
            columns={"period": "Data", "value": "Meu resultado", "volume": "Volume"}
        )
        merged = mine.merge(
            team.rename(columns={"period": "Data", "team_avg": "Média da equipe"}),
            on="Data",
            how="left",
        )
        merged["Data"] = pd.to_datetime(merged["Data"], errors="coerce")
        merged = merged.dropna(subset=["Data"]).sort_values("Data", ascending=False).head(7)
        if merged.empty:
            return

        merged["Data"] = merged["Data"].dt.strftime("%d/%m/%Y")
        merged["Meu resultado"] = merged["Meu resultado"].map(
            lambda value: _format_ptbr_metric(_number(value), unit)
        )
        merged["Média da equipe"] = merged["Média da equipe"].map(
            lambda value: "—" if pd.isna(value) else _format_ptbr_metric(_number(value), unit)
        )
        st.markdown("#### Últimos dias")
        st.dataframe(merged, use_container_width=True, hide_index=True)

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
            value = _number(row.get("value"))
            team_avg = _number(row.get("team_avg"))
            rows.append({
                "Período": str(row.get("period")),
                "Indicador": str(row.get("name")),
                "Meu resultado": _format_ptbr_metric(value, row.get("unit")),
                "Média da equipe": "—" if team_avg is None else _format_ptbr_metric(team_avg, row.get("unit")),
                "Comparação": _comparison_label(
                    value,
                    team_avg,
                    str(row.get("direction") or "higher_is_better"),
                    row.get("unit"),
                ),
                "Meta": _target_text(row),
                "Volume": int(row.get("volume") or 0),
            })

        st.markdown("### Histórico mensal")
        st.caption("A equipe aparece somente como média agregada de referência.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _latest_by_indicator(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("indicator_key"))
        if key not in latest or str(row.get("period")) > str(latest[key].get("period")):
            latest[key] = row
    return sorted(latest.values(), key=lambda row: str(row.get("name") or ""))


def _latest_indicator_rows(rows: list[dict], indicator_key: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows or [])
    if frame.empty or "indicator_key" not in frame.columns:
        return pd.DataFrame()
    frame = frame[frame["indicator_key"].astype(str) == indicator_key].copy()
    if frame.empty:
        return frame
    if "period" in frame.columns:
        latest_period = frame["period"].dropna().astype(str).max()
        frame = frame[frame["period"].astype(str) == latest_period].copy()
    return frame


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None or frame.empty or "dimension" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["dimension"].astype(str) == dimension].copy()


def _team_value(team_details: pd.DataFrame, dimension: str, value: str) -> float | None:
    rows = _dimension_rows(team_details, dimension)
    if rows.empty or "dimension_value" not in rows.columns:
        return None
    rows = rows[rows["dimension_value"].astype(str) == str(value)]
    return _weighted_team_avg(rows)


def _weighted_team_avg(rows: pd.DataFrame) -> float | None:
    if rows is None or rows.empty:
        return None
    if "team_avg" not in rows.columns:
        return None
    values = pd.to_numeric(rows["team_avg"], errors="coerce")
    weights = pd.to_numeric(rows.get("team_volume"), errors="coerce").fillna(0)
    valid = values.notna() & weights.gt(0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _target_metric(row: dict | pd.Series) -> str:
    target = row.get("target_value")
    if target is None or pd.isna(target):
        return "—"
    return _format_ptbr_metric(float(target), row.get("unit"))


def _target_text(row: dict | pd.Series) -> str:
    target = row.get("target_value")
    direction = row.get("direction")
    unit = row.get("unit")
    return format_target(None if target is None or pd.isna(target) else target, unit, direction).replace(".", ",")


def _comparison_label(
    value: float | None,
    team_avg: float | None,
    direction: str,
    unit: str | None,
) -> str:
    if value is None or team_avg is None:
        return "—"
    delta = value - team_avg
    if abs(delta) < 0.05:
        return "Na média"

    favorable = delta > 0 if direction != "lower_is_better" else delta < 0
    label = "melhor" if favorable else "pior"
    if (unit or "percent").lower() == "percent":
        amount = f"{abs(delta):.1f}".replace(".", ",")
        return f"{amount} pp {label}"
    amount = f"{abs(delta):.1f}".replace(".", ",")
    return f"{amount} {label}"


def _format_ptbr_metric(value: float | None, unit: str | None) -> str:
    if value is None:
        return "—"
    formatted = format_metric(value, unit)
    if (unit or "percent").lower() == "percent":
        return formatted.replace(".", ",")
    return formatted


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%".replace(".", ",")


def _number(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_date(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value or "")
    return parsed.strftime("%d/%m/%Y")
