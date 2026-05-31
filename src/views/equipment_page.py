from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.equipment_service import EquipmentService
from services.user_service import UserService


def render_equipment_page():
    """Renderiza o gerenciamento de provas."""
    if "user_id" not in st.session_state:
        st.error("Voce precisa estar logado para acessar as provas.")
        st.switch_page("pages/home_page.py")
        return

    user_id = st.session_state.user_id
    user_role = _get_current_user_role(user_id)
    is_admin = user_role == "admin"

    st.title("Provas")
    if not is_admin:
        st.caption("Consulte provas, gabaritos e materiais disponibilizados pelo administrador do sistema.")

    _ensure_equipment_page_state()

    search_col, action_col = st.columns([4, 1.4])
    search_query = search_col.text_input(
        "Pesquisar provas",
        key="equipment_search_query",
        placeholder="Buscar por nome, banca ou descricao",
        label_visibility="collapsed",
    )
    if is_admin:
        if action_col.button("Adicionar prova", type="primary", use_container_width=True):
            st.session_state.equipment_form_mode = "create"
            st.session_state.editing_equipment_id = None
            st.rerun()
    else:
        action_col.caption("Cadastro restrito ao administrador.")

    _render_equipment_form(user_id, is_admin)

    st.divider()
    st.subheader("Provas cadastradas")
    _render_equipment_list(user_id, search_query, is_admin)


def _ensure_equipment_page_state() -> None:
    """Inicializa o estado local da pagina de provas."""
    if "equipment_form_mode" not in st.session_state:
        st.session_state.equipment_form_mode = None
    if "editing_equipment_id" not in st.session_state:
        st.session_state.editing_equipment_id = None


def _render_equipment_form(user_id: int, is_admin: bool) -> None:
    """Exibe o formulario de cadastro ou edicao quando solicitado."""
    if not is_admin:
        _clear_equipment_form_state()
        return

    form_mode = st.session_state.get("equipment_form_mode")
    editing_equipment_id = st.session_state.get("editing_equipment_id")

    if form_mode not in {"create", "edit"}:
        return

    is_editing = form_mode == "edit"
    equipment = None
    existing_documents = []

    if is_editing:
        details_result = EquipmentService.get_equipment(editing_equipment_id, user_id)
        if not details_result["success"]:
            st.error(details_result["message"])
            _clear_equipment_form_state()
            return
        equipment = details_result["equipment"]
        existing_documents = equipment.get("documents", [])

    with st.container(border=True):
        st.write("**Editar prova**" if is_editing else "**Nova prova**")
        if is_editing and existing_documents:
            exam_documents = [doc["file_name"] for doc in existing_documents if doc.get("document_role") == "exam"]
            answer_key_documents = [doc["file_name"] for doc in existing_documents if doc.get("document_role") == "answer_key"]
            supporting_documents = [
                doc["file_name"] for doc in existing_documents if doc.get("document_role") not in {"exam", "answer_key"}
            ]
            if exam_documents:
                st.caption("Prova atual: " + ", ".join(exam_documents))
            if answer_key_documents:
                st.caption("Gabarito atual: " + ", ".join(answer_key_documents))
            if supporting_documents:
                st.caption("Materiais complementares: " + ", ".join(supporting_documents))
        elif is_editing:
            st.caption("Esta prova ainda nao possui arquivos vinculados.")

        with st.form("equipment_edit_form" if is_editing else "equipment_create_form", clear_on_submit=not is_editing):
            name = st.text_input(
                "Nome da prova",
                value=equipment["name"] if equipment else "",
            )
            description = st.text_area(
                "Descricao e observacoes de estudo",
                value=equipment["description"] if equipment else "",
                height=140,
                placeholder="Informe banca, ano, disciplina, nivel de dificuldade e observacoes importantes.",
            )
            exam_file = st.file_uploader(
                "Arquivo da prova" if not is_editing else "Adicionar nova versao da prova",
                type=["pdf", "doc", "docx"],
                accept_multiple_files=False,
                help=(
                    "Envie o arquivo principal da prova."
                    if not is_editing
                    else "Envie uma nova prova para complementar o cadastro atual."
                ),
            )
            answer_key_file = st.file_uploader(
                "Arquivo do gabarito" if not is_editing else "Adicionar nova versao do gabarito",
                type=["pdf", "doc", "docx"],
                accept_multiple_files=False,
                help=(
                    "Envie o gabarito correspondente a prova."
                    if not is_editing
                    else "Envie um novo gabarito para complementar o cadastro atual."
                ),
            )
            supporting_files = st.file_uploader(
                "Materiais complementares (opcional)",
                type=["pdf", "doc", "docx"],
                accept_multiple_files=True,
                help=(
                    "Adicione materiais extras, como resolucoes comentadas, editais ou resumos."
                    if not is_editing
                    else "Envie novos arquivos para anexar a prova sem remover os arquivos atuais."
                ),
            )

            save_col, cancel_col = st.columns(2)
            submitted = save_col.form_submit_button(
                "Salvar alteracoes" if is_editing else "Cadastrar prova",
                type="primary",
                use_container_width=True,
            )
            cancelled = cancel_col.form_submit_button("Cancelar", use_container_width=True)

        if cancelled:
            _clear_equipment_form_state()
            st.rerun()

        if not submitted:
            return

        should_show_progress = bool(exam_file or answer_key_file or supporting_files)
        progress_placeholder = st.empty() if should_show_progress else None
        status_placeholder = st.empty() if should_show_progress else None
        progress_bar = (
            progress_placeholder.progress(0, text="Preparando processamento dos arquivos...")
            if should_show_progress
            else None
        )

        def progress_callback(progress_value: float, message: str) -> None:
            if progress_bar is None or status_placeholder is None:
                return
            bounded_progress = min(max(progress_value, 0.0), 1.0)
            progress_bar.progress(int(bounded_progress * 100), text=message)
            status_placeholder.caption(message)

        if is_editing:
            result = EquipmentService.update_equipment(
                user_id,
                editing_equipment_id,
                name,
                description,
            )
            if result["success"] and (exam_file or answer_key_file or supporting_files):
                documents_result = EquipmentService.add_equipment_documents(
                    user_id,
                    editing_equipment_id,
                    exam_file=exam_file,
                    answer_key_file=answer_key_file,
                    supporting_files=supporting_files,
                    progress_callback=progress_callback,
                )
                if not documents_result["success"]:
                    if progress_placeholder is not None:
                        progress_placeholder.empty()
                    if status_placeholder is not None:
                        status_placeholder.empty()
                    st.error(documents_result["message"])
                    return
                result["message"] = f"{result['message']} {documents_result['message']}"
        else:
            result = EquipmentService.register_equipment(
                user_id,
                name,
                description,
                exam_file=exam_file,
                answer_key_file=answer_key_file,
                supporting_files=supporting_files,
                progress_callback=progress_callback,
            )

        if result["success"]:
            if progress_bar is not None and status_placeholder is not None:
                progress_bar.progress(100, text="Processamento concluido")
                status_placeholder.caption("Arquivos processados com sucesso.")
            if not is_editing:
                st.session_state.selected_equipment_id = result["equipment_id"]
            _reset_chat_state()
            _clear_equipment_form_state()
            st.success(result["message"])
            st.rerun()

        if progress_placeholder is not None:
            progress_placeholder.empty()
        if status_placeholder is not None:
            status_placeholder.empty()
        st.error(result["message"])


def _inject_equipment_table_styles() -> None:
    """Aplica um visual de tabela para a lista de provas."""
    st.markdown(
        """
        <style>
        .st-key-equipment-table {
            border: 1px solid rgba(15, 23, 42, 0.14);
            border-radius: 1rem;
            overflow: hidden;
            background: #ffffff;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        }

        .st-key-equipment-table .st-key-equipment-header {
            background: #e5e7eb;
            border-bottom: 1px solid rgba(15, 23, 42, 0.16);
            padding: 0.55rem 0.75rem;
        }

        .st-key-equipment-table [class*="st-key-equipment-row-"] {
            padding: 0.35rem 0.75rem;
            border-bottom: 1px solid rgba(15, 23, 42, 0.1);
            background: #ffffff;
        }

        .st-key-equipment-table [class*="st-key-equipment-row-"]:last-child {
            border-bottom: none;
        }

        .st-key-equipment-table [class*="st-key-equipment-row-"]:nth-of-type(odd) {
            background: #f3f4f6;
        }

        .st-key-equipment-table [class*="st-key-equipment-row-"] [data-testid="stHorizontalBlock"] {
            align-items: center;
            gap: 0.75rem;
        }

        .st-key-equipment-table [class*="st-key-equipment-row-"] [data-testid="column"] {
            min-width: 0;
        }

        .st-key-equipment-table .equipment-table-heading {
            font-size: 0.78rem;
            font-weight: 700;
            color: #111827;
            line-height: 1.2;
        }

        .st-key-equipment-table .equipment-cell {
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
            min-width: 0;
        }

        .st-key-equipment-table .equipment-cell__label {
            display: none;
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            color: #6b7280;
            line-height: 1.2;
        }

        .st-key-equipment-table .equipment-cell__value {
            font-size: 0.95rem;
            color: #111827;
            line-height: 1.35;
            word-break: break-word;
        }

        .st-key-equipment-table .equipment-cell__value--muted {
            color: #6b7280;
        }

        .st-key-equipment-table [class*="st-key-equipment-actions-"] [data-testid="stHorizontalBlock"] {
            gap: 0.5rem;
        }

        .st-key-equipment-table [class*="st-key-equipment-actions-"] [data-testid="stButton"] > button {
            min-height: 2.5rem;
        }

        .st-key-equipment-table p,
        .st-key-equipment-table div {
            margin-bottom: 0;
        }

        @media (max-width: 900px) {
            .st-key-equipment-table .st-key-equipment-header {
                display: none;
            }

            .st-key-equipment-table [class*="st-key-equipment-row-"] {
                padding: 0.75rem;
            }

            .st-key-equipment-table [class*="st-key-equipment-row-"] [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
                row-gap: 0.75rem;
            }

            .st-key-equipment-table [class*="st-key-equipment-row-"] [data-testid="column"] {
                flex: 1 1 calc(50% - 0.5rem) !important;
                width: calc(50% - 0.5rem) !important;
            }

            .st-key-equipment-table [class*="st-key-equipment-row-"] [data-testid="column"]:nth-child(1),
            .st-key-equipment-table [class*="st-key-equipment-row-"] [data-testid="column"]:nth-child(2),
            .st-key-equipment-table [class*="st-key-equipment-row-"] [data-testid="column"]:nth-child(6) {
                flex-basis: 100% !important;
                width: 100% !important;
            }

            .st-key-equipment-table .equipment-cell__label {
                display: block;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_equipment_list(user_id: int, search_query: str = "", is_admin: bool = False) -> None:
    """Lista as provas do usuario em formato de tabela."""
    equipments_result = EquipmentService.get_user_equipments(user_id)
    equipments = _filter_equipments(equipments_result["equipments"], search_query)

    if not equipments and search_query.strip():
        st.info("Nenhuma prova encontrada para essa pesquisa.")
        return

    if not equipments:
        st.info("Nenhuma prova cadastrada ainda. Use o botao de adicionar para criar a primeira.")
        return

    _inject_equipment_table_styles()

    with st.container(key="equipment-table"):
        with st.container(key="equipment-header"):
            if is_admin:
                name_col, description_col, exam_col, answer_key_col, chunks_col, actions_col = st.columns([1.7, 2.9, 1.0, 1.0, 0.8, 2.3])
            else:
                name_col, description_col, exam_col, answer_key_col, chunks_col, actions_col = st.columns([1.9, 3.2, 1.0, 1.0, 0.8, 1.8])
            name_col.markdown(_build_table_heading("Nome"), unsafe_allow_html=True)
            description_col.markdown(_build_table_heading("Descricao"), unsafe_allow_html=True)
            exam_col.markdown(_build_table_heading("Prova"), unsafe_allow_html=True)
            answer_key_col.markdown(_build_table_heading("Gabarito"), unsafe_allow_html=True)
            chunks_col.markdown(_build_table_heading("Trechos"), unsafe_allow_html=True)
            actions_col.markdown(_build_table_heading("Acoes"), unsafe_allow_html=True)

        for row_index, equipment in enumerate(equipments):
            with st.container(key=f"equipment-row-{row_index}"):
                if is_admin:
                    name_col, description_col, exam_col, answer_key_col, chunks_col, actions_col = st.columns([1.7, 2.9, 1.0, 1.0, 0.8, 2.3])
                else:
                    name_col, description_col, exam_col, answer_key_col, chunks_col, actions_col = st.columns([1.9, 3.2, 1.0, 1.0, 0.8, 1.8])
                name_col.markdown(_build_table_cell("Nome", equipment["name"]), unsafe_allow_html=True)
                description_col.markdown(
                    _build_table_cell("Descricao", _truncate_text(equipment["description"], 110), muted=True),
                    unsafe_allow_html=True,
                )
                exam_col.markdown(
                    _build_table_cell("Prova", str(equipment.get("exam_document_count", 0))),
                    unsafe_allow_html=True,
                )
                answer_key_col.markdown(
                    _build_table_cell("Gabarito", str(equipment.get("answer_key_document_count", 0))),
                    unsafe_allow_html=True,
                )
                chunks_col.markdown(_build_table_cell("Trechos", str(equipment.get("chunk_count", 0))), unsafe_allow_html=True)

                if is_admin:
                    with actions_col.container(key=f"equipment-actions-{row_index}"):
                        open_col, edit_col, delete_col = st.columns(3)

                    if open_col.button("Abrir estudo", key=f"open_equipment_chat_{equipment['id']}", use_container_width=True):
                        st.session_state.selected_equipment_id = equipment["id"]
                        _reset_chat_state()
                        st.switch_page("pages/chat_page.py")

                    if edit_col.button("Editar", key=f"edit_equipment_{equipment['id']}", use_container_width=True):
                        st.session_state.equipment_form_mode = "edit"
                        st.session_state.editing_equipment_id = equipment["id"]
                        st.rerun()

                    if delete_col.button("Excluir", key=f"delete_equipment_{equipment['id']}", use_container_width=True):
                        result = EquipmentService.delete_equipment(user_id, equipment["id"])
                        if result["success"]:
                            if st.session_state.get("selected_equipment_id") == equipment["id"]:
                                st.session_state.pop("selected_equipment_id", None)
                            if st.session_state.get("editing_equipment_id") == equipment["id"]:
                                _clear_equipment_form_state()
                            _reset_chat_state()
                            st.success("Prova excluida com sucesso.")
                            st.rerun()

                        st.error(result["message"])
                else:
                    if actions_col.button(
                        "Abrir estudo",
                        key=f"open_equipment_chat_{equipment['id']}",
                        use_container_width=True,
                    ):
                        st.session_state.selected_equipment_id = equipment["id"]
                        _reset_chat_state()
                        st.switch_page("pages/chat_page.py")


def _truncate_text(text: str, limit: int) -> str:
    """Reduz textos longos para caber na tabela."""
    normalized_text = (text or "").strip()
    if len(normalized_text) <= limit:
        return normalized_text
    return f"{normalized_text[:limit].rstrip()}..."


def _filter_equipments(equipments: list[dict], search_query: str) -> list[dict]:
    """Filtra provas por nome ou descricao."""
    normalized_query = (search_query or "").strip().lower()
    if not normalized_query:
        return equipments

    filtered_equipments = []
    for equipment in equipments:
        searchable_text = f"{equipment.get('name', '')} {equipment.get('description', '')}".lower()
        if normalized_query in searchable_text:
            filtered_equipments.append(equipment)

    return filtered_equipments


def _build_table_heading(label: str) -> str:
    """Monta o html padronizado do cabecalho da tabela."""
    return f'<div class="equipment-table-heading">{label}</div>'


def _build_table_cell(label: str, value: str, muted: bool = False) -> str:
    """Monta o html padronizado de cada celula da tabela."""
    value_class = "equipment-cell__value equipment-cell__value--muted" if muted else "equipment-cell__value"
    safe_label = label.strip()
    safe_value = (value or "").strip()
    return (
        '<div class="equipment-cell">'
        f'<div class="equipment-cell__label">{safe_label}</div>'
        f'<div class="{value_class}">{safe_value}</div>'
        "</div>"
    )


def _clear_equipment_form_state() -> None:
    """Fecha o formulario de criacao/edicao."""
    st.session_state.equipment_form_mode = None
    st.session_state.editing_equipment_id = None


def _get_current_user_role(user_id: int) -> str:
    """Resolve o papel do usuario atual, inclusive em sessoes antigas."""
    session_role = (st.session_state.get("user_role") or "").strip().lower()
    if session_role:
        return session_role

    profile_result = UserService.get_user_profile(user_id)
    if profile_result["success"]:
        resolved_role = (profile_result["user"].get("role") or "user").strip().lower()
        st.session_state.user_role = resolved_role
        return resolved_role

    return "user"


def _reset_chat_state() -> None:
    """Limpa a conversa ativa ao trocar de prova."""
    st.session_state.pop("conversation_id", None)
    st.session_state.pop("messages", None)
    st.session_state.pop("current_conversation_title", None)
    st.session_state.pop("document_uploader_key", None)
