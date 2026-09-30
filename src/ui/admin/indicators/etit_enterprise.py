from __future__ import annotations

import math

import pandas as pd
import streamlit as st


INDICATOR_KEY = "emp_etit_event"


def render_admin_enterprise_etit(
    *,
    rows: pd.DataFrame,
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
    details: pd.DataFrame,
    period: str,
    data_through: str,
) -> None:
    """Visão operacional dedicada ao Admin para ETIT por Evento Empresarial."""

    _inject_styles()

    overall = overall_summary(rows, metrics, details)
    st.markdown("### ⚡ ETIT POR EVENTO — Análise da Equipe")
    st.caption(
        f"Competência: {period or '—'} · Dados até: {data_through or period or '—'}"
    )
    _render_kpis(overall)

    st.markdown("#### 🏆 Ranking ETIT por Analista")
    ranking = build_ranking_table(people, metrics, analyst_breakdowns)
    if ranking.empty:
        st.info("Nenhum analista com resultado para a competência atual.")
    else:
        st.dataframe(
            style_ranking_table(ranking),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 📋 Aderentes e Não Aderentes por Analista — RAL e REC")
    averages = demand_team_averages(people, analyst_breakdowns)
    _render_average_cards(averages)

    split_table = build_demand_analyst_table(people, analyst_breakdowns)
    if not split_table.empty:
        st.dataframe(
            style_demand_analyst_table(split_table),
            use_container_width=True,
            hide_index=True,
        )

    left, right = st.columns(2)
    with left:
        st.markdown("#### Por Demanda (RAL/REC)")
        demand_table = build_dimension_table(details, "demand", "Demanda", durations=True)
        if demand_table.empty:
            st.caption("Sem dados de demanda nesta carga.")
        else:
            st.dataframe(
                style_breakdown_table(demand_table),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("#### Por Tipo")
        type_table = build_dimension_table(details, "type", "Tipo")
        if type_table.empty:
            st.caption("Sem dados de tipo nesta carga.")
        else:
            st.dataframe(
                style_breakdown_table(type_table),
                use_container_width=True,
                hide_index=True,
            )

    left, right = st.columns(2)
    with left:
        st.markdown("#### Por Causa")
        cause_table = build_dimension_table(details, "cause", "Causa", top=15)
        if cause_table.empty:
            st.caption("Sem dados de causa nesta carga.")
        else:
            st.dataframe(
                style_breakdown_table(cause_table),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("#### Por Grupo (IN_GRUPO) — Regional Leste")
        group_table = build_dimension_table(details, "group", "Grupo")
        if group_table.empty:
            st.caption("Sem dados de grupo nesta carga.")
        else:
            best = group_table.sort_values(
                ["Aderência %", "Eventos"], ascending=[False, False]
            ).iloc[0]
            worst = group_table.sort_values(
                ["Aderência %", "Eventos"], ascending=[True, False]
            ).iloc[0]
            st.markdown(
                (
                    "<div class='cop-emp-bestworst'>"
                    f"<span class='cop-emp-best'>●</span> Melhor: "
                    f"<b>{best['Grupo']}</b> ({best['Aderência %']:.1f}%) · "
                    "<span class='cop-emp-worst'>●</span> Pior: "
                    f"<b>{worst['Grupo']}</b> ({worst['Aderência %']:.1f}%)"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            st.dataframe(
                style_breakdown_table(group_table),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("#### Por Turno")
    turn_table = build_dimension_table(details, "turn", "Turno")
    if turn_table.empty:
        st.caption("Sem dados de turno nesta carga.")
    else:
        turn_table = sort_turn_table(turn_table)
        st.dataframe(
            style_breakdown_table(turn_table),
            use_container_width=True,
            hide_index=True,
        )


def overall_summary(
    rows: pd.DataFrame,
    metrics: pd.DataFrame,
    details: pd.DataFrame,
) -> dict:
    overall = _dimension_rows(details, "overall")
    if not overall.empty:
        volume = _sum(overall, "volume")
        successes = _sum(overall, "successes")
        tma = _weighted(overall, "tma_seconds", "volume")
        tmr = _weighted(overall, "tmr_seconds", "volume")
    else:
        volume = _sum(rows, "volume")
        rate = _weighted(rows, "value", "volume") or 0.0
        successes = volume * rate / 100 if volume > 0 else 0.0
        tma = _weighted(metrics, "tma_seconds", "volume")
        tmr = _weighted(metrics, "tmr_seconds", "volume")

    analysts = 0
    if rows is not None and not rows.empty and "analysts" in rows.columns:
        analysts = int(round(_sum(rows, "analysts")))
    elif metrics is not None and not metrics.empty and "login" in metrics.columns:
        analysts = int(metrics["login"].dropna().astype(str).nunique())

    return {
        "events": int(round(volume)),
        "adherents": int(round(successes)),
        "adherence": _ratio(successes, volume),
        "analysts": analysts,
        "tma_seconds": tma,
        "tmr_seconds": tmr,
    }


def build_ranking_table(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
) -> pd.DataFrame:
    if people is None or people.empty:
        return pd.DataFrame()

    base = people.copy()
    identity = (
        base[["login", "display_name", "segment_name"]]
        .dropna(subset=["login"])
        .drop_duplicates(subset=["login"])
    )

    if metrics is not None and not metrics.empty:
        metric_cols = [
            column
            for column in (
                "login",
                "volume",
                "successes",
                "losses",
                "tma_seconds",
                "tmr_seconds",
            )
            if column in metrics.columns
        ]
        metric_frame = metrics[metric_cols].copy()
        for column in ("volume", "successes", "losses"):
            if column in metric_frame.columns:
                metric_frame[column] = pd.to_numeric(
                    metric_frame[column], errors="coerce"
                ).fillna(0)
        agg = {
            "volume": "sum",
            "successes": "sum",
            "losses": "sum",
            "tma_seconds": "mean",
            "tmr_seconds": "mean",
        }
        agg = {key: value for key, value in agg.items() if key in metric_frame.columns}
        totals = metric_frame.groupby("login", dropna=False).agg(agg).reset_index()
    else:
        base["volume"] = pd.to_numeric(base["volume"], errors="coerce").fillna(0)
        base["value"] = pd.to_numeric(base["value"], errors="coerce").fillna(0)
        base["_successes"] = base["volume"] * base["value"] / 100
        totals = (
            base.groupby("login", dropna=False)
            .agg(volume=("volume", "sum"), successes=("_successes", "sum"))
            .reset_index()
        )
        totals["losses"] = totals["volume"] - totals["successes"]
        totals["tma_seconds"] = None
        totals["tmr_seconds"] = None

    demand = _dimension_rows(analyst_breakdowns, "demand")
    demand_pivot = _analyst_demand_volume_pivot(demand)

    totals = totals.merge(identity, on="login", how="left")
    if not demand_pivot.empty:
        totals = totals.merge(demand_pivot, on="login", how="left")

    for column in ("volume", "successes", "losses", "RAL", "REC"):
        if column not in totals.columns:
            totals[column] = 0
        totals[column] = pd.to_numeric(totals[column], errors="coerce").fillna(0)

    totals["Aderência %"] = totals.apply(
        lambda row: _ratio(row["successes"], row["volume"]),
        axis=1,
    )
    # O ranking operacional segue o volume de eventos, como na referência:
    # quem atuou em mais eventos aparece primeiro; aderência desempata.
    totals = totals.sort_values(
        ["volume", "Aderência %", "display_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    totals.insert(0, "#", range(1, len(totals) + 1))

    output = pd.DataFrame(
        {
            "#": totals["#"],
            "Nome": totals["display_name"].fillna(totals["login"]),
            "Setor": totals["segment_name"].fillna("—").astype(str).str.upper(),
            "Eventos": totals["volume"].round().astype(int),
            "Aderentes": totals["successes"].round().astype(int),
            "Aderência %": totals["Aderência %"],
            "RAL": totals["RAL"].round().astype(int),
            "REC": totals["REC"].round().astype(int),
            "TMA": totals["tma_seconds"].apply(_duration),
            "TMR": totals["tmr_seconds"].apply(_duration),
        }
    )
    return output


def demand_team_averages(
    people: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
) -> dict:
    universe = _analyst_universe(people)
    rows = _dimension_rows(analyst_breakdowns, "demand")
    result = {
        "ral_adherents": 0.0,
        "rec_adherents": 0.0,
        "ral_non_adherents": 0.0,
        "rec_non_adherents": 0.0,
    }
    if not universe or rows.empty:
        return result

    for demand, prefix in (("RAL", "ral"), ("REC", "rec")):
        part = rows[rows["dimension_value"].astype(str).str.upper() == demand].copy()
        if part.empty:
            continue
        for column in ("successes", "losses"):
            part[column] = pd.to_numeric(part[column], errors="coerce").fillna(0)
        grouped = (
            part.groupby("login", dropna=False)
            .agg(successes=("successes", "sum"), losses=("losses", "sum"))
            .reindex(universe, fill_value=0)
        )
        result[f"{prefix}_adherents"] = float(grouped["successes"].mean())
        result[f"{prefix}_non_adherents"] = float(grouped["losses"].mean())

    return result


def build_demand_analyst_table(
    people: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
) -> pd.DataFrame:
    universe = _analyst_universe(people)
    rows = _dimension_rows(analyst_breakdowns, "demand")
    if not universe or rows.empty:
        return pd.DataFrame()

    identities = (
        people[["login", "display_name"]]
        .dropna(subset=["login"])
        .drop_duplicates(subset=["login"])
        .set_index("login")["display_name"]
        .to_dict()
    )

    output = []
    for login in universe:
        item = {"login": login, "Analista": identities.get(login, login)}
        for demand in ("RAL", "REC"):
            part = rows[
                (rows["login"].astype(str) == str(login))
                & (rows["dimension_value"].astype(str).str.upper() == demand)
            ]
            volume = _sum(part, "volume")
            successes = _sum(part, "successes")
            losses = _sum(part, "losses")
            item[f"{demand} Ader."] = int(round(successes))
            item[f"{demand} N. Ader."] = int(round(losses))
            item[f"% {demand} Ader."] = _ratio(successes, volume)
            item[f"% {demand} N. Ader."] = _ratio(losses, volume)
        output.append(item)

    table = pd.DataFrame(output)
    table["_total"] = (
        table["RAL Ader."]
        + table["REC Ader."]
        + table["RAL N. Ader."]
        + table["REC N. Ader."]
    )
    table = table.sort_values(
        ["_total", "Analista"],
        ascending=[False, True],
    ).reset_index(drop=True)
    table.insert(0, "#", range(1, len(table) + 1))
    return table[
        [
            "#",
            "Analista",
            "RAL Ader.",
            "REC Ader.",
            "RAL N. Ader.",
            "REC N. Ader.",
            "% RAL Ader.",
            "% RAL N. Ader.",
            "% REC Ader.",
            "% REC N. Ader.",
        ]
    ]


def build_dimension_table(
    details: pd.DataFrame,
    dimension: str,
    label: str,
    *,
    durations: bool = False,
    top: int | None = None,
) -> pd.DataFrame:
    rows = _dimension_rows(details, dimension)
    if rows.empty:
        return pd.DataFrame()

    frame = rows.copy()
    for column in ("volume", "successes", "losses"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    records = []
    for dimension_value, part in frame.groupby("dimension_value", dropna=False):
        if dimension_value is None or not str(dimension_value).strip():
            continue
        volume = _sum(part, "volume")
        successes = _sum(part, "successes")
        record = {
            label: str(dimension_value),
            "Eventos": int(round(volume)),
            "Aderentes": int(round(successes)),
        }
        if durations:
            record["TMA"] = _duration(_weighted(part, "tma_seconds", "volume"))
            record["TMR"] = _duration(_weighted(part, "tmr_seconds", "volume"))
        record["Aderência %"] = _ratio(successes, volume)
        records.append(record)

    table = pd.DataFrame(records)
    if table.empty:
        return table

    table = table.sort_values(
        ["Eventos", "Aderência %", label],
        ascending=[False, False, True],
    )
    if top is not None:
        table = table.head(top)
    return table.reset_index(drop=True)


def sort_turn_table(table: pd.DataFrame) -> pd.DataFrame:
    if table is None or table.empty or "Turno" not in table.columns:
        return table
    order = {
        "MADRUGADA": 0,
        "MANHÃ": 1,
        "MANHA": 1,
        "TARDE": 2,
        "NOITE": 3,
    }
    result = table.copy()
    result["_order"] = result["Turno"].astype(str).str.upper().map(order).fillna(99)
    return result.sort_values(["_order", "Turno"]).drop(columns="_order").reset_index(drop=True)


def _render_kpis(summary: dict) -> None:
    cards = (
        ("TOTAL EVENTOS", str(summary["events"]), "#8e44ad"),
        ("ADERENTES", str(summary["adherents"]), "#27ae60"),
        ("ADERÊNCIA", f"{summary['adherence']:.1f}%", "#27ae60"),
        ("ANALISTAS", str(summary["analysts"]), "#2980b9"),
        ("TMA MÉDIO", _duration(summary["tma_seconds"]), "#1f5a7a"),
        ("TMR MÉDIO", _duration(summary["tmr_seconds"]), "#f39c12"),
    )
    cols = st.columns(6)
    for col, (label, value, accent) in zip(cols, cards):
        with col:
            st.markdown(
                (
                    "<div class='cop-emp-card'>"
                    f"<div class='cop-emp-card-label'>{label}</div>"
                    f"<div class='cop-emp-card-value' style='color:{accent}'>{value}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _render_average_cards(values: dict) -> None:
    cards = (
        ("Média Equipe — RAL Ader.", values["ral_adherents"]),
        ("Média Equipe — REC Ader.", values["rec_adherents"]),
        ("Média Equipe — RAL N. Ader.", values["ral_non_adherents"]),
        ("Média Equipe — REC N. Ader.", values["rec_non_adherents"]),
    )
    cols = st.columns(4)
    for col, (label, value) in zip(cols, cards):
        with col:
            st.markdown(
                (
                    "<div class='cop-emp-average'>"
                    f"<div class='cop-emp-average-label'>{label}</div>"
                    f"<div class='cop-emp-average-value'>{value:.1f}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def style_ranking_table(frame: pd.DataFrame):
    styler = frame.style.format({"Aderência %": "{:.1f}"}, na_rep="—")
    if "Eventos" in frame.columns:
        styler = styler.background_gradient(cmap="Purples", subset=["Eventos"])
    if "Aderência %" in frame.columns:
        styler = styler.background_gradient(cmap="YlGn", subset=["Aderência %"])
    return styler


def style_demand_analyst_table(frame: pd.DataFrame):
    formatters = {
        column: "{:.1f}%"
        for column in frame.columns
        if str(column).startswith("% ")
    }
    styler = frame.style.format(formatters, na_rep="—")
    for column in ("RAL Ader.", "REC Ader."):
        if column in frame.columns:
            styler = styler.background_gradient(cmap="Greens", subset=[column])
    for column in ("RAL N. Ader.", "REC N. Ader."):
        if column in frame.columns:
            styler = styler.background_gradient(cmap="Reds", subset=[column])
    for column in ("% RAL Ader.", "% REC Ader."):
        if column in frame.columns:
            styler = styler.background_gradient(cmap="YlGn", subset=[column])
    return styler


def style_breakdown_table(frame: pd.DataFrame):
    styler = frame.style.format({"Aderência %": "{:.1f}"}, na_rep="—")
    if "Eventos" in frame.columns:
        styler = styler.background_gradient(cmap="Purples", subset=["Eventos"])
    if "Aderência %" in frame.columns:
        styler = styler.background_gradient(cmap="YlGn", subset=["Aderência %"])
    return styler


def _analyst_demand_volume_pivot(rows: pd.DataFrame) -> pd.DataFrame:
    if rows is None or rows.empty or not {"login", "dimension_value", "volume"}.issubset(rows.columns):
        return pd.DataFrame()

    frame = rows.copy()
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
    frame["demand"] = frame["dimension_value"].astype(str).str.upper()
    frame = frame[frame["demand"].isin(["RAL", "REC"])]
    if frame.empty:
        return pd.DataFrame()

    pivot = (
        frame.groupby(["login", "demand"], dropna=False)["volume"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    for column in ("RAL", "REC"):
        if column not in pivot.columns:
            pivot[column] = 0
    return pivot[["login", "RAL", "REC"]]


def _analyst_universe(people: pd.DataFrame) -> list[str]:
    if people is None or people.empty or "login" not in people.columns:
        return []
    return sorted(
        login
        for login in people["login"].dropna().astype(str).unique()
        if login.strip()
    )


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None or frame.empty or "dimension" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["dimension"] == dimension].copy()


def _sum(frame: pd.DataFrame, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _weighted(
    frame: pd.DataFrame,
    value_col: str,
    weight_col: str,
) -> float | None:
    if (
        frame is None
        or frame.empty
        or value_col not in frame.columns
        or weight_col not in frame.columns
    ):
        return None
    values = pd.to_numeric(frame[value_col], errors="coerce")
    weights = pd.to_numeric(frame[weight_col], errors="coerce").fillna(0)
    valid = values.notna() & (weights > 0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _ratio(numerator, denominator) -> float:
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return 0.0
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 100


def _duration(seconds) -> str:
    if seconds is None:
        return "—"
    try:
        number = float(seconds)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(number) or number < 0:
        return "—"
    total = int(round(number))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-emp-card {
            background: #ffffff;
            border: 1px solid rgba(15, 23, 42, .06);
            border-left: 4px solid #111827;
            border-radius: 16px;
            box-shadow: 0 8px 20px rgba(15, 23, 42, .07);
            min-height: 96px;
            padding: 18px 16px 14px;
            text-align: center;
        }
        .cop-emp-card-label {
            color: #858990;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .cop-emp-card-value {
            font-size: 1.72rem;
            font-weight: 800;
            line-height: 1.1;
            margin-top: 8px;
        }
        .cop-emp-average {
            background: #ffffff;
            border: 1px solid rgba(15, 23, 42, .08);
            border-radius: 14px;
            min-height: 102px;
            padding: 18px 18px 14px;
        }
        .cop-emp-average-label {
            color: #30343b;
            font-size: .82rem;
        }
        .cop-emp-average-value {
            color: #1f2937;
            font-size: 1.75rem;
            font-weight: 800;
            margin-top: 10px;
        }
        .cop-emp-bestworst {
            color: #8a8f98;
            font-size: .84rem;
            margin: 2px 0 12px 2px;
        }
        .cop-emp-best { color: #48c78e; }
        .cop-emp-worst { color: #e76f7f; }
        </style>
        """,
        unsafe_allow_html=True,
    )
