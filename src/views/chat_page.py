import mimetypes
import streamlit as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.chat_service import ChatService
from services.gemini_service import GeminiService, GeminiServiceError
from utils.config import APP_NAME


def _load_conversation(conversation_id: int, user_id: int):
    """Carrega uma conversa para o estado da sessao."""
    history_result = ChatService.get_conversation_history(conversation_id, user_id)
    if not history_result["success"]:
        st.error(f"❌ {history_result['message']}")
        return

    conversation_result = ChatService.get_conversation(conversation_id, user_id)
    if not conversation_result["success"]:
        st.error(f"❌ {conversation_result['message']}")
        return

    st.session_state.conversation_id = conversation_id
    st.session_state.messages = history_result["messages"]
    st.session_state.current_conversation_title = conversation_result["conversation"]["title"]


def _start_new_conversation(user_id: int):
    """Cria e seleciona uma nova conversa."""
    result = ChatService.start_conversation(user_id)
    st.session_state.conversation_id = result["conversation_id"]
    st.session_state.messages = []
    st.session_state.current_conversation_title = ChatService.DEFAULT_TITLE


def _select_fallback_conversation(user_id: int):
    """Seleciona uma conversa existente ou cria uma nova."""
    conversations = ChatService.get_user_conversations(user_id)["conversations"]
    if conversations:
        _load_conversation(conversations[0]["id"], user_id)
    else:
        _start_new_conversation(user_id)


def _build_document_payload(uploaded_document):
    """Transforma o arquivo do Streamlit em payload para o Gemini."""
    if uploaded_document is None:
        return None

    mime_type = uploaded_document.type or mimetypes.guess_type(uploaded_document.name)[0] or ""
    if mime_type not in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        raise ValueError("Formato nao suportado. Envie um arquivo PDF ou DOCX.")

    return {
        "name": uploaded_document.name,
        "mime_type": mime_type,
        "content": uploaded_document.getvalue(),
    }


def _get_document_note(document_payload: dict | None) -> str:
    """Retorna a anotacao de documento para exibir e salvar no chat."""
    if not document_payload:
        return ""
    return f"\n\nDocumento anexado: {document_payload['name']}"


def render_chat():
    """Renderiza a pagina de chat."""
    if "user_id" not in st.session_state:
        st.error("❌ Você precisa estar logado!")
        st.switch_page("pages/home_page.py")
        return

    user_id = st.session_state.user_id
    username = st.session_state.username

    if "conversation_id" not in st.session_state:
        _start_new_conversation(user_id)

    if "messages" not in st.session_state:
        _load_conversation(st.session_state.conversation_id, user_id)

    if "current_conversation_title" not in st.session_state:
        conversation_result = ChatService.get_conversation(st.session_state.conversation_id, user_id)
        if conversation_result["success"]:
            st.session_state.current_conversation_title = conversation_result["conversation"]["title"]
        else:
            _select_fallback_conversation(user_id)

    if "document_uploader_key" not in st.session_state:
        st.session_state.document_uploader_key = 0

    with st.sidebar:
        st.markdown(f"### Olá, {username}")
        st.caption("Bem-vindo!")

        if st.button("➕ Nova Conversa", use_container_width=True):
            _start_new_conversation(user_id)
            st.rerun()

        st.divider()
        st.subheader("📚 Histórico")
        conversations = ChatService.get_user_conversations(user_id)

        if not conversations["conversations"]:
            st.caption("Nenhuma conversa criada ainda.")

        for conv in conversations["conversations"]:
            conv_id = conv["id"]
            title = conv["title"] or ChatService.DEFAULT_TITLE
            is_current = conv_id == st.session_state.get("conversation_id")
            if is_current and title == ChatService.DEFAULT_TITLE:
                continue
            select_label = f"{'👉' if is_current else '📄'} {title[:28]}{'...' if len(title) > 28 else ''}"

            open_col, action_col = st.columns([6, 1])

            if open_col.button(select_label, key=f"open_{conv_id}", use_container_width=True):
                _load_conversation(conv_id, user_id)
                st.rerun()

            with action_col.popover("⋯", use_container_width=True):
                st.caption("Ações da conversa")
                new_title = st.text_input(
                    "Novo título",
                    key=f"title_input_{conv_id}",
                    placeholder="Digite um título",
                )

                if st.button("Salvar título", key=f"save_{conv_id}", use_container_width=True):
                    new_title = st.session_state.get(f"title_input_{conv_id}", "")
                    update_result = ChatService.update_conversation_title(conv_id, user_id, new_title)
                    if update_result["success"]:
                        if conv_id == st.session_state.get("conversation_id"):
                            st.session_state.current_conversation_title = update_result["title"]
                        st.success("Título atualizado.")
                        st.rerun()
                    else:
                        st.error(f"❌ {update_result['message']}")

                st.divider()

                if st.button("Excluir conversa", key=f"delete_{conv_id}", use_container_width=True):
                    delete_result = ChatService.delete_conversation(conv_id, user_id)
                    if delete_result["success"]:
                        if conv_id == st.session_state.get("conversation_id"):
                            st.session_state.pop("conversation_id", None)
                            st.session_state.pop("messages", None)
                            st.session_state.pop("current_conversation_title", None)
                            _select_fallback_conversation(user_id)

                        st.success("Conversa excluída.")
                        st.rerun()
                    else:
                        st.error(f"❌ {delete_result['message']}")

        st.divider()

        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.clear()
            st.switch_page("pages/home_page.py")

    current_title = st.session_state.get("current_conversation_title", ChatService.DEFAULT_TITLE)
    st.title(APP_NAME)
    st.caption(f"Conversa atual: {current_title}")

    uploaded_document = st.file_uploader(
        "Anexe um documento para a IA responder com base nele",
        type=["pdf", "docx"],
        key=f"document_uploader_{st.session_state.document_uploader_key}",
        help="PDF preserva melhor a estrutura. DOCX sera lido como texto.",
    )

    if uploaded_document is not None:
        st.info(f"Documento pronto para consulta: {uploaded_document.name}")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Digite sua mensagem..."):
        prompt = prompt.strip()
        if not prompt:
            st.warning("⚠️ Digite uma mensagem antes de enviar.")
            return

        try:
            document_payload = _build_document_payload(uploaded_document)
        except ValueError as e:
            st.error(f"❌ {str(e)}")
            return

        user_message_to_store = f"{prompt}{_get_document_note(document_payload)}"

        with st.chat_message("user"):
            st.write(prompt)
            if document_payload:
                st.caption(f"Documento anexado: {document_payload['name']}")

        with st.chat_message("assistant"):
            with st.spinner("🤔 Pensando..."):
                try:
                    gemini = GeminiService()
                    response = gemini.get_response(
                        prompt,
                        st.session_state.messages,
                        document=document_payload,
                    )
                    st.write(response)

                    save_result = ChatService.send_message(
                        st.session_state.conversation_id,
                        user_id,
                        user_message_to_store,
                        response,
                    )

                    if save_result["success"]:
                        st.session_state.messages.append({"role": "user", "content": user_message_to_store})
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        if save_result.get("title"):
                            st.session_state.current_conversation_title = save_result["title"]
                        if document_payload:
                            st.session_state.document_uploader_key += 1
                        st.rerun()
                    else:
                        st.error(f"❌ {save_result['message']}")
                except GeminiServiceError as e:
                    st.warning(f"⚠️ {str(e)}")
                except Exception as e:
                    st.error(f"❌ Erro: {str(e)}")
