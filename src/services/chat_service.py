import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.chat_model import ChatModel


class ChatService:
    """Servico de logica de chat."""

    DEFAULT_TITLE = "Novo Estudo"

    @staticmethod
    def start_conversation(user_id: int, equipment_id: int | None, title: str | None = None) -> dict:
        """Inicia uma nova conversa."""
        conversation_title = title or ChatService.DEFAULT_TITLE
        conversation_id = ChatModel.create_conversation(user_id, equipment_id, conversation_title)

        return {
            "success": True,
            "conversation_id": conversation_id,
            "message": "Conversa iniciada",
        }

    @staticmethod
    def get_conversation(conversation_id: int, user_id: int) -> dict:
        """Obtem uma conversa especifica do usuario."""
        conversation = ChatModel.get_conversation(conversation_id, user_id)
        if not conversation:
            return {"success": False, "message": "Conversa nao encontrada"}

        return {"success": True, "conversation": conversation}

    @staticmethod
    def get_user_conversations(user_id: int, equipment_id: int | None = None) -> dict:
        """Lista todas as conversas do usuario."""
        conversations = ChatModel.get_conversations(user_id, equipment_id)
        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations),
        }

    @staticmethod
    def update_conversation_title(conversation_id: int, user_id: int, title: str) -> dict:
        """Atualiza o titulo de uma conversa."""
        normalized_title = ChatService._normalize_title(title)
        if not normalized_title:
            return {"success": False, "message": "Digite um titulo para a conversa"}

        success = ChatModel.update_conversation_title(conversation_id, user_id, normalized_title)
        if not success:
            return {"success": False, "message": "Conversa nao encontrada"}

        return {
            "success": True,
            "message": "Titulo atualizado",
            "title": normalized_title,
        }

    @staticmethod
    def send_message(
        conversation_id: int,
        user_id: int,
        user_message: str,
        assistant_response: str,
    ) -> dict:
        """Salva mensagem do usuario e resposta da IA."""
        try:
            conversation = ChatModel.get_conversation(conversation_id, user_id)
            if not conversation:
                return {"success": False, "message": "Conversa nao encontrada"}

            ChatModel.add_message(conversation_id, "user", user_message)
            ChatModel.add_message(conversation_id, "assistant", assistant_response)

            updated_title = None
            current_title = (conversation.get("title") or "").strip()
            if not current_title or current_title == ChatService.DEFAULT_TITLE:
                updated_title = ChatService._build_title_from_message(user_message)
                ChatModel.update_conversation_title(conversation_id, user_id, updated_title)

            return {
                "success": True,
                "message": "Mensagens salvas",
                "assistant_response": assistant_response,
                "title": updated_title or current_title,
            }
        except Exception as e:
            return {"success": False, "message": f"Erro ao salvar mensagens: {str(e)}"}

    @staticmethod
    def get_conversation_history(conversation_id: int, user_id: int) -> dict:
        """Obtem o historico de uma conversa do usuario."""
        conversation = ChatModel.get_conversation(conversation_id, user_id)
        if not conversation:
            return {"success": False, "message": "Conversa nao encontrada", "messages": []}

        messages = ChatModel.get_messages(conversation_id)
        return {
            "success": True,
            "messages": messages,
            "total_messages": len(messages),
        }

    @staticmethod
    def delete_conversation(conversation_id: int, user_id: int) -> dict:
        """Deleta uma conversa do usuario."""
        success = ChatModel.delete_conversation(conversation_id, user_id)
        if success:
            return {"success": True, "message": "Conversa deletada"}
        return {"success": False, "message": "Conversa nao encontrada"}

    @staticmethod
    def _build_title_from_message(user_message: str) -> str:
        """Gera um titulo simples com base na primeira mensagem."""
        base_message = user_message
        for marker in ("Material anexado:", "Documento anexado:"):
            base_message = base_message.split(marker, 1)[0]
        cleaned = re.sub(r"\s+", " ", base_message).strip(" .,:;!?-\n\t")
        if not cleaned:
            return ChatService.DEFAULT_TITLE

        if len(cleaned) <= 45:
            return cleaned

        shortened = cleaned[:45].rsplit(" ", 1)[0].strip()
        return f"{shortened or cleaned[:45]}..."

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normaliza o titulo informado manualmente."""
        cleaned = re.sub(r"\s+", " ", (title or "")).strip()
        if len(cleaned) > 60:
            cleaned = cleaned[:60].rstrip()
        return cleaned
