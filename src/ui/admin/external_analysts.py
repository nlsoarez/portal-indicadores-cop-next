"""Admin-only night-shift performance for out-of-team analysts.

The stored external_hour breakdown identifies each imported event by hour or
by a weaker source-reported shift label. The strict 22:00-05:59 view includes
ONLY confirmed hours; data without verified hours are kept separate.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext, Segment

NIGHT_HOURS = frozenset({22, 23, 0, 1, 2, 3, 4, 5})


def _hour_from_label(value: object) -> int | None:
    """Parse stored integral hour buckets only, never assume 'Madrugada'."""
    raw = str(value or "").strip()
    if not raw.isdecimal():
        return None
    hour = int(raw)
    return hour if 0 <= hour <= 23 else None


def _partition_external_records(records: list[dict]) -> dict[str, list[dict]]:
    """Never include missing-hour or daytime rows in strict night totals."""
    results: dict[str, list[dict]] = {
        "confirmed": [],
        "reported_shift": [],
        "unknown_hour": [],
        "outside_window": [],
    }
    for row in records:
        hour = _hour_from_label(row.get("hour_label"))
        if hour is not None:
            category = "confirmed" if hour in NIGHT_HOURS else "outside_window"
        elif str(row.get("hour_label") or "").strip().upper() == "MADRUGADA":
            category = "reported_shift"
        else:
            category = "unknown_hour"
        results[category].append(row)
    return results


def _as_frame(records: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    for col in (
        "volume", "successes", "losses", "tma_sum", "tma_count",
        "tmr_sum", "tmr_count",
    ):
        frame[col] = (
            pd.to_numeric(frame[col], errors="coerce").fillna(0)
            if col in frame.columns else 0
        )
    return frame


def _pct(successes: float, total: float) -> str:
    if total <= 0:
        return "—"
    return f"{successes / total * 100:.1f}%".replace(".", ",")


def _indicator_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    table = frame.groupby(
        ["segment_name", "indicator_key", "name"], as_index=False
    ).agg(
        logins=("login", "nunique"),
        volume=("volume", "sum"),
        successes=("successes", "sum"),
        losses=("losses", "sum"),
    )
    table["Aderência"] = [
        _pct(success, total)
        for success, total in zip(table["successes"], table["volume"])
    ]
    return table.rename(columns={
        "segment_name": "Segmento", "name": "Indicador", "logins": "Logins",
        "volume": "Volume", "successes": "Aderentes / não canceladas",
        "losses": "Não aderentes / canceladas",
    })[
        ["Segmento", "Indicador", "Logins", "Volume",
         "Aderentes / não canceladas", "Não aderentes / canceladas", "Aderência"]
    ].sort_values(["Segmento", "Indicador"])


def _monthly_indicator_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Full-month weighted performance, separately for each indicator/segment.

    Every day's positive and total counts are added BEFORE calculating the
    percentage, preventing an average of daily percentages or double counting.
    """
    if frame.empty:
        return pd.DataFrame()
    table = frame.groupby(
        ["month", "segment_name", "indicator_key", "name"], as_index=False
    ).agg(
        external_logins=("login", "nunique"),
        monthly_volume=("volume", "sum"),
        monthly_success=("successes", "sum"),
        monthly_losses=("losses", "sum"),
    )
    table["Resultado mensal (%)"] = [
        _pct(success, total)
        for success, total in zip(table["monthly_success"], table["monthly_volume"])
    ]
    return table.rename(columns={
        "month": "Competência",
        "segment_name": "Segmento",
        "name": "Indicador",
        "external_logins": "Analistas externos",
        "monthly_volume": "Volume no mês",
        "monthly_success": "Positivos no mês",
        "monthly_losses": "Negativos no mês",
    })[
        ["Competência", "Segmento", "Indicador", "Analistas externos",
         "Volume no mês", "Positivos no mês", "Negativos no mês",
         "Resultado mensal (%)"]
    ].sort_values(["Segmento", "Indicador"]).reset_index(drop=True)


def _monthly_external_people(frame: pd.DataFrame) -> pd.DataFrame:
    """One monthly row per analyst and indicator; daily data only in drilldown."""
    if frame.empty:
        return pd.DataFrame()
    table = frame.groupby(
        ["month", "segment_name", "indicator_key", "name", "login", "analyst_name"],
        as_index=False,
    ).agg(
        monthly_volume=("volume", "sum"),
        monthly_success=("successes", "sum"),
        monthly_losses=("losses", "sum"),
    )
    table["Resultado mensal (%)"] = [
        _pct(success, total)
        for success, total in zip(table["monthly_success"], table["monthly_volume"])
    ]
    return table.rename(columns={
        "month": "Competência",
        "segment_name": "Segmento",
        "name": "Indicador",
        "login": "Login",
        "analyst_name": "Nome",
        "monthly_volume": "Volume no mês",
        "monthly_success": "Positivos no mês",
        "monthly_losses": "Negativos no mês",
    })[
        ["Competência", "Segmento", "Indicador", "Login", "Nome",
         "Volume no mês", "Positivos no mês", "Negativos no mês",
         "Resultado mensal (%)"]
    ].sort_values(
        ["Volume no mês", "Indicador", "Login"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def _people_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    table = frame.groupby(
        ["segment_name", "name", "login", "analyst_name"], as_index=False
    ).agg(
        volume=("volume", "sum"),
        successes=("successes", "sum"),
        losses=("losses", "sum"),
        days=("day", "nunique"),
    )
    table["Aderência"] = [
        _pct(success, total)
        for success, total in zip(table["successes"], table["volume"])
    ]
    return table.rename(columns={
        "segment_name": "Segmento", "name": "Indicador",
        "login": "Login", "analyst_name": "Nome",
        "volume": "Volume", "successes": "Aderentes / não canceladas",
        "losses": "Não aderentes / canceladas", "days": "Dias com dados",
    })[
        ["Segmento", "Indicador", "Login", "Nome", "Dias com dados",
         "Volume", "Aderentes / não canceladas",
         "Não aderentes / canceladas", "Aderência"]
    ].sort_values("Volume", ascending=False)


def _unverified_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """No night claim for records without hour, especially DPA."""
    if frame.empty:
        return pd.DataFrame()
    table = frame.groupby(
        ["segment_name", "name", "indicator_key", "login", "analyst_name"],
        as_index=False,
    ).agg(
        volume=("volume", "sum"),
        successes=("successes", "sum"),
        days=("day", "nunique"),
    )
    table["Resultado da fonte"] = [
        _pct(success, total)
        for success, total in zip(table["successes"], table["volume"])
    ]
    table["Base"] = [
        (
            f"{float(total) / 3600:.1f} h de jornada".replace(".", ",")
            if key == "dpa_official" else f"{int(total):,} ocorrências".replace(",", ".")
        )
        for key, total in zip(table["indicator_key"], table["volume"])
    ]
    return table.rename(columns={
        "segment_name": "Segmento", "name": "Indicador",
        "login": "Login", "analyst_name": "Nome", "days": "Dias com dados",
    })[
        ["Segmento", "Indicador", "Login", "Nome", "Dias com dados",
         "Base", "Resultado da fonte"]
    ].sort_values(["Segmento", "Indicador", "Login"])


def _detail_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    detail = frame.copy()
    detail["Aderência"] = [
        _pct(success, total)
        for success, total in zip(detail["successes"], detail["volume"])
    ]
    detail["Hora"] = detail["hour_label"].map(
        lambda value: f"{int(value):02d}:00–{int(value):02d}:59"
    )
    return detail.rename(columns={
        "segment_name": "Segmento", "name": "Indicador",
        "login": "Login", "analyst_name": "Nome", "day": "Data",
        "volume": "Volume", "successes": "Aderentes / não canceladas",
        "losses": "Não aderentes / canceladas",
    })[
        ["Segmento", "Indicador", "Login", "Nome", "Data", "Hora",
         "Volume", "Aderentes / não canceladas",
         "Não aderentes / canceladas", "Aderência"]
    ].sort_values(["Data", "Hora", "Login"], ascending=[False, True, True])


def render_external_monthly_by_indicator(
    ctx: AccessContext,
    dashboard: DashboardService,
    segment_id: int,
    indicator_labels: dict[str, str],
    *,
    widget_prefix: str,
    title: str,
) -> None:
    """Admin: all indicators visible, with INDEPENDENT month per indicator.

    Important: missing data in the current month is not a zero percent and must
    never be replaced silently with the previous month's performance.
    """
    if not ctx.is_admin:
        raise PermissionError("Analistas externos disponíveis apenas ao administrador")
    st.markdown(f"### {title}")
    st.caption(
        "Resultados de outras equipes, exclusivamente entre 22h00 e 05h59. "
        "Cada indicador possui sua própria seleção de competência. "
        "O desempenho é calculado sobre o VOLUME TOTAL do mês do indicador, "
        "sem misturar dias ou indicadores."
    )
    keys = list(indicator_labels)
    coverage = dashboard.external_night_coverage(ctx, [segment_id], keys)
    if not coverage:
        st.info(
            "Não há eventos externos com hora confirmada nesta fonte. "
            "A ausência de registros não representa 0% de aderência."
        )
        return

    by_key: dict[str, list[dict]] = {
        key: sorted(
            (item for item in coverage if item["indicator_key"] == key),
            key=lambda item: str(item["month"]),
            reverse=True,
        )
        for key in keys
    }
    newest_global_month = max(str(item["month"]) for item in coverage)
    display = []
    for key in keys:
        rows = by_key[key]
        latest = rows[0] if rows else None
        current = next(
            (item for item in rows if str(item["month"]) == newest_global_month),
            None,
        )
        display.append({
            "Indicador": indicator_labels[key],
            "Última competência com externos": (
                str(latest["month"]) if latest else "Sem registros"
            ),
            f"Eventos em {newest_global_month}": (
                int(current["volume"]) if current else 0
            ),
            "Volume da última competência": (
                int(latest["volume"]) if latest else 0
            ),
            "Resultado da última competência": (
                _pct(float(latest["successes"]), float(latest["volume"]))
                if latest else "—"
            ),
        })
    st.markdown("#### Cobertura mensal por indicador")
    st.dataframe(
        pd.DataFrame(display), use_container_width=True, hide_index=True
    )
    stale = [
        indicator_labels[key] for key in keys
        if by_key[key] and str(by_key[key][0]["month"]) != newest_global_month
    ]
    if stale:
        st.warning(
            f"Sem registros externos em {newest_global_month} para: "
            + ", ".join(stale)
            + ". O histórico anterior está disponível na aba de cada indicador "
            "e NÃO será somado à competência atual."
        )

    # All expected indicators appear, even when absent in the latest month.
    # Each tab independently selects its latest available month.
    tabs = st.tabs([indicator_labels[key] for key in keys])
    loaded_months: dict[str, list[dict]] = {}
    for tab, key in zip(tabs, keys):
        with tab:
            rows = by_key[key]
            if not rows:
                st.info(
                    f"{indicator_labels[key]}: não há histórico de analistas externos "
                    "com horários comprovados entre 22h00 e 05h59."
                )
                continue
            months = [str(item["month"]) for item in rows]
            selected = st.selectbox(
                f"Competência — {indicator_labels[key]}",
                months,
                key=f"{widget_prefix}_month_{key}_v4",
            )
            if selected != newest_global_month:
                key_latest = months[0]
                if key_latest != newest_global_month:
                    st.info(
                        f"{indicator_labels[key]} — dados da competência {selected}. "
                        f"Não há dados externos dessa fonte em {newest_global_month}; "
                        "as competências não são mescladas."
                    )
                else:
                    st.caption(
                        f"Consulta histórica de {selected}; a competência "
                        f"mais recente de {indicator_labels[key]} é {key_latest}."
                    )
            if selected not in loaded_months:
                loaded_months[selected] = dashboard.external_night_payload(
                    ctx, [segment_id], selected
                )
            all_records = loaded_months[selected]
            records = _partition_external_records(all_records)["confirmed"]
            data = _as_frame([
                item for item in records
                if item["indicator_key"] == key
            ])
            if data.empty:
                st.warning(
                    "A competência possui registros, mas nenhum horário "
                    "estritamente confirmável para este indicador."
                )
                continue
            volume = int(data["volume"].sum())
            successes = int(data["successes"].sum())
            losses = int(data["losses"].sum())
            is_assertiveness = key.startswith("res_assert_")
            label = "Assertividade mensal" if is_assertiveness else "Aderência mensal"
            cols = st.columns(5)
            cols[0].metric(label, _pct(successes, volume))
            cols[1].metric("Atendimentos no mês", volume)
            cols[2].metric("Positivos", successes)
            cols[3].metric("Negativos", losses)
            cols[4].metric("Analistas externos", data["login"].nunique())

            st.markdown(f"#### Consolidado mensal dos analistas — {selected}")
            month_people = _monthly_external_people(data)
            st.dataframe(
                month_people, use_container_width=True, hide_index=True
            )
            st.download_button(
                "Exportar consolidado mensal (CSV)",
                data=month_people.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"externos_{key}_{selected}_mensal.csv",
                mime="text/csv",
                key=f"{widget_prefix}_export_{key}_v4",
            )
            with st.expander("Detalhamento por dia e hora", expanded=False):
                details = _detail_table(data)
                st.dataframe(
                    details, use_container_width=True, hide_index=True
                )
            out_of_period = sum(
                not str(row.get("day") or "").startswith(selected)
                for row in records if row["indicator_key"] == key
            )
            if out_of_period:
                st.warning(
                    f"{out_of_period} registro(s) têm data do evento fora do "
                    f"mês {selected}, embora a competência da carga seja {selected}. "
                    "Confira os arquivos de origem; não houve reclassificação de datas."
                )


def render_admin_external_analysts(
    ctx: AccessContext,
    segments: list[Segment],
    dashboard: DashboardService,
) -> None:
    if not ctx.is_admin:
        raise PermissionError("Analistas externos disponíveis apenas ao administrador")
    selected_ids = [segment.id for segment in segments]
    months = dashboard.external_night_months(ctx, selected_ids)
    st.markdown("### Analistas externos · janela 22h00–05h59")
    st.caption(
        "Pessoas fora da equipe cadastrada para cada segmento na importação, "
        "mas com atendimento registrado na regional Leste durante a madrugada. "
        "Os volumes externos NÃO entram nos resultados da equipe. "
        "Nas fontes globais (TOA, Chat e DPA), o segmento mostra onde o dado "
        "foi armazenado; não comprova a equipe de origem do analista externo."
    )
    if not months:
        st.info(
            "Ainda não há registros externos preservados nesta seleção. "
            "Confira os arquivos importados em Atualização de dados."
        )
        return
    month = st.selectbox(
        "Competência dos analíticos externos",
        months,
        key="admin_external_night_month_v1",
    )
    records = dashboard.external_night_payload(ctx, selected_ids, month)
    groups = _partition_external_records(records)
    confirmed = _as_frame(groups["confirmed"])
    declared = _as_frame(groups["reported_shift"])
    missing = _as_frame(groups["unknown_hour"])

    if confirmed.empty:
        st.warning(
            "Não há ocorrências com hora confirmada entre 22h00 e 05h59 "
            "para a competência escolhida."
        )
    else:
        total = int(confirmed["volume"].sum())
        columns = st.columns(5)
        columns[0].metric("Logins externos", confirmed["login"].nunique())
        columns[1].metric("Volume de registros", f"{total:,}".replace(",", "."))
        columns[2].metric("Indicadores", confirmed["indicator_key"].nunique())
        columns[3].metric("Dias com atendimentos", confirmed["day"].nunique())
        columns[4].metric("Segmentos", confirmed["segment_slug"].nunique())
        st.caption(
            "Volume de fontes diferentes não deve ser interpretado como "
            "um índice único de produtividade ou aderência. Consulte "
            "a taxa de cada indicador separadamente."
        )

        st.markdown(f"#### Percentual mensal por indicador — {month}")
        st.caption(
            "Somatório de todos os dias da competência entre 22h00 e 05h59. "
            "Percentual mensal = total positivo ÷ volume total do indicador."
        )
        st.dataframe(
            _monthly_indicator_summary(confirmed),
            use_container_width=True,
            hide_index=True,
        )

        choices = (
            confirmed[["segment_slug", "segment_name", "indicator_key", "name"]]
            .drop_duplicates()
            .sort_values(["segment_name", "name"])
            .to_dict("records")
        )
        options = [None, *range(len(choices))]
        option = st.selectbox(
            "Detalhar indicador",
            options,
            format_func=lambda item: (
                "Todos os indicadores"
                if item is None else f"{choices[item]['segment_name']} · {choices[item]['name']}"
            ),
            key="admin_external_night_indicator_v1",
        )
        scoped = confirmed
        if option is not None:
            choice = choices[option]
            scoped = confirmed[
                (confirmed["segment_slug"] == choice["segment_slug"])
                & (confirmed["indicator_key"] == choice["indicator_key"])
            ]

        search = st.text_input(
            "Filtrar por nome ou login", key="admin_external_night_login_search_v1",
        ).strip()
        if search:
            scoped = scoped[
                scoped["login"].astype(str).str.contains(search, case=False, regex=False)
                | scoped["analyst_name"].astype(str).str.contains(search, case=False, regex=False)
            ]

        st.markdown(f"#### Resultado do mês inteiro por analista externo — {month}")
        st.dataframe(
            _monthly_external_people(scoped),
            use_container_width=True,
            hide_index=True,
        )
        with st.expander("Abrir ocorrências por dia e hora", expanded=False):
            detail = _detail_table(scoped)
            st.caption(
                "Data = data da ocorrência registrada no arquivo; "
                "o sistema não reatribui automaticamente eventos de 00h–05h59 "
                "à data anterior do turno."
            )
            st.dataframe(detail, use_container_width=True, hide_index=True)
            st.download_button(
                "Baixar ocorrências externas (CSV)",
                data=detail.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"analistas_externos_madrugada_{month}.csv",
                mime="text/csv",
            )

        inconsistent_dates = sum(
            not str(row.get("day") or "").startswith(month)
            for row in groups["confirmed"]
        )
        if inconsistent_dates:
            st.warning(
                f"{inconsistent_dates} registro(s) têm data diferente do mês "
                "de competência informado na origem. Confira ANOMES e datas "
                "antes de comparar períodos."
            )

    if groups["reported_shift"]:
        with st.expander(
            f"Turno Madrugada informado, sem hora verificável · "
            f"{len(groups['reported_shift'])} registro(s)"
        ):
            st.caption(
                "Os dados vieram marcados como Madrugada na planilha. "
                "Não entram nos totais estritos 22h00–05h59 porque falta "
                "uma hora de evento que permita confirmar o intervalo."
            )
            st.dataframe(
                _people_summary(declared), use_container_width=True, hide_index=True
            )

    if groups["unknown_hour"]:
        with st.expander(
            f"Fontes sem horário para confirmar a madrugada · "
            f"{len(groups['unknown_hour'])} registro(s)"
        ):
            st.warning(
                "Por exemplo, a fonte DPA não informa hora de cada registro. "
                "Esses valores são apresentados apenas para conferência, "
                "sem afirmar que ocorreram entre 22h00 e 05h59."
            )
            st.dataframe(
                _unverified_summary(missing),
                use_container_width=True,
                hide_index=True,
            )

    if groups["outside_window"]:
        st.caption(
            f"{len(groups['outside_window'])} registro(s) externo(s) "
            "apresentaram hora fora de 22h00–05h59 e foram excluídos "
            "dos resultados noturnos."
        )
