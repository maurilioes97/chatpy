from datetime import datetime

from src.banco import obter_conexao


def listar_conversas_da_lista(lista_id):
    with obter_conexao() as conexao:
        cursor = conexao.execute(
            """
            SELECT
                id,
                lista_pecas_id,
                titulo,
                data_criacao,
                data_atualizacao
            FROM conversas_estoque
            WHERE lista_pecas_id = ?
            ORDER BY data_atualizacao DESC, id DESC
            """,
            (lista_id,),
        )

        linhas = cursor.fetchall()
        conversas = []
        for linha in linhas:
            conversas.append(dict(linha))

        return conversas


def criar_conversa(lista_id, titulo):
    data_atual = datetime.now().isoformat(timespec="seconds")

    with obter_conexao() as conexao:
        cursor = conexao.execute(
            """
            INSERT INTO conversas_estoque (
                lista_pecas_id,
                titulo,
                data_criacao,
                data_atualizacao
            )
            VALUES (?, ?, ?, ?)
            """,
            (lista_id, titulo, data_atual, data_atual),
        )

        return int(cursor.lastrowid)


def criar_conversa_inicial_se_necessario(lista_id):
    conversas = listar_conversas_da_lista(lista_id)

    if conversas:
        return int(conversas[0]["id"])

    return criar_conversa(lista_id, "Consulta inicial")


def excluir_conversa(conversa_id):
    with obter_conexao() as conexao:
        conexao.execute(
            "DELETE FROM conversas_estoque WHERE id = ?",
            (conversa_id,),
        )


def listar_mensagens_da_conversa(conversa_id):
    with obter_conexao() as conexao:
        cursor = conexao.execute(
            """
            SELECT
                id,
                conversa_id,
                papel,
                conteudo,
                data_criacao
            FROM mensagens_estoque
            WHERE conversa_id = ?
            ORDER BY id ASC
            """,
            (conversa_id,),
        )

        linhas = cursor.fetchall()
        mensagens = []
        for linha in linhas:
            mensagens.append(dict(linha))

        return mensagens


def adicionar_mensagem(conversa_id, papel, conteudo):
    data_atual = datetime.now().isoformat(timespec="seconds")

    with obter_conexao() as conexao:
        cursor = conexao.execute(
            """
            INSERT INTO mensagens_estoque (
                conversa_id,
                papel,
                conteudo,
                data_criacao
            )
            VALUES (?, ?, ?, ?)
            """,
            (conversa_id, papel, conteudo, data_atual),
        )

        conexao.execute(
            """
            UPDATE conversas_estoque
            SET data_atualizacao = ?
            WHERE id = ?
            """,
            (data_atual, conversa_id),
        )

        return int(cursor.lastrowid)
