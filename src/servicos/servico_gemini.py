import os
import re
import unicodedata

from google import genai
from google.genai import types

from src.configuracoes import MODELO_GEMINI


PROMPT_SISTEMA = """
Voce e um especialista em almoxarifado e controle de estoque.
Seu objetivo e analisar listas de pecas e responder consultas com precisao.

REGRAS ABSOLUTAS
1. IDIOMA: Responda unica e exclusivamente em Portugues do Brasil.
2. CONTEXTO RESTRITO: Baseie suas respostas somente no arquivo de lista enviado, nos trechos relevantes separados para a pergunta atual e no historico recente da conversa. E proibido inventar quantidades, codigos, faltas ou localizacoes que nao aparecam no material.
3. HONESTIDADE: Se a informacao solicitada nao estiver presente ou clara no material enviado, responda exatamente: Esta informacao nao esta clara no material fornecido.
4. FALTAS E QUANTIDADES: Ao falar de falta de estoque, considere como falta apenas o que estiver explicitamente marcado como ausente, zerado, indisponivel, negativo ou claramente em falta no material. Se isso nao estiver explicito, diga que nao da para afirmar.
5. BUSCA DE PECAS: Quando o usuario procurar uma peca especifica, informe o nome encontrado, o codigo se existir, a quantidade se existir e qualquer observacao relevante presente no arquivo.
6. CONSULTAS PLURAIS: Se a pergunta pedir varios itens, categorias ou listas, como "quais sensores", "liste", "todos", "quais itens", "mostre os", nao pare no primeiro resultado. Liste todos os itens relevantes encontrados nos trechos fornecidos e diga quantos encontrou.

FORMATO DE SAIDA
- Mantenha um tom objetivo, profissional e facil de escanear.
- Quando fizer resumo, prefira listas curtas e claras.
- Quando citar quantidades ou faltas, mostre o trecho-base do arquivo quando isso for possivel.
- Se encontrar mais de um item correspondente, apresente em lista.
""".strip()


def gerar_resposta_consulta(lista, mensagens):
    chave_api = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not chave_api:
        raise ValueError("Defina GEMINI_API_KEY no arquivo .env antes de usar o chat.")

    cliente = genai.Client(api_key=chave_api)

    try:
        prompt = montar_prompt(lista, mensagens)
        resposta = cliente.models.generate_content(
            model=MODELO_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=3500,
                system_instruction=PROMPT_SISTEMA,
            ),
        )

        texto = (resposta.text or "").strip()
        if not texto:
            return "Nao consegui gerar uma resposta desta vez."

        if resposta_foi_cortada(resposta):
            aviso = (
                "[Resposta interrompida por limite de tokens. "
                "Se quiser, peca para eu continuar a listagem.]"
            )
            return f"{texto}\n\n{aviso}"

        return texto
    finally:
        cliente.close()


def montar_prompt(lista, mensagens):
    ultima_pergunta = obter_ultima_pergunta(mensagens)
    historico = formatar_historico(mensagens[-8:])
    conteudo_lista = lista.get("conteudo_lista", "")
    trechos_relevantes = selecionar_trechos_relevantes(conteudo_lista, ultima_pergunta)
    conteudo_completo = limitar_texto(conteudo_lista, 22000)

    return f"""
Nome da lista:
{lista.get("nome", "")}

Descricao da lista:
{lista.get("descricao", "")}

Ultima pergunta do usuario:
{ultima_pergunta}

Trechos possivelmente relevantes para a pergunta atual:
{trechos_relevantes}

Conteudo extraido completo da lista de pecas:
{conteudo_completo}

Historico recente da conversa:
{historico}

Responda a ultima mensagem do usuario de forma objetiva e fiel ao material.
Se a pergunta for plural ou pedir categoria, liste todos os itens relevantes que voce encontrar nos trechos e no conteudo enviado.
""".strip()


def obter_ultima_pergunta(mensagens):
    for mensagem in reversed(mensagens):
        if mensagem["papel"] == "user":
            return mensagem["conteudo"]
    return ""


def selecionar_trechos_relevantes(texto_lista, pergunta):
    linhas = []
    for linha in texto_lista.splitlines():
        linha = linha.strip()
        if linha:
            linhas.append(linha)

    if not linhas:
        return "Nenhum trecho relevante encontrado."

    palavras_importantes = extrair_palavras_importantes(pergunta)
    if not palavras_importantes:
        return limitar_texto("\n".join(linhas[:40]), 6000)

    linhas_encontradas = []

    for linha in linhas:
        linha_normalizada = normalizar_texto(linha)
        pontos = 0

        for palavra in palavras_importantes:
            if palavra in linha_normalizada:
                pontos += 2
            elif palavra.endswith("s") and palavra[:-1] in linha_normalizada:
                pontos += 1
            elif f"{palavra}s" in linha_normalizada:
                pontos += 1

        if pontos > 0:
            linhas_encontradas.append((pontos, linha))

    if not linhas_encontradas:
        return limitar_texto("\n".join(linhas[:40]), 6000)

    linhas_encontradas.sort(key=lambda item: (-item[0], item[1]))

    melhores_linhas = []
    for _, linha in linhas_encontradas[:60]:
        melhores_linhas.append(linha)

    return limitar_texto("\n".join(melhores_linhas), 8000)


def extrair_palavras_importantes(texto):
    palavras_ignoradas = {
        "qual",
        "quais",
        "que",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "tem",
        "temos",
        "ha",
        "no",
        "na",
        "nos",
        "nas",
        "um",
        "uma",
        "uns",
        "umas",
        "me",
        "mostrar",
        "mostre",
        "listar",
        "liste",
        "todos",
        "todas",
        "item",
        "itens",
        "estoque",
        "peca",
        "pecas",
        "sobre",
    }

    texto = normalizar_texto(texto)
    palavras = re.findall(r"[a-z0-9]+", texto)

    palavras_boas = []
    for palavra in palavras:
        if len(palavra) < 3:
            continue
        if palavra in palavras_ignoradas:
            continue
        if palavra not in palavras_boas:
            palavras_boas.append(palavra)

    return palavras_boas


def formatar_historico(mensagens):
    linhas = []

    for mensagem in mensagens:
        if mensagem["papel"] == "user":
            papel = "Usuario"
        else:
            papel = "Assistente"

        linhas.append(f"{papel}: {mensagem['conteudo']}")

    return "\n".join(linhas)


def resposta_foi_cortada(resposta):
    candidatos = getattr(resposta, "candidates", None) or []
    if not candidatos:
        return False

    primeiro_candidato = candidatos[0]
    motivo = getattr(primeiro_candidato, "finish_reason", None)
    if motivo is None:
        return False

    nome = getattr(motivo, "name", str(motivo))
    return nome == "MAX_TOKENS"


def limitar_texto(texto, limite):
    texto = texto.strip()
    if len(texto) <= limite:
        return texto

    return texto[:limite] + "\n[trecho truncado]"


def normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto_sem_acento = []

    for caractere in texto:
        if not unicodedata.combining(caractere):
            texto_sem_acento.append(caractere)

    return "".join(texto_sem_acento).lower().strip()
