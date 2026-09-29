from __future__ import annotations

import streamlit as st

from src.application.auth_service import AuthService
from src.application.access_service import AccessService
from src.config.seed import seed_foundation
from src.infrastructure.database import initialize_database
from src.infrastructure.repositories import SegmentRepository
from src.ui.admin.shell import AdminShell
from src.ui.analyst.shell import AnalystShell
from src.ui.shared.style import inject_global_style


def _bootstrap() -> None:
    initialize_database()
    seed_foundation()


def _login() -> None:
    st.markdown("<div class='cop-eyebrow'>COP Rede</div>", unsafe_allow_html=True)
    st.markdown("<div class='cop-title'>Portal de Indicadores</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='cop-subtitle'>Acesso por perfil e segmento.</div>", unsafe_allow_html=True
    )
    with st.form("login"):
        login = st.text_input("Login")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
    if submitted:
        result = AuthService().authenticate(login, password)
        if not result:
            st.error("Credenciais inválidas.")
            return
        st.session_state["user_id"] = result.user_id
        st.session_state["must_change_password"] = result.must_change_password
        st.rerun()


def _change_password(user_id: int) -> None:
    st.warning("Troca de senha obrigatória no primeiro acesso.")
    with st.form("change-password"):
        p1 = st.text_input("Nova senha", type="password")
        p2 = st.text_input("Confirme a nova senha", type="password")
        submitted = st.form_submit_button("Salvar senha")
    if submitted:
        if p1 != p2:
            st.error("As senhas não conferem.")
            return
        try:
            AuthService().change_password(user_id, p1)
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["must_change_password"] = False
        st.success("Senha alterada.")
        st.rerun()


def run() -> None:
    st.set_page_config(page_title="Portal de Indicadores COP", page_icon="📊", layout="wide")
    inject_global_style()
    _bootstrap()

    user_id = st.session_state.get("user_id")
    if not user_id:
        _login()
        return
    if st.session_state.get("must_change_password"):
        _change_password(int(user_id))
        return

    access = AccessService()
    ctx = access.context(int(user_id))
    segments = SegmentRepository().list_for_user(ctx.user.id)
    if not segments:
        st.error("Seu usuário não possui segmento autorizado.")
        return

    with st.sidebar:
        if st.button("Sair", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    if ctx.is_admin:
        AdminShell().render(ctx, segments)
    else:
        AnalystShell().render(ctx, segments)
