from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.banco import inicializar_banco
from src.configuracoes import TITULO_APLICACAO
from src.navegacao import ir_para_tela, obter_tela_atual
from src.telas.tela_adicionar_lista import renderizar_tela_adicionar_lista
from src.telas.tela_consulta_estoque import renderizar_tela_consulta_estoque
from src.telas.tela_inicial import renderizar_tela_inicial
from src.telas.tela_listas_pecas import renderizar_tela_listas_pecas


def preparar_pastas():
    for pasta in ("dados", "uploads"):
        Path(pasta).mkdir(parents=True, exist_ok=True)


def configurar_pagina():
    st.set_page_config(
        page_title=TITULO_APLICACAO,
        page_icon="\U0001F4E6",
        layout="wide",
    )


def executar_aplicacao():
    load_dotenv()
    preparar_pastas()
    configurar_pagina()
    inicializar_banco()

    if "tela_atual" not in st.session_state:
        ir_para_tela("inicial")

    tela_atual = obter_tela_atual()

    if tela_atual == "inicial":
        renderizar_tela_inicial()
    elif tela_atual == "listas":
        renderizar_tela_listas_pecas()
    elif tela_atual == "adicionar_lista":
        renderizar_tela_adicionar_lista()
    elif tela_atual == "consulta":
        renderizar_tela_consulta_estoque()
    else:
        st.error("Tela desconhecida.")
