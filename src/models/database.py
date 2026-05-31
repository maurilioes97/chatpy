import sqlite3
import os
from pathlib import Path

# Diretorio do banco de dados
DB_PATH = Path(__file__).parent.parent.parent / "data" / "chatbot.db"
DB_PATH.parent.mkdir(exist_ok=True)


def get_connection():
    """Conecta ao banco SQLite."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializa o banco e cria as tabelas."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("PRAGMA table_info(users)")
    user_columns = {row["name"] for row in cursor.fetchall()}
    if "password_hash" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
    if "role" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

    admin_username = os.getenv("ADMIN_USERNAME", "").strip()
    cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'")
    admin_count = cursor.fetchone()["total"]
    if admin_count == 0:
        if admin_username:
            cursor.execute("UPDATE users SET role = 'admin' WHERE username = ?", (admin_username,))
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    UPDATE users
                    SET role = 'admin'
                    WHERE id = (SELECT id FROM users ORDER BY id ASC LIMIT 1)
                    """
                )
        else:
            cursor.execute(
                """
                UPDATE users
                SET role = 'admin'
                WHERE id = (SELECT id FROM users ORDER BY id ASC LIMIT 1)
                """
            )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS equipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            document_role TEXT NOT NULL DEFAULT 'supporting',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (equipment_id) REFERENCES equipments(id)
        )
        """
    )
    cursor.execute("PRAGMA table_info(equipment_documents)")
    document_columns = {row["name"] for row in cursor.fetchall()}
    if "document_role" not in document_columns:
        cursor.execute("ALTER TABLE equipment_documents ADD COLUMN document_role TEXT NOT NULL DEFAULT 'supporting'")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment_document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            equipment_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            source_label TEXT NOT NULL DEFAULT '',
            extraction_method TEXT NOT NULL DEFAULT 'text',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES equipment_documents(id),
            FOREIGN KEY (equipment_id) REFERENCES equipments(id)
        )
        """
    )
    cursor.execute("PRAGMA table_info(equipment_document_chunks)")
    chunk_columns = {row["name"] for row in cursor.fetchall()}
    if "extraction_method" not in chunk_columns:
        cursor.execute("ALTER TABLE equipment_document_chunks ADD COLUMN extraction_method TEXT NOT NULL DEFAULT 'text'")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            equipment_id INTEGER,
            title TEXT DEFAULT 'Nova Conversa',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (equipment_id) REFERENCES equipments(id)
        )
        """
    )
    cursor.execute("PRAGMA table_info(conversations)")
    conversation_columns = {row["name"] for row in cursor.fetchall()}
    if "equipment_id" not in conversation_columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN equipment_id INTEGER")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
        """
    )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Banco de dados inicializado!")
