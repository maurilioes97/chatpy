from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.equipment_service import EquipmentService


def render_equipment_page():
    """Renderiza o gerenciamento de equipamentos."""
    if "user_id" not in st.session_state:
        st.error("Voce precisa estar logado para acessar os equipamentos.")
        st.switch_page("pages/home_page.py")
        return

    user_id = st.session_state.user_id
    username = st.session_state.get("username", "usuario")

    st.title("Equipamentos")
    st.caption(f"Cadastre as maquinas do manutentor {username} e conecte o chat aos manuais tecnicos.")

    _render_creation_form(user_id)

    st.divider()
    st.subheader("Equipamentos cadastrados")
    _render_equipment_list(user_id)


def _render_creation_form(user_id: int) -> None:
    """Exibe o formulario de cadastro de equipamento."""
    with st.form("equipment_form", clear_on_submit=True):
        st.write("**Novo equipamento**")
        name = st.text_input("Nome da maquina ou equipamento")
        description = st.text_area(
            "Descricao tecnica",
            height=140,
            placeholder="Informe modelo, funcao, setor, caracteristicas e observacoes importantes.",
        )
        uploaded_files = st.file_uploader(
            "Manuais e documentos tecnicos",
            type=["pdf", "doc", "docx"],
            accept_multiple_files=True,
            help="Adicione pelo menos um manual ou documento de apoio do equipamento.",
        )
        submitted = st.form_submit_button("Cadastrar equipamento", type="primary", use_container_width=True)

    if not submitted:
        return

    result = EquipmentService.register_equipment(user_id, name, description, uploaded_files)
    if result["success"]:
        st.session_state.selected_equipment_id = result["equipment_id"]
        _reset_chat_state()
        st.success(result["message"])
        st.rerun()

    st.error(result["message"])


def _render_equipment_list(user_id: int) -> None:
    """Lista os equipamentos do usuario."""
    equipments_result = EquipmentService.get_user_equipments(user_id)
    equipments = equipments_result["equipments"]

    if not equipments:
        st.info("Nenhum equipamento cadastrado ainda. Adicione o primeiro manual acima.")
        return

    for equipment in equipments:
        with st.container(border=True):
            st.markdown(f"### {equipment['name']}")
            st.write(equipment["description"])
            st.caption(f"Documentos vinculados: {equipment['document_count']}")
            st.caption(f"Trechos indexados: {equipment.get('chunk_count', 0)}")

            details_result = EquipmentService.get_equipment(equipment["id"], user_id)
            if details_result["success"] and details_result["equipment"]["documents"]:
                document_names = [doc["file_name"] for doc in details_result["equipment"]["documents"]]
                st.caption("Arquivos: " + ", ".join(document_names))

            open_col, delete_col = st.columns([3, 1])

            if open_col.button(
                "Iniciar conversa tecnica",
                key=f"open_equipment_{equipment['id']}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state.selected_equipment_id = equipment["id"]
                _reset_chat_state()
                st.switch_page("pages/chat_page.py")

            if delete_col.button(
                "Excluir",
                key=f"delete_equipment_{equipment['id']}",
                use_container_width=True,
            ):
                result = EquipmentService.delete_equipment(user_id, equipment["id"])
                if result["success"]:
                    if st.session_state.get("selected_equipment_id") == equipment["id"]:
                        st.session_state.pop("selected_equipment_id", None)
                    _reset_chat_state()
                    st.success("Equipamento excluido com sucesso.")
                    st.rerun()

                st.error(result["message"])


def _reset_chat_state() -> None:
    """Limpa a conversa ativa ao trocar de equipamento."""
    st.session_state.pop("conversation_id", None)
    st.session_state.pop("messages", None)
    st.session_state.pop("current_conversation_title", None)
    st.session_state.pop("document_uploader_key", None)
