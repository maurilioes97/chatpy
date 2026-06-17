import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from src.banco import obter_conexao
from src.configuracoes import PASTA_UPLOADS
from src.utils.extracao_texto import extrair_texto_de_arquivo


def listar_listas_pecas(busca=""):
    busca = busca.strip()

    if busca:
        sql = """
        SELECT
            id,
            nome,
            descricao,
            caminho_arquivo_lista,
            data_criacao
        FROM listas_pecas
        WHERE nome LIKE ? OR descricao LIKE ?
        ORDER BY id DESC
        """
        valor_busca = f"%{busca}%"
        parametros = (valor_busca, valor_busca)
    else:
        sql = """
        SELECT
            id,
            nome,
            descricao,
            caminho_arquivo_lista,
            data_criacao
        FROM listas_pecas
        ORDER BY id DESC
        """
        parametros = ()

    with obter_conexao() as conexao:
        cursor = conexao.execute(sql, parametros)
        linhas = cursor.fetchall()

    listas = []
    for linha in linhas:
        listas.append(dict(linha))

    return listas


def obter_lista_pecas_por_id(lista_id):
    sql = """
    SELECT
        id,
        nome,
        descricao,
        caminho_arquivo_lista,
        conteudo_lista,
        data_criacao
    FROM listas_pecas
    WHERE id = ?
    """

    with obter_conexao() as conexao:
        cursor = conexao.execute(sql, (lista_id,))
        linha = cursor.fetchone()

    if linha is None:
        return None

    return dict(linha)


def cadastrar_lista_pecas(nome, descricao, arquivo_lista):
    caminho_arquivo = ""

    try:
        caminho_arquivo = salvar_arquivo_enviado(arquivo_lista, "listas_pecas")
        conteudo_lista = extrair_texto_de_arquivo(caminho_arquivo)
        data_criacao = datetime.now().isoformat(timespec="seconds")

        sql = """
        INSERT INTO listas_pecas (
            nome,
            descricao,
            caminho_arquivo_lista,
            conteudo_lista,
            data_criacao
        )
        VALUES (?, ?, ?, ?, ?)
        """

        with obter_conexao() as conexao:
            cursor = conexao.execute(
                sql,
                (
                    nome.strip(),
                    descricao.strip(),
                    caminho_arquivo,
                    conteudo_lista,
                    data_criacao,
                ),
            )
            return int(cursor.lastrowid)
    except Exception:
        if caminho_arquivo:
            apagar_arquivo(caminho_arquivo)
        raise


def excluir_lista_pecas(lista_id):
    lista = obter_lista_pecas_por_id(lista_id)
    if lista is None:
        return

    with obter_conexao() as conexao:
        conexao.execute("DELETE FROM listas_pecas WHERE id = ?", (lista_id,))

    apagar_arquivo(lista["caminho_arquivo_lista"])


def salvar_arquivo_enviado(arquivo, nome_pasta):
    pasta_destino = PASTA_UPLOADS / nome_pasta
    pasta_destino.mkdir(parents=True, exist_ok=True)

    nome_original = arquivo.name
    nome_limpo = limpar_nome_arquivo(nome_original)
    nome_final = f"{uuid4().hex}_{nome_limpo}"

    caminho_arquivo = pasta_destino / nome_final
    caminho_arquivo.write_bytes(arquivo.getvalue())

    return str(caminho_arquivo)


def limpar_nome_arquivo(nome_arquivo):
    nome_arquivo = nome_arquivo.strip().replace(" ", "_")
    nome_arquivo = re.sub(r"[^A-Za-z0-9._-]", "", nome_arquivo)

    if nome_arquivo:
        return nome_arquivo

    return "arquivo"


def apagar_arquivo(caminho_arquivo):
    caminho = Path(caminho_arquivo)
    if caminho.exists():
        caminho.unlink()
