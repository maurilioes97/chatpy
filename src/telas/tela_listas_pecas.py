import re

import streamlit as st

from src.navegacao import definir_conversa_atual, definir_lista_atual, ir_para_tela
from src.servicos.servico_listas_pecas import excluir_lista_pecas, listar_listas_pecas


def renderizar_tela_listas_pecas():
    aplicar_estilo_tabela()

    st.title("Listas de pecas cadastradas")
    st.caption("Cadastre listas de almoxarifado e abra uma area de consulta para cada arquivo.")

    busca = mostrar_barra_superior()

    st.divider()
    st.subheader("Lista de listas")

    listas = listar_listas_pecas(busca)
    if not listas:
        st.warning("Nenhuma lista encontrada. Cadastre a primeira lista para comecar.")
        return

    mostrar_cabecalho()

    for indice, lista in enumerate(listas):
        mostrar_linha(indice, lista)


def mostrar_barra_superior():
    coluna_busca, coluna_adicionar = st.columns([4.6, 1.4], vertical_alignment="bottom")

    with coluna_busca:
        busca = st.text_input(
            "Buscar por nome ou descricao",
            placeholder="Ex.: Estoque eletrica - deposito central",
        )

    with coluna_adicionar:
        st.write("")
        if st.button("Adicionar lista", use_container_width=True, type="primary"):
            ir_para_tela("adicionar_lista")
            st.rerun()

    return busca


def aplicar_estilo_tabela():
    st.markdown(
        """
        <style>
        .cabecalho-coluna {
            font-weight: 700;
            color: #1f2937;
            padding: 0.15rem 0 0.35rem 0;
        }

        .texto-celula {
            color: #374151;
            word-break: break-word;
            padding-top: 0.2rem;
            line-height: 1.35;
        }

        div[class*="st-key-linha_par_"],
        div[class*="st-key-linha_impar_"] {
            border-radius: 8px;
            padding: 0.45rem 0.55rem;
            margin: 0.25rem 0 0.45rem 0;
        }

        div[class*="st-key-linha_par_"] {
            background: #f3f4f6;
        }

        div[class*="st-key-linha_impar_"] {
            background: #ffffff;
        }

        div[class*="st-key-linha_par_"] [data-testid="stHorizontalBlock"],
        div[class*="st-key-linha_impar_"] [data-testid="stHorizontalBlock"] {
            align-items: center;
        }

        div[class*="st-key-linha_par_"] [data-testid="stMarkdownContainer"] p,
        div[class*="st-key-linha_impar_"] [data-testid="stMarkdownContainer"] p {
            margin: 0;
        }

        div[class*="st-key-linha_par_"] button[kind="primary"],
        div[class*="st-key-linha_impar_"] button[kind="primary"] {
            background: #11a8c9;
            border: none;
        }

        div[data-testid="stTextInput"] label {
            font-weight: 600;
            color: #1f2937;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def mostrar_cabecalho():
    coluna_id, coluna_nome, coluna_descricao, coluna_arquivo, coluna_acoes = st.columns(
        [0.6, 2.2, 3.5, 2.0, 2.2]
    )

    with coluna_id:
        st.markdown('<div class="cabecalho-coluna">id</div>', unsafe_allow_html=True)
    with coluna_nome:
        st.markdown('<div class="cabecalho-coluna">Nome da Lista</div>', unsafe_allow_html=True)
    with coluna_descricao:
        st.markdown('<div class="cabecalho-coluna">Descricao</div>', unsafe_allow_html=True)
    with coluna_arquivo:
        st.markdown('<div class="cabecalho-coluna">Arquivo</div>', unsafe_allow_html=True)
    with coluna_acoes:
        st.markdown('<div class="cabecalho-coluna">Acoes</div>', unsafe_allow_html=True)


def mostrar_linha(indice, lista):
    nome_arquivo = obter_nome_arquivo(lista["caminho_arquivo_lista"])
    nome_arquivo = resumir_texto(nome_arquivo, 26)
    descricao = resumir_texto(lista["descricao"], 60)

    if indice % 2 == 0:
        chave_linha = f"linha_par_{lista['id']}"
    else:
        chave_linha = f"linha_impar_{lista['id']}"

    with st.container(key=chave_linha):
        coluna_id, coluna_nome, coluna_descricao, coluna_arquivo, coluna_acoes = st.columns(
            [0.6, 2.2, 3.5, 2.0, 2.2]
        )

        with coluna_id:
            st.markdown(
                f'<div class="texto-celula">{lista["id"]}</div>',
                unsafe_allow_html=True,
            )

        with coluna_nome:
            st.markdown(
                f'<div class="texto-celula">{lista["nome"]}</div>',
                unsafe_allow_html=True,
            )

        with coluna_descricao:
            st.markdown(
                f'<div class="texto-celula">{descricao}</div>',
                unsafe_allow_html=True,
            )

        with coluna_arquivo:
            st.markdown(
                f'<div class="texto-celula">{nome_arquivo}</div>',
                unsafe_allow_html=True,
            )

        with coluna_acoes:
            coluna_abrir, coluna_excluir = st.columns(2)

            with coluna_abrir:
                if st.button(
                    "Abrir",
                    key=f"abrir_{lista['id']}",
                    use_container_width=True,
                    type="primary",
                ):
                    definir_lista_atual(int(lista["id"]))
                    definir_conversa_atual(None)
                    ir_para_tela("consulta")
                    st.rerun()

            with coluna_excluir:
                if st.button(
                    "Excluir",
                    key=f"excluir_{lista['id']}",
                    use_container_width=True,
                ):
                    excluir_lista_pecas(int(lista["id"]))
                    st.success("Lista excluida com sucesso.")
                    st.rerun()


def obter_nome_arquivo(caminho_arquivo):
    partes = caminho_arquivo.replace("\\", "/").split("/")
    nome_arquivo = partes[-1]

    if re.match(r"^[a-f0-9]{32}_.+", nome_arquivo):
        return nome_arquivo.split("_", 1)[1]

    return nome_arquivo


def resumir_texto(texto, limite):
    if len(texto) <= limite:
        return texto

    return texto[: limite - 3] + "..."
