import streamlit as st

from src.navegacao import ir_para_tela


def renderizar_tela_inicial():
    st.title("Bem-vindo ao AlmoxarifadoIA")
    st.caption("Um sistema simples para consultar listas de pecas de almoxarifado com ajuda da API do Gemini.")

    coluna_texto, coluna_acoes = st.columns([3, 2])

    with coluna_texto:
        st.subheader("Sobre o sistema")
        st.write(
            "Esta aplicacao permite cadastrar uma planilha .xlsx com itens de estoque "
            "e depois fazer perguntas em linguagem natural sobre a lista."
        )
        st.write(
            "Voce pode procurar pecas especificas, pedir quantidades, listar itens em falta "
            "e solicitar resumos do conteudo enviado."
        )

        st.subheader("Integrantes")
        st.write("Danilo Pimentel de Andrade")
        st.write("Luan Santos de Souza")
        st.write("Pedro Henrique Silva Rodrigues")
        st.write("Maurilio Eufrasio dos Santos")
        st.write("Vitor Barbosa de Souza")

    with coluna_acoes:
        st.subheader("Comecar")
        st.write("Clique no botao abaixo para acessar as listas cadastradas.")
        if st.button("Entrar no sistema", use_container_width=True):
            ir_para_tela("listas")
            st.rerun()

        st.link_button(
            "Baixar planilha teste",
            "https://drive.google.com/drive/folders/12RFYmjlwjqQQuncvEgQYXie7_o_XCsUK?usp=drive_link",
            use_container_width=True,
        )

        st.info(
            "Formato aceito atualmente: planilha .xlsx"
        )
