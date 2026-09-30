from __future__ import annotations

from html import escape

import streamlit as st

from src.ui.shared.visual_assets import webp_data_uri


ROLE_LABELS = {
    "admin": "Administrador",
    "subadmin": "Liderança",
    "analyst": "Analista",
}


def render_sidebar_brand(
    *,
    role: str,
    user_name: str,
    segment_name: str | None = None,
) -> None:
    globe = webp_data_uri("globe")
    role_label = ROLE_LABELS.get(role, role.title())
    segment = f"<span>{escape(segment_name)}</span>" if segment_name else ""
    st.sidebar.markdown(
        (
            "<div class='cop-brand-shell'>"
            "<div class='cop-brand-mark'>"
            "<span class='cop-brand-word'>Claro</span>"
            "<span class='cop-brand-pulse'></span>"
            "</div>"
            "<div class='cop-brand-product'>Portal de Desempenho</div>"
            "<div class='cop-brand-context'>COP REDE</div>"
            "</div>"
            f"<div class='cop-user-mini' style='--cop-mini-art:url(\"{globe}\")'>"
            "<div>"
            f"<strong>{escape(user_name)}</strong>"
            f"<span>{escape(role_label)}</span>"
            f"{segment}"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_page_header(
    *,
    title: str,
    subtitle: str,
    eyebrow: str | None = None,
    badge: str | None = None,
) -> None:
    eyebrow_html = (
        f"<div class='cop-page-eyebrow'>{escape(eyebrow)}</div>"
        if eyebrow
        else ""
    )
    badge_html = (
        f"<span class='cop-page-badge'>{escape(badge)}</span>"
        if badge
        else ""
    )
    st.markdown(
        (
            "<div class='cop-page-head'>"
            "<div>"
            f"{eyebrow_html}"
            "<div class='cop-page-title-row'>"
            f"<h1>{escape(title)}</h1>{badge_html}"
            "</div>"
            f"<p>{escape(subtitle)}</p>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_dashboard_hero(
    *,
    title: str,
    subtitle: str,
    kicker: str = "Dados · Pessoas · Conexão",
) -> None:
    art = webp_data_uri("hero")
    st.markdown(
        (
            f"<section class='cop-hero' style='--cop-hero-art:url(\"{art}\")'>"
            "<div class='cop-hero-copy'>"
            f"<span>{escape(kicker)}</span>"
            f"<h2>{escape(title)}</h2>"
            f"<p>{escape(subtitle)}</p>"
            "</div>"
            "<div class='cop-hero-signal'>"
            "<i></i><i></i><i></i>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_login_intro() -> None:
    art = webp_data_uri("hero")
    st.markdown(
        (
            f"<section class='cop-login-hero' style='--cop-hero-art:url(\"{art}\")'>"
            "<div class='cop-login-copy'>"
            "<span>COP REDE · Operação conectada</span>"
            "<h1>Performance que gera resultado.</h1>"
            "<p>Indicadores, qualidade operacional e gestão de equipe em um único ambiente.</p>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )
