from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from src.application.access_service import AccessService
from src.application.dashboard_service import DashboardService
from src.domain.entities import AccessContext, Segment


RESIDENTIAL_RULES = {
    "etit": "res_etit_fibra_hfc",
    "dpa": "dpa_official",
    "assert_hfc": "res_assert_fibra_hfc",
    "assert_gpon": "res_assert_gpon",
}
ENTERPRISE_RULES = {
    "etit": "emp_etit_event",
    "dpa": "dpa_official",
}

ETIT_TARGET = 90.0
DPA_TARGET = 90.0
DPA_ALERT_MIN = 85.0
ASSERT_TARGET = 85.0


@dataclass(frozen=True)
class CertificationSummary:
    total: int
    green: int
    yellow: int
    red: int
    certified: int
    certified_pct: float


def render_certified_analysts(
    ctx: AccessContext,
    segments: list[Segment],
    dashboard: DashboardService,
    access: AccessService,
) -> None:
    """Aba administrativa de certificação, baseada no dashboard legado."""

    eligible_segments = [
        segment
        for segment in segments
        if segment.slug in {"residencial", "empresarial"}
    ]
    if not eligible_segments:
        st.info("Nenhum segmento elegível para certificação.")
        return

    payload = dashboard.management_payload(
        ctx,
        [segment.id for segment in eligible_segments],
    )
    analyst_summary = pd.DataFrame(payload.get("analyst_summary", []))
    roster = build_roster(ctx, eligible_segments, access)
    certification = build_certification_table(roster, analyst_summary)

    _inject_styles()

    st.markdown("### ✅ Analista Certificado")
    st.caption(
        "Status de certificação de cada analista da sua equipe, segundo as regras "
        "Residencial (ETIT Fibra HFC · DPA · Média Assertividade) ou "
        "Empresarial (ETIT por Evento · DPA)."
    )

    if certification.empty:
        st.info("Nenhum analista no escopo desta visão.")
        return

    summary = certification_summary(certification)
    _render_summary_cards(summary)
    _render_segment_cards(certification)

    st.caption(
        "Indicadores sem dados são considerados dentro da meta — veja a coluna "
        "Observação para identificar analistas avaliados com base em dados parciais."
    )

    left, right = st.columns(2)
    with left:
        situation_options = ["Todos"] + sorted(
            certification["Situação"].dropna().astype(str).unique().tolist()
        )
        situation = st.selectbox(
            "Situação",
            situation_options,
            key="certification_situation_filter",
        )
    with right:
        segment_options = ["Todos"] + sorted(
            value
            for value in certification["Segmento"].dropna().astype(str).unique().tolist()
            if value != "—"
        )
        segment = st.selectbox(
            "Segmento",
            segment_options,
            key="certification_segment_filter",
        )

    view = certification.copy()
    if situation != "Todos":
        view = view[view["Situação"] == situation]
    if segment != "Todos":
        view = view[view["Segmento"] == segment]

    view = sort_certification_table(view)
    view.insert(0, "#", range(1, len(view) + 1))

    formatters = {
        "ETIT Fibra HFC %": "{:.1f}",
        "DPA %": "{:.1f}",
        "Assert. Fibra HFC %": "{:.1f}",
        "Assert. GPON %": "{:.1f}",
        "Média Assert. %": "{:.1f}",
        "ETIT por Evento %": "{:.1f}",
    }
    st.dataframe(
        view.style.format(
            {key: value for key, value in formatters.items() if key in view.columns},
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
        height=min(640, 80 + 36 * max(1, len(view))),
    )

    csv_data = view.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Baixar status de certificação (CSV)",
        data=csv_data,
        file_name="analistas_certificacao.csv",
        mime="text/csv",
        key="download_certification_csv",
    )


def build_roster(
    ctx: AccessContext,
    segments: list[Segment],
    access: AccessService,
) -> pd.DataFrame:
    records: list[dict] = []
    for segment in segments:
        if segment.slug not in {"residencial", "empresarial"}:
            continue

        segment_name = (
            "Residencial" if segment.slug == "residencial" else "Empresarial"
        )
        team_name = (
            "Nelson (Res.)" if segment.slug == "residencial" else "Nelson (Emp.)"
        )
        for user in access.visible_users(ctx, segment.id):
            records.append(
                {
                    "login": str(user.login).upper(),
                    "Analista": user.full_name,
                    "Matrícula": user.login,
                    "Segmento": segment_name,
                    "Equipe": team_name,
                }
            )

    if not records:
        return pd.DataFrame(
            columns=["login", "Analista", "Matrícula", "Segmento", "Equipe"]
        )

    return (
        pd.DataFrame(records)
        .drop_duplicates(subset=["login", "Segmento"])
        .sort_values(["Segmento", "Analista"])
        .reset_index(drop=True)
    )


def build_certification_table(
    roster: pd.DataFrame,
    analyst_summary: pd.DataFrame,
) -> pd.DataFrame:
    if roster is None or roster.empty:
        return pd.DataFrame()

    values = indicator_value_map(analyst_summary)
    rows: list[dict] = []

    for _, person in roster.iterrows():
        login = str(person["login"]).upper()
        segment = str(person["Segmento"])

        if segment == "Residencial":
            row = _evaluate_residential(person, values)
        elif segment == "Empresarial":
            row = _evaluate_enterprise(person, values)
        else:
            row = {
                "Status": "⚪",
                "Analista": person["Analista"],
                "Matrícula": person["Matrícula"],
                "Segmento": segment,
                "Equipe": person["Equipe"],
                "ETIT Fibra HFC %": None,
                "DPA %": None,
                "Assert. Fibra HFC %": None,
                "Assert. GPON %": None,
                "Média Assert. %": None,
                "ETIT por Evento %": None,
                "Situação": "Segmento não identificado",
                "Observação": "",
            }
        rows.append(row)

    return pd.DataFrame(rows)


def indicator_value_map(
    analyst_summary: pd.DataFrame,
) -> dict[tuple[str, str, str], float]:
    if analyst_summary is None or analyst_summary.empty:
        return {}

    required = {"login", "segment_slug", "indicator_key", "value"}
    if not required.issubset(analyst_summary.columns):
        return {}

    frame = analyst_summary.copy()
    frame["login"] = frame["login"].astype(str).str.upper()
    frame["segment_slug"] = frame["segment_slug"].astype(str).str.lower()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame[frame["value"].notna()].copy()

    output: dict[tuple[str, str, str], float] = {}
    for _, row in frame.iterrows():
        output[
            (
                str(row["login"]),
                str(row["segment_slug"]),
                str(row["indicator_key"]),
            )
        ] = float(row["value"])
    return output


def _value(
    values: dict[tuple[str, str, str], float],
    login: str,
    segment_slug: str,
    indicator_key: str,
) -> float | None:
    return values.get((login.upper(), segment_slug.lower(), indicator_key))


def _evaluate_residential(
    person: pd.Series,
    values: dict[tuple[str, str, str], float],
) -> dict:
    login = str(person["login"]).upper()
    etit = _value(values, login, "residencial", RESIDENTIAL_RULES["etit"])
    dpa = _value(values, login, "residencial", RESIDENTIAL_RULES["dpa"])
    assert_hfc = _value(
        values,
        login,
        "residencial",
        RESIDENTIAL_RULES["assert_hfc"],
    )
    assert_gpon = _value(
        values,
        login,
        "residencial",
        RESIDENTIAL_RULES["assert_gpon"],
    )
    mean_assert = mean_available(assert_hfc, assert_gpon)

    etit_ok = etit is None or etit >= ETIT_TARGET
    dpa_ok = dpa is None or dpa >= DPA_TARGET
    dpa_alert = dpa is not None and DPA_ALERT_MIN <= dpa < DPA_TARGET
    assert_ok = mean_assert is None or mean_assert >= ASSERT_TARGET

    missing: list[str] = []
    if etit is None:
        missing.append("ETIT Fibra HFC")
    if dpa is None:
        missing.append("DPA")
    if mean_assert is None:
        missing.append("Média Assertividade")

    if etit_ok and dpa_ok and assert_ok:
        situation = "Certificando"
        status = "🟢"
        observation = ""
    elif etit_ok and dpa_alert and assert_ok:
        situation = "Certificando (DPA fora da meta)"
        status = "🟡"
        observation = "DPA individual entre 85% e 90%."
    else:
        situation = "NÃO Certificando"
        status = "🔴"
        reasons: list[str] = []
        if etit is not None and etit < ETIT_TARGET:
            reasons.append(f"ETIT HFC {etit:.1f}%")
        if dpa is not None and dpa < DPA_ALERT_MIN:
            reasons.append(f"DPA {dpa:.1f}%")
        if mean_assert is not None and mean_assert < ASSERT_TARGET:
            reasons.append(f"Média Assert. {mean_assert:.1f}%")
        observation = " · ".join(reasons)

    observation = append_missing_note(observation, missing)

    return {
        "Status": status,
        "Analista": person["Analista"],
        "Matrícula": person["Matrícula"],
        "Segmento": person["Segmento"],
        "Equipe": person["Equipe"],
        "ETIT Fibra HFC %": etit,
        "DPA %": dpa,
        "Assert. Fibra HFC %": assert_hfc,
        "Assert. GPON %": assert_gpon,
        "Média Assert. %": mean_assert,
        "ETIT por Evento %": None,
        "Situação": situation,
        "Observação": observation,
    }


def _evaluate_enterprise(
    person: pd.Series,
    values: dict[tuple[str, str, str], float],
) -> dict:
    login = str(person["login"]).upper()
    etit = _value(values, login, "empresarial", ENTERPRISE_RULES["etit"])
    dpa = _value(values, login, "empresarial", ENTERPRISE_RULES["dpa"])

    etit_ok = etit is None or etit >= ETIT_TARGET
    dpa_ok = dpa is None or dpa >= DPA_TARGET
    dpa_alert = dpa is not None and DPA_ALERT_MIN <= dpa < DPA_TARGET

    missing: list[str] = []
    if etit is None:
        missing.append("ETIT por Evento")
    if dpa is None:
        missing.append("DPA")

    if etit_ok and dpa_ok:
        situation = "Certificando"
        status = "🟢"
        observation = ""
    elif etit_ok and dpa_alert:
        situation = "Certificando (DPA fora da meta)"
        status = "🟡"
        observation = "DPA individual entre 85% e 90%."
    else:
        situation = "NÃO Certificando"
        status = "🔴"
        reasons: list[str] = []
        if etit is not None and etit < ETIT_TARGET:
            reasons.append(f"ETIT Evento {etit:.1f}%")
        if dpa is not None and dpa < DPA_ALERT_MIN:
            reasons.append(f"DPA {dpa:.1f}%")
        observation = " · ".join(reasons)

    observation = append_missing_note(observation, missing)

    return {
        "Status": status,
        "Analista": person["Analista"],
        "Matrícula": person["Matrícula"],
        "Segmento": person["Segmento"],
        "Equipe": person["Equipe"],
        "ETIT Fibra HFC %": None,
        "DPA %": dpa,
        "Assert. Fibra HFC %": None,
        "Assert. GPON %": None,
        "Média Assert. %": None,
        "ETIT por Evento %": etit,
        "Situação": situation,
        "Observação": observation,
    }


def mean_available(first: float | None, second: float | None) -> float | None:
    values = [value for value in (first, second) if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def append_missing_note(observation: str, missing: list[str]) -> str:
    if not missing:
        return observation
    note = f"sem dados de {', '.join(missing)} (considerados dentro da meta)"
    return f"{observation} · {note}" if observation else note


def certification_summary(table: pd.DataFrame) -> CertificationSummary:
    total = len(table)
    green = int((table["Status"] == "🟢").sum())
    yellow = int((table["Status"] == "🟡").sum())
    red = int((table["Status"] == "🔴").sum())
    certified = green + yellow
    certified_pct = certified / total * 100.0 if total else 0.0
    return CertificationSummary(
        total=total,
        green=green,
        yellow=yellow,
        red=red,
        certified=certified,
        certified_pct=certified_pct,
    )


def sort_certification_table(table: pd.DataFrame) -> pd.DataFrame:
    if table is None or table.empty:
        return table.copy() if table is not None else pd.DataFrame()

    order = {
        "NÃO Certificando": 0,
        "Certificando (DPA fora da meta)": 1,
        "Certificando": 2,
        "Segmento não identificado": 3,
    }
    result = table.copy()
    result["_order"] = result["Situação"].map(order).fillna(99)
    return (
        result.sort_values(
            ["_order", "Segmento", "Analista"],
            ascending=[True, True, True],
        )
        .drop(columns=["_order"])
        .reset_index(drop=True)
    )


def _render_summary_cards(summary: CertificationSummary) -> None:
    pct_color = (
        "#18a957"
        if summary.certified_pct >= 90.0
        else "#f0a000"
        if summary.certified_pct >= 70.0
        else "#e74c3c"
    )
    cards = (
        ("TOTAL ANALISTAS", str(summary.total), "#1f5a7a"),
        ("🟢 CERTIFICANDO", str(summary.green), "#18a957"),
        ("🟡 DPA FORA DA META", str(summary.yellow), "#f0a000"),
        ("🔴 NÃO CERTIFICANDO", str(summary.red), "#e74c3c"),
        ("% CERTIFICANDO (GERAL)", f"{summary.certified_pct:.1f}%", pct_color),
    )

    cols = st.columns(5)
    for column, (label, value, color) in zip(cols, cards):
        with column:
            _render_card(label, value, color)


def _render_segment_cards(table: pd.DataFrame) -> None:
    cards: list[tuple[str, float, int, int]] = []
    for segment in ("Residencial", "Empresarial"):
        part = table[table["Segmento"] == segment]
        if part.empty:
            continue
        total = len(part)
        certified = int(part["Status"].isin(["🟢", "🟡"]).sum())
        pct = certified / total * 100.0 if total else 0.0
        cards.append((segment, pct, certified, total))

    if not cards:
        return

    cols = st.columns(len(cards))
    for column, (segment, pct, certified, total) in zip(cols, cards):
        color = (
            "#18a957"
            if pct >= 90.0
            else "#f0a000"
            if pct >= 70.0
            else "#e74c3c"
        )
        with column:
            _render_card(
                f"% CERTIFICANDO — {segment.upper()}",
                f"{pct:.1f}% ({certified}/{total})",
                color,
                wide=True,
            )


def _render_card(label: str, value: str, color: str, *, wide: bool = False) -> None:
    card_class = "cop-cert-card cop-cert-card-wide" if wide else "cop-cert-card"
    st.markdown(
        (
            f"<div class='{card_class}'>"
            f"<div class='cop-cert-card-label'>{label}</div>"
            f"<div class='cop-cert-card-value' style='color:{color}'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .cop-cert-card {
            background: #ffffff;
            border: 1px solid rgba(15,23,42,.06);
            border-left: 4px solid #111827;
            border-radius: 16px;
            box-shadow: 0 8px 20px rgba(15,23,42,.07);
            min-height: 96px;
            padding: 18px 16px 14px;
            text-align: center;
            margin-bottom: 12px;
        }
        .cop-cert-card-wide {
            min-height: 88px;
        }
        .cop-cert-card-label {
            color: #858990;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .cop-cert-card-value {
            font-size: 1.72rem;
            font-weight: 800;
            line-height: 1.1;
            margin-top: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
