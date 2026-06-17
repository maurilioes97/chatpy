import streamlit as st

from src.navegacao import definir_conversa_atual, definir_lista_atual, ir_para_tela
from src.servicos.servico_listas_pecas import cadastrar_lista_pecas


def renderizar_tela_adicionar_lista():
    st.title("Adicionar lista de pecas")
    st.caption("Cadastre a lista e envie a planilha .xlsx com os itens do almoxarifado.")

    with st.form("formulario_adicionar_lista"):
        nome = st.text_input("Nome da lista")
        descricao = st.text_area("Descricao")
        arquivo = st.file_uploader(
            "Planilha da lista",
            type=["xlsx"],
            accept_multiple_files=False,
        )
        if arquivo is not None:
            st.caption(f"Arquivo selecionado: {arquivo.name}")

        coluna_cadastrar, coluna_cancelar = st.columns(2)
        with coluna_cadastrar:
            cadastrar = st.form_submit_button(
                "Cadastrar lista",
                use_container_width=True,
            )
        with coluna_cancelar:
            cancelar = st.form_submit_button(
                "Cancelar",
                use_container_width=True,
            )

    if cadastrar:
        if not nome.strip():
            st.error("Informe o nome da lista.")
        elif not descricao.strip():
            st.error("Informe uma descricao para a lista.")
        elif arquivo is None:
            st.error("Envie a planilha .xlsx com a lista de pecas.")
        else:
            lista_id = cadastrar_lista_pecas(nome, descricao, arquivo)
            definir_lista_atual(lista_id)
            definir_conversa_atual(None)
            ir_para_tela("consulta")
            st.rerun()

    if cancelar:
        ir_para_tela("listas")
        st.rerun()
