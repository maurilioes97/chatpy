import mimetypes
from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.chat_service import ChatService
from services.equipment_service import EquipmentService
from services.llm_service import LLMService, LLMServiceError
from utils.config import DIRECT_STUDY_RESOLVER_ENABLED

DEFAULT_CHAT_PROVIDER = "gemini"


def render_chat():
    """Renderiza a tela de estudos sobre provas."""
    if "user_id" not in st.session_state:
        st.error("Voce precisa estar logado para acessar os estudos.")
        st.switch_page("pages/home_page.py")
        return

    user_id = st.session_state.user_id
    username = st.session_state.get("username", "usuario")

    equipments_result = EquipmentService.get_user_equipments(user_id)
    equipments = equipments_result["equipments"]
    if not equipments:
        st.warning("Nenhuma prova cadastrada ainda.")
        if st.button("Cadastrar prova", type="primary", use_container_width=True):
            st.switch_page("pages/equipment_page.py")
        return

    equipment_map = {equipment["id"]: equipment for equipment in equipments}
    selected_equipment_id = _ensure_selected_equipment(equipment_map)
    selected_equipment = equipment_map[selected_equipment_id]

    _ensure_active_conversation(user_id, selected_equipment_id)

    if "document_uploader_key" not in st.session_state:
        st.session_state.document_uploader_key = 0
    if "selected_llm_provider" not in st.session_state:
        st.session_state.selected_llm_provider = DEFAULT_CHAT_PROVIDER

    _render_sidebar(user_id, username, equipment_map, selected_equipment_id)

    current_title = st.session_state.get("current_conversation_title", ChatService.DEFAULT_TITLE)

    st.subheader(selected_equipment["name"])
    st.caption(f"Estudo atual: {current_title}")
    _inject_document_uploader_styles()

    with st.container(key="chat-document-uploader"):
        uploaded_document = st.file_uploader(
            "Anexe um material complementar para a analise",
            type=["pdf", "doc", "docx"],
            key=f"document_uploader_{st.session_state.document_uploader_key}",
            help="Use esse campo para um arquivo adicional, sem alterar os arquivos fixos da prova.",
            label_visibility="collapsed",
        )
        st.caption("Anexe um material complementar para a analise.")

    if uploaded_document is not None:
        st.info(f"Material pronto para consulta: {uploaded_document.name}")

    for message in st.session_state.get("messages", []):
        with st.chat_message(
            message["role"],
            avatar=_get_message_avatar(message),
        ):
            st.write(message["content"])

    prompt = st.chat_input("Pergunte algo sobre esta prova ou peca um simulado...")
    if not prompt:
        return

    prompt = prompt.strip()
    if not prompt:
        st.warning("Digite uma mensagem antes de enviar.")
        return

    try:
        document_payload = _build_document_payload(uploaded_document)
    except ValueError as exc:
        st.error(str(exc))
        return

    user_message_to_store = f"{prompt}{_get_document_note(document_payload)}"
    llm_prompt = prompt

    direct_query_result = {"handled": False}
    if DIRECT_STUDY_RESOLVER_ENABLED:
        direct_query_result = EquipmentService.resolve_direct_study_query(
            selected_equipment_id,
            user_id,
            prompt,
            conversation_history=st.session_state.get("messages", []),
        )

    # Mostra a pergunta imediatamente antes das etapas mais pesadas.
    with st.chat_message("user", avatar=_get_message_avatar({"role": "user"})):
        st.write(prompt)
        if document_payload:
            st.caption(f"Material anexado: {document_payload['name']}")

    if direct_query_result.get("handled"):
        if not direct_query_result.get("success", False):
            st.error(direct_query_result.get("message", "Nao foi possivel consultar a prova."))
            return

        direct_response = direct_query_result["response"]
        selected_provider = st.session_state.get("selected_llm_provider", DEFAULT_CHAT_PROVIDER).strip().lower()
        with st.chat_message("assistant", avatar=_get_assistant_avatar(selected_provider)):
            st.write(direct_response)

        save_result = ChatService.send_message(
            st.session_state.conversation_id,
            user_id,
            user_message_to_store,
            direct_response,
        )
        if not save_result["success"]:
            st.error(save_result["message"])
            return

        st.session_state.messages.append({"role": "user", "content": user_message_to_store})
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": direct_response,
                "provider": selected_provider,
            }
        )
        if save_result.get("title"):
            st.session_state.current_conversation_title = save_result["title"]
        if document_payload:
            st.session_state.document_uploader_key += 1
        st.rerun()

    equipment_context_result = EquipmentService.get_equipment_context(selected_equipment_id, user_id)
    if not equipment_context_result["success"]:
        st.error(equipment_context_result["message"])
        return

    knowledge_result = EquipmentService.search_equipment_knowledge(
        selected_equipment_id,
        user_id,
        prompt,
    )
    if not knowledge_result["success"]:
        st.error(knowledge_result["message"])
        return

    resolved_context_text = direct_query_result.get("resolved_context_text", "")
    if resolved_context_text:
        equipment_context_result["context_text"] = (
            f"{equipment_context_result['context_text']}\n\n"
            f"Contexto objetivo recuperado para esta pergunta:\n{resolved_context_text}"
        )
    if direct_query_result.get("rewritten_query"):
        llm_prompt = direct_query_result["rewritten_query"]

    selected_provider = st.session_state.get("selected_llm_provider", DEFAULT_CHAT_PROVIDER).strip().lower()

    with st.chat_message("assistant", avatar=_get_assistant_avatar(selected_provider)):
        with st.spinner("Pensando..."):
            try:
                llm_service = LLMService(selected_provider)
                if selected_provider == "ollama":
                    response_placeholder = st.empty()
                    response = ""
                    for chunk in llm_service.stream_response(
                        llm_prompt,
                        st.session_state.messages,
                        document=document_payload,
                        equipment_context=equipment_context_result["context_text"],
                        knowledge_chunks=knowledge_result["chunks"],
                        had_direct_matches=knowledge_result.get("had_direct_matches", False),
                    ):
                        response += chunk
                        response_placeholder.markdown(response)
                else:
                    response = llm_service.get_response(
                        llm_prompt,
                        st.session_state.messages,
                        document=document_payload,
                        equipment_context=equipment_context_result["context_text"],
                        knowledge_chunks=knowledge_result["chunks"],
                        had_direct_matches=knowledge_result.get("had_direct_matches", False),
                    )
                    st.write(response)

                save_result = ChatService.send_message(
                    st.session_state.conversation_id,
                    user_id,
                    user_message_to_store,
                    response,
                )

                if not save_result["success"]:
                    st.error(save_result["message"])
                    return

                st.session_state.messages.append({"role": "user", "content": user_message_to_store})
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "provider": selected_provider,
                    }
                )
                if save_result.get("title"):
                    st.session_state.current_conversation_title = save_result["title"]
                if document_payload:
                    st.session_state.document_uploader_key += 1
                st.rerun()
            except LLMServiceError as exc:
                st.warning(str(exc))
            except Exception as exc:
                st.error(f"Erro: {str(exc)}")


def _inject_history_styles() -> None:
    """Aplica um visual mais compacto e arredondado aos itens do historico."""
    st.markdown(
        """
        <style>
        .stSidebar .st-key-history-list {
            margin-top: 0.35rem;
        }

        .stSidebar .st-key-history-list .st-key-history-item {
            margin-bottom: 0.65rem;
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="stHorizontalBlock"] {
            align-items: center;
            gap: 0.4rem;
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="column"] {
            min-width: 0;
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="stButton"] > button {
            min-height: 2.9rem;
            border-radius: 999px;
            border: 1px solid rgba(15, 23, 42, 0.1);
            padding: 0 0.95rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
            transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="stButton"] > button p {
            width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 0.95rem;
            font-weight: 500;
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="column"]:first-child [data-testid="stButton"] > button {
            justify-content: flex-start;
            background: #f3f4f6;
            color: #111827;
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="column"]:first-child [data-testid="stButton"] > button:hover {
            background: #e5e7eb;
            border-color: rgba(15, 23, 42, 0.18);
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="column"]:first-child [data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(180deg, #eef2ff 0%, #e5edff 100%);
            color: #1e3a8a;
            border-color: rgba(59, 130, 246, 0.2);
            box-shadow: 0 8px 20px rgba(59, 130, 246, 0.12);
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="column"]:last-child button {
            min-height: 2.9rem;
            min-width: 2.9rem;
            border-radius: 1rem;
            padding: 0;
            background: #ffffff;
            color: #374151;
            border: 1px solid rgba(15, 23, 42, 0.12);
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        }

        .stSidebar .st-key-history-list .st-key-history-item [data-testid="column"]:last-child button:hover {
            background: #f9fafb;
            border-color: rgba(15, 23, 42, 0.2);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_document_uploader_styles() -> None:
    """Oculta a legenda padrao do uploader para usar um texto personalizado."""
    st.markdown(
        """
        <style>
        .st-key-chat-document-uploader [data-testid="stFileUploaderDropzoneInstructions"] small {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar(user_id: int, username: str, equipment_map: dict[int, dict], selected_equipment_id: int) -> None:
    """Renderiza a barra lateral da tela de estudos."""
    with st.sidebar:
        st.markdown(f'### Ola "{username}"')
        _render_llm_provider_switch()

        equipment_ids = list(equipment_map.keys())
        selected_option = st.selectbox(
            "Prova ativa",
            options=equipment_ids,
            index=equipment_ids.index(selected_equipment_id),
            format_func=lambda equipment_id: equipment_map[equipment_id]["name"],
        )

        if selected_option != selected_equipment_id:
            st.session_state.selected_equipment_id = selected_option
            _reset_chat_state()
            st.rerun()

        if st.button("Novo estudo", use_container_width=True):
            _start_new_conversation(user_id, selected_equipment_id)
            st.rerun()

        st.divider()
        st.subheader("Historico")
        _inject_history_styles()
        conversations_result = ChatService.get_user_conversations(user_id, selected_equipment_id)
        conversations = conversations_result["conversations"]

        if not conversations:
            st.caption("Nenhum estudo criado ainda para esta prova.")

        with st.container(key="history-list"):
            for conversation in conversations:
                _render_conversation_item(conversation, user_id, selected_equipment_id)

        st.divider()

        if st.button("Sair", use_container_width=True):
            st.session_state.clear()
            st.switch_page("pages/home_page.py")


def _render_llm_provider_switch() -> None:
    """Permite alternar entre IA local e API Gemini pela interface."""
    current_provider = st.session_state.get("selected_llm_provider", DEFAULT_CHAT_PROVIDER).strip().lower()
    use_local_llm = st.toggle(
        "Usar IA local",
        value=current_provider == "ollama",
        help="Ative para usar o Ollama local. Desative para usar a API do Gemini.",
    )

    selected_provider = "ollama" if use_local_llm else "gemini"
    st.session_state.selected_llm_provider = selected_provider


def _get_message_avatar(message: dict) -> str:
    """Resolve o avatar de cada mensagem do chat."""
    role = message.get("role")
    if role == "user":
        return "👤"

    provider = (
        message.get("provider")
        or st.session_state.get("selected_llm_provider")
        or DEFAULT_CHAT_PROVIDER
    ).strip().lower()
    return _get_assistant_avatar(provider)


def _get_assistant_avatar(provider_name: str) -> str:
    """Define um avatar visual para cada provider."""
    if provider_name == "ollama":
        return "🦙"
    return "🤖"


def _render_conversation_item(conversation: dict, user_id: int, equipment_id: int) -> None:
    """Renderiza um item do historico."""
    conversation_id = conversation["id"]
    title = conversation["title"] or ChatService.DEFAULT_TITLE
    is_current = conversation_id == st.session_state.get("conversation_id")

    if is_current and title == ChatService.DEFAULT_TITLE:
        return

    button_title = title[:34].strip()
    if len(title) > 34:
        button_title = f"{button_title}..."
    button_label = f"Atual: {button_title}" if is_current else button_title

    with st.container(key=f"history-item-{conversation_id}"):
        open_col, action_col = st.columns([6, 1])

        if open_col.button(
            button_label,
            key=f"open_{conversation_id}",
            type="primary" if is_current else "secondary",
            use_container_width=True,
        ):
            _load_conversation(conversation_id, user_id)
            st.rerun()

        with action_col.popover(" ", use_container_width=True):
            st.caption("Acoes do estudo")
            st.text_input(
                "Novo titulo",
                key=f"title_input_{conversation_id}",
                value=title,
                placeholder="Digite um titulo",
            )

            if st.button("Salvar titulo", key=f"save_{conversation_id}", use_container_width=True):
                new_title = st.session_state.get(f"title_input_{conversation_id}", "")
                update_result = ChatService.update_conversation_title(conversation_id, user_id, new_title)
                if update_result["success"]:
                    if conversation_id == st.session_state.get("conversation_id"):
                        st.session_state.current_conversation_title = update_result["title"]
                    st.success("Titulo atualizado.")
                    st.rerun()

                st.error(update_result["message"])

            st.divider()

            if st.button("Excluir estudo", key=f"delete_{conversation_id}", use_container_width=True):
                delete_result = ChatService.delete_conversation(conversation_id, user_id)
                if delete_result["success"]:
                    if conversation_id == st.session_state.get("conversation_id"):
                        _reset_chat_state()
                        _load_latest_or_new_conversation(user_id, equipment_id)
                    st.success("Estudo excluido.")
                    st.rerun()

                st.error(delete_result["message"])


def _ensure_selected_equipment(equipment_map: dict[int, dict]) -> int:
    """Garante que sempre exista uma prova selecionada."""
    selected_equipment_id = st.session_state.get("selected_equipment_id")
    if selected_equipment_id not in equipment_map:
        selected_equipment_id = next(iter(equipment_map))
        st.session_state.selected_equipment_id = selected_equipment_id
    return selected_equipment_id


def _ensure_active_conversation(user_id: int, equipment_id: int) -> None:
    """Sincroniza a conversa ativa com a prova selecionada."""
    conversation_id = st.session_state.get("conversation_id")
    if not conversation_id:
        _load_latest_or_new_conversation(user_id, equipment_id)
        return

    conversation_result = ChatService.get_conversation(conversation_id, user_id)
    if not conversation_result["success"]:
        _load_latest_or_new_conversation(user_id, equipment_id)
        return

    conversation = conversation_result["conversation"]
    if conversation.get("equipment_id") != equipment_id:
        _reset_chat_state()
        _load_latest_or_new_conversation(user_id, equipment_id)
        return

    if "messages" not in st.session_state or "current_conversation_title" not in st.session_state:
        _load_conversation(conversation_id, user_id)


def _load_conversation(conversation_id: int, user_id: int) -> None:
    """Carrega uma conversa no estado da sessao."""
    history_result = ChatService.get_conversation_history(conversation_id, user_id)
    if not history_result["success"]:
        st.error(history_result["message"])
        return

    conversation_result = ChatService.get_conversation(conversation_id, user_id)
    if not conversation_result["success"]:
        st.error(conversation_result["message"])
        return

    st.session_state.conversation_id = conversation_id
    st.session_state.messages = history_result["messages"]
    st.session_state.current_conversation_title = conversation_result["conversation"]["title"]


def _start_new_conversation(user_id: int, equipment_id: int) -> None:
    """Cria uma nova conversa para a prova ativa."""
    result = ChatService.start_conversation(user_id, equipment_id)
    st.session_state.conversation_id = result["conversation_id"]
    st.session_state.messages = []
    st.session_state.current_conversation_title = ChatService.DEFAULT_TITLE
    st.session_state.document_uploader_key = st.session_state.get("document_uploader_key", 0) + 1


def _load_latest_or_new_conversation(user_id: int, equipment_id: int) -> None:
    """Carrega a conversa mais recente da prova ou cria uma nova."""
    conversations = ChatService.get_user_conversations(user_id, equipment_id)["conversations"]
    if conversations:
        _load_conversation(conversations[0]["id"], user_id)
        return

    _start_new_conversation(user_id, equipment_id)


def _build_document_payload(uploaded_document):
    """Transforma o arquivo do Streamlit em payload para o Gemini."""
    if uploaded_document is None:
        return None

    mime_type = uploaded_document.type or mimetypes.guess_type(uploaded_document.name)[0] or ""
    if mime_type not in {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        raise ValueError("Formato nao suportado. Envie um arquivo PDF, DOC ou DOCX.")

    return {
        "name": uploaded_document.name,
        "mime_type": mime_type,
        "content": uploaded_document.getvalue(),
    }


def _get_document_note(document_payload: dict | None) -> str:
    """Gera a anotacao de material complementar no texto salvo."""
    if not document_payload:
        return ""
    return f"\n\nMaterial anexado: {document_payload['name']}"


def _reset_chat_state() -> None:
    """Limpa o estado da conversa atual."""
    st.session_state.pop("conversation_id", None)
    st.session_state.pop("messages", None)
    st.session_state.pop("current_conversation_title", None)
    st.session_state.pop("document_uploader_key", None)
