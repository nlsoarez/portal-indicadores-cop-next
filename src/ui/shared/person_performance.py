from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext, User


def render_person_performance(
    ctx: AccessContext,
    segment_id: int,
    target: User,
    dashboard: DashboardService,
    *,
    comparison_label: str = "média dos analistas",
) -> None:
    payload = dashboard.analyst_payload(ctx, segment_id, target.id)
    latest = _latest_by_indicator(payload["summary"])
    team_index = {
        (row["period"], row["indicator_key"]): row
        for row in payload["team_averages"]
    }

    st.markdown(f"### {target.display_name}")
    st.caption(f"{target.login} · {target.full_name}")

    if not latest:
        st.info("Ainda não há indicadores processados para este usuário.")
        return

    columns = st.columns(min(3, len(latest)))
    for index, row in enumerate(latest):
        team = team_index.get((row["period"], row["indicator_key"]), {})
        value = float(row.get("value") or 0)
        team_avg = team.get("team_avg")
        delta = (
            None
            if team_avg is None
            else f"{value - float(team_avg):+.1f} p.p. vs {comparison_label}"
        )
        with columns[index % len(columns)]:
            st.metric(row["name"], f"{value:.1f}%", delta=delta)
            target_value = row.get("target_value")
            meta = f"Meta ≥ {float(target_value):.0f}%" if target_value is not None else "Sem meta"
            st.caption(f"{meta} · Volume {int(row.get('volume') or 0)} · {row['period']}")

    with st.expander("Evolução diária", expanded=False):
        st.dataframe(
            pd.DataFrame(payload["individual"]),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Histórico mensal", expanded=False):
        st.dataframe(
            pd.DataFrame(payload["summary"]),
            use_container_width=True,
            hide_index=True,
        )


def _latest_by_indicator(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row["indicator_key"])
        if key not in latest or str(row["period"]) > str(latest[key]["period"]):
            latest[key] = row
    return sorted(latest.values(), key=lambda row: str(row["name"]))
