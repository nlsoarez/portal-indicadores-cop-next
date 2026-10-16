from __future__ import annotations

from html import escape
import pandas as pd
import streamlit as st


INDICATOR_KEY = "closing_assertiveness"


def render_admin_closing_assertiveness(
    *,
    rows: pd.DataFrame,
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    details: pd.DataFrame,
    period: str,
    data_through: str,
) -> None:
    """Visão administrativa dedicada ao Fechamento TOA x SIR da madrugada."""

    _inject_styles()
    summary = overall_summary(rows, metrics, details)
    period_label = compact_period(period or data_through)

    st.markdown(
        f"### 🌙 Fechamento TOA x SIR — Madrugada · Período: {period_label} (mês mais recente)"
    )
    st.caption(
        "Dados do turno Madrugada. Assertividade = fechamento TOA com causa compatível "
        "com o fechamento SIR."
    )

    _render_kpis(summary)

    st.divider()
    st.markdown("### 👥 Analistas — Assertividade Madrugada")
    st.markdown("#### 🏆 Ranking por Analista")

    ranking = build_analyst_ranking(people, metrics)
    if ranking.empty:
        st.info("Nenhum analista com resultado de fechamento TOA x SIR na competência atual.")
    else:
        st.dataframe(
            style_ranking(ranking),
            use_container_width=True,
            hide_index=True,
        )
        best, worst = ranking_extremes(ranking)
        left, right = st.columns(2)
        with left:
            _render_extreme_card("🏆 MELHOR ASSERTIVIDADE", best, positive=True)
        with right:
            _render_extreme_card("⚠ MENOR ASSERTIVIDADE", worst, positive=False)

    left, right = st.columns(2)
    with left:
        st.markdown("#### ❌ Top Causas Não Assertivas — TOA")
        toa = build_non_assertive_cause_table(details, "cause_toa", "Causa TOA")
        if toa.empty:
            st.caption("Sem causas TOA não assertivas nesta carga.")
        else:
            st.dataframe(
                style_loss_table(toa),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("#### ❌ Top Causas Não Assertivas — SIR")
        sir = build_non_assertive_cause_table(details, "cause_sir", "Causa SIR")
        if sir.empty:
            st.caption("Sem causas SIR não assertivas nesta carga.")
        else:
            st.dataframe(
                style_loss_table(sir),
                use_container_width=True,
                hide_index=True,
            )

    left, right = st.columns(2)
    with left:
        st.markdown("#### 🗺️ Por Grupo (IN_GRUPO) — Regional Leste")
        group_table = build_assertiveness_dimension_table(details, "group", "Grupo")
        if group_table.empty:
            st.caption("Sem dados de grupo nesta carga.")
        else:
            best_group = group_table.sort_values(
                ["Assertividade %", "Volume"], ascending=[False, False]
            ).iloc[0]
            worst_group = group_table.sort_values(
                ["Assertividade %", "Volume"], ascending=[True, False]
            ).iloc[0]
            st.markdown(
                (
                    "<div class='cop-close-bestworst'>"
                    f"<span class='cop-close-best'>●</span> Melhor: "
                    f"<b>{escape(str(best_group['Grupo']))}</b> ({best_group['Assertividade %']:.1f}%) · "
                    "<span class='cop-close-worst'>●</span> Pior: "
                    f"<b>{escape(str(worst_group['Grupo']))}</b> ({worst_group['Assertividade %']:.1f}%)"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            st.dataframe(
                style_assertiveness_table(group_table),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("#### 📋 Por Tipo de Demanda")
        demand_table = build_assertiveness_dimension_table(details, "demand", "Demanda")
        if demand_table.empty:
            st.caption("Sem dados de demanda nesta carga.")
        else:
            st.dataframe(
                style_assertiveness_table(demand_table),
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
        total = _sum(overall, "volume")
        assertive = _sum(overall, "successes")
        non_assertive = _sum(overall, "losses")
    elif metrics is not None and not metrics.empty:
        total = _sum(metrics, "volume")
        assertive = _sum(metrics, "successes")
        non_assertive = _sum(metrics, "losses")
    else:
        total = _sum(rows, "volume")
        rate = _weighted_value(rows) or 0.0
        assertive = total * rate / 100 if total > 0 else 0.0
        non_assertive = max(total - assertive, 0.0)

    analysts = 0
    if people_like := _analyst_count(metrics):
        analysts = people_like
    elif rows is not None and not rows.empty and "analysts" in rows.columns:
        analysts = int(round(_sum(rows, "analysts")))

    return {
        "total": int(round(total)),
        "assertive": int(round(assertive)),
        "non_assertive": int(round(non_assertive)),
        "assertiveness": _ratio(assertive, total),
        "analysts": analysts,
    }


def build_analyst_ranking(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
) -> pd.DataFrame:
    if people is None or people.empty:
        return pd.DataFrame()

    identity = (
        people[["login", "display_name", "segment_name"]]
        .dropna(subset=["login"])
        .drop_duplicates(subset=["login"])
    )

    if metrics is not None and not metrics.empty and {
        "login", "volume", "successes", "losses"
    }.issubset(metrics.columns):
        frame = metrics.copy()
        for column in ("volume", "successes", "losses"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
        totals = (
            frame.groupby("login", dropna=False)
            .agg(
                Tarefas=("volume", "sum"),
                Assertivos=("successes", "sum"),
                Nao_Assertivos=("losses", "sum"),
            )
            .reset_index()
        )
    else:
        frame = people.copy()
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce").fillna(0)
        frame["_assertive"] = frame["volume"] * frame["value"] / 100
        totals = (
            frame.groupby("login", dropna=False)
            .agg(
                Tarefas=("volume", "sum"),
                Assertivos=("_assertive", "sum"),
            )
            .reset_index()
        )
        totals["Nao_Assertivos"] = totals["Tarefas"] - totals["Assertivos"]

    totals = totals.merge(identity, on="login", how="left")
    for column in ("Tarefas", "Assertivos", "Nao_Assertivos"):
        totals[column] = pd.to_numeric(totals[column], errors="coerce").fillna(0)

    totals = totals[totals["Tarefas"] > 0].copy()
    totals["Assertividade %"] = totals.apply(
        lambda row: _ratio(row["Assertivos"], row["Tarefas"]),
        axis=1,
    )
    totals["Analista"] = totals["display_name"].fillna(totals["login"])
    totals["Setor"] = totals["segment_name"].fillna("—").astype(str).str.upper()

    totals = totals.sort_values(
        ["Assertividade %", "Tarefas", "Analista"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    totals.insert(0, "#", range(1, len(totals) + 1))

    for column in ("Tarefas", "Assertivos", "Nao_Assertivos"):
        totals[column] = totals[column].round().astype(int)

    return totals[
        ["#", "Analista", "Setor", "Tarefas", "Assertivos", "Assertividade %"]
    ]


def ranking_extremes(ranking: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if ranking is None or ranking.empty:
        empty = pd.Series(dtype="object")
        return empty, empty

    best = ranking.sort_values(
        ["Assertividade %", "Tarefas"],
        ascending=[False, False],
    ).iloc[0]
    worst = ranking.sort_values(
        ["Assertividade %", "Tarefas"],
        ascending=[True, False],
    ).iloc[0]
    return best, worst


def build_non_assertive_cause_table(
    details: pd.DataFrame,
    dimension: str,
    label: str,
    *,
    top: int = 15,
) -> pd.DataFrame:
    rows = _dimension_rows(details, dimension)
    if rows.empty or "losses" not in rows.columns:
        return pd.DataFrame()

    frame = rows.copy()
    frame["losses"] = pd.to_numeric(frame["losses"], errors="coerce").fillna(0)
    grouped = (
        frame.groupby("dimension_value", dropna=False)["losses"]
        .sum()
        .reset_index()
        .rename(columns={"dimension_value": label, "losses": "Não Assertivo"})
    )
    grouped = grouped[grouped[label].notna()].copy()
    grouped[label] = grouped[label].astype(str)
    grouped = grouped[grouped[label].str.strip().ne("")]
    grouped = grouped[grouped["Não Assertivo"] > 0]
    if grouped.empty:
        return pd.DataFrame()

    grouped["Não Assertivo"] = grouped["Não Assertivo"].round().astype(int)
    return (
        grouped.sort_values(
            ["Não Assertivo", label],
            ascending=[False, True],
        )
        .head(top)
        .reset_index(drop=True)
    )


def build_assertiveness_dimension_table(
    details: pd.DataFrame,
    dimension: str,
    label: str,
) -> pd.DataFrame:
    rows = _dimension_rows(details, dimension)
    if rows.empty:
        return pd.DataFrame()

    frame = rows.copy()
    for column in ("volume", "successes", "losses"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    records = []
    for value, part in frame.groupby("dimension_value", dropna=False):
        if value is None or not str(value).strip():
            continue
        volume = _sum(part, "volume")
        assertive = _sum(part, "successes")
        records.append(
            {
                label: str(value),
                "Volume": int(round(volume)),
                "Assertivos": int(round(assertive)),
                "Assertividade %": _ratio(assertive, volume),
            }
        )

    table = pd.DataFrame(records)
    if table.empty:
        return table

    return table.sort_values(
        ["Volume", "Assertividade %", label],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def style_ranking(frame: pd.DataFrame):
    styler = frame.style.format({"Assertividade %": "{:.1f}"}, na_rep="—")
    if "Tarefas" in frame.columns:
        styler = styler.background_gradient(cmap="Purples", subset=["Tarefas"])
    if "Assertividade %" in frame.columns:
        styler = styler.background_gradient(cmap="RdYlGn", subset=["Assertividade %"])
    return styler


def style_loss_table(frame: pd.DataFrame):
    styler = frame.style
    if "Não Assertivo" in frame.columns:
        styler = styler.background_gradient(cmap="Reds", subset=["Não Assertivo"])
    return styler


def style_assertiveness_table(frame: pd.DataFrame):
    styler = frame.style.format({"Assertividade %": "{:.1f}"}, na_rep="—")
    if "Volume" in frame.columns:
        styler = styler.background_gradient(cmap="Purples", subset=["Volume"])
    if "Assertividade %" in frame.columns:
        styler = styler.background_gradient(cmap="RdYlGn", subset=["Assertividade %"])
    return styler


def compact_period(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    digits = "".join(character for character in raw if character.isdigit())
    return digits[:6] if len(digits) >= 6 else raw


def _render_kpis(summary: dict) -> None:
    cards = (
        ("TOTAL TAREFAS", str(summary["total"]), "#8e44ad"),
        ("ASSERTIVOS ✅", str(summary["assertive"]), "#27ae60"),
        ("NÃO ASSERTIVOS ❌", str(summary["non_assertive"]), "#e74c3c"),
        ("ASSERTIVIDADE", f"{summary['assertiveness']:.1f}%", "#27ae60"),
        ("ANALISTAS", str(summary["analysts"]), "#2e86c1"),
    )
    cols = st.columns(5)
    for column, (label, value, color) in zip(cols, cards):
        with column:
            st.markdown(
                (
                    "<div class='cop-close-card'>"
                    f"<div class='cop-close-card-label'>{label}</div>"
                    f"<div class='cop-close-card-value' style='color:{color}'>{value}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _render_extreme_card(
    label: str,
    row: pd.Series,
    *,
    positive: bool,
) -> None:
    if row is None or row.empty:
        return

    border = "#22a35a" if positive else "#e53935"
    background = "rgba(34,163,90,.10)" if positive else "rgba(229,57,53,.10)"
    st.markdown(
        (
            f"<div class='cop-close-extreme' style='border-left-color:{border};background:{background}'>"
            f"<div class='cop-close-extreme-label'>{label}</div>"
            f"<div class='cop-close-extreme-name' style='color:{border}'>{escape(str(row.get('Analista') or '—'))}</div>"
            f"<div class='cop-close-extreme-sub'>{float(row.get('Assertividade %') or 0):.1f}% · "
            f"{int(row.get('Tarefas') or 0)} tarefas</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None or frame.empty or "dimension" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["dimension"] == dimension].copy()


def _sum(frame: pd.DataFrame, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _weighted_value(rows: pd.DataFrame) -> float | None:
    if rows is None or rows.empty or not {"value", "volume"}.issubset(rows.columns):
        return None
    values = pd.to_numeric(rows["value"], errors="coerce")
    weights = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (weights > 0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _analyst_count(metrics: pd.DataFrame) -> int:
    if metrics is None or metrics.empty or "login" not in metrics.columns:
        return 0
    return int(metrics["login"].dropna().astype(str).nunique())


def _ratio(numerator, denominator) -> float:
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return 0.0
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 100


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-close-card {
            background: #ffffff;
            border: 1px solid rgba(15,23,42,.06);
            border-left: 4px solid #111827;
            border-radius: 16px;
            box-shadow: 0 8px 20px rgba(15,23,42,.07);
            min-height: 96px;
            padding: 18px 16px 14px;
            text-align: center;
        }
        .cop-close-card-label {
            color: #858990;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .cop-close-card-value {
            font-size: 1.72rem;
            font-weight: 800;
            line-height: 1.1;
            margin-top: 8px;
        }
        .cop-close-extreme {
            border-left: 4px solid;
            border-radius: 14px;
            min-height: 98px;
            padding: 16px 16px 12px;
        }
        .cop-close-extreme-label {
            color: #858990;
            font-size: .67rem;
            font-weight: 800;
            letter-spacing: .07em;
        }
        .cop-close-extreme-name {
            font-size: .98rem;
            font-weight: 800;
            margin-top: 8px;
        }
        .cop-close-extreme-sub {
            color: #7b7f87;
            font-size: .74rem;
            margin-top: 7px;
        }
        .cop-close-bestworst {
            color: #8a8f98;
            font-size: .84rem;
            margin: 2px 0 12px 2px;
        }
        .cop-close-best { color: #48c78e; }
        .cop-close-worst { color: #e76f7f; }
        </style>
        """,
        unsafe_allow_html=True,
    )
