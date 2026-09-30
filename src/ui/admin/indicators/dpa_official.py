from __future__ import annotations

from datetime import datetime
import math

import pandas as pd
import streamlit as st


INDICATOR_KEY = "dpa_official"
GREEN_THRESHOLD = 90.0
YELLOW_THRESHOLD = 85.0


def render_admin_dpa(
    *,
    rows: pd.DataFrame,
    people: pd.DataFrame,
    period: str,
    data_through: str,
) -> None:
    """Visão administrativa dedicada à Ocupação DPA oficial."""

    _inject_styles()

    latest_label = format_month_label(period or data_through)
    summary = build_dpa_summary(rows, people)

    st.markdown(
        f"### 📊 Ocupação DPA — Dados Oficiais · Mês mais recente: {latest_label}"
    )
    st.caption(
        "O mês exibido é o mais recente disponível na carga oficial. "
        "Os percentuais representam o consolidado de ocupação disponível para cada analista."
    )

    _render_kpis(summary, period or data_through)

    st.markdown("#### 🏆 Ranking de Ocupação DPA por Analista")
    ranking = build_dpa_ranking(people)
    if ranking.empty:
        st.info("Nenhum analista com DPA disponível na competência atual.")
    else:
        st.dataframe(
            style_dpa_table(ranking),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### 🏢🏠 Ocupação DPA por Setor")
    sector_summaries = build_sector_summaries(people)
    sector_tables = build_sector_tables(ranking)

    if sector_summaries.empty:
        st.caption("Sem dados suficientes para consolidar os setores.")
    else:
        sectors = sector_summaries["Setor"].tolist()
        for start in range(0, len(sectors), 2):
            cols = st.columns(2)
            for column, sector in zip(cols, sectors[start:start + 2]):
                with column:
                    summary_row = sector_summaries[
                        sector_summaries["Setor"] == sector
                    ].iloc[0]
                    _render_sector_block(
                        sector,
                        summary_row,
                        sector_tables.get(sector, pd.DataFrame()),
                    )

    st.markdown("### 🚦 Painel de Semáforo — Todos os Analistas")
    _render_traffic_panel(ranking)


def build_dpa_summary(rows: pd.DataFrame, people: pd.DataFrame) -> dict:
    team_dpa = _weighted_value(rows)
    monitored = 0
    green = 0
    red = 0

    if people is not None and not people.empty and {"login", "value"}.issubset(people.columns):
        latest = _latest_people(people)
        monitored = len(latest)
        values = pd.to_numeric(latest["value"], errors="coerce")
        green = int((values >= GREEN_THRESHOLD).sum())
        red = int((values < YELLOW_THRESHOLD).sum())

    return {
        "team_dpa": 0.0 if team_dpa is None else float(team_dpa),
        "monitored": monitored,
        "green": green,
        "red": red,
    }


def build_dpa_ranking(people: pd.DataFrame) -> pd.DataFrame:
    if people is None or people.empty:
        return pd.DataFrame()

    required = {"login", "display_name", "segment_name", "value"}
    if not required.issubset(people.columns):
        return pd.DataFrame()

    frame = _latest_people(people)
    frame["DPA %"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame[frame["DPA %"].notna()].copy()
    if frame.empty:
        return pd.DataFrame()

    frame["Status"] = frame["DPA %"].apply(status_dot)
    frame["Analista"] = frame["display_name"].fillna(frame["login"])
    frame["Setor"] = frame["segment_name"].fillna("—").astype(str).str.upper()
    frame = frame.sort_values(
        ["DPA %", "Analista"],
        ascending=[False, True],
    ).reset_index(drop=True)
    frame.insert(0, "#", range(1, len(frame) + 1))

    return frame[["#", "Status", "Analista", "Setor", "DPA %"]]


def build_sector_summaries(people: pd.DataFrame) -> pd.DataFrame:
    if (
        people is None
        or people.empty
        or not {"segment_name", "value"}.issubset(people.columns)
    ):
        return pd.DataFrame()

    frame = _latest_people(people)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame[frame["value"].notna()].copy()
    if frame.empty:
        return pd.DataFrame()

    result = (
        frame.groupby("segment_name", dropna=False)["value"]
        .mean()
        .reset_index()
        .rename(columns={"segment_name": "Setor", "value": "Média DPA %"})
    )
    result["Setor"] = result["Setor"].fillna("—").astype(str)
    return result.sort_values("Setor").reset_index(drop=True)


def build_sector_tables(ranking: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if ranking is None or ranking.empty or "Setor" not in ranking.columns:
        return {}

    output: dict[str, pd.DataFrame] = {}
    for sector, part in ranking.groupby("Setor", dropna=False):
        sector_name = str(sector or "—")
        scoped = part.copy().sort_values(
            ["DPA %", "Analista"],
            ascending=[False, True],
        ).reset_index(drop=True)
        scoped["#"] = range(1, len(scoped) + 1)
        output[sector_name] = scoped[["#", "Status", "Analista", "DPA %"]]
    return output


def style_dpa_table(frame: pd.DataFrame):
    styler = frame.style.format({"DPA %": "{:.1f}"}, na_rep="—")
    if "DPA %" in frame.columns:
        styler = styler.background_gradient(
            cmap="RdYlGn",
            subset=["DPA %"],
        )
    return styler


def status_bucket(value) -> str:
    number = _number(value)
    if number is None:
        return "unknown"
    if number >= GREEN_THRESHOLD:
        return "green"
    if number >= YELLOW_THRESHOLD:
        return "yellow"
    return "red"


def status_dot(value) -> str:
    bucket = status_bucket(value)
    if bucket == "green":
        return "🟢"
    if bucket == "yellow":
        return "🟡"
    if bucket == "red":
        return "🔴"
    return "⚪"


def status_color(value) -> str:
    bucket = status_bucket(value)
    if bucket == "green":
        return "#18a957"
    if bucket == "yellow":
        return "#f0a000"
    if bucket == "red":
        return "#f04438"
    return "#64748b"


def format_month_label(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"

    normalized = raw[:7]
    try:
        date = datetime.strptime(normalized, "%Y-%m")
    except ValueError:
        return raw

    months = (
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    )
    return f"{months[date.month - 1]} {date.year}"


def _month_abbrev(value: str | None) -> str:
    raw = str(value or "").strip()
    try:
        date = datetime.strptime(raw[:7], "%Y-%m")
    except ValueError:
        return "ATUAL"
    abbreviations = (
        "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
        "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
    )
    return abbreviations[date.month - 1]


def _render_kpis(summary: dict, period: str | None) -> None:
    cards = (
        (f"DPA EQUIPE ({_month_abbrev(period)})", f"{summary['team_dpa']:.1f}%", "#18a957"),
        ("ANALISTAS MONITORADOS", str(summary["monitored"]), "#2e86c1"),
        ("≥ 90% 🟢", str(summary["green"]), "#18a957"),
        ("ABAIXO DE 85% 🔴", str(summary["red"]), "#e74c3c"),
    )
    cols = st.columns(4)
    for col, (label, value, accent) in zip(cols, cards):
        with col:
            st.markdown(
                (
                    "<div class='cop-dpa-card'>"
                    f"<div class='cop-dpa-card-label'>{label}</div>"
                    f"<div class='cop-dpa-card-value' style='color:{accent}'>{value}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _render_sector_block(
    sector: str,
    summary: pd.Series,
    table: pd.DataFrame,
) -> None:
    icon = _sector_icon(sector)
    mean = float(summary["Média DPA %"])
    st.markdown(f"#### {icon} {str(sector).upper()}")
    st.markdown(
        (
            "<div class='cop-dpa-sector-caption'>"
            f"Média do setor: <b>{mean:.1f}%</b> {status_dot(mean)}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if table is not None and not table.empty:
        st.dataframe(
            style_dpa_table(table),
            use_container_width=True,
            hide_index=True,
        )


def _render_traffic_panel(ranking: pd.DataFrame) -> None:
    if ranking is None or ranking.empty:
        st.caption("Sem dados para o painel de semáforo.")
        return

    columns_per_row = 4
    rows = ranking.reset_index(drop=True)
    for start in range(0, len(rows), columns_per_row):
        cols = st.columns(columns_per_row)
        for col, (_, row) in zip(cols, rows.iloc[start:start + columns_per_row].iterrows()):
            value = float(row["DPA %"])
            sector = _sector_abbrev(row.get("Setor"))
            color = status_color(value)
            with col:
                st.markdown(
                    (
                        f"<div class='cop-dpa-traffic' style='border-left-color:{color}'>"
                        "<div class='cop-dpa-traffic-name'>"
                        f"{status_dot(value)} <b>{row['Analista']}</b> "
                        f"<span>{sector}</span>"
                        "</div>"
                        f"<div class='cop-dpa-traffic-value' style='color:{color}'>{value:.1f}%</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )


def _latest_people(people: pd.DataFrame) -> pd.DataFrame:
    frame = people.copy()
    if "period" in frame.columns:
        period = frame["period"].astype(str)
        latest = period.max()
        if latest:
            frame = frame[period == latest].copy()

    subset = [column for column in ("login", "segment_name") if column in frame.columns]
    if subset:
        frame = frame.sort_values(subset).drop_duplicates(subset=subset, keep="last")
    return frame.reset_index(drop=True)


def _weighted_value(rows: pd.DataFrame) -> float | None:
    if rows is None or rows.empty or not {"value", "volume"}.issubset(rows.columns):
        return None
    values = pd.to_numeric(rows["value"], errors="coerce")
    volumes = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (volumes > 0)
    if not valid.any():
        return None
    return float((values[valid] * volumes[valid]).sum() / volumes[valid].sum())


def _sector_icon(sector: str) -> str:
    normalized = str(sector or "").strip().upper()
    if normalized == "EMPRESARIAL":
        return "🏢"
    if normalized == "RESIDENCIAL":
        return "🏠"
    if normalized == "PREVENTIVA":
        return "🛠️"
    return "📍"


def _sector_abbrev(sector: str) -> str:
    normalized = str(sector or "").strip().upper()
    aliases = {
        "EMPRESARIAL": "EMP",
        "RESIDENCIAL": "RES",
        "PREVENTIVA": "PREV",
    }
    return aliases.get(normalized, normalized[:4] or "—")


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-dpa-card {
            background: #ffffff;
            border: 1px solid rgba(15,23,42,.06);
            border-left: 4px solid #111827;
            border-radius: 16px;
            box-shadow: 0 8px 20px rgba(15,23,42,.07);
            min-height: 96px;
            padding: 18px 16px 14px;
            text-align: center;
        }
        .cop-dpa-card-label {
            color: #858990;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .cop-dpa-card-value {
            font-size: 1.72rem;
            font-weight: 800;
            line-height: 1.1;
            margin-top: 8px;
        }
        .cop-dpa-sector-caption {
            color: #8a8f98;
            font-size: .78rem;
            margin: 4px 0 12px;
        }
        .cop-dpa-traffic {
            background: #ffffff;
            border: 1px solid rgba(15,23,42,.08);
            border-left: 4px solid;
            border-radius: 14px;
            min-height: 92px;
            padding: 15px 16px 12px;
            margin-bottom: 10px;
        }
        .cop-dpa-traffic-name {
            color: #111827;
            font-size: .78rem;
        }
        .cop-dpa-traffic-name span {
            color: #9ca3af;
            font-size: .65rem;
            font-weight: 700;
        }
        .cop-dpa-traffic-value {
            font-size: 1.22rem;
            font-weight: 800;
            margin-top: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
