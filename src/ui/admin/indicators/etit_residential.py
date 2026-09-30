from __future__ import annotations

import math

import pandas as pd
import streamlit as st


def render_admin_residential_etit(
    *,
    indicator_key: str,
    rows: pd.DataFrame,
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    analyst_breakdowns: pd.DataFrame,
    details: pd.DataFrame,
    period: str,
    data_through: str,
) -> None:
    """Visão operacional dedicada ao Admin para ETIT/Assertividade GPON e HFC."""

    labels = _indicator_labels(indicator_key)
    title = labels["title"]
    is_gpon = labels["is_gpon"]
    base_detail = _overall_detail(details, indicator_key)
    base_numbers = _overall_numbers(rows, base_detail)

    _inject_styles()

    header = (
        f"🔎 {title} — {base_numbers['volume']} registros · "
        f"{base_numbers['adherence']:.1f}% {labels['rate_lower']}"
    )
    with st.expander(header, expanded=True):
        st.caption(
            f"Competência: {period or '—'} · Dados até: {data_through or period or '—'}"
        )

        service_choice = "Todos"
        scoped_details = details.copy()
        scoped_analyst_breakdowns = analyst_breakdowns.copy()

        # Regra de negócio: GPON é segmentado por Brownfield/Greenfield;
        # HFC permanece consolidado, tanto em ETIT quanto em Assertividade.
        if is_gpon:
            service_rows = _dimension_rows(details, "service")
            service_table = dimension_table(service_rows, "Serviço")
            if not service_table.empty:
                st.markdown("#### Consolidado por serviço GPON")
                st.dataframe(
                    style_table(_presentation_table(service_table, labels), volume_cmap="Blues"),
                    use_container_width=True,
                    hide_index=True,
                )

                available_services = [
                    str(value)
                    for value in service_table["Serviço"].dropna().tolist()
                    if str(value).strip()
                ]
                preferred = [
                    service for service in ("BROWNFIELD", "GREENFIELD")
                    if service in {value.upper() for value in available_services}
                ]
                if preferred:
                    canonical = {value.upper(): value for value in available_services}
                    available_services = [canonical[item] for item in preferred] + [
                        value for value in available_services
                        if value.upper() not in preferred
                    ]

                service_choice = st.radio(
                    "Serviço",
                    ["Todos", *available_services],
                    horizontal=True,
                    key=f"admin_etit_service_{indicator_key}",
                )
                if service_choice != "Todos":
                    scoped_details = _service_scoped_details(details, service_choice)
                    service_analyst_rows = _dimension_rows(analyst_breakdowns, "service")
                    scoped_analyst_breakdowns = service_analyst_rows[
                        service_analyst_rows["dimension_value"].astype(str) == str(service_choice)
                    ].copy()
            else:
                st.caption("A carga atual não possui o campo de serviço para segmentação GPON.")

        selected_detail = _overall_detail(scoped_details, indicator_key)
        numbers = _overall_numbers(rows, selected_detail)

        _render_metric_cards(numbers, labels)

        st.markdown("#### 👥 Por Analista")
        analyst_table = analyst_table_for_etit(
            people,
            metrics,
            service_rows=(
                scoped_analyst_breakdowns
                if is_gpon and service_choice != "Todos"
                else None
            ),
        )
        if analyst_table.empty:
            st.info("Nenhum analista com resultado para este recorte.")
        else:
            st.dataframe(
                style_table(_presentation_table(analyst_table, labels), volume_cmap="Blues"),
                use_container_width=True,
                hide_index=True,
            )

        group_rows = _dimension_rows(scoped_details, "group")
        group_table = dimension_table(group_rows, "IN_GRUPO")
        if not group_table.empty:
            st.markdown("#### Por Grupo (IN_GRUPO) — Regional Leste")
            best = group_table.sort_values(
                ["Aderência %", "Volume"], ascending=[False, False]
            ).iloc[0]
            worst = group_table.sort_values(
                ["Aderência %", "Volume"], ascending=[True, False]
            ).iloc[0]
            st.markdown(
                (
                    "<div class='cop-etit-bestworst'>"
                    f"<span class='cop-etit-best'>●</span> Melhor: "
                    f"<b>{best['IN_GRUPO']}</b> ({best['Aderência %']:.1f}%) · "
                    "<span class='cop-etit-worst'>●</span> Pior: "
                    f"<b>{worst['IN_GRUPO']}</b> ({worst['Aderência %']:.1f}%)"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            st.dataframe(
                style_table(_presentation_table(group_table, labels), volume_cmap="Blues"),
                use_container_width=True,
                hide_index=True,
            )

        solution_rows = _dimension_rows(scoped_details, "solution")
        solution_table = dimension_table(solution_rows, "Solução", top=15)
        if not solution_table.empty:
            st.markdown("#### Top 15 Soluções")
            st.dataframe(
                style_table(_presentation_table(solution_table, labels), volume_cmap="YlOrRd"),
                use_container_width=True,
                hide_index=True,
            )

        impact_rows = _dimension_rows(scoped_details, "impact")
        impact_table = dimension_table(impact_rows, "Impacto")
        if not impact_table.empty:
            st.markdown("#### Por Impacto")
            st.dataframe(
                style_table(_presentation_table(impact_table, labels), volume_cmap="Blues"),
                use_container_width=True,
                hide_index=True,
            )


def dimension_table(
    rows: pd.DataFrame,
    label: str,
    *,
    top: int | None = None,
) -> pd.DataFrame:
    required = {"dimension_value", "volume", "successes", "losses"}
    if rows is None or rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame()

    frame = rows.copy()
    for column in ("volume", "successes", "losses"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    grouped = (
        frame.groupby("dimension_value", dropna=False)
        .agg(
            Volume=("volume", "sum"),
            Aderentes=("successes", "sum"),
            Nao_Aderentes=("losses", "sum"),
        )
        .reset_index()
        .rename(columns={"dimension_value": label})
    )
    grouped = grouped[grouped[label].notna()].copy()
    grouped[label] = grouped[label].astype(str)
    grouped = grouped[grouped[label].str.strip().ne("")]
    if grouped.empty:
        return pd.DataFrame()

    grouped["Aderência %"] = grouped.apply(
        lambda row: 0.0 if row["Volume"] <= 0 else row["Aderentes"] / row["Volume"] * 100,
        axis=1,
    )
    grouped["Não Aderência %"] = grouped.apply(
        lambda row: 0.0 if row["Volume"] <= 0 else row["Nao_Aderentes"] / row["Volume"] * 100,
        axis=1,
    )
    grouped = grouped.sort_values(
        ["Volume", "Aderência %", label],
        ascending=[False, False, True],
    )
    if top is not None:
        grouped = grouped.head(top)

    for column in ("Volume", "Aderentes", "Nao_Aderentes"):
        grouped[column] = grouped[column].round().astype(int)

    return grouped.rename(columns={"Nao_Aderentes": "Não Aderentes"}).reset_index(drop=True)


def analyst_table_for_etit(
    people: pd.DataFrame,
    metrics: pd.DataFrame,
    *,
    service_rows: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if people is None or people.empty:
        return pd.DataFrame()

    identity = (
        people[["login", "display_name", "segment_name"]]
        .dropna(subset=["login"])
        .drop_duplicates(subset=["login"])
    )

    if service_rows is not None:
        required = {"login", "volume", "successes", "losses"}
        if service_rows.empty or not required.issubset(service_rows.columns):
            return pd.DataFrame()
        working = service_rows.copy()
        for column in ("volume", "successes", "losses"):
            working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0)
        totals = (
            working.groupby("login", dropna=False)
            .agg(
                Volume=("volume", "sum"),
                Aderentes=("successes", "sum"),
                Nao_Aderentes=("losses", "sum"),
            )
            .reset_index()
        )
    else:
        base = people.copy()
        base["volume"] = pd.to_numeric(base["volume"], errors="coerce").fillna(0)
        base["value"] = pd.to_numeric(base["value"], errors="coerce")
        totals = (
            base.groupby("login", dropna=False)
            .agg(Volume=("volume", "sum"))
            .reset_index()
        )

        metric_totals = pd.DataFrame()
        if (
            metrics is not None
            and not metrics.empty
            and {"login", "successes", "losses"}.issubset(metrics.columns)
        ):
            metric_frame = metrics.copy()
            metric_frame["successes"] = pd.to_numeric(
                metric_frame["successes"], errors="coerce"
            ).fillna(0)
            metric_frame["losses"] = pd.to_numeric(
                metric_frame["losses"], errors="coerce"
            ).fillna(0)
            metric_totals = (
                metric_frame.groupby("login", dropna=False)
                .agg(
                    Aderentes=("successes", "sum"),
                    Nao_Aderentes=("losses", "sum"),
                )
                .reset_index()
            )

        if not metric_totals.empty:
            totals = totals.merge(metric_totals, on="login", how="left")
        else:
            ratio = (
                base.assign(
                    _weighted_success=base["volume"] * base["value"].fillna(0) / 100
                )
                .groupby("login", dropna=False)
                .agg(Aderentes=("_weighted_success", "sum"))
                .reset_index()
            )
            totals = totals.merge(ratio, on="login", how="left")
            totals["Nao_Aderentes"] = totals["Volume"] - totals["Aderentes"]

    totals = totals.merge(identity, on="login", how="left")
    for column in ("Volume", "Aderentes", "Nao_Aderentes"):
        totals[column] = pd.to_numeric(totals[column], errors="coerce").fillna(0)

    totals["Aderência %"] = totals.apply(
        lambda row: 0.0 if row["Volume"] <= 0 else row["Aderentes"] / row["Volume"] * 100,
        axis=1,
    )
    totals["Não Aderência %"] = totals.apply(
        lambda row: 0.0 if row["Volume"] <= 0 else row["Nao_Aderentes"] / row["Volume"] * 100,
        axis=1,
    )
    totals = totals.sort_values(
        ["Aderência %", "Volume", "display_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    totals.insert(0, "#", range(1, len(totals) + 1))
    totals["Analista"] = totals["display_name"].fillna(totals["login"])
    totals["Setor"] = totals["segment_name"].fillna("—").astype(str).str.upper()

    for column in ("Volume", "Aderentes", "Nao_Aderentes"):
        totals[column] = totals[column].round().astype(int)

    return totals[
        [
            "#",
            "Analista",
            "Setor",
            "Volume",
            "Aderentes",
            "Nao_Aderentes",
            "Aderência %",
            "Não Aderência %",
        ]
    ].rename(columns={"Nao_Aderentes": "Não Aderentes"})


def style_table(frame: pd.DataFrame, *, volume_cmap: str = "Blues"):
    percent_columns = [
        column
        for column in (
            "Aderência %",
            "Não Aderência %",
            "Assertividade %",
            "Não Assertividade %",
        )
        if column in frame.columns
    ]
    styler = frame.style.format(
        {column: "{:.1f}" for column in percent_columns},
        na_rep="—",
    )
    if "Volume" in frame.columns and pd.to_numeric(
        frame["Volume"], errors="coerce"
    ).notna().any():
        styler = styler.background_gradient(cmap=volume_cmap, subset=["Volume"])

    result_column = next(
        (
            column
            for column in ("Aderência %", "Assertividade %")
            if column in frame.columns
        ),
        None,
    )
    if result_column and pd.to_numeric(
        frame[result_column], errors="coerce"
    ).notna().any():
        styler = styler.background_gradient(cmap="Greens", subset=[result_column])
    return styler


def _indicator_labels(indicator_key: str) -> dict:
    is_assertiveness = indicator_key in {
        "res_assert_gpon",
        "res_assert_fibra_hfc",
    }
    is_gpon = indicator_key in {
        "res_etit_gpon",
        "res_assert_gpon",
    }

    if is_assertiveness:
        title = "Assertividade GPON" if is_gpon else "Assertividade HFC"
        return {
            "title": title,
            "is_gpon": is_gpon,
            "is_assertiveness": True,
            "success": "Assertivos",
            "loss": "Não Assertivos",
            "rate": "Assertividade",
            "non_rate": "Não Assertividade",
            "rate_lower": "assertividade",
        }

    title = "ETIT GPON" if is_gpon else "ETIT HFC"
    return {
        "title": title,
        "is_gpon": is_gpon,
        "is_assertiveness": False,
        "success": "Aderentes",
        "loss": "Não Aderentes",
        "rate": "Aderência",
        "non_rate": "Não Aderência",
        "rate_lower": "aderência",
    }


def _presentation_table(frame: pd.DataFrame, labels: dict) -> pd.DataFrame:
    if frame is None or frame.empty or not labels.get("is_assertiveness"):
        return frame

    return frame.rename(
        columns={
            "Aderentes": labels["success"],
            "Não Aderentes": labels["loss"],
            "Aderência %": f"{labels['rate']} %",
            "Não Aderência %": f"{labels['non_rate']} %",
        }
    )


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-etit-card {
            background: #ffffff;
            border: 1px solid rgba(15, 23, 42, .06);
            border-left: 4px solid #111827;
            border-radius: 16px;
            box-shadow: 0 8px 22px rgba(15, 23, 42, .07);
            min-height: 92px;
            padding: 18px 20px 16px;
            margin-bottom: 4px;
            text-align: center;
        }
        .cop-etit-card-label {
            color: #7b7f87;
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: 7px;
        }
        .cop-etit-card-value {
            font-size: 1.75rem;
            line-height: 1.05;
            font-weight: 800;
        }
        .cop-etit-bestworst {
            color: #8a8f98;
            font-size: .86rem;
            margin: 2px 0 12px 2px;
        }
        .cop-etit-best { color: #48c78e; }
        .cop-etit-worst { color: #e76f7f; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_cards(numbers: dict, labels: dict) -> None:
    first_row = (
        ("VOLUME", str(numbers["volume"]), "#8e44ad"),
        (labels["success"].upper(), str(numbers["successes"]), "#27ae60"),
        (labels["loss"].upper(), str(numbers["losses"]), "#e74c3c"),
        (labels["rate"].upper(), f"{numbers['adherence']:.1f}%", "#27ae60"),
        (labels["non_rate"].upper(), f"{numbers['non_adherence']:.1f}%", "#e74c3c"),
    )
    columns = st.columns(5)
    for column, (label, value, color) in zip(columns, first_row):
        with column:
            _render_card(label, value, color)

    second_row = st.columns(2)
    with second_row[0]:
        _render_card("TMA MÉDIO", _duration(numbers.get("tma_seconds")), "#2980b9")
    with second_row[1]:
        _render_card("TMR MÉDIO", _duration(numbers.get("tmr_seconds")), "#f39c12")


def _render_card(label: str, value: str, color: str) -> None:
    st.markdown(
        (
            "<div class='cop-etit-card'>"
            f"<div class='cop-etit-card-label'>{label}</div>"
            f"<div class='cop-etit-card-value' style='color:{color}'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _overall_numbers(rows: pd.DataFrame, detail: dict | None) -> dict:
    volume_series = (
        pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
        if rows is not None and "volume" in rows.columns
        else pd.Series(dtype="float64")
    )
    raw_volume = float(volume_series.sum())
    adherence = _weighted_value(rows)

    if detail:
        volume = int(round(_number(detail.get("volume")) or 0))
        successes = int(round(_number(detail.get("successes")) or 0))
        losses_value = _number(detail.get("losses"))
        losses = int(round(losses_value if losses_value is not None else max(volume - successes, 0)))
        if volume > 0:
            adherence = successes / volume * 100
        tma_seconds = _number(detail.get("tma_seconds"))
        tmr_seconds = _number(detail.get("tmr_seconds"))
    else:
        volume = int(round(raw_volume))
        adherence = float(adherence or 0)
        successes = int(round(volume * adherence / 100)) if volume > 0 else 0
        losses = max(volume - successes, 0)
        tma_seconds = None
        tmr_seconds = None

    adherence = float(adherence or 0)
    return {
        "volume": volume,
        "successes": successes,
        "losses": losses,
        "adherence": adherence,
        "non_adherence": max(0.0, 100.0 - adherence) if volume > 0 else 0.0,
        "tma_seconds": tma_seconds,
        "tmr_seconds": tmr_seconds,
    }


def _dimension_rows(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if frame.empty or "dimension" not in frame.columns:
        return frame.iloc[0:0].copy()
    return frame[frame["dimension"] == dimension].copy()


def _service_scoped_details(rows: pd.DataFrame, service: str) -> pd.DataFrame:
    if rows is None or rows.empty or not {"dimension", "dimension_value"}.issubset(rows.columns):
        return rows.iloc[0:0].copy() if rows is not None else pd.DataFrame()

    direct_service = rows[
        (rows["dimension"] == "service")
        & (rows["dimension_value"].astype(str) == service)
    ].copy()

    composite = rows[rows["dimension"].astype(str).str.startswith("service__", na=False)].copy()
    if composite.empty:
        return direct_service

    split_values = composite["dimension_value"].astype(str).str.split(
        "|||", n=1, expand=True, regex=False
    )
    if split_values.shape[1] < 2:
        return direct_service

    composite = composite[split_values[0] == service].copy()
    if composite.empty:
        return direct_service

    selected_values = composite["dimension_value"].astype(str).str.split(
        "|||", n=1, expand=True, regex=False
    )
    composite["dimension_value"] = selected_values[1].values
    composite["dimension"] = composite["dimension"].astype(str).str.replace(
        r"^service__", "", regex=True
    )
    return pd.concat([direct_service, composite], ignore_index=True)


def _overall_detail(breakdown_df: pd.DataFrame, indicator_key: str) -> dict | None:
    required = {"indicator_key", "dimension", "volume", "successes", "losses"}
    if (
        breakdown_df is None
        or breakdown_df.empty
        or not required.issubset(breakdown_df.columns)
    ):
        return None

    rows = breakdown_df[
        (breakdown_df["indicator_key"] == indicator_key)
        & (breakdown_df["dimension"] == "overall")
    ].copy()
    if rows.empty:
        return None

    volume = float(pd.to_numeric(rows["volume"], errors="coerce").fillna(0).sum())
    successes = float(pd.to_numeric(rows["successes"], errors="coerce").fillna(0).sum())
    losses = float(pd.to_numeric(rows["losses"], errors="coerce").fillna(0).sum())

    return {
        "volume": volume,
        "successes": successes,
        "losses": losses,
        "tma_seconds": _weighted_duration(rows, "tma_seconds"),
        "tmr_seconds": _weighted_duration(rows, "tmr_seconds"),
    }


def _weighted_duration(rows: pd.DataFrame, column: str) -> float | None:
    if rows is None or rows.empty or column not in rows.columns or "volume" not in rows.columns:
        return None
    values = pd.to_numeric(rows[column], errors="coerce")
    weights = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (weights > 0)
    if not valid.any():
        return None
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def _weighted_value(rows: pd.DataFrame) -> float | None:
    if rows is None or rows.empty or not {"value", "volume"}.issubset(rows.columns):
        return None
    values = pd.to_numeric(rows["value"], errors="coerce")
    volumes = pd.to_numeric(rows["volume"], errors="coerce").fillna(0)
    valid = values.notna() & (volumes > 0)
    if not valid.any():
        return None
    return round(float((values[valid] * volumes[valid]).sum() / volumes[valid].sum()), 1)


def _duration(seconds) -> str:
    number = _number(seconds)
    if number is None or number < 0:
        return "—"
    total = int(round(number))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


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
