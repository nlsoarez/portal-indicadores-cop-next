from __future__ import annotations

from html import escape
import math

import pandas as pd
import streamlit as st


INDICATOR_KEY = "validacao_20m"


def render_admin_validation_time(
    *,
    rows: pd.DataFrame,
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    details: pd.DataFrame,
    period: str,
    data_through: str,
    target,
) -> None:
    """Visão administrativa dedicada ao Tempo de Validação do Formulário."""

    _inject_styles()

    target_num = _number(target)
    summary = overall_summary(rows, metrics, details)

    st.markdown("### ✅ Tempo de Validação do Formulário")
    if target_num is not None:
        st.caption(
            f"Aderência ao tempo máximo permitido para validar o formulário TOA. "
            f"Meta de aderência: ≥ {target_num:.0f}%. · "
            f"Competência: {period or '—'} · Dados até: {data_through or period or '—'}"
        )
    else:
        st.caption(
            f"Aderência ao tempo máximo permitido para validar o formulário TOA. "
            f"Competência: {period or '—'} · Dados até: {data_through or period or '—'}"
        )

    _render_kpis(summary, target_num)

    st.markdown("#### 🏆 Ranking por Analista")
    ranking = build_ranking_table(people, metrics)
    if ranking.empty:
        st.info("Nenhum analista com resultado para a competência atual.")
    else:
        # A referência exibe os 10 melhores; os destaques de melhor/pior
        # continuam considerando toda a equipe, inclusive quem ficou fora do top 10.
        st.dataframe(
            style_ranking_table(ranking.head(10), target_num),
            use_container_width=True,
            hide_index=True,
        )

        best, worst = ranking_extremes(ranking)
        left, right = st.columns(2)
        with left:
            _render_extreme_card("🏆 MELHOR ADERÊNCIA", best, positive=True)
        with right:
            _render_extreme_card("⚠ MENOR ADERÊNCIA", worst, positive=False)

    st.markdown("### 🏢🏠 Aderência por Setor")
    sector_summary = build_sector_summary(rows, metrics)
    sector_tables = build_sector_tables(people, metrics)

    if sector_summary.empty:
        st.caption("Sem dados suficientes para consolidar os setores.")
    else:
        sector_names = sector_summary["Setor"].tolist()
        cols = st.columns(min(2, max(1, len(sector_names))))
        for idx, sector_name in enumerate(sector_names):
            column = cols[idx % len(cols)]
            with column:
                _render_sector_block(
                    sector_name,
                    sector_summary[
                        sector_summary["Setor"] == sector_name
                    ].iloc[0],
                    sector_tables.get(sector_name, pd.DataFrame()),
                    target_num,
                )

    st.markdown("### Por Grupo (IN_GRUPO) — Regional Leste")
    group_table = build_group_table(details)
    if group_table.empty:
        st.caption("Sem dados de grupo nesta carga.")
    else:
        best = group_table.sort_values(
            ["Aderência %", "Total"], ascending=[False, False]
        ).iloc[0]
        worst = group_table.sort_values(
            ["Aderência %", "Total"], ascending=[True, False]
        ).iloc[0]

        st.markdown(
            (
                "<div class='cop-val-bestworst'>"
                f"<span class='cop-val-best'>●</span> Melhor: "
                f"<b>{escape(str(best['Grupo']))}</b> ({best['Aderência %']:.1f}%) · "
                "<span class='cop-val-worst'>●</span> Pior: "
                f"<b>{escape(str(worst['Grupo']))}</b> ({worst['Aderência %']:.1f}%)"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        st.dataframe(
            style_group_table(group_table, target_num),
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
        adherents = _sum(overall, "successes")
        non_adherents = _sum(overall, "losses")
        tmr_seconds = _weighted(overall, "tmr_seconds", "volume")
    elif metrics is not None and not metrics.empty:
        total = _sum(metrics, "volume")
        adherents = _sum(metrics, "successes")
        non_adherents = _sum(metrics, "losses")
        tmr_seconds = _weighted(metrics, "tmr_seconds", "volume")
    else:
        total = _sum(rows, "volume")
        adherence = _weighted(rows, "value", "volume") or 0.0
        adherents = total * adherence / 100 if total > 0 else 0.0
        non_adherents = max(total - adherents, 0.0)
        tmr_seconds = None

    return {
        "total": int(round(total)),
        "adherents": int(round(adherents)),
        "non_adherents": int(round(non_adherents)),
        "adherence": _ratio(adherents, total),
        "tmr_minutes": _minutes(tmr_seconds),
    }


def build_ranking_table(
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

    if metrics is not None and not metrics.empty:
        frame = metrics.copy()
        for column in ("volume", "successes", "losses"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(
                    frame[column], errors="coerce"
                ).fillna(0)
        grouped = (
            frame.groupby("login", dropna=False)
            .agg(
                Total=("volume", "sum"),
                Aderentes=("successes", "sum"),
                Nao_Aderentes=("losses", "sum"),
                tmr_seconds=("tmr_seconds", "mean"),
            )
            .reset_index()
        )
    else:
        frame = people.copy()
        frame["volume"] = pd.to_numeric(
            frame["volume"], errors="coerce"
        ).fillna(0)
        frame["value"] = pd.to_numeric(
            frame["value"], errors="coerce"
        ).fillna(0)
        frame["_success"] = frame["volume"] * frame["value"] / 100
        grouped = (
            frame.groupby("login", dropna=False)
            .agg(
                Total=("volume", "sum"),
                Aderentes=("_success", "sum"),
            )
            .reset_index()
        )
        grouped["Nao_Aderentes"] = grouped["Total"] - grouped["Aderentes"]
        grouped["tmr_seconds"] = None

    grouped = grouped.merge(identity, on="login", how="left")
    for column in ("Total", "Aderentes", "Nao_Aderentes"):
        grouped[column] = pd.to_numeric(grouped[column], errors="coerce").fillna(0)

    grouped["Aderência %"] = grouped.apply(
        lambda row: _ratio(row["Aderentes"], row["Total"]),
        axis=1,
    )
    grouped["TMR Médio (min)"] = grouped["tmr_seconds"].apply(_minutes)
    grouped = grouped.sort_values(
        ["Aderência %", "Total", "display_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    grouped.insert(0, "#", range(1, len(grouped) + 1))

    for column in ("Total", "Aderentes", "Nao_Aderentes"):
        grouped[column] = grouped[column].round().astype(int)

    return grouped[
        [
            "#",
            "display_name",
            "segment_name",
            "Total",
            "Aderentes",
            "Aderência %",
            "TMR Médio (min)",
        ]
    ].rename(
        columns={
            "display_name": "Analista",
            "segment_name": "Setor",
        }
    )


def ranking_extremes(ranking: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if ranking is None or ranking.empty:
        empty = pd.Series(dtype="object")
        return empty, empty

    best = ranking.sort_values(
        ["Aderência %", "Total"],
        ascending=[False, False],
    ).iloc[0]
    worst = ranking.sort_values(
        ["Aderência %", "Total"],
        ascending=[True, False],
    ).iloc[0]
    return best, worst


def build_sector_summary(
    rows: pd.DataFrame,
    metrics: pd.DataFrame,
) -> pd.DataFrame:
    if rows is None or rows.empty or "segment_name" not in rows.columns:
        return pd.DataFrame()

    output = []
    for sector, part in rows.groupby("segment_name", dropna=False):
        sector_name = str(sector or "—")
        total = _sum(part, "volume")
        adherence = _weighted(part, "value", "volume") or 0.0

        metric_part = pd.DataFrame()
        if (
            metrics is not None
            and not metrics.empty
            and "segment_name" in metrics.columns
        ):
            metric_part = metrics[metrics["segment_name"] == sector].copy()

        if not metric_part.empty:
            total = _sum(metric_part, "volume")
            adherents = _sum(metric_part, "successes")
            adherence = _ratio(adherents, total)
            tmr_minutes = _minutes(
                _weighted(metric_part, "tmr_seconds", "volume")
            )
        else:
            tmr_minutes = None

        output.append(
            {
                "Setor": sector_name,
                "Aderência Média": adherence,
                "TMR Médio (min)": tmr_minutes,
                "Total": int(round(total)),
            }
        )

    return pd.DataFrame(output).sort_values("Setor").reset_index(drop=True)


def build_sector_tables(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    ranking = build_ranking_table(people, metrics)
    if ranking.empty:
        return {}

    result: dict[str, pd.DataFrame] = {}
    for sector, part in ranking.groupby("Setor", dropna=False):
        sector_name = str(sector or "—")
        scoped = part.copy().sort_values(
            ["Aderência %", "Total", "Analista"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        scoped["#"] = range(1, len(scoped) + 1)
        result[sector_name] = scoped[
            ["#", "Analista", "Total", "Aderência %", "TMR Médio (min)"]
        ]
    return result


def build_group_table(details: pd.DataFrame) -> pd.DataFrame:
    rows = _dimension_rows(details, "group")
    if rows.empty:
        return pd.DataFrame()

    records = []
    for group, part in rows.groupby("dimension_value", dropna=False):
        if group is None or not str(group).strip():
            continue
        total = _sum(part, "volume")
        adherents = _sum(part, "successes")
        records.append(
            {
                "Grupo": str(group),
                "Total": int(round(total)),
                "Aderentes": int(round(adherents)),
                "Aderência %": _ratio(adherents, total),
                "TMR (min)": _minutes(
                    _weighted(part, "tmr_seconds", "volume")
                ),
            }
        )

    if not records:
        return pd.DataFrame()

    return (
        pd.DataFrame(records)
        .sort_values(
            ["Total", "Aderência %", "Grupo"],
            ascending=[False, False, True],
        )
        .reset_index(drop=True)
    )


def _render_kpis(summary: dict, target: float | None) -> None:
    cards = (
        ("TOTAL", str(summary["total"]), "#2e86c1"),
        ("ADERENTES", str(summary["adherents"]), "#27ae60"),
        ("NÃO ADERENTES", str(summary["non_adherents"]), "#e74c3c"),
        (
            "ADERÊNCIA",
            f"{summary['adherence']:.1f}%",
            _result_color(float(summary["adherence"]), target),
        ),
        (
            "TMR MÉDIO (MIN)",
            "—" if summary["tmr_minutes"] is None else f"{summary['tmr_minutes']:.1f}",
            "#f39c12",
        ),
    )
    cols = st.columns(5)
    for col, (label, value, accent) in zip(cols, cards):
        with col:
            st.markdown(
                (
                    "<div class='cop-val-card'>"
                    f"<div class='cop-val-card-label'>{label}</div>"
                    f"<div class='cop-val-card-value' style='color:{accent}'>{value}</div>"
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
    tmr = row.get("TMR Médio (min)")
    tmr_label = "—" if tmr is None or pd.isna(tmr) else f"{float(tmr):.1f} min"
    st.markdown(
        (
            f"<div class='cop-val-extreme' style='border-left-color:{border};background:{background}'>"
            f"<div class='cop-val-extreme-label'>{label}</div>"
            f"<div class='cop-val-extreme-name' style='color:{border}'>{escape(str(row.get('Analista') or '—'))}</div>"
            f"<div class='cop-val-extreme-sub'>{float(row.get('Aderência %') or 0):.1f}% · TMR: {tmr_label}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_sector_block(
    sector_name: str,
    summary: pd.Series,
    table: pd.DataFrame,
    target: float | None,
) -> None:
    icon = "🏢" if str(sector_name).strip().upper() == "EMPRESARIAL" else "🏠"
    st.markdown(f"#### {icon} {sector_name.upper()}")

    c1, c2 = st.columns(2)
    with c1:
        _render_sector_metric(
            "ADERÊNCIA MÉDIA",
            f"{float(summary['Aderência Média']):.1f}%",
            _result_color(float(summary["Aderência Média"]), target),
        )
    with c2:
        tmr = summary.get("TMR Médio (min)")
        _render_sector_metric(
            "TMR MÉDIO (MIN)",
            "—" if tmr is None or pd.isna(tmr) else f"{float(tmr):.1f}",
            "#2e86c1",
        )

    if table is not None and not table.empty:
        st.dataframe(
            style_sector_table(table, target),
            use_container_width=True,
            hide_index=True,
        )


def _render_sector_metric(label: str, value: str, accent: str) -> None:
    st.markdown(
        (
            "<div class='cop-val-sector-card'>"
            f"<div class='cop-val-card-label'>{label}</div>"
            f"<div class='cop-val-card-value' style='color:{accent}'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def style_ranking_table(frame: pd.DataFrame, target: float | None):
    styler = frame.style.format(
        {
            "Aderência %": "{:.1f}",
            "TMR Médio (min)": "{:.1f}",
        },
        na_rep="—",
    )
    if "Aderência %" in frame.columns:
        styler = styler.apply(
            lambda series: [
                _adherence_style(value, target)
                for value in series
            ],
            subset=["Aderência %"],
        )
    if "TMR Médio (min)" in frame.columns:
        styler = styler.background_gradient(
            cmap="RdYlGn_r",
            subset=["TMR Médio (min)"],
        )
    return styler


def style_sector_table(frame: pd.DataFrame, target: float | None):
    return style_ranking_table(frame, target)


def style_group_table(frame: pd.DataFrame, target: float | None):
    styler = frame.style.format(
        {
            "Aderência %": "{:.1f}",
            "TMR (min)": "{:.1f}",
        },
        na_rep="—",
    )
    if "Total" in frame.columns:
        styler = styler.background_gradient(cmap="Blues", subset=["Total"])
    if "Aderência %" in frame.columns:
        styler = styler.apply(
            lambda series: [
                _adherence_style(value, target)
                for value in series
            ],
            subset=["Aderência %"],
        )
    return styler


def _adherence_style(value, target: float | None) -> str:
    number = _number(value)
    if number is None:
        return ""
    threshold = 85.0 if target is None else float(target)
    if number >= threshold:
        return "background-color: rgba(34, 197, 94, .22); color: #0b6b2d; font-weight: 700;"
    if number >= threshold - 5:
        return "background-color: rgba(250, 204, 21, .22); color: #8a6300; font-weight: 700;"
    return "background-color: rgba(239, 68, 68, .22); color: #b00020; font-weight: 700;"


def _result_color(value: float, target: float | None) -> str:
    threshold = 85.0 if target is None else float(target)
    if value >= threshold:
        return "#27ae60"
    if value >= threshold - 5:
        return "#d4a000"
    return "#e74c3c"


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


def _minutes(seconds) -> float | None:
    number = _number(seconds)
    if number is None or number < 0:
        return None
    return number / 60.0


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
        .cop-val-card,
        .cop-val-sector-card {
            background: #ffffff;
            border: 1px solid rgba(15,23,42,.06);
            border-left: 4px solid #111827;
            border-radius: 16px;
            box-shadow: 0 8px 20px rgba(15,23,42,.07);
            min-height: 96px;
            padding: 18px 16px 14px;
            text-align: center;
        }
        .cop-val-card-label {
            color: #858990;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .cop-val-card-value {
            font-size: 1.72rem;
            font-weight: 800;
            line-height: 1.1;
            margin-top: 8px;
        }
        .cop-val-extreme {
            border-left: 4px solid;
            border-radius: 14px;
            min-height: 100px;
            padding: 16px 16px 12px;
        }
        .cop-val-extreme-label {
            color: #858990;
            font-size: .67rem;
            font-weight: 800;
            letter-spacing: .07em;
        }
        .cop-val-extreme-name {
            font-size: .98rem;
            font-weight: 800;
            margin-top: 8px;
        }
        .cop-val-extreme-sub {
            color: #7b7f87;
            font-size: .74rem;
            margin-top: 7px;
        }
        .cop-val-bestworst {
            color: #8a8f98;
            font-size: .84rem;
            margin: 2px 0 12px 2px;
        }
        .cop-val-best { color: #48c78e; }
        .cop-val-worst { color: #e76f7f; }
        </style>
        """,
        unsafe_allow_html=True,
    )
