import hashlib
import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.chat_model import ChatModel
from models.user_model import UserModel


class UserService:
    """Servico de logica de usuario."""

    @staticmethod
    def register_user(username: str, email: str, password: str) -> dict:
        """Registra um novo usuario."""
        if not username or len(username) < 3:
            return {"success": False, "message": "Username deve ter no minimo 3 caracteres"}

        if not email or "@" not in email:
            return {"success": False, "message": "Email invalido"}

        if not password or len(password) < 6:
            return {"success": False, "message": "A senha deve ter no minimo 6 caracteres"}

        password_hash = UserService._hash_password(password)
        user_id = UserModel.create_user(username, email, password_hash)

        if user_id:
            return {"success": True, "message": "Usuario criado!", "user_id": user_id}
        return {"success": False, "message": "Usuario ou email ja existem"}

    @staticmethod
    def get_user_profile(user_id: int) -> dict:
        """Obtem perfil do usuario."""
        user = UserModel.get_user(user_id)

        if user:
            return {"success": True, "user": user}
        return {"success": False, "message": "Usuario nao encontrado"}

    @staticmethod
    def authenticate_user(username: str, password: str) -> dict:
        """Autentica um usuario com username e senha."""
        user = UserModel.get_user_by_username(username)

        if not user:
            return {"success": False, "message": "Usuario nao encontrado"}

        password_hash = user.get("password_hash") or ""
        if not password_hash:
            return {
                "success": False,
                "message": "Essa conta antiga nao possui senha cadastrada. Crie uma nova conta.",
            }

        if not UserService._verify_password(password, password_hash):
            return {"success": False, "message": "Senha incorreta"}

        return {"success": True, "user_id": user["id"], "username": user["username"]}

    @staticmethod
    def delete_account(user_id: int) -> dict:
        """Exclui a conta do usuario e todas as conversas associadas."""
        user = UserModel.get_user(user_id)
        if not user:
            return {"success": False, "message": "Usuario nao encontrado"}

        ChatModel.delete_user_conversations(user_id)
        deleted = UserModel.delete_user(user_id)
        if not deleted:
            return {"success": False, "message": "Nao foi possivel excluir a conta"}

        return {"success": True, "message": "Conta excluida com sucesso"}

    @staticmethod
    def _hash_password(password: str) -> str:
        """Gera hash PBKDF2 com salt aleatorio."""
        salt = os.urandom(16)
        derived_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return f"{salt.hex()}:{derived_key.hex()}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        """Confere se a senha bate com o hash armazenado."""
        try:
            salt_hex, hash_hex = stored_hash.split(":", 1)
            salt = bytes.fromhex(salt_hex)
            expected_hash = bytes.fromhex(hash_hex)
        except ValueError:
            return False

        candidate_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(candidate_hash, expected_hash)
