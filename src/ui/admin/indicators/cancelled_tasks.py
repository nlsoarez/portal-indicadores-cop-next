from __future__ import annotations

import math

import pandas as pd
import streamlit as st


INDICATOR_KEY = "toa_cancellation_rate"


def render_admin_cancelled_tasks(
    *,
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    details: pd.DataFrame,
    period: str,
    data_through: str,
) -> None:
    """Visão administrativa dedicada às Tarefas Canceladas."""

    _inject_styles()

    st.markdown("### ❌ Tarefas Canceladas")
    st.caption(
        "Cada linha consolida as tarefas canceladas por analista no período. "
        f"Competência: {period or '—'} · Dados até: {data_through or period or '—'}"
    )

    st.markdown("#### 🏆 Ranking por Analista")
    ranking = build_cancelled_ranking(people, metrics)
    if ranking.empty:
        st.info("Nenhuma tarefa cancelada pela equipe na competência atual.")
    else:
        st.dataframe(
            style_cancelled_table(ranking),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 🗺️ Por Grupo (IN_GRUPO) — Regional Leste")
    group_table = build_group_cancelled_table(details)
    if group_table.empty:
        st.caption("Sem tarefas canceladas com grupo identificado nesta carga.")
    else:
        st.dataframe(
            style_cancelled_table(group_table),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### 🏢🏠 Canceladas por Setor")
    sector_tables = build_sector_cancelled_tables(ranking)
    if not sector_tables:
        st.caption("Sem tarefas canceladas para detalhar por setor.")
        return

    sectors = list(sector_tables)
    for start in range(0, len(sectors), 2):
        cols = st.columns(2)
        for column, sector in zip(cols, sectors[start:start + 2]):
            with column:
                icon = _sector_icon(sector)
                st.markdown(f"#### {icon} {sector.upper()}")
                st.dataframe(
                    style_cancelled_table(sector_tables[sector]),
                    use_container_width=True,
                    hide_index=True,
                )


def build_cancelled_ranking(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
) -> pd.DataFrame:
    if people is None or people.empty or metrics is None or metrics.empty:
        return pd.DataFrame()

    identity = (
        people[["login", "display_name", "segment_name"]]
        .dropna(subset=["login"])
        .drop_duplicates(subset=["login"])
    )

    required = {"login", "losses"}
    if not required.issubset(metrics.columns):
        return pd.DataFrame()

    frame = metrics.copy()
    frame["losses"] = pd.to_numeric(frame["losses"], errors="coerce").fillna(0)
    if "volume" in frame.columns:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
    else:
        frame["volume"] = 0

    records = []
    for login, part in frame.groupby("login", dropna=False):
        cancelled = float(part["losses"].sum())
        if cancelled <= 0:
            continue

        records.append(
            {
                "login": login,
                "Canceladas": int(round(cancelled)),
                "TMR Médio (h)": _hours(_weighted_tmr(part)),
            }
        )

    if not records:
        return pd.DataFrame()

    table = pd.DataFrame(records).merge(identity, on="login", how="left")
    table["Analista"] = table["display_name"].fillna(table["login"])
    table["Setor"] = table["segment_name"].fillna("—").astype(str).str.upper()
    table = table.sort_values(
        ["Canceladas", "TMR Médio (h)", "Analista"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    table.insert(0, "#", range(1, len(table) + 1))

    return table[
        ["#", "Analista", "Setor", "Canceladas", "TMR Médio (h)"]
    ]


def build_group_cancelled_table(details: pd.DataFrame) -> pd.DataFrame:
    rows = _dimension_rows(details, "group")
    if rows.empty or "losses" not in rows.columns:
        return pd.DataFrame()

    frame = rows.copy()
    frame["losses"] = pd.to_numeric(frame["losses"], errors="coerce").fillna(0)

    grouped = (
        frame.groupby("dimension_value", dropna=False)["losses"]
        .sum()
        .reset_index()
        .rename(columns={"dimension_value": "Grupo", "losses": "Canceladas"})
    )
    grouped = grouped[grouped["Grupo"].notna()].copy()
    grouped["Grupo"] = grouped["Grupo"].astype(str)
    grouped = grouped[grouped["Grupo"].str.strip().ne("")]
    grouped = grouped[grouped["Canceladas"] > 0]
    if grouped.empty:
        return pd.DataFrame()

    grouped["Canceladas"] = grouped["Canceladas"].round().astype(int)
    return grouped.sort_values(
        ["Canceladas", "Grupo"],
        ascending=[False, True],
    ).reset_index(drop=True)


def build_sector_cancelled_tables(
    ranking: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    if ranking is None or ranking.empty or "Setor" not in ranking.columns:
        return {}

    output: dict[str, pd.DataFrame] = {}
    for sector, part in ranking.groupby("Setor", dropna=False):
        sector_name = str(sector or "—")
        scoped = part.copy().sort_values(
            ["Canceladas", "TMR Médio (h)", "Analista"],
            ascending=[False, False, True],
            na_position="last",
        ).reset_index(drop=True)
        scoped["#"] = range(1, len(scoped) + 1)
        output[sector_name] = scoped[
            ["#", "Analista", "Canceladas", "TMR Médio (h)"]
        ]
    return output


def style_cancelled_table(frame: pd.DataFrame):
    formatters = {}
    if "TMR Médio (h)" in frame.columns:
        formatters["TMR Médio (h)"] = "{:.2f}"

    styler = frame.style.format(formatters, na_rep="—")
    if "Canceladas" in frame.columns:
        styler = styler.background_gradient(
            cmap="Reds",
            subset=["Canceladas"],
        )
    return styler


def _weighted_tmr(frame: pd.DataFrame) -> float | None:
    if frame is None or frame.empty or "tmr_seconds" not in frame.columns:
        return None

    values = pd.to_numeric(frame["tmr_seconds"], errors="coerce")
    if "volume" in frame.columns:
        weights = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
        valid = values.notna() & (weights > 0)
        if valid.any():
            return float((values[valid] * weights[valid]).sum() / weights[valid].sum())

    valid_values = values.dropna()
    if valid_values.empty:
        return None
    return float(valid_values.mean())


def _hours(seconds) -> float | None:
    number = _number(seconds)
    if number is None or number < 0:
        return None
    return number / 3600.0


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None or frame.empty or "dimension" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["dimension"] == dimension].copy()


def _sector_icon(sector: str) -> str:
    normalized = str(sector or "").strip().upper()
    if normalized == "EMPRESARIAL":
        return "🏢"
    if normalized == "RESIDENCIAL":
        return "🏠"
    if normalized == "PREVENTIVA":
        return "🛠️"
    return "📍"


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
        .cop-cancel-caption {
            color: #8a8f98;
            font-size: .80rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
