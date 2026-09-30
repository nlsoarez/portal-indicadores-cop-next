from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext, Segment, User
from src.infrastructure.repositories import UserRepository
from src.ui.admin.indicators.productivity import SECTOR_COMPONENTS


PRODUCTIVITY_KEY = "productivity_avg_daily"
DPA_KEY = "dpa_official"


def render_leaders_overview(
    ctx: AccessContext,
    segments: list[Segment],
    dashboard: DashboardService,
    access: AccessService,
    users: UserRepository,
) -> None:
    """Visão consolidada dos líderes, baseada no dashboard legado."""

    _inject_styles()

    leaders = access.visible_subadmins(ctx)
    if not leaders:
        st.info("Nenhum líder cadastrado.")
        return

    segment_map = {
        segment.id: segment
        for segment in segments
        if segment.slug in {"residencial", "empresarial"}
    }
    if not segment_map:
        st.info("Nenhum segmento operacional elegível para a visão dos líderes.")
        return

    team_payload = dashboard.management_payload(ctx, list(segment_map))
    analyst_summary = pd.DataFrame(team_payload.get("analyst_summary", []))
    analyst_breakdowns = pd.DataFrame(team_payload.get("analyst_breakdowns", []))

    peers = build_peer_performance(analyst_summary, analyst_breakdowns)
    leader_rows: list[dict] = []

    for leader in leaders:
        performance_segments = users.performance_segments_for_user(leader.id)
        perf_segment = next(
            (
                item
                for item in performance_segments
                if item.slug in {"residencial", "empresarial"}
            ),
            None,
        )
        if perf_segment is None:
            continue

        payload = dashboard.analyst_payload(
            ctx,
            perf_segment.id,
            leader.id,
        )
        leader_rows.append(
            build_leader_performance(
                leader,
                perf_segment,
                payload,
            )
        )

    if not leader_rows:
        st.info("Nenhum líder possui dados operacionais para os segmentos Residencial ou Empresarial.")
        return

    leaders_df = pd.DataFrame(leader_rows)
    leaders_df = leaders_df.sort_values(
        ["Vol. Total", "Média/Dia", "Líder"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    all_people = combine_leaders_and_peers(leaders_df, peers)
    leaders_df = enrich_leader_comparison(leaders_df, peers, all_people)

    st.caption("Comparação entre os líderes e as médias das suas equipes.")
    _render_leader_cards(leaders_df)

    st.divider()
    st.markdown("### 📊 Comparação Detalhada")
    st.caption(
        "Volume, média diária e composição de atividades lado a lado para comparar "
        "cada liderança com a realidade da própria equipe."
    )
    detail = leader_detail_table(leaders_df)
    st.dataframe(
        style_leader_detail(detail),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.markdown("### 💡 Insights dos Líderes")
    st.caption(
        "Sinais comparativos para orientar acompanhamento; use os destaques como ponto de "
        "partida para investigação, não como avaliação isolada."
    )
    insights = build_leader_insights(leaders_df, all_people)
    _render_insight_cards(insights)


def build_peer_performance(
    analyst_summary: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
) -> pd.DataFrame:
    if analyst_summary is None or analyst_summary.empty:
        return pd.DataFrame()

    prod = analyst_summary[
        analyst_summary["indicator_key"].astype(str) == PRODUCTIVITY_KEY
    ].copy()
    if prod.empty:
        return pd.DataFrame()

    prod["login"] = prod["login"].astype(str).str.upper()
    prod["Setor"] = prod["segment_name"].fillna("—").astype(str).str.upper()
    prod["Analista"] = prod["display_name"].fillna(prod["login"])
    prod["Dias"] = pd.to_numeric(prod["volume"], errors="coerce").fillna(0)
    prod["Média/Dia"] = pd.to_numeric(prod["value"], errors="coerce")

    exact_totals = exact_total_map(analyst_breakdowns)
    prod["Vol. Total"] = prod.apply(
        lambda row: exact_totals.get(
            (str(row["login"]), str(row["Setor"])),
            _fallback_total(row["Média/Dia"], row["Dias"]),
        ),
        axis=1,
    )

    dpa = analyst_summary[
        analyst_summary["indicator_key"].astype(str) == DPA_KEY
    ].copy()
    dpa_map: dict[tuple[str, str], float] = {}
    if not dpa.empty:
        dpa["login"] = dpa["login"].astype(str).str.upper()
        dpa["Setor"] = dpa["segment_name"].fillna("—").astype(str).str.upper()
        dpa["value"] = pd.to_numeric(dpa["value"], errors="coerce")
        for _, row in dpa[dpa["value"].notna()].iterrows():
            dpa_map[(row["login"], row["Setor"])] = float(row["value"])

    component_map = productivity_component_map(analyst_breakdowns)
    component_columns = all_component_labels()

    records: list[dict] = []
    for _, row in prod.iterrows():
        login = str(row["login"])
        sector = str(row["Setor"])
        item = {
            "login": login,
            "Nome": row["Analista"],
            "Setor": sector,
            "Vol. Total": int(round(float(row["Vol. Total"] or 0))),
            "Dias": int(round(float(row["Dias"] or 0))),
            "Média/Dia": _number(row["Média/Dia"]) or 0.0,
            "DPA %": dpa_map.get((login, sector)),
            "is_leader": False,
        }
        components = component_map.get((login, sector), {})
        for column in component_columns:
            item[column] = int(round(float(components.get(column, 0) or 0)))
        records.append(item)

    return pd.DataFrame(records)


def build_leader_performance(
    leader: User,
    segment: Segment,
    payload: dict,
) -> dict:
    summary = pd.DataFrame(payload.get("summary", []))
    breakdowns = pd.DataFrame(payload.get("breakdowns", []))

    prod = latest_indicator_row(summary, PRODUCTIVITY_KEY)
    dpa = latest_indicator_row(summary, DPA_KEY)

    average = _number(prod.get("value")) if prod is not None else None
    days = _number(prod.get("volume")) if prod is not None else None

    exact = leader_exact_total(breakdowns)
    total = exact if exact is not None else _fallback_total(average, days)

    components = leader_components(breakdowns)
    sector = str(segment.name).upper()

    leader_name = _short_name(
        getattr(leader, "full_name", None) or getattr(leader, "display_name", None)
    )
    item = {
        "login": str(leader.login).upper(),
        "Líder": leader_name,
        "Nome": leader_name,
        "Setor": sector,
        "Vol. Total": int(round(total or 0)),
        "Dias": int(round(days or 0)),
        "Média/Dia": average or 0.0,
        "DPA %": _number(dpa.get("value")) if dpa is not None else None,
        "is_leader": True,
    }

    for column in all_component_labels():
        item[column] = int(round(float(components.get(column, 0) or 0)))

    return item


def latest_indicator_row(
    summary: pd.DataFrame,
    indicator_key: str,
) -> dict | None:
    if (
        summary is None
        or summary.empty
        or not {"indicator_key", "period"}.issubset(summary.columns)
    ):
        return None

    rows = summary[
        summary["indicator_key"].astype(str) == indicator_key
    ].copy()
    if rows.empty:
        return None

    rows["_period"] = rows["period"].astype(str)
    return rows.sort_values("_period").iloc[-1].to_dict()


def leader_exact_total(breakdowns: pd.DataFrame) -> float | None:
    if breakdowns is None or breakdowns.empty:
        return None
    required = {"indicator_key", "dimension", "successes"}
    if not required.issubset(breakdowns.columns):
        return None

    rows = breakdowns[
        (breakdowns["indicator_key"].astype(str) == PRODUCTIVITY_KEY)
        & (breakdowns["dimension"].astype(str) == "productivity_total")
    ].copy()
    if rows.empty:
        return None

    return float(
        pd.to_numeric(rows["successes"], errors="coerce")
        .fillna(0)
        .sum()
    )


def leader_components(breakdowns: pd.DataFrame) -> dict[str, float]:
    if breakdowns is None or breakdowns.empty:
        return {}
    required = {"indicator_key", "dimension", "dimension_value", "successes"}
    if not required.issubset(breakdowns.columns):
        return {}

    rows = breakdowns[
        (breakdowns["indicator_key"].astype(str) == PRODUCTIVITY_KEY)
        & (breakdowns["dimension"].astype(str) == "productivity_component")
    ].copy()
    if rows.empty:
        return {}

    rows["successes"] = pd.to_numeric(rows["successes"], errors="coerce").fillna(0)
    grouped = rows.groupby("dimension_value", dropna=False)["successes"].sum()
    return {
        display_label(str(label)): float(value)
        for label, value in grouped.items()
        if str(label).strip()
    }


def exact_total_map(
    analyst_breakdowns: pd.DataFrame,
) -> dict[tuple[str, str], float]:
    if analyst_breakdowns is None or analyst_breakdowns.empty:
        return {}
    required = {"login", "segment_name", "indicator_key", "dimension", "successes"}
    if not required.issubset(analyst_breakdowns.columns):
        return {}

    rows = analyst_breakdowns[
        (analyst_breakdowns["indicator_key"].astype(str) == PRODUCTIVITY_KEY)
        & (analyst_breakdowns["dimension"].astype(str) == "productivity_total")
    ].copy()
    if rows.empty:
        return {}

    rows["login"] = rows["login"].astype(str).str.upper()
    rows["Setor"] = rows["segment_name"].fillna("—").astype(str).str.upper()
    rows["successes"] = pd.to_numeric(rows["successes"], errors="coerce").fillna(0)

    grouped = (
        rows.groupby(["login", "Setor"], dropna=False)["successes"]
        .sum()
        .reset_index()
    )
    return {
        (str(row["login"]), str(row["Setor"])): float(row["successes"])
        for _, row in grouped.iterrows()
    }


def productivity_component_map(
    analyst_breakdowns: pd.DataFrame,
) -> dict[tuple[str, str], dict[str, float]]:
    if analyst_breakdowns is None or analyst_breakdowns.empty:
        return {}
    required = {
        "login",
        "segment_name",
        "indicator_key",
        "dimension",
        "dimension_value",
        "successes",
    }
    if not required.issubset(analyst_breakdowns.columns):
        return {}

    rows = analyst_breakdowns[
        (analyst_breakdowns["indicator_key"].astype(str) == PRODUCTIVITY_KEY)
        & (analyst_breakdowns["dimension"].astype(str) == "productivity_component")
    ].copy()
    if rows.empty:
        return {}

    rows["login"] = rows["login"].astype(str).str.upper()
    rows["Setor"] = rows["segment_name"].fillna("—").astype(str).str.upper()
    rows["successes"] = pd.to_numeric(rows["successes"], errors="coerce").fillna(0)
    rows["Label"] = rows["dimension_value"].astype(str).apply(display_label)

    grouped = (
        rows.groupby(["login", "Setor", "Label"], dropna=False)["successes"]
        .sum()
        .reset_index()
    )

    output: dict[tuple[str, str], dict[str, float]] = {}
    for _, row in grouped.iterrows():
        key = (str(row["login"]), str(row["Setor"]))
        output.setdefault(key, {})[str(row["Label"])] = float(row["successes"])
    return output


def display_label(source: str) -> str:
    mapping = {
        source_name: display
        for components in SECTOR_COMPONENTS.values()
        for source_name, display in components
    }
    return mapping.get(source, source)


def all_component_labels() -> list[str]:
    preferred = [
        "Ab. New Monitor",
        "Fech. New Monitor",
        "Ab. SGO",
        "Fech. SGO",
        "Trat. RAL",
        "Trat. REC",
        "Ab. Remedy",
        "Ligações Realiz.",
        "1ª Interação TOA",
        "Fech. Tarefa TOA",
    ]
    return preferred


def combine_leaders_and_peers(
    leaders: pd.DataFrame,
    peers: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "login",
        "Nome",
        "Setor",
        "Vol. Total",
        "Dias",
        "Média/Dia",
        "DPA %",
        "is_leader",
        *all_component_labels(),
    ]

    parts = []
    for frame in (peers, leaders):
        if frame is None or frame.empty:
            continue
        prepared = frame.copy()
        for column in columns:
            if column not in prepared.columns:
                prepared[column] = 0 if column in all_component_labels() else None
        parts.append(prepared[columns])

    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)


def enrich_leader_comparison(
    leaders: pd.DataFrame,
    peers: pd.DataFrame,
    all_people: pd.DataFrame,
) -> pd.DataFrame:
    result = leaders.copy()
    result["vs Equipe Vol. %"] = 0.0
    result["vs Equipe Média %"] = 0.0
    result["Rank"] = 0
    result["Peers"] = 0

    for index, row in result.iterrows():
        sector = str(row["Setor"]).upper()
        team = peers[
            peers["Setor"].astype(str).str.upper() == sector
        ] if peers is not None and not peers.empty else pd.DataFrame()

        avg_vol = (
            pd.to_numeric(team["Vol. Total"], errors="coerce").dropna().mean()
            if not team.empty
            else None
        )
        avg_daily = (
            pd.to_numeric(team["Média/Dia"], errors="coerce").dropna().mean()
            if not team.empty
            else None
        )

        result.at[index, "vs Equipe Vol. %"] = percent_vs(row["Vol. Total"], avg_vol)
        result.at[index, "vs Equipe Média %"] = percent_vs(row["Média/Dia"], avg_daily)

        sector_all = all_people[
            all_people["Setor"].astype(str).str.upper() == sector
        ] if all_people is not None and not all_people.empty else pd.DataFrame()
        if not sector_all.empty:
            result.at[index, "Rank"] = int(
                (pd.to_numeric(sector_all["Vol. Total"], errors="coerce") > float(row["Vol. Total"])).sum()
                + 1
            )
            result.at[index, "Peers"] = int(len(sector_all))

    return result


def leader_detail_table(leaders: pd.DataFrame) -> pd.DataFrame:
    if leaders is None or leaders.empty:
        return pd.DataFrame()

    table = leaders.sort_values(
        ["Vol. Total", "Média/Dia", "Líder"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    table.insert(0, "#", range(1, len(table) + 1))

    columns = [
        "#",
        "Líder",
        "Setor",
        "Vol. Total",
        "Dias",
        "Média/Dia",
        *all_component_labels(),
    ]
    return table[columns]


def build_leader_insights(
    leaders: pd.DataFrame,
    all_people: pd.DataFrame,
) -> list[dict]:
    if leaders is None or leaders.empty:
        return []

    insights: list[dict] = []
    for _, row in leaders.iterrows():
        sector = str(row["Setor"]).upper()
        peers = all_people[
            all_people["Setor"].astype(str).str.upper() == sector
        ].copy()
        if peers.empty:
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

            peer_values = pd.to_numeric(peers[column], errors="coerce").fillna(0)
            rank = int((peer_values > value).sum() + 1)
            if rank == 1:
                strengths.append(column)
            elif rank >= len(peers):
                weaknesses.append(column)

        insights.append(
            {
                "nome": row["Líder"],
                "setor": sector,
                "vol_total": int(row["Vol. Total"]),
                "vol_diff": float(row.get("vs Equipe Vol. %") or 0),
                "rank": int(row.get("Rank") or 0),
                "peers": int(row.get("Peers") or len(peers)),
                "dpa": row.get("DPA %"),
                "strengths": strengths[:4],
                "weaknesses": weaknesses[:4],
            }
        )

    return insights


def style_leader_detail(frame: pd.DataFrame):
    styler = frame.style.format(
        {
            "Média/Dia": "{:.1f}",
            "Dias": "{:.0f}",
        },
        na_rep="—",
    )
    if "Vol. Total" in frame.columns:
        styler = styler.background_gradient(
            cmap="YlOrBr",
            subset=["Vol. Total"],
        )
    return styler


def percent_vs(value, benchmark) -> float:
    value_num = _number(value)
    benchmark_num = _number(benchmark)
    if value_num is None or benchmark_num is None or benchmark_num <= 0:
        return 0.0
    return (value_num / benchmark_num - 1.0) * 100.0


def _render_leader_cards(leaders: pd.DataFrame) -> None:
    ordered = leaders.sort_values(
        ["Vol. Total", "Líder"],
        ascending=[False, True],
    ).reset_index(drop=True)

    per_row = min(4, max(1, len(ordered)))
    for start in range(0, len(ordered), per_row):
        chunk = ordered.iloc[start:start + per_row]
        cols = st.columns(per_row)
        for column, (_, row) in zip(cols, chunk.iterrows()):
            sector_badge = _sector_abbrev(row["Setor"])
            dpa = _number(row.get("DPA %"))
            dpa_text = "—" if dpa is None else f"{dpa:.1f}%"
            vol_diff = float(row.get("vs Equipe Vol. %") or 0)
            avg_diff = float(row.get("vs Equipe Média %") or 0)

            with column:
                st.markdown(
                    (
                        "<div class='cop-leader-card'>"
                        "<div class='cop-leader-card-head'>"
                        f"<strong>{escape(str(row['Líder']))}</strong>"
                        f"<span class='cop-leader-badge'>{sector_badge}</span>"
                        "</div>"
                        f"<div class='cop-leader-volume'>{int(row['Vol. Total']):,}</div>"
                        "<div class='cop-leader-stat'>"
                        f"Média: {float(row['Média/Dia']):.1f}/dia · "
                        f"Dias: {int(row['Dias'])} · DPA: {dpa_text}"
                        "</div>"
                        "<div class='cop-leader-stat cop-leader-vs'>"
                        "vs Equipe: "
                        f"{_delta_html(vol_diff, 'vol')} · "
                        f"{_delta_html(avg_diff, 'média')}"
                        "</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )


def _render_insight_cards(insights: list[dict]) -> None:
    if not insights:
        st.caption("Sem dados suficientes para gerar os insights dos líderes.")
        return

    left, right = st.columns(2)
    for index, insight in enumerate(insights):
        target = left if index % 2 == 0 else right
        diff = float(insight["vol_diff"])
        border = "#2ecc71" if diff >= 10 else "#e74c3c" if diff < -10 else "#5dade2"
        color = "#2ecc71" if diff >= 0 else "#e74c3c"
        icon = "▲" if diff >= 0 else "▼"
        dpa = _number(insight.get("dpa"))
        dpa_text = "—" if dpa is None else f"{dpa:.1f}%"

        strong_tags = "".join(
            f"<span class='cop-leader-tag-green'>{escape(value)}</span>"
            for value in insight["strengths"]
        ) or "<span class='cop-leader-empty'>—</span>"
        weak_tags = "".join(
            f"<span class='cop-leader-tag-red'>{escape(value)}</span>"
            for value in insight["weaknesses"]
        ) or "<span class='cop-leader-empty'>—</span>"

        with target:
            st.markdown(
                (
                    f"<div class='cop-leader-insight' style='border-left-color:{border}'>"
                    "<div class='cop-leader-insight-head'>"
                    "<div>"
                    f"<strong>{escape(str(insight['nome']))}</strong>"
                    f"<span class='cop-leader-badge'>{_sector_abbrev(insight['setor'])}</span>"
                    f"<span class='cop-leader-rank'>#{insight['rank']}/{insight['peers']}</span>"
                    "</div>"
                    "<div class='cop-leader-insight-metric'>"
                    f"<strong>{insight['vol_total']:,}</strong> "
                    f"<span style='color:{color}'>{icon}{abs(diff):.0f}%</span> "
                    f"<span class='cop-leader-dpa'>DPA:{dpa_text}</span>"
                    "</div>"
                    "</div>"
                    "<div class='cop-leader-insight-tags'>"
                    "<span class='cop-leader-label'>Forte:</span> "
                    f"{strong_tags}"
                    "<span class='cop-leader-label cop-leader-label-gap'>Atenção:</span> "
                    f"{weak_tags}"
                    "</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _delta_html(value: float, label: str) -> str:
    color = "#2ecc71" if value >= 0 else "#e74c3c"
    icon = "▲" if value >= 0 else "▼"
    return (
        f"<span style='color:{color};font-weight:700'>"
        f"{icon}{abs(value):.0f}% {label}</span>"
    )


def _sector_abbrev(value: str) -> str:
    normalized = str(value or "").upper()
    if normalized == "RESIDENCIAL":
        return "RES"
    if normalized == "EMPRESARIAL":
        return "EMP"
    return normalized[:4] or "—"


def _short_name(value) -> str:
    # Mesma regra do dashboard legado: primeiro + último sobrenome.
    text = " ".join(str(value or "").split())
    if not text:
        return "—"
    parts = text.split()
    if len(parts) <= 2:
        return text.upper()
    return f"{parts[0]} {parts[-1]}".upper()


def _fallback_total(average, days) -> float:
    avg = _number(average)
    day_count = _number(days)
    if avg is None or day_count is None:
        return 0.0
    return avg * day_count


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
        .cop-leader-card {
            background:linear-gradient(180deg, rgba(17,37,59,.96), rgba(9,22,37,.98)) !important;
            border:1px solid rgba(148,163,184,.16) !important;
            border-top:3px solid rgba(247,184,75,.88) !important;
            border-radius:16px;
            box-shadow:0 14px 34px rgba(0,0,0,.16) !important;
            min-height:150px;
            padding:18px 19px 16px;
            margin-bottom:12px;
            color:#f4f7fb !important;
        }
        .cop-leader-card-head {
            display:flex;
            gap:8px;
            align-items:center;
            flex-wrap:wrap;
            color:#f8fbff !important;
            font-size:.82rem;
        }
        .cop-leader-card-head strong {
            color:#f8fbff !important;
            font-weight:850;
            letter-spacing:.01em;
        }
        .cop-leader-badge {
            display:inline-flex;
            align-items:center;
            background:rgba(247,184,75,.10) !important;
            border:1px solid rgba(247,184,75,.30) !important;
            color:#ffd98c !important;
            border-radius:7px;
            padding:2px 7px;
            margin-left:4px;
            font-size:.62rem;
            font-weight:850;
        }
        .cop-leader-volume {
            color:#ff5361 !important;
            font-size:1.42rem;
            font-weight:850;
            margin-top:10px;
            letter-spacing:-.02em;
        }
        .cop-leader-stat {
            color:#91a2b7 !important;
            font-size:.73rem;
            margin-top:7px;
            line-height:1.45;
        }
        .cop-leader-vs {
            color:#c9d6e5 !important;
        }
        .cop-leader-vs span {
            font-weight:800 !important;
        }

        .cop-leader-insight {
            background:linear-gradient(180deg, rgba(17,37,59,.96), rgba(9,22,37,.98)) !important;
            border:1px solid rgba(148,163,184,.16) !important;
            border-left:3px solid !important;
            border-radius:14px;
            padding:15px 17px;
            min-height:96px;
            margin-bottom:12px;
            color:#eef5fb !important;
            box-shadow:0 12px 30px rgba(0,0,0,.14);
        }
        .cop-leader-insight-head {
            display:flex;
            justify-content:space-between;
            gap:12px;
            align-items:center;
            font-size:.78rem;
            color:#eef5fb !important;
        }
        .cop-leader-insight-head strong {
            color:#f8fbff !important;
            font-weight:850;
        }
        .cop-leader-rank {
            display:inline-flex;
            align-items:center;
            background:rgba(148,163,184,.10) !important;
            border:1px solid rgba(148,163,184,.18) !important;
            color:#c8d5e4 !important;
            border-radius:7px;
            padding:2px 7px;
            margin-left:6px;
            font-size:.61rem;
            font-weight:750;
        }
        .cop-leader-insight-metric {
            white-space:nowrap;
            text-align:right;
            color:#dce7f3 !important;
        }
        .cop-leader-insight-metric strong {
            color:#f8fbff !important;
        }
        .cop-leader-dpa {
            color:#8fa1b6 !important;
            font-size:.69rem;
            margin-left:6px;
        }
        .cop-leader-insight-tags {
            margin-top:10px;
            font-size:.72rem;
            color:#c9d6e5 !important;
        }
        .cop-leader-label {
            color:#8193a9 !important;
        }
        .cop-leader-label-gap {
            margin-left:10px;
        }
        .cop-leader-tag-green,
        .cop-leader-tag-red {
            display:inline-block;
            border-radius:7px;
            padding:3px 7px;
            margin-left:4px;
            font-size:.64rem;
            font-weight:800;
        }
        .cop-leader-tag-green {
            color:#70e7ac !important;
            background:rgba(34,197,94,.10) !important;
            border:1px solid rgba(34,197,94,.30);
        }
        .cop-leader-tag-red {
            color:#ff8b94 !important;
            background:rgba(239,68,68,.10) !important;
            border:1px solid rgba(239,68,68,.30);
        }
        .cop-leader-empty {
            color:#61738a !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
