import sqlite3

from .database import get_connection


class UserModel:
    @staticmethod
    def create_user(username: str, email: str, password_hash: str, role: str = "user") -> int | None:
        """Cria um novo usuario."""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, email, password_hash, role),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    @staticmethod
    def get_user(user_id: int):
        """Obtem um usuario pelo ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None

    @staticmethod
    def get_user_by_username(username: str):
        """Obtem um usuario pelo nome."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None

    @staticmethod
    def count_users_by_role(role: str) -> int:
        """Conta usuarios de um papel especifico."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = ?", (role,))
        total = int(cursor.fetchone()["total"])
        conn.close()
        return total

    @staticmethod
    def delete_user(user_id: int) -> bool:
        """Deleta um usuario."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
