from .database import get_connection


class EquipmentModel:
    @staticmethod
    def create_equipment(user_id: int, name: str, description: str) -> int:
        """Cria um equipamento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO equipments (user_id, name, description) VALUES (?, ?, ?)",
            (user_id, name, description),
        )
        conn.commit()
        equipment_id = cursor.lastrowid
        conn.close()
        return equipment_id

    @staticmethod
    def get_equipment(equipment_id: int):
        """Retorna um equipamento pelo ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM equipments WHERE id = ?",
            (equipment_id,),
        )
        equipment = cursor.fetchone()
        conn.close()
        return dict(equipment) if equipment else None

    @staticmethod
    def get_user_equipments():
        """Lista todos os equipamentos visiveis do sistema."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                equipments.*,
                COUNT(DISTINCT equipment_documents.id) AS document_count,
                COUNT(DISTINCT CASE WHEN equipment_documents.document_role = 'exam' THEN equipment_documents.id END) AS exam_document_count,
                COUNT(DISTINCT CASE WHEN equipment_documents.document_role = 'answer_key' THEN equipment_documents.id END) AS answer_key_document_count,
                COUNT(DISTINCT equipment_document_chunks.id) AS chunk_count
            FROM equipments
            LEFT JOIN equipment_documents
                ON equipment_documents.equipment_id = equipments.id
            LEFT JOIN equipment_document_chunks
                ON equipment_document_chunks.equipment_id = equipments.id
            GROUP BY equipments.id
            ORDER BY LOWER(equipments.name) ASC, equipments.id ASC
            """
        )
        equipments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return equipments

    @staticmethod
    def get_owned_equipments(user_id: int):
        """Lista equipamentos pertencentes a um usuario especifico."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                equipments.*,
                COUNT(DISTINCT equipment_documents.id) AS document_count,
                COUNT(DISTINCT CASE WHEN equipment_documents.document_role = 'exam' THEN equipment_documents.id END) AS exam_document_count,
                COUNT(DISTINCT CASE WHEN equipment_documents.document_role = 'answer_key' THEN equipment_documents.id END) AS answer_key_document_count,
                COUNT(DISTINCT equipment_document_chunks.id) AS chunk_count
            FROM equipments
            LEFT JOIN equipment_documents
                ON equipment_documents.equipment_id = equipments.id
            LEFT JOIN equipment_document_chunks
                ON equipment_document_chunks.equipment_id = equipments.id
            WHERE equipments.user_id = ?
            GROUP BY equipments.id
            ORDER BY LOWER(equipments.name) ASC, equipments.id ASC
            """,
            (user_id,),
        )
        equipments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return equipments

    @staticmethod
    def update_equipment(equipment_id: int, user_id: int, name: str, description: str) -> bool:
        """Atualiza nome e descricao de um equipamento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE equipments
            SET name = ?, description = ?
            WHERE id = ? AND user_id = ?
            """,
            (name, description, equipment_id, user_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    @staticmethod
    def add_document(
        equipment_id: int,
        file_name: str,
        file_path: str,
        file_type: str,
        document_role: str = "supporting",
    ) -> int:
        """Adiciona documento a um equipamento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO equipment_documents (equipment_id, file_name, file_path, file_type, document_role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (equipment_id, file_name, file_path, file_type, document_role),
        )
        conn.commit()
        document_id = cursor.lastrowid
        conn.close()
        return document_id

    @staticmethod
    def get_documents(equipment_id: int):
        """Lista documentos de um equipamento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                equipment_documents.*,
                COUNT(equipment_document_chunks.id) AS chunk_count
            FROM equipment_documents
            LEFT JOIN equipment_document_chunks
                ON equipment_document_chunks.document_id = equipment_documents.id
            WHERE equipment_documents.equipment_id = ?
            GROUP BY equipment_documents.id
            ORDER BY
                CASE equipment_documents.document_role
                    WHEN 'exam' THEN 0
                    WHEN 'answer_key' THEN 1
                    ELSE 2
                END ASC,
                equipment_documents.id ASC
            """,
            (equipment_id,),
        )
        documents = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return documents

    @staticmethod
    def add_document_chunk(
        document_id: int,
        equipment_id: int,
        chunk_index: int,
        chunk_text: str,
        source_label: str,
        extraction_method: str = "text",
    ) -> int:
        """Salva um trecho indexado de documento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO equipment_document_chunks (
                document_id,
                equipment_id,
                chunk_index,
                chunk_text,
                source_label,
                extraction_method
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (document_id, equipment_id, chunk_index, chunk_text, source_label, extraction_method),
        )
        conn.commit()
        chunk_id = cursor.lastrowid
        conn.close()
        return chunk_id

    @staticmethod
    def get_document_chunks(document_id: int):
        """Lista os trechos de um documento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM equipment_document_chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC, id ASC
            """,
            (document_id,),
        )
        chunks = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return chunks

    @staticmethod
    def get_equipment_chunks(equipment_id: int):
        """Lista todos os trechos de um equipamento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                equipment_document_chunks.*,
                equipment_documents.file_name,
                equipment_documents.document_role
            FROM equipment_document_chunks
            INNER JOIN equipment_documents
                ON equipment_documents.id = equipment_document_chunks.document_id
            WHERE equipment_document_chunks.equipment_id = ?
            ORDER BY
                CASE equipment_documents.document_role
                    WHEN 'exam' THEN 0
                    WHEN 'answer_key' THEN 1
                    ELSE 2
                END ASC,
                equipment_document_chunks.document_id ASC,
                equipment_document_chunks.chunk_index ASC,
                equipment_document_chunks.id ASC
            """,
            (equipment_id,),
        )
        chunks = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return chunks

    @staticmethod
    def delete_document_chunks(document_id: int) -> int:
        """Remove os trechos de um documento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM equipment_document_chunks WHERE document_id = ?", (document_id,))
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        return deleted_count

    @staticmethod
    def delete_documents(equipment_id: int) -> int:
        """Remove metadados de documentos de um equipamento."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM equipment_document_chunks WHERE equipment_id = ?", (equipment_id,))
        cursor.execute("DELETE FROM equipment_documents WHERE equipment_id = ?", (equipment_id,))
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        return deleted_count

    @staticmethod
    def delete_equipment(equipment_id: int, user_id: int) -> bool:
        """Remove um equipamento do usuario."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM equipments WHERE id = ? AND user_id = ?", (equipment_id, user_id))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
