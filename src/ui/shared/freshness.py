from __future__ import annotations

from datetime import datetime

import streamlit as st


def render_indicator_freshness(
    rows: list[dict],
    *,
    compact: bool = False,
    show_title: bool = True,
    columns: int | None = None,
) -> None:
    """Mostra a cobertura real dos dados, não apenas o horário em que o arquivo foi enviado."""
    if show_title:
        st.markdown("#### Atualização dos indicadores")

    if not rows:
        st.caption("Nenhum indicador configurado para este segmento.")
        return

    if compact:
        parts = []
        for row in rows:
            parts.append(f"**{row['name']}** · {_coverage_label(row.get('data_through'))}")
        st.markdown(" &nbsp;&nbsp; ".join(parts))
        return

    column_count = columns or min(4, max(1, len(rows)))
    column_count = max(1, min(int(column_count), max(1, len(rows))))
    grid = st.columns(column_count)
    for index, row in enumerate(rows):
        with grid[index % len(grid)]:
            data_label = _coverage_label(row.get("data_through"))
            st.markdown(
                f"""
                <div class="cop-freshness-card">
                    <div class="cop-freshness-name">{row['name']}</div>
                    <div class="cop-freshness-date">{data_label}</div>
                    <div class="cop-freshness-meta">{_upload_label(row)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def freshness_table_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "Indicador": row["name"],
            "Dados até": _date_ptbr(row.get("data_through")) or "Sem dados",
            "Fonte": row.get("source_key") or "—",
            "Último upload": _datetime_ptbr(row.get("uploaded_at")) or "—",
        }
        for row in rows
    ]


def _coverage_label(value: str | None) -> str:
    formatted = _date_ptbr(value)
    return f"Dados até {formatted}" if formatted else "Aguardando primeiro upload"


def _upload_label(row: dict) -> str:
    uploaded = _datetime_ptbr(row.get("uploaded_at"))
    source = row.get("source_key")
    if uploaded and source:
        return f"{source} · enviado em {uploaded}"
    if uploaded:
        return f"Enviado em {uploaded}"
    if source:
        return str(source)
    return "Sem arquivo processado"


def _date_ptbr(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def _datetime_ptbr(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)
