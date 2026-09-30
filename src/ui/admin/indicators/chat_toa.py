from __future__ import annotations

import math

import pandas as pd
import streamlit as st


INDICATOR_KEY = "chat_10m"
TMA_LIMIT_MINUTES = 10.0


def render_admin_chat_toa(
    *,
    rows: pd.DataFrame,
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    details: pd.DataFrame,
    period: str,
    data_through: str,
    target,
) -> None:
    """Visão administrativa dedicada ao Chat TOA — TMA <= 10 minutos."""

    _inject_styles()

    target_num = _number(target)
    summary = overall_summary(rows, metrics, details)
    period_label = compact_period(period or data_through)

    target_label = "—" if target_num is None else f"{target_num:.0f}%"
    st.markdown(
        f"### 💬 Chat TOA — TMA (≤10 min) · Meta: ≥{target_label} · Período: {period_label}"
    )
    st.caption(
        "TMA (Tempo Médio de Atendimento): cada chat com duração ≤ 10 min é aderente; "
        f"a meta é ter ao menos {target_label} dos chats aderentes."
    )

    _render_kpis(summary, target_num)

    st.markdown("### ⏱️ TMA — Tempo Médio de Atendimento")
    st.caption(
        "Meta: ≥ 75% dos chats com TMA ≤ 10 minutos. "
        "Volume: chats válidos processados pelo indicador."
    )

    st.markdown("#### 🏆 Ranking por Analista — TMA")
    ranking = build_tma_ranking(people, metrics)
    if ranking.empty:
        st.info("Nenhum analista com dados de Chat TOA na competência atual.")
        return

    # A referência exibe os 10 maiores volumes; melhor/pior consideram a equipe inteira.
    st.dataframe(
        style_tma_ranking(ranking.head(10), target_num),
        use_container_width=True,
        hide_index=True,
    )

    best, worst = ranking_extremes(ranking)
    _render_extremes(best, worst)


def overall_summary(
    rows: pd.DataFrame,
    metrics: pd.DataFrame,
    details: pd.DataFrame,
) -> dict:
    overall = _dimension_rows(details, "overall")

    if not overall.empty:
        volume = _sum(overall, "volume")
        adherents = _sum(overall, "successes")
        tma_seconds = _weighted(overall, "tma_seconds", "volume")
    elif metrics is not None and not metrics.empty:
        volume = _sum(metrics, "volume")
        adherents = _sum(metrics, "successes")
        tma_seconds = _weighted(metrics, "tma_seconds", "volume")
    else:
        volume = _sum(rows, "volume")
        adherence = _weighted(rows, "value", "volume") or 0.0
        adherents = volume * adherence / 100 if volume > 0 else 0.0
        tma_seconds = None

    return {
        "volume": int(round(volume)),
        "adherents": int(round(adherents)),
        "adherence": _ratio(adherents, volume),
        "tma_minutes": _minutes(tma_seconds),
    }


def build_tma_ranking(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
) -> pd.DataFrame:
    if people is None or people.empty:
        return pd.DataFrame()

    identity_cols = [
        column
        for column in ("login", "display_name", "segment_name")
        if column in people.columns
    ]
    if "login" not in identity_cols:
        return pd.DataFrame()

    identity = (
        people[identity_cols]
        .dropna(subset=["login"])
        .drop_duplicates(subset=["login"])
    )

    if (
        metrics is not None
        and not metrics.empty
        and {"login", "volume", "successes"}.issubset(metrics.columns)
    ):
        frame = metrics.copy()
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
        frame["successes"] = pd.to_numeric(frame["successes"], errors="coerce").fillna(0)

        records = []
        for login, part in frame.groupby("login", dropna=False):
            volume = float(part["volume"].sum())
            adherents = float(part["successes"].sum())
            records.append(
                {
                    "login": login,
                    "Vol. TMA": volume,
                    "Aderentes": adherents,
                    "TMA Médio (min)": _minutes(
                        _weighted(part, "tma_seconds", "volume")
                    ),
                }
            )
        totals = pd.DataFrame(records)
    else:
        frame = people.copy()
        if not {"login", "volume", "value"}.issubset(frame.columns):
            return pd.DataFrame()

        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce").fillna(0)
        frame["_adherents"] = frame["volume"] * frame["value"] / 100
        totals = (
            frame.groupby("login", dropna=False)
            .agg(
                **{
                    "Vol. TMA": ("volume", "sum"),
                    "Aderentes": ("_adherents", "sum"),
                }
            )
            .reset_index()
        )
        totals["TMA Médio (min)"] = None

    if totals.empty:
        return pd.DataFrame()

    totals = totals.merge(identity, on="login", how="left")
    totals["Vol. TMA"] = pd.to_numeric(totals["Vol. TMA"], errors="coerce").fillna(0)
    totals["Aderentes"] = pd.to_numeric(totals["Aderentes"], errors="coerce").fillna(0)
    totals = totals[totals["Vol. TMA"] > 0].copy()

    totals["TMA %"] = totals.apply(
        lambda row: _ratio(row["Aderentes"], row["Vol. TMA"]),
        axis=1,
    )
    totals["Analista"] = totals.get(
        "display_name",
        pd.Series(index=totals.index, dtype="object"),
    ).fillna(totals["login"])
    totals["Setor"] = totals.get(
        "segment_name",
        pd.Series(index=totals.index, dtype="object"),
    ).fillna("—").astype(str).str.upper()

    for column in ("Vol. TMA", "Aderentes"):
        totals[column] = totals[column].round().astype(int)

    # Ranking da referência é por volume de chats, não por aderência.
    totals = totals.sort_values(
        ["Vol. TMA", "TMA %", "Analista"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    totals.insert(0, "#", range(1, len(totals) + 1))

    return totals[
        [
            "#",
            "Analista",
            "Setor",
            "Vol. TMA",
            "Aderentes",
            "TMA %",
            "TMA Médio (min)",
        ]
    ]


def ranking_extremes(
    ranking: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    if ranking is None or ranking.empty:
        empty = pd.Series(dtype="object")
        return empty, empty

    best = ranking.sort_values(
        ["TMA %", "Vol. TMA", "Analista"],
        ascending=[False, False, True],
    ).iloc[0]
    worst = ranking.sort_values(
        ["TMA %", "Vol. TMA", "Analista"],
        ascending=[True, False, True],
    ).iloc[0]
    return best, worst


def style_tma_ranking(
    frame: pd.DataFrame,
    target: float | None,
):
    styler = frame.style.format(
        {
            "TMA %": "{:.1f}",
            "TMA Médio (min)": "{:.2f}",
        },
        na_rep="—",
    )

    if "Vol. TMA" in frame.columns:
        styler = styler.background_gradient(
            cmap="Blues",
            subset=["Vol. TMA"],
        )

    if "TMA %" in frame.columns:
        styler = styler.apply(
            lambda series: [
                _adherence_style(value, target)
                for value in series
            ],
            subset=["TMA %"],
        )

    return styler


def compact_period(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"

    digits = "".join(character for character in raw if character.isdigit())
    return digits[:6] if len(digits) >= 6 else raw


def _render_kpis(
    summary: dict,
    target: float | None,
) -> None:
    adherence_color = _result_color(summary["adherence"], target)

    cards = (
        ("VOL. CHAT TMA", str(summary["volume"]), "#1abc9c"),
        ("TMA ADERENTES", str(summary["adherents"]), "#27ae60"),
        ("TMA %", f"{summary['adherence']:.1f}%", adherence_color),
        (
            "TMA MÉDIO (MIN)",
            "—"
            if summary["tma_minutes"] is None
            else f"{summary['tma_minutes']:.1f}",
            "#2980b9",
        ),
    )

    cols = st.columns(4)
    for column, (label, value, color) in zip(cols, cards):
        with column:
            st.markdown(
                (
                    "<div class='cop-chat-card'>"
                    f"<div class='cop-chat-card-label'>{label}</div>"
                    f"<div class='cop-chat-card-value' style='color:{color}'>{value}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _render_extremes(
    best: pd.Series,
    worst: pd.Series,
) -> None:
    if best is None or best.empty or worst is None or worst.empty:
        return

    st.markdown(
        (
            "<div class='cop-chat-extreme cop-chat-best'>"
            f"🏅 <b>Melhor TMA: {best['Analista']}</b> — {float(best['TMA %']):.1f}%"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        (
            "<div class='cop-chat-extreme cop-chat-worst'>"
            f"⚠️ <b>Pior TMA: {worst['Analista']}</b> — {float(worst['TMA %']):.1f}%"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _adherence_style(
    value,
    target: float | None,
) -> str:
    number = _number(value)
    if number is None:
        return ""

    threshold = 75.0 if target is None else float(target)
    if number >= threshold:
        return (
            "background-color: rgba(34,197,94,.24); "
            "color:#0b6b2d; font-weight:700;"
        )
    return (
        "background-color: rgba(239,68,68,.22); "
        "color:#b00020; font-weight:700;"
    )


def _result_color(
    value,
    target: float | None,
) -> str:
    number = _number(value) or 0.0
    threshold = 75.0 if target is None else float(target)
    return "#27ae60" if number >= threshold else "#e74c3c"


def _dimension_rows(
    frame: pd.DataFrame,
    dimension: str,
) -> pd.DataFrame:
    if frame is None or frame.empty or "dimension" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["dimension"] == dimension].copy()


def _sum(
    frame: pd.DataFrame,
    column: str,
) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return float(
        pd.to_numeric(frame[column], errors="coerce")
        .fillna(0)
        .sum()
    )


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

    return float(
        (values[valid] * weights[valid]).sum()
        / weights[valid].sum()
    )


def _ratio(
    numerator,
    denominator,
) -> float:
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
        .cop-chat-card {
            background:#ffffff;
            border:1px solid rgba(15,23,42,.06);
            border-left:4px solid #111827;
            border-radius:16px;
            box-shadow:0 8px 20px rgba(15,23,42,.07);
            min-height:96px;
            padding:18px 16px 14px;
            text-align:center;
            margin-bottom:12px;
        }
        .cop-chat-card-label {
            color:#858990;
            font-size:.68rem;
            font-weight:800;
            letter-spacing:.08em;
            text-transform:uppercase;
        }
        .cop-chat-card-value {
            font-size:1.72rem;
            font-weight:800;
            line-height:1.1;
            margin-top:8px;
        }
        .cop-chat-extreme {
            padding:4px 8px;
            font-size:.82rem;
            line-height:1.4;
        }
        .cop-chat-best {
            background:rgba(34,197,94,.11);
        }
        .cop-chat-worst {
            background:rgba(239,68,68,.10);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
