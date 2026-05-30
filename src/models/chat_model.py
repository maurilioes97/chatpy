from .database import get_connection


class ChatModel:
    @staticmethod
    def create_conversation(user_id: int, title: str = "Nova Conversa") -> int:
        """Cria uma nova conversa."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
            (user_id, title),
        )
        conn.commit()
        conversation_id = cursor.lastrowid
        conn.close()
        return conversation_id

    @staticmethod
    def get_conversation(conversation_id: int, user_id: int):
        """Retorna uma conversa especifica do usuario."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        conversation = cursor.fetchone()
        conn.close()
        return dict(conversation) if conversation else None

    @staticmethod
    def get_conversations(user_id: int):
        """Lista todas as conversas de um usuario."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        conversations = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return conversations

    @staticmethod
    def update_conversation_title(conversation_id: int, user_id: int, title: str) -> bool:
        """Atualiza o titulo de uma conversa do usuario."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
            (title, conversation_id, user_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    @staticmethod
    def add_message(conversation_id: int, role: str, content: str) -> int:
        """Adiciona uma mensagem a conversa."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content),
        )
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()
        return message_id

    @staticmethod
    def get_messages(conversation_id: int):
        """Obtem todas as mensagens de uma conversa."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        )
        messages = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return messages

    @staticmethod
    def delete_user_conversations(user_id: int) -> int:
        """Deleta todas as conversas e mensagens de um usuario."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)",
            (user_id,),
        )
        cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        return deleted_count

    @staticmethod
    def delete_conversation(conversation_id: int, user_id: int) -> bool:
        """Deleta uma conversa do usuario e suas mensagens."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE id = ? AND user_id = ?)",
            (conversation_id, user_id),
        )
        cursor.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
