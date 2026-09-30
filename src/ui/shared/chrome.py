from __future__ import annotations

from html import escape

import streamlit as st

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
    role_label = ROLE_LABELS.get(role, role.title())
    segment = f"<span>{escape(segment_name)}</span>" if segment_name else ""
    initials = "".join(
        part[:1] for part in str(user_name or "").split()[:2]
    ).upper() or "U"
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
            "<div class='cop-user-mini'>"
            f"<div class='cop-user-avatar'>{escape(initials)}</div>"
            "<div class='cop-user-copy'>"
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
    st.markdown(
        (
            "<section class='cop-hero'>"
            "<div class='cop-hero-art' aria-hidden='true'>"
            "<i class='cop-orbit cop-orbit-a'></i>"
            "<i class='cop-orbit cop-orbit-b'></i>"
            "<i class='cop-node cop-node-a'></i>"
            "<i class='cop-node cop-node-b'></i>"
            "<i class='cop-node cop-node-c'></i>"
            "</div>"
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
    st.markdown(
        (
            "<section class='cop-login-panel'>"
            "<div class='cop-login-brandline'>"
            "<span class='cop-login-logo'>Claro</span>"
            "<span class='cop-login-logo-dot'></span>"
            "<span class='cop-login-product'>Portal de Desempenho</span>"
            "</div>"
            "<div class='cop-login-art' aria-hidden='true'>"
            "<i class='cop-orbit cop-orbit-a'></i>"
            "<i class='cop-orbit cop-orbit-b'></i>"
            "<i class='cop-node cop-node-a'></i>"
            "<i class='cop-node cop-node-b'></i>"
            "<i class='cop-node cop-node-c'></i>"
            "</div>"
            "<div class='cop-login-copy'>"
            "<div class='cop-login-kicker'>COP REDE</div>"
            "<h1>Operação em foco.<br><span>Decisões com contexto.</span></h1>"
            "<p>Indicadores, produtividade e qualidade operacional em um ambiente único, rápido e seguro.</p>"
            "<div class='cop-login-features'>"
            "<span>Indicadores consolidados</span>"
            "<span>Gestão de equipe</span>"
            "<span>Atualização segura</span>"
            "</div>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )
