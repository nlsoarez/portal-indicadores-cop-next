from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext, Segment
from src.ui.admin.indicators.productivity import SECTOR_COMPONENTS
from src.ui.admin.leaders_overview import build_peer_performance


def render_dashboard_insights(
    ctx: AccessContext,
    segments: list[Segment],
    dashboard: DashboardService,
) -> None:
    """Insights comparativos dos analistas no Dashboard administrativo."""

    eligible = [
        segment
        for segment in segments
        if segment.slug in {"residencial", "empresarial"}
    ]
    if not eligible:
        return

    payload = dashboard.management_payload(
        ctx,
        [segment.id for segment in eligible],
    )
    analyst_summary = pd.DataFrame(payload.get("analyst_summary", []))
    analyst_breakdowns = pd.DataFrame(payload.get("analyst_breakdowns", []))

    peers = build_peer_performance(
        analyst_summary,
        analyst_breakdowns,
    )
    if peers.empty:
        st.info("Ainda não há dados suficientes para gerar os insights da equipe.")
        return

    insights = build_analyst_insights(peers)
    if not insights:
        st.info("Ainda não há dados suficientes para gerar os insights da equipe.")
        return

    _inject_styles()
    st.markdown("### 💡 Insights — Pontos Fortes e Oportunidades")
    st.caption(
        "Leitura comparativa dos analistas dentro do próprio setor, priorizando volume, "
        "ritmo e componentes que realmente diferenciam a atuação."
    )
    _render_insight_cards(insights)


def build_analyst_insights(peers: pd.DataFrame) -> list[dict]:
    if peers is None or peers.empty:
        return []

    data: list[dict] = []
    ordered = peers.sort_values(
        ["Vol. Total", "Média/Dia", "Nome"],
        ascending=[False, False, True],
    )

    for _, row in ordered.iterrows():
        sector = str(row.get("Setor") or "").upper()
        sector_peers = peers[
            peers["Setor"].astype(str).str.upper() == sector
        ].copy()
        n_peers = len(sector_peers)
        if n_peers < 2:
            continue

        relevant = [
            display
            for _, display in SECTOR_COMPONENTS.get(sector, ())
            if display in peers.columns
        ]

        strengths: list[str] = []
        weaknesses: list[str] = []

        for column in relevant:
            value = _number(row.get(column)) or 0.0
            if value == 0:
                continue

            values = pd.to_numeric(
                sector_peers[column],
                errors="coerce",
            ).fillna(0)

            rank = int((values > value).sum() + 1)
            if rank == 1:
                strengths.append(column)
            elif rank >= n_peers:
                weaknesses.append(column)

        avg_volume = pd.to_numeric(
            sector_peers["Vol. Total"],
            errors="coerce",
        ).dropna().mean()

        volume = _number(row.get("Vol. Total")) or 0.0
        vol_diff = (
            (volume / float(avg_volume) - 1.0) * 100
            if pd.notna(avg_volume) and float(avg_volume) > 0
            else 0.0
        )
        vol_rank = int(
            (
                pd.to_numeric(
                    sector_peers["Vol. Total"],
                    errors="coerce",
                ).fillna(0)
                > volume
            ).sum()
            + 1
        )

        data.append(
            {
                "nome": _short_name(row.get("Nome")),
                "setor": sector,
                "vol_total": int(round(volume)),
                "vol_diff": float(vol_diff),
                "vol_rank": vol_rank,
                "dpa": _number(row.get("DPA %")),
                "strengths": strengths[:4],
                "weaknesses": weaknesses[:4],
                "n_peers": n_peers,
            }
        )

    return data


def _render_insight_cards(insights: list[dict]) -> None:
    left, right = st.columns(2)

    for index, insight in enumerate(insights):
        target = left if index % 2 == 0 else right

        diff = float(insight["vol_diff"])
        border = (
            "#2ecc71"
            if diff >= 10
            else "#e74c3c"
            if diff < -10
            else "#5dade2"
        )
        diff_color = "#2ecc71" if diff >= 0 else "#e74c3c"
        diff_icon = "▲" if diff >= 0 else "▼"

        dpa = insight.get("dpa")
        dpa_text = "—" if dpa is None else f"{float(dpa):.1f}%"

        strength_tags = "".join(
            (
                "<span class='cop-dashboard-tag cop-dashboard-tag-green'>"
                f"{escape(str(label))}</span>"
            )
            for label in insight["strengths"]
        ) or "<span class='cop-dashboard-empty'>—</span>"

        weakness_tags = "".join(
            (
                "<span class='cop-dashboard-tag cop-dashboard-tag-red'>"
                f"{escape(str(label))}</span>"
            )
            for label in insight["weaknesses"]
        ) or "<span class='cop-dashboard-empty'>—</span>"

        with target:
            st.markdown(
                (
                    f"<div class='cop-dashboard-insight' style='border-left-color:{border}'>"
                    "<div class='cop-dashboard-insight-head'>"
                    "<div>"
                    f"<strong>{escape(str(insight['nome']))}</strong>"
                    f"<span class='cop-dashboard-sector'>{_sector_abbrev(insight['setor'])}</span>"
                    f"<span class='cop-dashboard-rank'>#{insight['vol_rank']}/{insight['n_peers']}</span>"
                    "</div>"
                    "<div class='cop-dashboard-metric'>"
                    f"<strong>{insight['vol_total']:,}</strong> "
                    f"<span style='color:{diff_color}'>{diff_icon}{abs(diff):.0f}%</span> "
                    f"<span class='cop-dashboard-dpa'>DPA:{dpa_text}</span>"
                    "</div>"
                    "</div>"
                    "<div class='cop-dashboard-tags'>"
                    "<span class='cop-dashboard-label'>Forte:</span> "
                    f"{strength_tags}"
                    "<span class='cop-dashboard-label cop-dashboard-gap'>Atenção:</span> "
                    f"{weakness_tags}"
                    "</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _short_name(value) -> str:
    # Mesma regra do dashboard legado: primeiro + último sobrenome.
    text = " ".join(str(value or "").split())
    if not text:
        return "—"
    parts = text.split()
    if len(parts) <= 2:
        return text.upper()
    return f"{parts[0]} {parts[-1]}".upper()


def _sector_abbrev(value: str) -> str:
    normalized = str(value or "").upper()
    if normalized == "RESIDENCIAL":
        return "RES"
    if normalized == "EMPRESARIAL":
        return "EMP"
    return normalized[:4] or "—"


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-dashboard-insight {
            background:linear-gradient(180deg, rgba(15,32,52,.96), rgba(9,22,37,.98));
            border:1px solid rgba(148,163,184,.16);
            border-left:3px solid;
            border-radius:14px;
            padding:16px 18px;
            min-height:104px;
            margin-bottom:12px;
            color:#eef5fb;
        }
        .cop-dashboard-insight-head {
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
            font-size:.79rem;
        }
        .cop-dashboard-sector {
            display:inline-block;
            background:rgba(56,189,248,.10);
            border:1px solid rgba(56,189,248,.28);
            color:#9be2ff;
            border-radius:7px;
            padding:2px 7px;
            margin-left:7px;
            font-size:.62rem;
            font-weight:800;
        }
        .cop-dashboard-rank {
            display:inline-block;
            background:rgba(148,163,184,.10);
            border:1px solid rgba(148,163,184,.18);
            color:#cbd7e6;
            border-radius:7px;
            padding:2px 7px;
            margin-left:6px;
            font-size:.61rem;
        }
        .cop-dashboard-insight strong {
            color:#f8fbff;
        }
        .cop-dashboard-metric {
            white-space:nowrap;
            text-align:right;
            color:#dce7f3;
        }
        .cop-dashboard-dpa {
            color:#8fa1b6;
            font-size:.70rem;
            margin-left:6px;
        }
        .cop-dashboard-tags {
            margin-top:9px;
            font-size:.72rem;
        }
        .cop-dashboard-label {
            color:#8fa1b6;
        }
        .cop-dashboard-gap {
            margin-left:9px;
        }
        .cop-dashboard-tag {
            display:inline-block;
            border-radius:7px;
            padding:2px 7px;
            margin-left:4px;
            font-size:.64rem;
            font-weight:700;
        }
        .cop-dashboard-tag-green {
            color:#72e8ad;
            background:rgba(34,197,94,.10);
            border:1px solid rgba(34,197,94,.30);
        }
        .cop-dashboard-tag-red {
            color:#ff8b94;
            background:rgba(239,68,68,.10);
            border:1px solid rgba(239,68,68,.32);
        }
        .cop-dashboard-empty {
            color:#66788d;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
