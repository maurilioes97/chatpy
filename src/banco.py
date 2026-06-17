import sqlite3

from src.configuracoes import CAMINHO_BANCO


def obter_conexao():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def inicializar_banco():
    script = """
    CREATE TABLE IF NOT EXISTS listas_pecas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT NOT NULL,
        caminho_arquivo_lista TEXT NOT NULL,
        conteudo_lista TEXT NOT NULL DEFAULT '',
        data_criacao TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS conversas_estoque (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lista_pecas_id INTEGER NOT NULL,
        titulo TEXT NOT NULL,
        data_criacao TEXT NOT NULL,
        data_atualizacao TEXT NOT NULL,
        FOREIGN KEY (lista_pecas_id) REFERENCES listas_pecas (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS mensagens_estoque (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversa_id INTEGER NOT NULL,
        papel TEXT NOT NULL,
        conteudo TEXT NOT NULL,
        data_criacao TEXT NOT NULL,
        FOREIGN KEY (conversa_id) REFERENCES conversas_estoque (id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS indice_conversas_estoque_lista_id
    ON conversas_estoque (lista_pecas_id);

    CREATE INDEX IF NOT EXISTS indice_mensagens_estoque_conversa_id
    ON mensagens_estoque (conversa_id);
    """

    with obter_conexao() as conexao:
        conexao.executescript(script)
