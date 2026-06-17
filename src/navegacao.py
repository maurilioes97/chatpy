import streamlit as st


def ir_para_tela(nome_tela):
    st.session_state["tela_atual"] = nome_tela


def obter_tela_atual():
    return st.session_state.get("tela_atual", "inicial")


def definir_lista_atual(lista_id):
    st.session_state["lista_atual_id"] = lista_id


def obter_lista_atual():
    return st.session_state.get("lista_atual_id")


def definir_conversa_atual(conversa_id):
    st.session_state["conversa_atual_id"] = conversa_id


def obter_conversa_atual():
    return st.session_state.get("conversa_atual_id")
