from __future__ import annotations

from html import escape
import math

import pandas as pd
import streamlit as st


INDICATOR_KEY = "chat_10m"
TMA_LIMIT_MINUTES = 10.0

# Fallback de identidade preservado do dashboard legado. É usado somente quando
# a matrícula existe no analítico de Chat, mas ainda não possui nome no cadastro
# atual do portal.
LEGACY_TEAM_NAMES = {
    "N6088107": "LEANDRO CARVALHO",
    "N5619600": "BRUNO BUCARD",
    "N0189105": "IGOR MARINS",
    "N5737414": "SANDRO CARVALHO",
    "N5713690": "GABRIELA SILVA",
    "N5802257": "MAGNO MORAIS",
    "F201714": "FERNANDA FREITAS",
    "N6173055": "JEFFERSON COITINHO",
    "N0125317": "ROBERTO NASCIMENTO",
    "F218860": "ALDENES SILVA",
    "N5819183": "RODRIGO BERNARDINO",
    "N5926003": "SUELLEN SILVA",
    "N5932064": "MONICA RODRIGUES",
    "N0238475": "MARLEY RIBEIRO",
    "N5923221": "KELLY LIRA",
    "N5772086": "THIAGO SILVA",
    "N0239871": "LEONARDO ALMEIDA",
    "N5577565": "MARISTELLA SANTOS",
    "N5972428": "CRISTIANE SILVA",
    "N4014011": "ALAN DIAS",
    "F106664": "RAISSA OLIVEIRA",
}


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

    st.markdown("### 🏢🏠 TMA por Segmento")
    st.caption(
        "Aderência e TMA individual separados por segmento, mantendo o mesmo critério de ≤ 10 minutos."
    )
    _render_sector_tables(
        build_tma_sector_tables(ranking),
        target_num,
    )


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
    people_frame = people.copy() if people is not None else pd.DataFrame()
    metrics_frame = metrics.copy() if metrics is not None else pd.DataFrame()

    identity: dict[str, dict[str, str]] = {}
    if not people_frame.empty and "login" in people_frame.columns:
        for _, row in people_frame.iterrows():
            login = _normalize_login(row.get("login"))
            if not login:
                continue
            identity[login] = {
                "display_name": _clean_text(row.get("display_name")),
                "segment_name": _clean_text(row.get("segment_name")),
            }

    if (
        not metrics_frame.empty
        and {"login", "volume", "successes"}.issubset(metrics_frame.columns)
    ):
        metrics_frame["login"] = metrics_frame["login"].apply(_normalize_login)
        metrics_frame["volume"] = pd.to_numeric(
            metrics_frame["volume"], errors="coerce"
        ).fillna(0)
        metrics_frame["successes"] = pd.to_numeric(
            metrics_frame["successes"], errors="coerce"
        ).fillna(0)

        records = []
        for login, part in metrics_frame.groupby("login", dropna=False):
            login = _normalize_login(login)
            if not login:
                continue

            volume = float(part["volume"].sum())
            adherents = float(part["successes"].sum())
            metric_name = _first_text(part, "display_name")
            metric_sector = _first_text(part, "segment_name")
            fallback = identity.get(login, {})

            records.append(
                {
                    "login": login,
                    "Analista": (
                        metric_name
                        or fallback.get("display_name")
                        or LEGACY_TEAM_NAMES.get(login)
                        or login
                    ),
                    "Setor": (
                        metric_sector
                        or fallback.get("segment_name")
                        or "—"
                    ).upper(),
                    "Vol. TMA": volume,
                    "Aderentes": adherents,
                    "TMA Médio (min)": _minutes(
                        _weighted(part, "tma_seconds", "volume")
                    ),
                }
            )
        totals = pd.DataFrame(records)
    else:
        if (
            people_frame.empty
            or not {"login", "volume", "value"}.issubset(people_frame.columns)
        ):
            return pd.DataFrame()

        people_frame["login"] = people_frame["login"].apply(_normalize_login)
        people_frame["volume"] = pd.to_numeric(
            people_frame["volume"], errors="coerce"
        ).fillna(0)
        people_frame["value"] = pd.to_numeric(
            people_frame["value"], errors="coerce"
        ).fillna(0)
        people_frame["_adherents"] = (
            people_frame["volume"] * people_frame["value"] / 100
        )

        records = []
        for login, part in people_frame.groupby("login", dropna=False):
            login = _normalize_login(login)
            if not login:
                continue
            records.append(
                {
                    "login": login,
                    "Analista": (
                        _first_text(part, "display_name")
                        or LEGACY_TEAM_NAMES.get(login)
                        or login
                    ),
                    "Setor": (_first_text(part, "segment_name") or "—").upper(),
                    "Vol. TMA": float(part["volume"].sum()),
                    "Aderentes": float(part["_adherents"].sum()),
                    "TMA Médio (min)": None,
                }
            )
        totals = pd.DataFrame(records)

    if totals.empty:
        return pd.DataFrame()

    totals["Vol. TMA"] = pd.to_numeric(
        totals["Vol. TMA"], errors="coerce"
    ).fillna(0)
    totals["Aderentes"] = pd.to_numeric(
        totals["Aderentes"], errors="coerce"
    ).fillna(0)
    totals = totals[totals["Vol. TMA"] > 0].copy()

    totals["TMA %"] = totals.apply(
        lambda row: _ratio(row["Aderentes"], row["Vol. TMA"]),
        axis=1,
    )
    totals["Analista"] = totals.apply(
        lambda row: _clean_text(row.get("Analista"))
        or LEGACY_TEAM_NAMES.get(_normalize_login(row.get("login")))
        or _normalize_login(row.get("login")),
        axis=1,
    )
    totals["Setor"] = totals["Setor"].fillna("—").astype(str).str.upper()

    for column in ("Vol. TMA", "Aderentes"):
        totals[column] = totals[column].round().astype(int)

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


def build_tma_sector_tables(
    ranking: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    if ranking is None or ranking.empty or "Setor" not in ranking.columns:
        return {}

    output: dict[str, pd.DataFrame] = {}
    for sector, part in ranking.groupby("Setor", dropna=False):
        sector_name = str(sector or "—").upper()
        scoped = part.copy().sort_values(
            ["TMA %", "Vol. TMA", "Analista"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        scoped["#"] = range(1, len(scoped) + 1)
        output[sector_name] = scoped[
            [
                "#",
                "Analista",
                "Vol. TMA",
                "Aderentes",
                "TMA %",
                "TMA Médio (min)",
            ]
        ]
    return output


def sector_tma_summary(table: pd.DataFrame) -> dict:
    if table is None or table.empty:
        return {"volume": 0, "adherents": 0, "adherence": 0.0, "tma_minutes": None}

    volume = float(pd.to_numeric(table["Vol. TMA"], errors="coerce").fillna(0).sum())
    adherents = float(
        pd.to_numeric(table["Aderentes"], errors="coerce").fillna(0).sum()
    )

    valid_tma = pd.to_numeric(table["TMA Médio (min)"], errors="coerce")
    weights = pd.to_numeric(table["Vol. TMA"], errors="coerce").fillna(0)
    valid = valid_tma.notna() & (weights > 0)
    tma_minutes = (
        float((valid_tma[valid] * weights[valid]).sum() / weights[valid].sum())
        if valid.any()
        else None
    )

    return {
        "volume": int(round(volume)),
        "adherents": int(round(adherents)),
        "adherence": _ratio(adherents, volume),
        "tma_minutes": tma_minutes,
    }


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


def _render_sector_tables(
    tables: dict[str, pd.DataFrame],
    target: float | None,
) -> None:
    if not tables:
        st.caption("Sem dados suficientes para separar os analistas por segmento.")
        return

    preferred = ["RESIDENCIAL", "EMPRESARIAL", "PREVENTIVA"]
    sectors = [sector for sector in preferred if sector in tables]
    sectors.extend(sorted(sector for sector in tables if sector not in sectors))

    for start in range(0, len(sectors), 2):
        cols = st.columns(2)
        for column, sector in zip(cols, sectors[start:start + 2]):
            table = tables[sector]
            summary = sector_tma_summary(table)
            color = _result_color(summary["adherence"], target)
            icon = _sector_icon(sector)
            tma_text = (
                "—"
                if summary["tma_minutes"] is None
                else f"{summary['tma_minutes']:.2f} min"
            )

            with column:
                st.markdown(
                    (
                        "<div class='cop-chat-sector-head'>"
                        f"<div><b>{icon} {sector}</b></div>"
                        "<div class='cop-chat-sector-meta'>"
                        f"<span style='color:{color}'>{summary['adherence']:.1f}% aderência</span>"
                        f"<span>{summary['volume']} chats</span>"
                        f"<span>TMA médio {tma_text}</span>"
                        "</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.dataframe(
                    style_tma_ranking(table, target),
                    use_container_width=True,
                    hide_index=True,
                )


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
            f"🏅 <b>Melhor TMA: {escape(str(best['Analista']))}</b> — {float(best['TMA %']):.1f}%"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        (
            "<div class='cop-chat-extreme cop-chat-worst'>"
            f"⚠️ <b>Pior TMA: {escape(str(worst['Analista']))}</b> — {float(worst['TMA %']):.1f}%"
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


def _normalize_login(value) -> str:
    return str(value or "").strip().upper()


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split()).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _first_text(frame: pd.DataFrame, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    for value in frame[column].tolist():
        text = _clean_text(value)
        if text:
            return text
    return ""


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
        .cop-chat-card {
            background:linear-gradient(180deg, rgba(17,37,59,.94), rgba(9,22,37,.97));
            border:1px solid rgba(148,163,184,.16);
            border-left:4px solid rgba(148,163,184,.28);
            border-radius:16px;
            box-shadow:0 14px 34px rgba(0,0,0,.16);
            min-height:96px;
            padding:18px 16px 14px;
            text-align:center;
            margin-bottom:12px;
        }
        .cop-chat-card-label {
            color:#8fa0b6;
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
            padding:7px 10px;
            font-size:.82rem;
            line-height:1.4;
            border-radius:8px;
        }
        .cop-chat-sector-head {
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:12px;
            margin:8px 0 10px;
            padding:10px 12px;
            border:1px solid rgba(148,163,184,.14);
            border-radius:12px;
            background:rgba(15,32,52,.72);
            color:#f4f7fb;
        }
        .cop-chat-sector-meta {
            display:flex;
            flex-wrap:wrap;
            justify-content:flex-end;
            gap:8px 12px;
            color:#8fa0b6;
            font-size:.68rem;
        }
        .cop-chat-sector-meta span:first-child {
            font-weight:800;
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
