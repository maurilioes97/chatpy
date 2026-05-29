import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.user_model import UserModel

class UserService:
    """Serviço de lógica de usuário"""
    
    @staticmethod
    def register_user(username: str, email: str) -> dict:
        """Registra um novo usuário"""
        # Valida entrada
        if not username or len(username) < 3:
            return {"success": False, "message": "Username deve ter no mínimo 3 caracteres"}
        
        if not email or "@" not in email:
            return {"success": False, "message": "Email inválido"}
        
        # Cria usuário
        user_id = UserModel.create_user(username, email)
        
        if user_id:
            return {"success": True, "message": "Usuário criado!", "user_id": user_id}
        else:
            return {"success": False, "message": "Usuário ou email já existem"}
    
    @staticmethod
    def get_user_profile(user_id: int) -> dict:
        """Obtém perfil do usuário"""
        user = UserModel.get_user(user_id)
        
        if user:
            return {"success": True, "user": user}
        else:
            return {"success": False, "message": "Usuário não encontrado"}
    
    @staticmethod
    def authenticate_user(username: str) -> dict:
        """Autentica um usuário (simplificado - sem senha)"""
        user = UserModel.get_user_by_username(username)
        
        if user:
            return {"success": True, "user_id": user["id"], "username": user["username"]}
        else:
            return {"success": False, "message": "Usuário não encontrado"}