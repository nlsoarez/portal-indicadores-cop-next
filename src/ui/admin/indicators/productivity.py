from __future__ import annotations

import math

import pandas as pd
import streamlit as st


INDICATOR_KEY = "productivity_avg_daily"

SECTOR_COMPONENTS = {
    "RESIDENCIAL": (
        ("Abertura New Monitor", "Ab. New Monitor"),
        ("Fechamento New Monitor", "Fech. New Monitor"),
        ("Abertura SGO", "Ab. SGO"),
        ("Fechamento SGO", "Fech. SGO"),
        ("Abertura Remedy", "Ab. Remedy"),
        ("Ligações Realizadas", "Ligações Realiz."),
        ("Primeira Interação TOA", "1ª Interação TOA"),
        ("Fechamento Tarefa TOA", "Fech. Tarefa TOA"),
    ),
    "EMPRESARIAL": (
        ("Tratativa RAL", "Trat. RAL"),
        ("Tratativa REC", "Trat. REC"),
        ("Abertura Remedy", "Ab. Remedy"),
        ("Ligações Realizadas", "Ligações Realiz."),
        ("Primeira Interação TOA", "1ª Interação TOA"),
        ("Fechamento Tarefa TOA", "Fech. Tarefa TOA"),
    ),
    "PREVENTIVA": (
        ("Abertura Remedy", "Ab. Remedy"),
        ("Ligações Realizadas", "Ligações Realiz."),
        ("Primeira Interação TOA", "1ª Interação TOA"),
        ("Fechamento Tarefa TOA", "Fech. Tarefa TOA"),
    ),
}


def render_admin_productivity(
    *,
    people: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
    dpa_people: pd.DataFrame,
    period: str,
    data_through: str,
) -> None:
    """Visão administrativa dedicada à produtividade consolidada."""

    _inject_styles()

    ranking = build_total_ranking(people, analyst_breakdowns)
    if ranking.empty:
        st.info("Nenhum dado de produtividade disponível na competência atual.")
        return

    st.markdown("### 📦 Ranking por Volume Total")
    st.caption(
        f"Competência: {period or '—'} · Dados até: {data_through or period or '—'}"
    )
    st.dataframe(
        style_total_ranking(ranking),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### 📋 Análise Detalhada por Setor")

    dpa_map = build_dpa_map(dpa_people)
    component_pivot = build_component_pivot(analyst_breakdowns)

    sectors = preferred_sector_order(ranking["Setor"].dropna().astype(str).unique())
    for sector in sectors:
        sector_table = build_sector_detail(
            ranking,
            sector=sector,
            component_pivot=component_pivot,
            dpa_map=dpa_map,
        )
        if sector_table.empty:
            continue

        _render_sector_heading(sector)
        st.dataframe(
            style_sector_detail(sector_table, sector),
            use_container_width=True,
            hide_index=True,
        )
        _render_sector_highlights(sector_table)


def build_total_ranking(
    people: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
) -> pd.DataFrame:
    if people is None or people.empty:
        return pd.DataFrame()

    required = {"login", "display_name", "segment_name", "value", "volume"}
    if not required.issubset(people.columns):
        return pd.DataFrame()

    base = people.copy()
    base["Média/Dia"] = pd.to_numeric(base["value"], errors="coerce")
    base["Dias"] = pd.to_numeric(base["volume"], errors="coerce").fillna(0)

    exact_totals = exact_productivity_totals(analyst_breakdowns)
    base["Vol. Total"] = base.apply(
        lambda row: exact_totals.get(
            (str(row.get("login")), str(row.get("segment_name"))),
            exact_totals.get(
                (str(row.get("login")), ""),
                _fallback_total(row.get("Média/Dia"), row.get("Dias")),
            ),
        ),
        axis=1,
    )

    base["Analista"] = base["display_name"].fillna(base["login"])
    base["Setor"] = base["segment_name"].fillna("—").astype(str).str.upper()
    base["Dias"] = base["Dias"].round().astype(int)
    base["Vol. Total"] = pd.to_numeric(base["Vol. Total"], errors="coerce").fillna(0).round().astype(int)

    base = base[base["Dias"] > 0].copy()
    base = base.sort_values(
        ["Vol. Total", "Média/Dia", "Analista"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    base.insert(0, "#", range(1, len(base) + 1))

    return base[["#", "Analista", "Setor", "Vol. Total", "Dias", "Média/Dia", "login"]]


def exact_productivity_totals(
    analyst_breakdowns: pd.DataFrame,
) -> dict[tuple[str, str], float]:
    rows = _dimension_rows(analyst_breakdowns, "productivity_total")
    if rows.empty or not {"login", "successes"}.issubset(rows.columns):
        return {}

    frame = rows.copy()
    frame["successes"] = pd.to_numeric(frame["successes"], errors="coerce").fillna(0)

    group_cols = ["login"]
    if "segment_name" in frame.columns:
        group_cols.append("segment_name")

    grouped = frame.groupby(group_cols, dropna=False)["successes"].sum().reset_index()
    output: dict[tuple[str, str], float] = {}
    for _, row in grouped.iterrows():
        login = str(row.get("login") or "")
        sector = str(row.get("segment_name") or "") if "segment_name" in grouped.columns else ""
        output[(login, sector)] = float(row["successes"])
        output[(login, "")] = float(row["successes"])
    return output


def build_component_pivot(
    analyst_breakdowns: pd.DataFrame,
) -> pd.DataFrame:
    rows = _dimension_rows(analyst_breakdowns, "productivity_component")
    if rows.empty or not {"login", "dimension_value", "successes"}.issubset(rows.columns):
        return pd.DataFrame()

    frame = rows.copy()
    frame["successes"] = pd.to_numeric(frame["successes"], errors="coerce").fillna(0)

    index_cols = ["login"]
    if "segment_name" in frame.columns:
        index_cols.append("segment_name")

    pivot = (
        frame.groupby(index_cols + ["dimension_value"], dropna=False)["successes"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    return pivot


def build_dpa_map(dpa_people: pd.DataFrame) -> dict[tuple[str, str], float]:
    if dpa_people is None or dpa_people.empty:
        return {}
    required = {"login", "value"}
    if not required.issubset(dpa_people.columns):
        return {}

    frame = dpa_people.copy()
    if "period" in frame.columns:
        frame["_period"] = frame["period"].astype(str)
        frame = frame.sort_values("_period")

    subset = ["login"]
    if "segment_name" in frame.columns:
        subset.append("segment_name")
    frame = frame.drop_duplicates(subset=subset, keep="last")

    output: dict[tuple[str, str], float] = {}
    for _, row in frame.iterrows():
        value = _number(row.get("value"))
        if value is None:
            continue
        login = str(row.get("login") or "")
        sector = str(row.get("segment_name") or "") if "segment_name" in frame.columns else ""
        output[(login, sector.upper())] = value
        output[(login, "")] = value
    return output


def build_sector_detail(
    ranking: pd.DataFrame,
    *,
    sector: str,
    component_pivot: pd.DataFrame,
    dpa_map: dict[tuple[str, str], float],
) -> pd.DataFrame:
    if ranking is None or ranking.empty:
        return pd.DataFrame()

    normalized_sector = str(sector).upper()
    table = ranking[ranking["Setor"].astype(str).str.upper() == normalized_sector].copy()
    if table.empty:
        return pd.DataFrame()

    mean_daily = float(pd.to_numeric(table["Média/Dia"], errors="coerce").dropna().mean())
    if mean_daily > 0:
        table["vs Média"] = table["Média/Dia"].apply(
            lambda value: ((float(value) / mean_daily) - 1.0) * 100
            if _number(value) is not None
            else None
        )
    else:
        table["vs Média"] = None

    table["DPA %"] = table.apply(
        lambda row: dpa_map.get(
            (str(row["login"]), normalized_sector),
            dpa_map.get((str(row["login"]), "")),
        ),
        axis=1,
    )

    table = _merge_components(table, component_pivot, normalized_sector)

    table = table.sort_values(
        ["Vol. Total", "Média/Dia", "Analista"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    table["#"] = range(1, len(table) + 1)

    columns = [
        "#",
        "Analista",
        "Vol. Total",
        "Dias",
        "Média/Dia",
        "vs Média",
        "DPA %",
    ]
    columns.extend(
        display
        for _, display in SECTOR_COMPONENTS.get(
            normalized_sector,
            SECTOR_COMPONENTS["PREVENTIVA"],
        )
        if display in table.columns
    )

    return table[columns]


def _merge_components(
    table: pd.DataFrame,
    component_pivot: pd.DataFrame,
    sector: str,
) -> pd.DataFrame:
    result = table.copy()
    configured = SECTOR_COMPONENTS.get(sector, SECTOR_COMPONENTS["PREVENTIVA"])
    for _, display in configured:
        result[display] = 0

    if component_pivot is None or component_pivot.empty:
        return result

    pivot = component_pivot.copy()
    if "segment_name" in pivot.columns:
        pivot = pivot[
            pivot["segment_name"].fillna("").astype(str).str.upper() == sector
        ].copy()

    component_map = {source: display for source, display in configured}
    keep_cols = ["login"] + [
        source for source in component_map if source in pivot.columns
    ]
    if len(keep_cols) == 1:
        return result

    reduced = pivot[keep_cols].copy().rename(columns=component_map)
    reduced = reduced.groupby("login", dropna=False).sum(numeric_only=True).reset_index()

    result = result.drop(columns=[display for _, display in configured], errors="ignore")
    result = result.merge(reduced, on="login", how="left")
    for _, display in configured:
        if display not in result.columns:
            result[display] = 0
        result[display] = pd.to_numeric(result[display], errors="coerce").fillna(0).round().astype(int)
    return result


def style_total_ranking(frame: pd.DataFrame):
    styler = frame.drop(columns=["login"], errors="ignore").style.format(
        {"Média/Dia": "{:.1f}"},
        na_rep="—",
    )
    if "Vol. Total" in frame.columns:
        styler = styler.background_gradient(cmap="Blues", subset=["Vol. Total"])
    return styler


def style_sector_detail(frame: pd.DataFrame, sector: str):
    formatters = {
        "Média/Dia": "{:.1f}",
        "vs Média": "{:+.1f}%",
        "DPA %": "{:.1f}",
    }
    styler = frame.style.format(
        {key: value for key, value in formatters.items() if key in frame.columns},
        na_rep="—",
    )

    volume_cmap = "Blues" if str(sector).upper() == "RESIDENCIAL" else "Oranges"
    if "Vol. Total" in frame.columns:
        styler = styler.background_gradient(cmap=volume_cmap, subset=["Vol. Total"])
    if "vs Média" in frame.columns:
        styler = styler.background_gradient(cmap="RdYlGn", subset=["vs Média"])
    if "DPA %" in frame.columns and pd.to_numeric(frame["DPA %"], errors="coerce").notna().any():
        styler = styler.background_gradient(cmap="RdYlGn", subset=["DPA %"])

    component_columns = [
        display
        for _, display in SECTOR_COMPONENTS.get(
            str(sector).upper(),
            SECTOR_COMPONENTS["PREVENTIVA"],
        )
        if display in frame.columns
    ]
    for column in component_columns:
        styler = styler.background_gradient(cmap=volume_cmap, subset=[column])

    return styler


def preferred_sector_order(values) -> list[str]:
    available = [str(value).upper() for value in values if str(value).strip()]
    preferred = ["RESIDENCIAL", "EMPRESARIAL", "PREVENTIVA"]
    output = [sector for sector in preferred if sector in available]
    output.extend(sorted(sector for sector in available if sector not in output))
    return output


def sector_highlights(table: pd.DataFrame) -> dict:
    if table is None or table.empty:
        return {}

    highest = table.sort_values(
        ["Vol. Total", "Média/Dia"], ascending=[False, False]
    ).iloc[0]
    lowest = table.sort_values(
        ["Vol. Total", "Média/Dia"], ascending=[True, True]
    ).iloc[0]

    dpa_rows = table[pd.to_numeric(table.get("DPA %"), errors="coerce").notna()].copy()
    best_dpa = None
    if not dpa_rows.empty:
        best_dpa = dpa_rows.sort_values(
            ["DPA %", "Vol. Total"], ascending=[False, False]
        ).iloc[0]

    return {
        "highest": highest,
        "lowest": lowest,
        "best_dpa": best_dpa,
    }


def _render_sector_highlights(table: pd.DataFrame) -> None:
    highlights = sector_highlights(table)
    if not highlights:
        return

    cols = st.columns(3)
    highest = highlights["highest"]
    lowest = highlights["lowest"]
    best_dpa = highlights["best_dpa"]

    with cols[0]:
        _render_highlight(
            "🏆 MAIOR VOLUME",
            str(highest["Analista"]),
            f"Vol: {int(highest['Vol. Total']):,} · Média: {float(highest['Média/Dia']):.1f}/dia",
            "#18a957",
            "rgba(24,169,87,.10)",
        )
    with cols[1]:
        _render_highlight(
            "⚠ MENOR VOLUME",
            str(lowest["Analista"]),
            f"Vol: {int(lowest['Vol. Total']):,} · Média: {float(lowest['Média/Dia']):.1f}/dia",
            "#e74c3c",
            "rgba(231,76,60,.10)",
        )
    with cols[2]:
        if best_dpa is None:
            _render_highlight(
                "📊 MELHOR DPA",
                "Sem dado disponível",
                "DPA não encontrado para este setor",
                "#2e86c1",
                "rgba(46,134,193,.10)",
            )
        else:
            _render_highlight(
                "📊 MELHOR DPA",
                str(best_dpa["Analista"]),
                f"DPA: {float(best_dpa['DPA %']):.1f}%",
                "#3498db",
                "rgba(52,152,219,.10)",
            )


def _render_sector_heading(sector: str) -> None:
    normalized = str(sector).upper()
    icon = "🏠" if normalized == "RESIDENCIAL" else "🏢" if normalized == "EMPRESARIAL" else "🛠️"
    background = "#eaf4fb" if normalized == "RESIDENCIAL" else "#f8eee4" if normalized == "EMPRESARIAL" else "#eef5ea"
    st.markdown(
        (
            f"<div class='cop-prod-sector-pill' style='background:{background}'>"
            f"{icon} {normalized}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_highlight(
    label: str,
    name: str,
    detail: str,
    color: str,
    background: str,
) -> None:
    st.markdown(
        (
            f"<div class='cop-prod-highlight' style='border-left-color:{color};background:{background}'>"
            f"<div class='cop-prod-highlight-label'>{label}</div>"
            f"<div class='cop-prod-highlight-name' style='color:{color}'>{name}</div>"
            f"<div class='cop-prod-highlight-detail'>{detail}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None or frame.empty or "dimension" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["dimension"] == dimension].copy()


def _fallback_total(avg_daily, days) -> float:
    avg = _number(avg_daily)
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
    if math.isnan(number):
        return None
    return number


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-prod-sector-pill {
            display: inline-block;
            border: 1px solid rgba(15,23,42,.08);
            border-radius: 8px;
            font-size: .78rem;
            font-weight: 800;
            padding: 7px 16px;
            margin: 8px 0 12px;
        }
        .cop-prod-highlight {
            border-left: 4px solid;
            border-radius: 14px;
            min-height: 98px;
            padding: 16px 16px 12px;
            margin: 12px 0 20px;
        }
        .cop-prod-highlight-label {
            color: #858990;
            font-size: .67rem;
            font-weight: 800;
            letter-spacing: .07em;
        }
        .cop-prod-highlight-name {
            font-size: .98rem;
            font-weight: 800;
            margin-top: 8px;
        }
        .cop-prod-highlight-detail {
            color: #7b7f87;
            font-size: .74rem;
            margin-top: 7px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
