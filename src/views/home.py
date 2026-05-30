from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.user_service import UserService
from utils.config import APP_DESCRIPTION, APP_NAME


def render_home():
    """Renderiza a pagina inicial."""
    st.title(APP_NAME)
    st.markdown(f"### {APP_DESCRIPTION}")
    st.caption("Um assistente tecnico para manutentores consultarem manuais e caracteristicas de equipamentos.")

    st.divider()

    if "user_id" in st.session_state:
        _render_logged_home()
    else:
        _render_auth_tabs()

    st.divider()
    st.markdown(
        """
### Sobre o ChatPy

O fluxo do sistema foi pensado para manutencao tecnica:

- o manutentor cria a conta e entra no sistema
- cadastra cada maquina ou equipamento com descricao tecnica
- envia manuais e documentos em PDF, DOC ou DOCX
- inicia conversas separadas por equipamento
- recebe respostas baseadas no contexto tecnico cadastrado
"""
    )


def _render_logged_home():
    """Exibe a home para usuario autenticado."""
    username = st.session_state.get("username", "usuario")

    st.subheader("Sessao ativa")
    st.write(f"Voce esta logado como **{username}**.")
    st.info("O proximo passo e cadastrar ou escolher um equipamento para iniciar o atendimento tecnico.")

    equipment_col, chat_col, logout_col = st.columns(3)

    if equipment_col.button("Abrir equipamentos", type="primary", use_container_width=True):
        st.switch_page("pages/equipment_page.py")

    if chat_col.button("Abrir conversas", use_container_width=True):
        st.switch_page("pages/chat_page.py")

    if logout_col.button("Sair da conta", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    with st.expander("Zona de perigo"):
        st.warning("Excluir a conta remove tambem equipamentos, documentos, conversas e mensagens salvas.")
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
    st.subheader("Comecar")
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
                    st.success(result["message"])
                    st.switch_page("pages/equipment_page.py")
                else:
                    st.error(result["message"])
