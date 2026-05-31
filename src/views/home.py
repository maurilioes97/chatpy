from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.user_service import UserService


def render_home():
    """Renderiza a pagina inicial."""
    st.title("ChatPy - Assistente inteligente para estudos de concursos")

    st.divider()

    if "user_id" in st.session_state:
        _render_logged_home()
    else:
        _render_auth_tabs()


def _render_logged_home():
    """Exibe a home para usuario autenticado."""
    username = st.session_state.get("username", "usuario")
    user_role = _get_current_user_role()

    st.subheader("Sessao ativa")
    st.write(f"Voce esta logado como **{username}**.")
    if user_role == "admin":
        st.info("Voce pode cadastrar provas, gabaritos e materiais de estudo para todos os usuarios do sistema.")
    else:
        st.info("As provas cadastradas pelo administrador estao disponiveis para estudo, consulta e simulados guiados pela IA.")

    proofs_col, study_col, logout_col = st.columns(3)

    if proofs_col.button("Abrir provas", type="primary", use_container_width=True):
        st.switch_page("pages/equipment_page.py")

    if study_col.button("Abrir estudos", use_container_width=True):
        st.switch_page("pages/chat_page.py")

    if logout_col.button("Sair da conta", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    with st.expander("Zona de perigo"):
        st.warning("Excluir a conta remove tambem provas, gabaritos, materiais, conversas e mensagens salvas.")
        confirmation_name = st.text_input(
            "Digite seu nome de usuario para confirmar",
            key="delete_account_username",
        )

        if st.button("Excluir minha conta", use_container_width=True):
            if confirmation_name.strip() != username:
                st.error("Confirmacao invalida. Digite exatamente seu nome de usuario.")
            else:
                result = UserService.delete_account(st.session_state.user_id)
                if result["success"]:
                    st.session_state.clear()
                    st.success("Conta excluida com sucesso.")
                    st.rerun()
                else:
                    st.error(result["message"])


def _render_auth_tabs():
    """Exibe login e registro."""
    login_tab, register_tab = st.tabs(["Login", "Registrar"])

    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            st.write("**Entre com seu nome de usuario e senha**")
            username = st.text_input("Nome de usuario", key="login_username")
            password = st.text_input("Senha", type="password", key="login_password")
            submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if submitted:
            normalized_username = username.strip()
            if not normalized_username:
                st.warning("Digite um nome de usuario.")
            elif not password:
                st.warning("Digite sua senha.")
            else:
                result = UserService.authenticate_user(normalized_username, password)
                if result["success"]:
                    st.session_state.user_id = result["user_id"]
                    st.session_state.username = result["username"]
                    st.session_state.user_role = result["role"]
                    st.success(f"Bem-vindo, {result['username']}!")
                    st.switch_page("pages/equipment_page.py")
                else:
                    st.error(result["message"])

    with register_tab:
        with st.form("register_form", clear_on_submit=False):
            st.write("**Crie sua conta**")
            new_username = st.text_input("Nome de usuario", key="register_username")
            new_email = st.text_input("Email", key="register_email")
            new_password = st.text_input("Senha", type="password", key="register_password")
            confirm_password = st.text_input("Confirmar senha", type="password", key="register_password_confirm")
            submitted = st.form_submit_button("Registrar", type="primary", use_container_width=True)

        if submitted:
            if new_password != confirm_password:
                st.error("As senhas nao coincidem.")
            else:
                result = UserService.register_user(
                    new_username.strip(),
                    new_email.strip(),
                    new_password,
                )
                if result["success"]:
                    st.session_state.user_id = result["user_id"]
                    st.session_state.username = result["username"]
                    st.session_state.user_role = result["role"]
                    st.success(result["message"])
                    st.switch_page("pages/equipment_page.py")
                else:
                    st.error(result["message"])


def _get_current_user_role() -> str:
    """Resolve o papel atual do usuario, mesmo em sessoes antigas."""
    session_role = (st.session_state.get("user_role") or "").strip().lower()
    if session_role:
        return session_role

    profile_result = UserService.get_user_profile(st.session_state.user_id)
    if profile_result["success"]:
        resolved_role = (profile_result["user"].get("role") or "user").strip().lower()
        st.session_state.user_role = resolved_role
        return resolved_role

    return "user"
