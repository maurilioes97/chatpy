from html import escape
import re

import streamlit as st

from src.navegacao import (
    definir_conversa_atual,
    obter_conversa_atual,
    obter_lista_atual,
    ir_para_tela,
)
from src.servicos.servico_conversas_estoque import (
    adicionar_mensagem,
    criar_conversa,
    criar_conversa_inicial_se_necessario,
    excluir_conversa,
    listar_conversas_da_lista,
    listar_mensagens_da_conversa,
)
from src.servicos.servico_gemini import gerar_resposta_consulta
from src.servicos.servico_listas_pecas import obter_lista_pecas_por_id


def renderizar_tela_consulta_estoque():
    lista_id = obter_lista_atual()
    if lista_id is None:
        st.warning("Selecione uma lista antes de entrar na area de consulta.")
        if st.button("Voltar para listas"):
            ir_para_tela("listas")
            st.rerun()
        return

    lista = obter_lista_pecas_por_id(lista_id)
    if lista is None:
        st.error("A lista selecionada nao foi encontrada.")
        if st.button("Voltar para listas"):
            ir_para_tela("listas")
            st.rerun()
        return

    conversa_id = preparar_conversa_atual(lista_id)
    conversas = listar_conversas_da_lista(lista_id)
    mensagens = listar_mensagens_da_conversa(conversa_id)

    aplicar_estilo_chat()

    st.title("Consulta de almoxarifado")
    st.caption("Pergunte sobre pecas, quantidades, faltas e resumos do arquivo enviado.")

    mostrar_barra_lateral(lista, lista_id, conversas, conversa_id)
    mostrar_resumo_chat(lista, conversas, conversa_id)
    mostrar_mensagens(mensagens)
    processar_pergunta(lista, conversa_id)


def preparar_conversa_atual(lista_id):
    conversa_id = obter_conversa_atual()
    conversas = listar_conversas_da_lista(lista_id)

    if conversa_id is None:
        conversa_id = criar_conversa_inicial_se_necessario(lista_id)
        definir_conversa_atual(conversa_id)
        return conversa_id

    ids_conversas = []
    for conversa in conversas:
        ids_conversas.append(int(conversa["id"]))

    if conversa_id in ids_conversas:
        return conversa_id

    if conversas:
        nova_conversa_atual = int(conversas[0]["id"])
    else:
        nova_conversa_atual = criar_conversa_inicial_se_necessario(lista_id)

    definir_conversa_atual(nova_conversa_atual)
    return nova_conversa_atual


def mostrar_barra_lateral(
    lista,
    lista_id,
    conversas,
    conversa_atual_id,
):
    with st.sidebar:
        st.subheader("Lista atual")
        st.markdown(f"**{lista['nome']}**")
        st.write(lista["descricao"])
        st.caption("Sugestoes: localizar uma peca, contar itens, listar faltas, resumir estoque.")
        st.divider()
        st.subheader("Historico de conversas")

        if st.button("Nova conversa", use_container_width=True):
            total_conversas = len(conversas) + 1
            titulo = f"Consulta {total_conversas}"
            nova_conversa_id = criar_conversa(lista_id, titulo)
            definir_conversa_atual(nova_conversa_id)
            st.rerun()

        for conversa in conversas:
            coluna_conversa, coluna_excluir = st.columns([5, 1])

            with coluna_conversa:
                if st.button(
                    conversa["titulo"],
                    key=f"conversa_{conversa['id']}",
                    use_container_width=True,
                ):
                    definir_conversa_atual(int(conversa["id"]))
                    st.rerun()

            with coluna_excluir:
                if st.button(
                    "X",
                    key=f"excluir_conversa_{conversa['id']}",
                    use_container_width=True,
                ):
                    excluir_conversa(int(conversa["id"]))
                    if conversa_atual_id == int(conversa["id"]):
                        definir_conversa_atual(None)
                    st.rerun()

        if st.button("Voltar para listas", use_container_width=True):
            ir_para_tela("listas")
            st.rerun()

        if st.button("Pagina inicial", use_container_width=True):
            ir_para_tela("inicial")
            st.rerun()


def mostrar_mensagens(mensagens):
    if not mensagens:
        st.markdown(
            """
            <div class="caixa-sem-mensagens">
                Esta conversa ainda nao tem mensagens.<br>
                Experimente perguntar: quais itens estao em falta?
            </div>
            """,
            unsafe_allow_html=True,
        )

    for mensagem in mensagens:
        mostrar_mensagem_chat(mensagem["papel"], mensagem["conteudo"])


def processar_pergunta(lista, conversa_id):
    pergunta = st.chat_input("Digite sua pergunta sobre a lista de pecas...")
    if not pergunta:
        return

    adicionar_mensagem(conversa_id, "user", pergunta)
    mostrar_mensagem_chat("user", pergunta)
    mostrar_digitando_chat()

    mensagens = listar_mensagens_da_conversa(conversa_id)

    try:
        resposta = gerar_resposta_consulta(lista, mensagens)
    except Exception as erro:
        resposta = formatar_erro_gemini(erro)

    adicionar_mensagem(conversa_id, "assistant", resposta)
    st.rerun()


def mostrar_resumo_chat(lista, conversas, conversa_id):
    titulo_conversa = obter_titulo_conversa_atual(conversas, conversa_id)
    nome_lista = escape(lista["nome"])
    descricao_lista = escape(lista["descricao"] or "Sem descricao cadastrada.")
    titulo_conversa = escape(titulo_conversa)

    st.markdown(
        f"""
        <div class="painel-chat">
            <div class="painel-chat-etiqueta">Lista em analise</div>
            <div class="painel-chat-titulo">{nome_lista}</div>
            <div class="painel-chat-descricao">{descricao_lista}</div>
            <div class="painel-chat-meta">
                Conversa atual: {titulo_conversa} | Total de conversas: {len(conversas)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_mensagem_chat(papel, conteudo):
    conteudo = preparar_conteudo_para_exibir(papel, conteudo)

    with st.chat_message(papel, avatar=obter_avatar_mensagem(papel)):
        st.markdown(
            f'<div class="{obter_classe_rotulo_mensagem(papel)}">'
            f"{obter_titulo_mensagem(papel)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(conteudo)


def mostrar_digitando_chat():
    mostrar_mensagem_chat("assistant", "*Digitando...*")


def obter_titulo_conversa_atual(conversas, conversa_id):
    for conversa in conversas:
        if int(conversa["id"]) == int(conversa_id):
            return conversa["titulo"]

    return "Consulta atual"


def obter_avatar_mensagem(papel):
    if papel == "user":
        return ":material/person:"

    return ":material/inventory_2:"


def obter_titulo_mensagem(papel):
    if papel == "user":
        return "Voce"

    return "Assistente de estoque"


def obter_classe_rotulo_mensagem(papel):
    if papel == "user":
        return "rotulo-mensagem rotulo-usuario"

    return "rotulo-mensagem rotulo-assistente"


def aplicar_estilo_chat():
    st.markdown(
        """
        <style>
        .painel-chat {
            background: linear-gradient(135deg, #f8fafc 0%, #eef6ff 100%);
            border: 1px solid #dbe4ef;
            border-radius: 10px;
            padding: 1rem 1.1rem;
            margin: 0.4rem 0 1rem 0;
        }

        .painel-chat-etiqueta {
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            color: #0f766e;
            letter-spacing: 0.04em;
            margin-bottom: 0.25rem;
        }

        .painel-chat-titulo {
            font-size: 1.15rem;
            font-weight: 700;
            color: #1f2937;
            margin-bottom: 0.25rem;
        }

        .painel-chat-descricao,
        .painel-chat-meta {
            color: #4b5563;
            line-height: 1.45;
        }

        .painel-chat-meta {
            margin-top: 0.45rem;
            font-size: 0.92rem;
        }

        .caixa-sem-mensagens {
            background: #fff7ed;
            border: 1px solid #fed7aa;
            border-radius: 10px;
            color: #9a3412;
            padding: 0.9rem 1rem;
            margin-bottom: 1rem;
            line-height: 1.5;
        }

        div[data-testid="stChatMessage"] {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 0.35rem 0.75rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            max-width: 100%;
        }

        div[data-testid="stChatMessage"] [data-testid="stChatMessageContent"],
        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
            max-width: 100%;
            min-width: 0;
            overflow-wrap: break-word;
            word-break: normal;
            white-space: normal;
        }

        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
            overflow-wrap: break-word;
            word-break: normal;
            white-space: normal;
        }

        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] code,
        div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] pre {
            white-space: pre-wrap;
            overflow-wrap: break-word;
            word-break: break-word;
        }

        div[data-testid="stChatMessage"]:has(.rotulo-usuario) {
            background: #e0f2fe;
            border: 1px solid #7dd3fc;
        }

        div[data-testid="stChatMessage"]:has(.rotulo-assistente) {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
        }

        div[data-testid="stChatMessage"] [data-testid="stChatMessageAvatar"] {
            background: #e0f2fe;
            border-radius: 999px;
            padding: 0.2rem;
        }

        div[data-testid="stChatMessage"]:has(.rotulo-usuario) [data-testid="stChatMessageAvatar"] {
            background: #bae6fd;
        }

        div[data-testid="stChatMessage"]:has(.rotulo-assistente) [data-testid="stChatMessageAvatar"] {
            background: #ccfbf1;
        }

        .rotulo-mensagem {
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }

        .rotulo-usuario {
            color: #075985;
        }

        .rotulo-assistente {
            color: #0f766e;
        }

        div[data-testid="stChatInput"] {
            padding-top: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def formatar_erro_gemini(erro):
    texto_erro = str(erro)
    codigo = extrair_codigo_erro(texto_erro)

    if codigo:
        return f"Nao foi possivel falar com o Gemini agora. Detalhe: {codigo}"

    return "Nao foi possivel falar com o Gemini agora."


def preparar_conteudo_para_exibir(papel, conteudo):
    if papel != "assistant":
        return conteudo

    if not conteudo.startswith("Nao foi possivel falar com o Gemini agora."):
        return conteudo

    codigo = extrair_codigo_erro(conteudo)
    if codigo:
        return f"Nao foi possivel falar com o Gemini agora. Detalhe: {codigo}"

    return "Nao foi possivel falar com o Gemini agora."


def extrair_codigo_erro(texto_erro):
    correspondencia = re.search(r"\b(\d{3})\b", texto_erro)
    if correspondencia:
        return correspondencia.group(1)

    return ""
