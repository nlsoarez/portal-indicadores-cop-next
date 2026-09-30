from __future__ import annotations

import time

import streamlit as st

from src.application.access_service import AccessService
from src.application.auth_service import AuthService
from src.config.seed import seed_foundation
from src.infrastructure.database import database_is_persistent, initialize_database, persistence_diagnostics
from src.infrastructure.repositories import SegmentRepository
from src.ui.admin.shell import AdminShell
from src.ui.analyst.shell import AnalystShell
from src.ui.shared.chrome import render_login_intro
from src.ui.shared.style import inject_global_style
from src.ui.subadmin.shell import SubadminShell


ACCESS_SNAPSHOT_TTL_SECONDS = 30.0


@st.cache_resource(show_spinner=False)
def _bootstrap() -> None:
    initialize_database()
    seed_foundation()


def _access_snapshot(user_id: int):
    now = time.monotonic()
    cached = st.session_state.get("_access_snapshot")
    if (
        isinstance(cached, dict)
        and cached.get("user_id") == user_id
        and now - float(cached.get("loaded_at", 0)) < ACCESS_SNAPSHOT_TTL_SECONDS
    ):
        return cached["ctx"], cached["segments"]

    access = AccessService()
    ctx = access.context(user_id)
    segments = SegmentRepository().list_for_user(user_id)
    st.session_state["_access_snapshot"] = {
        "user_id": user_id,
        "loaded_at": now,
        "ctx": ctx,
        "segments": segments,
    }
    return ctx, segments


def _login() -> None:
    render_login_intro()
    left, center, right = st.columns([1.1, 1.0, 1.1])
    with center:
        st.markdown("### Acesso ao portal")
        st.caption("Entre com seu login corporativo para acessar seu perfil e segmento.")
        with st.form("login"):
            login = st.text_input("Login", placeholder="Ex.: N1234567")
            password = st.text_input("Senha", type="password", placeholder="Sua senha")
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

    if not database_is_persistent():
        diag = persistence_diagnostics()
        st.error(
            "A troca de senha foi bloqueada porque este deployment ainda não está conectado "
            "ao PostgreSQL persistente."
        )
        st.code(
            "Backend: {backend}\n"
            "DATABASE_URL detectada: {database_url}\n"
            "POSTGRES_URL detectada: {postgres_url}\n"
            "Ambiente Vercel: {vercel_env}\n"
            "Commit: {commit}".format(
                backend=diag["backend"],
                database_url="SIM" if diag["database_url_detected"] else "NÃO",
                postgres_url="SIM" if diag["postgres_url_detected"] else "NÃO",
                vercel_env=diag["vercel_env"] or "não informado",
                commit=diag["commit"] or "não informado",
            )
        )
        return

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
        st.session_state.pop("_access_snapshot", None)
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

    ctx, segments = _access_snapshot(int(user_id))
    if not segments:
        st.error("Seu usuário não possui segmento autorizado.")
        return

    with st.sidebar:
        if st.button("Sair", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    if ctx.is_admin:
        AdminShell().render(ctx, segments)
    elif ctx.is_subadmin:
        SubadminShell().render(ctx, segments)
    else:
        AnalystShell().render(ctx, segments)
