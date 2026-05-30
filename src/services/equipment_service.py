import io
import mimetypes
import re
import shutil
import sys
import zipfile
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.chat_model import ChatModel
from models.equipment_model import EquipmentModel
from utils.config import EQUIPMENT_FILES_DIR


class EquipmentService:
    """Servico de logica de equipamentos."""

    SUPPORTED_MIME_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    INDEXABLE_MIME_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    CHUNK_SIZE = 1800
    CHUNK_OVERLAP = 240
    MAX_CHUNKS_FOR_PROMPT = 6
    STOPWORDS = {
        "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
        "um", "uma", "uns", "umas", "para", "por", "com", "sem", "sobre", "que", "como", "qual",
        "quais", "onde", "quando", "porque", "porquê", "ser", "estar", "esta", "esse", "essa",
        "isso", "isto", "ele", "ela", "eles", "elas", "se", "ao", "aos", "à", "às", "ou", "mais",
        "menos", "muito", "muita", "manual", "maquina", "equipamento",
    }

    @staticmethod
    def register_equipment(user_id: int, name: str, description: str, uploaded_files: list) -> dict:
        """Cadastra um equipamento e seus documentos."""
        normalized_name = (name or "").strip()
        normalized_description = (description or "").strip()
        valid_files = [file for file in (uploaded_files or []) if file is not None]

        if len(normalized_name) < 3:
            return {"success": False, "message": "Informe um nome de equipamento com pelo menos 3 caracteres"}

        if len(normalized_description) < 10:
            return {"success": False, "message": "Informe uma descricao mais completa do equipamento"}

        if not valid_files:
            return {"success": False, "message": "Adicione pelo menos um manual ou documento tecnico"}

        invalid_file = next((file for file in valid_files if not EquipmentService._resolve_mime_type(file)), None)
        if invalid_file:
            return {"success": False, "message": f"Formato nao suportado para {invalid_file.name}"}

        equipment_id = EquipmentModel.create_equipment(user_id, normalized_name, normalized_description)
        equipment_dir = EquipmentService._get_equipment_directory(user_id, equipment_id)
        equipment_dir.mkdir(parents=True, exist_ok=True)

        indexed_document_count = 0
        indexed_chunk_count = 0

        try:
            for uploaded_file in valid_files:
                file_name = Path(uploaded_file.name).name
                mime_type = EquipmentService._resolve_mime_type(uploaded_file)
                file_bytes = uploaded_file.getvalue()
                saved_path = equipment_dir / f"{uuid4().hex}_{file_name}"
                saved_path.write_bytes(file_bytes)
                document_id = EquipmentModel.add_document(
                    equipment_id,
                    file_name,
                    str(saved_path),
                    mime_type,
                )
                chunk_count = EquipmentService._index_document(
                    document_id=document_id,
                    equipment_id=equipment_id,
                    file_name=file_name,
                    mime_type=mime_type,
                    file_bytes=file_bytes,
                )
                if chunk_count > 0:
                    indexed_document_count += 1
                    indexed_chunk_count += chunk_count
        except Exception as exc:
            EquipmentService.delete_equipment(user_id, equipment_id)
            return {"success": False, "message": f"Erro ao salvar documentos: {str(exc)}"}

        message = "Equipamento cadastrado com sucesso."
        if indexed_document_count:
            message += f" {indexed_document_count} documento(s) indexado(s) em {indexed_chunk_count} trecho(s)."
        else:
            message += " Os arquivos foram salvos, mas nao geraram indice textual ainda."

        return {
            "success": True,
            "message": message,
            "equipment_id": equipment_id,
            "indexed_document_count": indexed_document_count,
            "indexed_chunk_count": indexed_chunk_count,
        }

    @staticmethod
    def get_user_equipments(user_id: int) -> dict:
        """Lista equipamentos do usuario."""
        equipments = EquipmentModel.get_user_equipments(user_id)
        return {"success": True, "equipments": equipments, "total": len(equipments)}

    @staticmethod
    def get_equipment(equipment_id: int, user_id: int) -> dict:
        """Retorna dados de um equipamento."""
        equipment = EquipmentModel.get_equipment(equipment_id, user_id)
        if not equipment:
            return {"success": False, "message": "Equipamento nao encontrado"}

        EquipmentService._ensure_equipment_chunks(equipment_id, user_id)
        documents = EquipmentModel.get_documents(equipment_id)
        equipment["documents"] = documents
        equipment["indexed_chunk_count"] = sum(int(doc.get("chunk_count") or 0) for doc in documents)
        return {"success": True, "equipment": equipment}

    @staticmethod
    def get_equipment_context(equipment_id: int, user_id: int) -> dict:
        """Monta contexto textual do equipamento."""
        result = EquipmentService.get_equipment(equipment_id, user_id)
        if not result["success"]:
            return {"success": False, "message": result["message"]}

        equipment = result["equipment"]
        document_names = [doc["file_name"] for doc in equipment["documents"]]
        document_summaries = EquipmentService._build_document_summaries(equipment["documents"])
        context_lines = [
            f"Equipamento: {equipment['name']}",
            f"Descricao tecnica: {equipment['description']}",
        ]
        if document_names:
            context_lines.append("Documentos tecnicos cadastrados: " + ", ".join(document_names))
        if document_summaries:
            context_lines.append("Resumo da indexacao:")
            context_lines.extend(document_summaries)

        return {
            "success": True,
            "equipment": equipment,
            "context_text": "\n".join(context_lines),
            "documents": equipment["documents"],
            "indexed_chunk_count": equipment["indexed_chunk_count"],
            "document_summaries": document_summaries,
        }

    @staticmethod
    def search_equipment_knowledge(equipment_id: int, user_id: int, query: str, limit: int | None = None) -> dict:
        """Busca os trechos mais relevantes do conhecimento indexado do equipamento."""
        equipment = EquipmentModel.get_equipment(equipment_id, user_id)
        if not equipment:
            return {"success": False, "message": "Equipamento nao encontrado", "chunks": []}

        EquipmentService._ensure_equipment_chunks(equipment_id, user_id)
        all_chunks = EquipmentModel.get_equipment_chunks(equipment_id)
        if not all_chunks:
            return {"success": True, "chunks": [], "total_indexed_chunks": 0}

        selected_limit = limit or EquipmentService.MAX_CHUNKS_FOR_PROMPT
        ranked_chunks, had_direct_matches = EquipmentService._rank_chunks(query, all_chunks, selected_limit)
        return {
            "success": True,
            "chunks": ranked_chunks,
            "total_indexed_chunks": len(all_chunks),
            "had_direct_matches": had_direct_matches,
        }

    @staticmethod
    def delete_equipment(user_id: int, equipment_id: int) -> dict:
        """Exclui equipamento, documentos e conversas associadas."""
        equipment = EquipmentModel.get_equipment(equipment_id, user_id)
        if not equipment:
            return {"success": False, "message": "Equipamento nao encontrado"}

        documents = EquipmentModel.get_documents(equipment_id)
        ChatModel.delete_equipment_conversations(equipment_id, user_id)
        EquipmentModel.delete_documents(equipment_id)

        for doc in documents:
            file_path = Path(doc["file_path"])
            if file_path.exists():
                file_path.unlink()

        equipment_dir = EquipmentService._get_equipment_directory(user_id, equipment_id)
        if equipment_dir.exists():
            shutil.rmtree(equipment_dir, ignore_errors=True)

        deleted = EquipmentModel.delete_equipment(equipment_id, user_id)
        if not deleted:
            return {"success": False, "message": "Nao foi possivel excluir o equipamento"}

        return {"success": True, "message": "Equipamento excluido com sucesso"}

    @staticmethod
    def delete_user_equipments(user_id: int) -> None:
        """Exclui todos os equipamentos e arquivos de um usuario."""
        equipments = EquipmentModel.get_user_equipments(user_id)
        for equipment in equipments:
            EquipmentService.delete_equipment(user_id, equipment["id"])

        user_dir = Path(EQUIPMENT_FILES_DIR) / f"user_{user_id}"
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)

    @staticmethod
    def _ensure_equipment_chunks(equipment_id: int, user_id: int) -> None:
        """Garante que documentos indexaveis antigos tambem tenham trechos gerados."""
        equipment = EquipmentModel.get_equipment(equipment_id, user_id)
        if not equipment:
            return

        documents = EquipmentModel.get_documents(equipment_id)
        for document in documents:
            if int(document.get("chunk_count") or 0) > 0:
                continue
            if document["file_type"] not in EquipmentService.INDEXABLE_MIME_TYPES:
                continue

            file_path = Path(document["file_path"])
            if not file_path.exists():
                continue

            EquipmentService._index_document(
                document_id=document["id"],
                equipment_id=equipment_id,
                file_name=document["file_name"],
                mime_type=document["file_type"],
                file_bytes=file_path.read_bytes(),
            )

    @staticmethod
    def _index_document(
        document_id: int,
        equipment_id: int,
        file_name: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> int:
        """Extrai e salva trechos de um documento."""
        if mime_type not in EquipmentService.INDEXABLE_MIME_TYPES:
            return 0

        existing_chunks = EquipmentModel.get_document_chunks(document_id)
        if existing_chunks:
            return len(existing_chunks)

        extracted_chunks = EquipmentService._extract_chunks(file_name, mime_type, file_bytes)
        for index, chunk in enumerate(extracted_chunks, start=1):
            EquipmentModel.add_document_chunk(
                document_id=document_id,
                equipment_id=equipment_id,
                chunk_index=index,
                chunk_text=chunk["text"],
                source_label=chunk["source_label"],
            )

        return len(extracted_chunks)

    @staticmethod
    def _extract_chunks(file_name: str, mime_type: str, file_bytes: bytes) -> list[dict]:
        """Extrai trechos de um documento indexavel."""
        if mime_type == "application/pdf":
            return EquipmentService._extract_pdf_chunks(file_name, file_bytes)

        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            extracted_text = EquipmentService._extract_docx_text(file_bytes)
            return EquipmentService._split_text_into_chunks(
                extracted_text,
                source_prefix=f"{file_name} - trecho",
            )

        return []

    @staticmethod
    def _extract_pdf_chunks(file_name: str, file_bytes: bytes) -> list[dict]:
        """Extrai texto de PDF pagina por pagina e divide em trechos."""
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
        except Exception:
            return []

        extracted_chunks = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""

            normalized_text = EquipmentService._normalize_text(page_text)
            if not normalized_text:
                continue

            page_chunks = EquipmentService._split_text_into_chunks(
                normalized_text,
                source_prefix=f"{file_name} - pagina {page_number}",
            )
            extracted_chunks.extend(page_chunks)

        return extracted_chunks

    @staticmethod
    def _extract_docx_text(file_bytes: bytes) -> str:
        """Extrai o texto principal de um arquivo DOCX."""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                xml_content = archive.read("word/document.xml")
        except Exception:
            return ""

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return ""

        paragraphs = []
        current_parts = []
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "t" and element.text:
                current_parts.append(element.text)
            elif tag == "p":
                paragraph = "".join(current_parts).strip()
                if paragraph:
                    paragraphs.append(paragraph)
                current_parts = []

        trailing = "".join(current_parts).strip()
        if trailing:
            paragraphs.append(trailing)

        return EquipmentService._normalize_text("\n".join(paragraphs))

    @staticmethod
    def _split_text_into_chunks(text: str, source_prefix: str) -> list[dict]:
        """Divide texto grande em trechos sobrepostos."""
        normalized_text = EquipmentService._normalize_text(text)
        if not normalized_text:
            return []

        chunks = []
        start = 0
        chunk_number = 1
        text_length = len(normalized_text)

        while start < text_length:
            end = min(start + EquipmentService.CHUNK_SIZE, text_length)
            if end < text_length:
                split_at = normalized_text.rfind(" ", start, end)
                if split_at > start + EquipmentService.CHUNK_SIZE // 2:
                    end = split_at

            chunk_text = normalized_text[start:end].strip()
            if chunk_text:
                source_label = source_prefix if chunk_number == 1 else f"{source_prefix}, trecho {chunk_number}"
                chunks.append({"text": chunk_text, "source_label": source_label})

            if end >= text_length:
                break

            start = max(end - EquipmentService.CHUNK_OVERLAP, start + 1)
            chunk_number += 1

        return chunks

    @staticmethod
    def _rank_chunks(query: str, chunks: list[dict], limit: int) -> tuple[list[dict], bool]:
        """Ranqueia os trechos mais relevantes para a pergunta."""
        query_text = EquipmentService._normalize_text(query).lower()
        query_terms = EquipmentService._extract_terms(query_text)

        scored_chunks = []
        for position, chunk in enumerate(chunks):
            chunk_text = (chunk.get("chunk_text") or "").lower()
            if not chunk_text:
                continue

            score = 0
            if query_text and query_text in chunk_text:
                score += 25

            for term in query_terms:
                occurrences = chunk_text.count(term)
                if occurrences:
                    score += 5 + (occurrences * 2)

            if score > 0:
                scored_chunks.append((score, position, chunk))

        if not scored_chunks:
            return [], False

        scored_chunks.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored_chunks[:limit]], True

    @staticmethod
    def _build_document_summaries(documents: list[dict]) -> list[str]:
        """Cria um resumo da cobertura dos documentos indexados."""
        summaries = []
        for document in documents:
            page_start, page_end = EquipmentService._extract_page_range_for_document(document["id"])
            chunk_count = int(document.get("chunk_count") or 0)
            if page_start is not None and page_end is not None:
                summaries.append(
                    f"- {document['file_name']}: {chunk_count} trecho(s), cobrindo da pagina {page_start} ate a pagina {page_end}."
                )
            elif chunk_count > 0:
                summaries.append(
                    f"- {document['file_name']}: {chunk_count} trecho(s) indexados."
                )
            else:
                summaries.append(
                    f"- {document['file_name']}: sem trechos textuais indexados."
                )
        return summaries

    @staticmethod
    def _extract_page_range_for_document(document_id: int) -> tuple[int | None, int | None]:
        """Extrai a faixa de paginas identificada nos source labels do documento."""
        chunks = EquipmentModel.get_document_chunks(document_id)
        page_numbers = []
        for chunk in chunks:
            source_label = chunk.get("source_label") or ""
            match = re.search(r"pagina\s+(\d+)", source_label, flags=re.IGNORECASE)
            if match:
                page_numbers.append(int(match.group(1)))

        if not page_numbers:
            return None, None

        return min(page_numbers), max(page_numbers)

    @staticmethod
    def _extract_terms(text: str) -> list[str]:
        """Extrai termos de busca relevantes."""
        terms = re.findall(r"[a-zA-Z0-9_-]{3,}", text.lower())
        unique_terms = []
        seen_terms = set()

        for term in terms:
            if term in EquipmentService.STOPWORDS or term in seen_terms:
                continue
            unique_terms.append(term)
            seen_terms.add(term)

        return unique_terms

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normaliza espacos em branco do texto."""
        return re.sub(r"\s+", " ", (text or "")).strip()

    @staticmethod
    def _get_equipment_directory(user_id: int, equipment_id: int) -> Path:
        """Retorna a pasta de arquivos de um equipamento."""
        return Path(EQUIPMENT_FILES_DIR) / f"user_{user_id}" / f"equipment_{equipment_id}"

    @staticmethod
    def _resolve_mime_type(uploaded_file) -> str | None:
        """Resolve o MIME type do arquivo enviado."""
        mime_type = getattr(uploaded_file, "type", "") or mimetypes.guess_type(uploaded_file.name)[0] or ""
        return mime_type if mime_type in EquipmentService.SUPPORTED_MIME_TYPES else None
