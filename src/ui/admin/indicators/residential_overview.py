from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext
from src.ui.admin.external_analysts import (
    _as_frame, _partition_external_records, _monthly_indicator_summary,
    _monthly_external_people, _detail_table,
)


RESIDENTIAL_INDICATOR_ORDER = (
    "res_etit_fibra_hfc",
    "res_etit_gpon",
    "res_assert_fibra_hfc",
    "res_assert_gpon",
)

INDICATOR_META = {
    "res_etit_fibra_hfc": {
        "title": "ETIT FIBRA HFC",
        "success": "aderentes",
        "loss": "não aderentes",
        "rate": "aderência",
        "accent": "#f57c00",
    },
    "res_etit_gpon": {
        "title": "ETIT GPON",
        "success": "aderentes",
        "loss": "não aderentes",
        "rate": "aderência",
        "accent": "#8e44ad",
    },
    "res_assert_fibra_hfc": {
        "title": "ASSERT. ACION. FIBRA HFC",
        "success": "assertivos",
        "loss": "não assertivos",
        "rate": "assertividade",
        "accent": "#2e86c1",
    },
    "res_assert_gpon": {
        "title": "ASSERT. ACION. GPON",
        "success": "assertivos",
        "loss": "não assertivos",
        "rate": "assertividade",
        "accent": "#27ae60",
    },
}


def render_admin_residential_overview(
    *,
    indicator_keys: tuple[str, ...] | list[str],
    ctx: AccessContext,
    dashboard: DashboardService,
    segment_df: pd.DataFrame,
    analyst_df: pd.DataFrame,
    analyst_breakdowns_df: pd.DataFrame,
    breakdown_df: pd.DataFrame,
) -> None:
    visible = [
        key
        for key in RESIDENTIAL_INDICATOR_ORDER
        if key in set(indicator_keys)
    ]
    if not visible:
        return

    _inject_styles()

    st.markdown("### 📊 Resumo por Indicador")
    cols = st.columns(len(visible))
    for column, key in zip(cols, visible):
        summary = indicator_summary(segment_df, breakdown_df, key)
        meta = INDICATOR_META[key]
        with column:
            _render_summary_card(meta, summary)

    turn_table = build_turn_table(breakdown_df, visible)
    if not turn_table.empty:
        st.markdown("### 🕘 Aderência / Assertividade por Turno")
        st.dataframe(
            _style_result_table(turn_table),
            use_container_width=True,
            hide_index=True,
        )

    # Primeiro: indicadores e comportamento da PRÓPRIA equipe.
    # A visão de outras equipes é renderizada só depois das abas detalhadas.
    with st.expander(
        "Atuação da minha equipe — dentro e fora da janela",
        expanded=True,
    ):
        st.markdown("#### Minha equipe — 22h00–05h59 × 06h00–21h59")
        st.caption(
            "Os logins aqui pertencem à equipe cadastrada e NÃO são externos. " 
            "Janela operacional considerada: 22:00–05:59. "
            "Fora da janela: 06:00–21:59."
        )
    
        window = build_window_summary(breakdown_df, visible)
        c1, c2, c3 = st.columns(3)
        with c1:
            _render_window_card(
                "Dentro da janela · 22:00–05:59",
                window["inside_volume"],
                window["inside_rate"],
                "#27ae60",
            )
        with c2:
            _render_window_card(
                "Fora da janela · 06:00–21:59",
                window["outside_volume"],
                window["outside_rate"],
                "#e67e22",
            )
        with c3:
            outside_share = window["outside_share"]
            st.markdown(
                (
                    "<div class='cop-window-card'>"
                    "<div class='cop-window-label'>PARTICIPAÇÃO FORA DA JANELA</div>"
                    f"<div class='cop-window-main'>{outside_share:.1f}%</div>"
                    "<div class='cop-window-sub'>do volume registrado</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
    
        outside_by_indicator = build_outside_indicator_table(breakdown_df, visible)
        outside_by_analyst = build_outside_analyst_table(
            analyst_breakdowns_df,
            analyst_df,
            visible,
        )
    
        left, right = st.columns(2)
        with left:
            st.markdown("#### Fora da janela por indicador")
            if outside_by_indicator.empty:
                st.caption("Nenhum registro da equipe entre 06:00 e 21:59.")
            else:
                st.dataframe(
                    _style_result_table(outside_by_indicator),
                    use_container_width=True,
                    hide_index=True,
                )
        with right:
            st.markdown("#### Meus analistas atuando fora da janela")
            if outside_by_analyst.empty:
                st.caption("Nenhum analista da equipe com atuação entre 06:00 e 21:59.")
            else:
                st.dataframe(
                    _style_result_table(outside_by_analyst),
                    use_container_width=True,
                    hide_index=True,
                )
    

    st.divider()


def _render_external_residential_night(
    ctx: AccessContext,
    dashboard: DashboardService,
    residential_segment_id: int,
) -> None:
    """Outras equipes atendendo no horário do administrador, nunca sua equipe."""
    st.markdown("### 🌙 Outras equipes trabalhando na minha janela")
    st.caption(
        "Analistas que NÃO pertencem à equipe cadastrada no portal, "
        "mas registraram demandas entre 22h00 e 05h59. "
        "Esta visão não inclui os meus próprios analistas, "
        "nem eventos diurnos. É independente da consulta 'fora da janela' da equipe."
    )
    months = dashboard.external_night_months(ctx, [residential_segment_id])
    if not months:
        st.info(
            "Nenhum analista de fora da equipe identificado nas fontes "
            "residenciais disponíveis."
        )
        return
    month = st.selectbox(
        "Competência — analistas de outras equipes",
        months,
        key="admin_residential_external_month_v2",
    )
    records = dashboard.external_night_payload(
        ctx, [residential_segment_id], month
    )
    verified = _partition_external_records(records)["confirmed"]
    # Restringir aos indicadores técnicos Residenciais. Chat/TOA são
    # analisados na área administrativa própria, não nesta tabela técnica.
    frame = _as_frame([
        item for item in verified
        if item["indicator_key"] in RESIDENTIAL_INDICATOR_ORDER
    ])
    if frame.empty:
        st.warning(
            "Sem atendimentos externos confirmados no período entre 22h00 "
            "e 05h59 para ETIT e Assertividade Residencial."
        )
        return

    metrics = st.columns(3)
    metrics[0].metric("Analistas externos no mês", frame["login"].nunique())
    metrics[1].metric("Atendimentos externos no mês", int(frame["volume"].sum()))
    metrics[2].metric("Indicadores com atendimentos", frame["indicator_key"].nunique())

    st.markdown(f"#### Resultado mensal por indicador — {month}")
    st.caption(
        "Consolidado do mês inteiro, exclusivamente entre 22h00 e 05h59. "
        "Resultado mensal = total de positivos no mês ÷ total de eventos "
        "do mesmo indicador. Não é a média simples dos percentuais diários."
    )
    summary = _monthly_indicator_summary(frame)
    st.dataframe(summary, use_container_width=True, hide_index=True)

    keys = [
        key for key in RESIDENTIAL_INDICATOR_ORDER
        if key in set(frame["indicator_key"])
    ]
    selection = st.selectbox(
        "Indicador para detalhamento mensal dos analistas externos",
        keys,
        format_func=lambda key: INDICATOR_META[key]["title"],
        key="admin_residential_external_indicator_monthly_v3",
    )
    scoped = frame[frame["indicator_key"] == selection]
    volume = int(scoped["volume"].sum())
    positives = int(scoped["successes"].sum())
    negatives = int(scoped["losses"].sum())
    monthly_result = positives * 100 / volume if volume else 0.0

    st.markdown(
        f"#### {INDICATOR_META[selection]['title']} — consolidado de {month}"
    )
    cards = st.columns(4)
    cards[0].metric("Aderência/Assertividade no mês", f"{monthly_result:.1f}%".replace(".", ","))
    cards[1].metric("Volume mensal", volume)
    cards[2].metric("Positivos no mês", positives)
    cards[3].metric("Negativos no mês", negatives)

    monthly_people = _monthly_external_people(scoped)
    st.markdown("##### Resultado mensal por analista externo")
    st.dataframe(
        monthly_people,
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Exportar consolidado mensal dos externos (CSV)",
        data=monthly_people.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"externos_{selection}_{month}_mensal.csv",
        mime="text/csv",
        key="admin_residential_external_monthly_export_v3",
    )
    with st.expander("Consultar dias e horários que compõem o mês", expanded=False):
        st.caption(
            "Esta tabela contém o detalhamento diário usado no consolidado "
            "acima. Os dias não são tratados como resultados mensais separados."
        )
        detail = _detail_table(scoped)
        st.dataframe(detail, use_container_width=True, hide_index=True)
        st.download_button(
            "Exportar ocorrências por dia e hora (CSV)",
            detail.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"externos_{selection}_{month}_ocorrencias.csv",
            mime="text/csv",
            key="admin_residential_external_detail_export_v3",
        )
    st.caption(
        "Os atendimentos de outras equipes não entram nos indicadores da "
        "minha equipe. Apenas horários confirmados entre 22h00 e 05h59 "
        "compõem os totais mensais."
    )


def indicator_summary(
    segment_df: pd.DataFrame,
    breakdown_df: pd.DataFrame,
    indicator_key: str,
) -> dict:
    rows = _indicator_rows(segment_df, indicator_key)
    detail = _overall_rows(breakdown_df, indicator_key)

    if not detail.empty:
        volume = _sum(detail, "volume")
        successes = _sum(detail, "successes")
        losses = _sum(detail, "losses")
        rate = 0.0 if volume <= 0 else successes / volume * 100
        tma = _weighted(detail, "tma_seconds", "volume")
        tmr = _weighted(detail, "tmr_seconds", "volume")
    else:
        volume = _sum(rows, "volume")
        rate = _weighted(rows, "value", "volume") or 0.0
        successes = volume * rate / 100 if volume > 0 else 0.0
        losses = max(volume - successes, 0.0)
        tma = None
        tmr = None

    return {
        "volume": int(round(volume)),
        "successes": int(round(successes)),
        "losses": int(round(losses)),
        "rate": float(rate),
        "non_rate": max(0.0, 100.0 - float(rate)) if volume > 0 else 0.0,
        "tma_seconds": tma,
        "tmr_seconds": tmr,
    }


def build_turn_table(
    breakdown_df: pd.DataFrame,
    indicator_keys: tuple[str, ...] | list[str],
) -> pd.DataFrame:
    rows = _dimension_rows(breakdown_df, indicator_keys, "turn")
    if rows.empty:
        return pd.DataFrame()

    table = _aggregate_ratio(rows, "dimension_value", "Turno")
    if table.empty:
        return table

    order_map = {
        "MANHÃ": 0,
        "MANHA": 0,
        "TARDE": 1,
        "MADRUGADA": 2,
        "NOITE": 3,
    }
    table["_order"] = table["Turno"].astype(str).str.upper().map(order_map).fillna(99)
    table = table.sort_values(["_order", "Turno"]).drop(columns="_order").reset_index(drop=True)
    return table


def build_window_summary(
    breakdown_df: pd.DataFrame,
    indicator_keys: tuple[str, ...] | list[str],
) -> dict:
    rows = _hour_rows(breakdown_df, indicator_keys)
    if rows.empty:
        return {
            "inside_volume": 0,
            "inside_rate": 0.0,
            "outside_volume": 0,
            "outside_rate": 0.0,
            "outside_share": 0.0,
        }

    inside = rows[rows["_hour"].apply(_inside_window)]
    outside = rows[~rows["_hour"].apply(_inside_window)]

    inside_volume = _sum(inside, "volume")
    inside_successes = _sum(inside, "successes")
    outside_volume = _sum(outside, "volume")
    outside_successes = _sum(outside, "successes")
    total = inside_volume + outside_volume

    return {
        "inside_volume": int(round(inside_volume)),
        "inside_rate": _ratio(inside_successes, inside_volume),
        "outside_volume": int(round(outside_volume)),
        "outside_rate": _ratio(outside_successes, outside_volume),
        "outside_share": 0.0 if total <= 0 else outside_volume / total * 100,
    }


def build_outside_indicator_table(
    breakdown_df: pd.DataFrame,
    indicator_keys: tuple[str, ...] | list[str],
) -> pd.DataFrame:
    rows = _hour_rows(breakdown_df, indicator_keys)
    if rows.empty:
        return pd.DataFrame()

    outside = rows[~rows["_hour"].apply(_inside_window)].copy()
    if outside.empty:
        return pd.DataFrame()

    output = []
    for key in RESIDENTIAL_INDICATOR_ORDER:
        if key not in set(indicator_keys):
            continue
        all_part = rows[rows["indicator_key"] == key]
        part = outside[outside["indicator_key"] == key]
        if part.empty:
            continue
        volume = _sum(part, "volume")
        successes = _sum(part, "successes")
        losses = _sum(part, "losses")
        total_volume = _sum(all_part, "volume")
        output.append(
            {
                "Indicador": INDICATOR_META[key]["title"],
                "Volume fora": int(round(volume)),
                "Positivos": int(round(successes)),
                "Negativos": int(round(losses)),
                "Resultado %": _ratio(successes, volume),
                "% do indicador fora": 0.0 if total_volume <= 0 else volume / total_volume * 100,
            }
        )

    return pd.DataFrame(output)


def build_outside_analyst_table(
    analyst_breakdowns_df: pd.DataFrame,
    analyst_df: pd.DataFrame,
    indicator_keys: tuple[str, ...] | list[str],
) -> pd.DataFrame:
    rows = _hour_rows(analyst_breakdowns_df, indicator_keys)
    if rows.empty or "login" not in rows.columns:
        return pd.DataFrame()

    outside = rows[~rows["_hour"].apply(_inside_window)].copy()
    if outside.empty:
        return pd.DataFrame()

    for column in ("volume", "successes", "losses"):
        outside[column] = pd.to_numeric(outside[column], errors="coerce").fillna(0)

    grouped = (
        outside.groupby("login", dropna=False)
        .agg(
            Volume=("volume", "sum"),
            Positivos=("successes", "sum"),
            Negativos=("losses", "sum"),
        )
        .reset_index()
    )

    names = {}
    if (
        analyst_df is not None
        and not analyst_df.empty
        and {"login", "display_name"}.issubset(analyst_df.columns)
    ):
        names = (
            analyst_df.dropna(subset=["login"])
            .drop_duplicates(subset=["login"])
            .set_index("login")["display_name"]
            .to_dict()
        )

    grouped["Analista"] = grouped["login"].map(names).fillna(grouped["login"])
    grouped["Resultado %"] = grouped.apply(
        lambda row: _ratio(row["Positivos"], row["Volume"]),
        axis=1,
    )
    for column in ("Volume", "Positivos", "Negativos"):
        grouped[column] = grouped[column].round().astype(int)

    grouped = grouped.sort_values(
        ["Volume", "Resultado %", "Analista"],
        ascending=[False, False, True],
    )
    return grouped[
        ["Analista", "login", "Volume", "Positivos", "Negativos", "Resultado %"]
    ].rename(columns={"login": "Matrícula"}).reset_index(drop=True)


def _render_summary_card(meta: dict, summary: dict) -> None:
    st.markdown(
        (
            f"<div class='cop-res-card' style='border-top-color:{meta['accent']}'>"
            f"<div class='cop-res-card-title'>{meta['title']}</div>"
            f"<div class='cop-res-card-volume' style='color:{meta['accent']}'>"
            f"{summary['volume']}</div>"
            f"<div class='cop-res-card-positive'>☑ {summary['successes']} "
            f"{meta['success']} · {summary['rate']:.1f}%</div>"
            f"<div class='cop-res-card-negative'>⚠ {summary['losses']} "
            f"{meta['loss']} · {summary['non_rate']:.1f}%</div>"
            f"<div class='cop-res-card-duration'>TMA: {_duration(summary['tma_seconds'])} "
            f"· TMR: {_duration(summary['tmr_seconds'])}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_window_card(label: str, volume: int, rate: float, accent: str) -> None:
    st.markdown(
        (
            f"<div class='cop-window-card' style='border-top-color:{accent}'>"
            f"<div class='cop-window-label'>{label}</div>"
            f"<div class='cop-window-main' style='color:{accent}'>{volume}</div>"
            f"<div class='cop-window-sub'>resultado consolidado · {rate:.1f}%</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _style_result_table(frame: pd.DataFrame):
    percent_columns = [
        column
        for column in (
            "Aderência / Assertividade %",
            "Não Aderência / Não Assertividade %",
            "Resultado %",
            "% do indicador fora",
        )
        if column in frame.columns
    ]
    styler = frame.style.format(
        {column: "{:.1f}" for column in percent_columns},
        na_rep="—",
    )

    result_column = next(
        (
            column
            for column in (
                "Aderência / Assertividade %",
                "Resultado %",
            )
            if column in frame.columns
        ),
        None,
    )
    if result_column is not None:
        styler = styler.background_gradient(cmap="RdYlGn", subset=[result_column])
    if "Volume" in frame.columns:
        styler = styler.background_gradient(cmap="Blues", subset=["Volume"])
    if "Volume fora" in frame.columns:
        styler = styler.background_gradient(cmap="Oranges", subset=["Volume fora"])
    return styler


def _aggregate_ratio(rows: pd.DataFrame, group_col: str, label: str) -> pd.DataFrame:
    required = {group_col, "volume", "successes", "losses"}
    if rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame()

    frame = rows.copy()
    for column in ("volume", "successes", "losses"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    grouped = (
        frame.groupby(group_col, dropna=False)
        .agg(
            Volume=("volume", "sum"),
            Positivos=("successes", "sum"),
            Negativos=("losses", "sum"),
        )
        .reset_index()
        .rename(columns={group_col: label})
    )
    grouped = grouped[grouped[label].notna()].copy()
    grouped[label] = grouped[label].astype(str)
    grouped = grouped[grouped[label].str.strip().ne("")]
    grouped["Aderência / Assertividade %"] = grouped.apply(
        lambda row: _ratio(row["Positivos"], row["Volume"]),
        axis=1,
    )
    grouped["Não Aderência / Não Assertividade %"] = grouped.apply(
        lambda row: _ratio(row["Negativos"], row["Volume"]),
        axis=1,
    )
    for column in ("Volume", "Positivos", "Negativos"):
        grouped[column] = grouped[column].round().astype(int)

    return grouped.reset_index(drop=True)


def _indicator_rows(frame: pd.DataFrame, indicator_key: str) -> pd.DataFrame:
    if frame is None or frame.empty or "indicator_key" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["indicator_key"] == indicator_key].copy()


def _overall_rows(frame: pd.DataFrame, indicator_key: str) -> pd.DataFrame:
    if (
        frame is None
        or frame.empty
        or not {"indicator_key", "dimension"}.issubset(frame.columns)
    ):
        return pd.DataFrame()
    return frame[
        (frame["indicator_key"] == indicator_key)
        & (frame["dimension"] == "overall")
    ].copy()


def _dimension_rows(
    frame: pd.DataFrame,
    indicator_keys: tuple[str, ...] | list[str],
    dimension: str,
) -> pd.DataFrame:
    if (
        frame is None
        or frame.empty
        or not {"indicator_key", "dimension"}.issubset(frame.columns)
    ):
        return pd.DataFrame()
    return frame[
        frame["indicator_key"].isin(indicator_keys)
        & (frame["dimension"] == dimension)
    ].copy()


def _hour_rows(
    frame: pd.DataFrame,
    indicator_keys: tuple[str, ...] | list[str],
) -> pd.DataFrame:
    rows = _dimension_rows(frame, indicator_keys, "hour")
    if rows.empty or "dimension_value" not in rows.columns:
        return pd.DataFrame()

    rows["_hour"] = pd.to_numeric(rows["dimension_value"], errors="coerce")
    rows = rows[rows["_hour"].notna()].copy()
    rows["_hour"] = rows["_hour"].astype(int)
    rows = rows[(rows["_hour"] >= 0) & (rows["_hour"] <= 23)]
    return rows


def _inside_window(hour: int) -> bool:
    return int(hour) >= 22 or int(hour) <= 5


def _sum(frame: pd.DataFrame, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _weighted(frame: pd.DataFrame, value_col: str, weight_col: str) -> float | None:
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


def _ratio(numerator: float, denominator: float) -> float:
    try:
        denominator = float(denominator)
        numerator = float(numerator)
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
        .cop-res-card {
            background: #ffffff;
            border: 1px solid rgba(15,23,42,.06);
            border-top: 3px solid;
            border-radius: 17px;
            box-shadow: 0 7px 18px rgba(15,23,42,.08);
            min-height: 168px;
            padding: 20px 20px 16px;
        }
        .cop-res-card-title {
            color: #7b7f87;
            font-size: .70rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .cop-res-card-volume {
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1.05;
            margin-bottom: 9px;
        }
        .cop-res-card-positive {
            color: #18a957;
            font-size: .87rem;
            font-weight: 700;
            margin-bottom: 7px;
        }
        .cop-res-card-negative {
            color: #8a8f98;
            font-size: .75rem;
            margin-bottom: 9px;
        }
        .cop-res-card-duration {
            color: #8a8f98;
            font-size: .68rem;
        }
        .cop-window-card {
            background: #ffffff;
            border: 1px solid rgba(15,23,42,.06);
            border-top: 3px solid #64748b;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(15,23,42,.06);
            min-height: 116px;
            padding: 17px 18px 14px;
            text-align: center;
        }
        .cop-window-label {
            color: #71717a;
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .04em;
            text-transform: uppercase;
        }
        .cop-window-main {
            color: #334155;
            font-size: 1.72rem;
            font-weight: 800;
            margin-top: 6px;
        }
        .cop-window-sub {
            color: #8a8f98;
            font-size: .72rem;
            margin-top: 4px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
