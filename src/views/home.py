import streamlit as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.user_service import UserService
from utils.config import APP_DESCRIPTION, APP_NAME


def render_home():
    """Renderiza a pagina inicial."""
    col1, col2 = st.columns([2, 1])

    with col1:
        st.title(f"🤖 {APP_NAME}")
        st.markdown(f"### {APP_DESCRIPTION}")

    with col2:
        st.image("https://img.icons8.com/color/96/000000/gemini.png", width=100)

    st.divider()

    st.subheader("🚀 Começar")
    tab1, tab2 = st.tabs(["Login", "Registrar"])

    with tab1:
        st.write("**Entre com seu nome de usuário**")
        username = st.text_input("Nome de usuário", key="login_username")

        if st.button("Entrar", type="primary", use_container_width=True):
            normalized_username = username.strip()
            if normalized_username:
                result = UserService.authenticate_user(normalized_username)
                if result["success"]:
                    st.session_state.user_id = result["user_id"]
                    st.session_state.username = result["username"]
                    st.success(f"✅ Bem-vindo, {result['username']}!")
                    st.switch_page("pages/chat_page.py")
                else:
                    st.error("❌ Usuário não encontrado")
            else:
                st.warning("⚠️ Digite um nome de usuário")

    with tab2:
        st.write("**Crie sua conta**")
        new_username = st.text_input("Nome de usuário", key="register_username")
        new_email = st.text_input("Email", key="register_email")

        if st.button("Registrar", type="primary", use_container_width=True):
            result = UserService.register_user(new_username.strip(), new_email.strip())
            if result["success"]:
                st.success(f"✅ {result['message']}")
                st.info("Agora você pode fazer login!")
            else:
                st.error(f"❌ {result['message']}")

    st.divider()

    st.markdown(
        """
    ### 📋 Sobre o ChatBot

    Este é um chatbot inteligente alimentado por **Google Gemini AI**.

    **Recursos:**
    - 💬 Conversas ilimitadas
    - 📚 Histórico de mensagens
    - 🚀 Respostas rápidas com IA
    - 💾 Dados salvos no SQLite
    """
    )
