import json
import mimetypes
import re
import shutil
import sys
from pathlib import Path
from uuid import uuid4
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.chat_model import ChatModel
from models.equipment_model import EquipmentModel
from models.user_model import UserModel
from services.embedding_service import EmbeddingService, EmbeddingServiceError
from utils.config import EQUIPMENT_FILES_DIR
from utils.document_processing import extract_docx_text, extract_pdf_pages, normalize_text


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
    SEMANTIC_MATCH_THRESHOLD = 0.18
    SEMANTIC_SEARCH_WEIGHT = 0.6
    STOPWORDS = {
        "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
        "um", "uma", "uns", "umas", "para", "por", "com", "sem", "sobre", "que", "como", "qual",
        "quais", "onde", "quando", "porque", "porquê", "ser", "estar", "esta", "esse", "essa",
        "isso", "isto", "ele", "ela", "eles", "elas", "se", "ao", "aos", "à", "às", "ou", "mais",
        "menos", "muito", "muita", "manual", "maquina", "equipamento",
    }

    @staticmethod
    def register_equipment(user_id: int, name: str, description: str, uploaded_files: list, progress_callback=None) -> dict:
        """Cadastra um equipamento e seus documentos."""
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem cadastrar equipamentos"}

        normalized_name = (name or "").strip()
        normalized_description = (description or "").strip()
        valid_files = [file for file in (uploaded_files or []) if file is not None]

        if not normalized_name:
            return {"success": False, "message": "Informe o nome do equipamento"}

        if not valid_files:
            return {"success": False, "message": "Adicione pelo menos um manual ou documento tecnico"}

        invalid_file = next((file for file in valid_files if not EquipmentService._resolve_mime_type(file)), None)
        if invalid_file:
            return {"success": False, "message": f"Formato nao suportado para {invalid_file.name}"}

        equipment_id = EquipmentModel.create_equipment(user_id, normalized_name, normalized_description)

        try:
            indexed_document_count, indexed_chunk_count = EquipmentService._store_equipment_documents(
                user_id=user_id,
                equipment_id=equipment_id,
                uploaded_files=valid_files,
                progress_callback=progress_callback,
            )
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
    def add_equipment_documents(user_id: int, equipment_id: int, uploaded_files: list, progress_callback=None) -> dict:
        """Adiciona novos documentos a um equipamento existente."""
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem adicionar documentos"}

        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Equipamento nao encontrado"}

        valid_files = [file for file in (uploaded_files or []) if file is not None]
        if not valid_files:
            return {"success": False, "message": "Selecione pelo menos um documento para adicionar"}

        invalid_file = next((file for file in valid_files if not EquipmentService._resolve_mime_type(file)), None)
        if invalid_file:
            return {"success": False, "message": f"Formato nao suportado para {invalid_file.name}"}

        try:
            indexed_document_count, indexed_chunk_count = EquipmentService._store_equipment_documents(
                user_id=user_id,
                equipment_id=equipment_id,
                uploaded_files=valid_files,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            return {"success": False, "message": f"Erro ao salvar documentos: {str(exc)}"}

        message = f"{len(valid_files)} documento(s) adicionado(s) ao equipamento."
        if indexed_document_count:
            message += f" {indexed_document_count} documento(s) indexado(s) em {indexed_chunk_count} trecho(s)."
        else:
            message += " Os arquivos foram salvos, mas nao geraram indice textual ainda."

        return {
            "success": True,
            "message": message,
            "indexed_document_count": indexed_document_count,
            "indexed_chunk_count": indexed_chunk_count,
        }

    @staticmethod
    def get_user_equipments(user_id: int) -> dict:
        """Lista equipamentos do usuario."""
        equipments = EquipmentModel.get_user_equipments()
        return {"success": True, "equipments": equipments, "total": len(equipments)}

    @staticmethod
    def update_equipment(user_id: int, equipment_id: int, name: str, description: str) -> dict:
        """Atualiza os dados principais de um equipamento."""
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem editar equipamentos"}

        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Equipamento nao encontrado"}

        normalized_name = (name or "").strip()
        normalized_description = (description or "").strip()

        if not normalized_name:
            return {"success": False, "message": "Informe o nome do equipamento"}

        updated = EquipmentModel.update_equipment(
            equipment_id,
            equipment["user_id"],
            normalized_name,
            normalized_description,
        )
        if not updated:
            return {"success": False, "message": "Nao foi possivel atualizar o equipamento"}

        return {"success": True, "message": "Equipamento atualizado com sucesso."}

    @staticmethod
    def get_equipment(equipment_id: int, user_id: int) -> dict:
        """Retorna dados de um equipamento."""
        equipment = EquipmentModel.get_equipment(equipment_id)
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
        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Equipamento nao encontrado", "chunks": []}

        EquipmentService._ensure_equipment_chunks(equipment_id, user_id)
        all_chunks = EquipmentModel.get_equipment_chunks(equipment_id)
        if not all_chunks:
            return {"success": True, "chunks": [], "total_indexed_chunks": 0}

        selected_limit = limit or EquipmentService.MAX_CHUNKS_FOR_PROMPT
        EquipmentService._ensure_chunk_embeddings(all_chunks)
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
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem excluir equipamentos"}

        return EquipmentService._delete_equipment_records(user_id, equipment_id)

    @staticmethod
    def delete_user_equipments(user_id: int) -> None:
        """Exclui todos os equipamentos e arquivos de um usuario."""
        equipments = EquipmentModel.get_owned_equipments(user_id)
        for equipment in equipments:
            EquipmentService._delete_equipment_records(user_id, equipment["id"])

        user_dir = Path(EQUIPMENT_FILES_DIR) / f"user_{user_id}"
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)

    @staticmethod
    def _ensure_equipment_chunks(equipment_id: int, user_id: int) -> None:
        """Garante que documentos indexaveis antigos tambem tenham trechos gerados."""
        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return

        documents = EquipmentModel.get_documents(equipment_id)
        for document in documents:
            if document["file_type"] not in EquipmentService.INDEXABLE_MIME_TYPES:
                continue

            file_path = Path(document["file_path"])
            if not file_path.exists():
                continue

            existing_chunks = EquipmentModel.get_document_chunks(document["id"])
            if existing_chunks:
                if not EquipmentService._chunks_need_reindex(existing_chunks):
                    continue
                EquipmentModel.delete_document_chunks(document["id"])

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
        progress_callback=None,
    ) -> int:
        """Extrai e salva trechos de um documento."""
        if mime_type not in EquipmentService.INDEXABLE_MIME_TYPES:
            return 0

        existing_chunks = EquipmentModel.get_document_chunks(document_id)
        if existing_chunks:
            return len(existing_chunks)

        extracted_chunks = EquipmentService._extract_chunks(
            file_name,
            mime_type,
            file_bytes,
            progress_callback=progress_callback,
        )
        if callable(progress_callback):
            progress_callback(0.82, f"Gravando trechos do documento {file_name}")
        saved_chunks = []
        for index, chunk in enumerate(extracted_chunks, start=1):
            chunk_id = EquipmentModel.add_document_chunk(
                document_id=document_id,
                equipment_id=equipment_id,
                chunk_index=index,
                chunk_text=chunk["text"],
                source_label=chunk["source_label"],
                extraction_method=chunk.get("extraction_method", "text"),
            )
            saved_chunks.append({"id": chunk_id, "chunk_text": chunk["text"]})

        if callable(progress_callback):
            progress_callback(0.9, f"Gerando embeddings do documento {file_name}")

        EquipmentService._store_chunk_embeddings(saved_chunks)

        if callable(progress_callback):
            progress_callback(1.0, f"Documento {file_name} processado")

        return len(extracted_chunks)

    @staticmethod
    def _extract_chunks(file_name: str, mime_type: str, file_bytes: bytes, progress_callback=None) -> list[dict]:
        """Extrai trechos de um documento indexavel."""
        if mime_type == "application/pdf":
            return EquipmentService._extract_pdf_chunks(file_name, file_bytes, progress_callback=progress_callback)

        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            if callable(progress_callback):
                progress_callback(0.45, f"Extraindo texto do documento {file_name}")
            extracted_text = extract_docx_text(file_bytes)
            if callable(progress_callback):
                progress_callback(0.7, f"Dividindo o documento {file_name} em trechos")
            return EquipmentService._split_text_into_chunks(
                extracted_text,
                source_prefix=f"{file_name} - trecho",
                extraction_method="text",
            )

        return []

    @staticmethod
    def _extract_pdf_chunks(file_name: str, file_bytes: bytes, progress_callback=None) -> list[dict]:
        """Extrai texto de PDF pagina por pagina e divide em trechos."""
        extracted_chunks = []
        page_progress = None
        if callable(progress_callback):
            def page_progress(current_page: int, total_pages: int, message: str) -> None:
                extraction_progress = 0.2 + ((current_page / max(total_pages, 1)) * 0.55)
                progress_callback(extraction_progress, f"{message} do documento {file_name}")

        for page in extract_pdf_pages(file_bytes, progress_callback=page_progress):
            page_number = page["page_number"]
            extraction_method = page.get("extraction_method", "text")
            source_suffix = f"pagina {page_number}"
            if extraction_method == "ocr":
                source_suffix += " (OCR)"
            page_chunks = EquipmentService._split_text_into_chunks(
                page["text"],
                source_prefix=f"{file_name} - {source_suffix}",
                extraction_method=extraction_method,
            )
            extracted_chunks.extend(page_chunks)

        if callable(progress_callback):
            progress_callback(0.78, f"Dividindo o PDF {file_name} em trechos")

        return extracted_chunks

    @staticmethod
    def _split_text_into_chunks(text: str, source_prefix: str, extraction_method: str = "text") -> list[dict]:
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
                chunks.append(
                    {
                        "text": chunk_text,
                        "source_label": source_label,
                        "extraction_method": extraction_method,
                    }
                )

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
        query_embedding = EquipmentService._embed_query(query_text)

        scored_chunks = []
        fallback_chunks = []
        for position, chunk in enumerate(chunks):
            chunk_text = (chunk.get("chunk_text") or "").lower()
            if not chunk_text:
                continue

            lexical_score = EquipmentService._score_lexical_match(query_text, query_terms, chunk_text)
            semantic_score = 0.0
            if query_embedding is not None:
                semantic_score = EquipmentService._cosine_similarity(
                    query_embedding,
                    EquipmentService._parse_embedding_vector(chunk.get("embedding_vector")),
                )

            lexical_component = lexical_score / 100.0
            if query_embedding is None:
                total_score = lexical_component
            else:
                total_score = (
                    (semantic_score * EquipmentService.SEMANTIC_SEARCH_WEIGHT)
                    + (lexical_component * (1 - EquipmentService.SEMANTIC_SEARCH_WEIGHT))
                )

            if query_text and query_text in chunk_text:
                total_score += 0.18

            if lexical_score > 0 or semantic_score >= EquipmentService.SEMANTIC_MATCH_THRESHOLD:
                scored_chunks.append((total_score, lexical_score, semantic_score, position, chunk))
            elif semantic_score > 0:
                fallback_chunks.append((semantic_score, position, chunk))

        if scored_chunks:
            scored_chunks.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
            return [item[4] for item in scored_chunks[:limit]], True

        if fallback_chunks:
            fallback_chunks.sort(key=lambda item: (-item[0], item[1]))
            return [item[2] for item in fallback_chunks[:limit]], False

        return [], False

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
        return normalize_text(text)

    @staticmethod
    def _get_equipment_directory(user_id: int, equipment_id: int) -> Path:
        """Retorna a pasta de arquivos de um equipamento."""
        return Path(EQUIPMENT_FILES_DIR) / f"user_{user_id}" / f"equipment_{equipment_id}"

    @staticmethod
    def _resolve_mime_type(uploaded_file) -> str | None:
        """Resolve o MIME type do arquivo enviado."""
        mime_type = getattr(uploaded_file, "type", "") or mimetypes.guess_type(uploaded_file.name)[0] or ""
        return mime_type if mime_type in EquipmentService.SUPPORTED_MIME_TYPES else None

    @staticmethod
    def _chunks_need_reindex(chunks: list[dict]) -> bool:
        """Detecta trechos antigos com texto corrompido por espacamento na extracao."""
        if not chunks:
            return False

        sample_text = " ".join((chunk.get("chunk_text") or "")[:500] for chunk in chunks[:3]).strip()
        if not sample_text:
            return True

        tokens = sample_text.split()
        if not tokens:
            return True

        single_char_ratio = sum(len(token) == 1 for token in tokens) / len(tokens)
        return single_char_ratio >= 0.35

    @staticmethod
    def _store_chunk_embeddings(chunks: list[dict]) -> None:
        """Gera e salva embeddings para os trechos inseridos."""
        if not chunks:
            return

        try:
            embedding_service = EmbeddingService()
            vectors = embedding_service.embed_texts([chunk["chunk_text"] for chunk in chunks])
        except EmbeddingServiceError:
            return

        for chunk, vector in zip(chunks, vectors):
            vector_json = json.dumps(vector)
            EquipmentModel.update_chunk_embedding(chunk["id"], vector_json, embedding_service.model_name)

    @staticmethod
    def _ensure_chunk_embeddings(chunks: list[dict]) -> None:
        """Preenche embeddings ausentes para documentos ja indexados."""
        if not chunks:
            return

        try:
            embedding_service = EmbeddingService()
        except EmbeddingServiceError:
            return

        pending_chunks = []
        for chunk in chunks:
            chunk_text = (chunk.get("chunk_text") or "").strip()
            if not chunk_text:
                continue
            if (chunk.get("embedding_vector") or "").strip() and chunk.get("embedding_model") == embedding_service.model_name:
                continue
            pending_chunks.append(chunk)

        if not pending_chunks:
            return

        batch_size = 12
        for start in range(0, len(pending_chunks), batch_size):
            batch = pending_chunks[start:start + batch_size]
            try:
                vectors = embedding_service.embed_texts([chunk["chunk_text"] for chunk in batch])
            except EmbeddingServiceError:
                return

            for chunk, vector in zip(batch, vectors):
                vector_json = json.dumps(vector)
                EquipmentModel.update_chunk_embedding(chunk["id"], vector_json, embedding_service.model_name)
                chunk["embedding_vector"] = vector_json
                chunk["embedding_model"] = embedding_service.model_name

    @staticmethod
    def _embed_query(query_text: str) -> list[float] | None:
        """Gera embedding da consulta, quando disponivel."""
        if not query_text:
            return None

        try:
            return EmbeddingService().embed_text(query_text)
        except EmbeddingServiceError:
            return None

    @staticmethod
    def _score_lexical_match(query_text: str, query_terms: list[str], chunk_text: str) -> int:
        """Calcula um score lexical para o trecho."""
        score = 0
        if query_text and query_text in chunk_text:
            score += 25

        for term in query_terms:
            occurrences = chunk_text.count(term)
            if occurrences:
                score += 5 + (occurrences * 2)

        return score

    @staticmethod
    def _parse_embedding_vector(embedding_vector: str | list | None) -> list[float] | None:
        """Converte o embedding salvo em lista numerica."""
        if not embedding_vector:
            return None

        if isinstance(embedding_vector, list):
            return embedding_vector

        try:
            parsed = json.loads(embedding_vector)
        except (TypeError, json.JSONDecodeError):
            return None

        return parsed if isinstance(parsed, list) else None

    @staticmethod
    def _cosine_similarity(query_vector: list[float] | None, chunk_vector: list[float] | None) -> float:
        """Calcula similaridade por cosseno entre consulta e trecho."""
        if not query_vector or not chunk_vector or len(query_vector) != len(chunk_vector):
            return 0.0

        query_array = np.array(query_vector, dtype=float)
        chunk_array = np.array(chunk_vector, dtype=float)
        denominator = np.linalg.norm(query_array) * np.linalg.norm(chunk_array)
        if denominator <= 0:
            return 0.0

        return float(np.dot(query_array, chunk_array) / denominator)

    @staticmethod
    def _store_equipment_documents(user_id: int, equipment_id: int, uploaded_files: list, progress_callback=None) -> tuple[int, int]:
        """Salva arquivos e indexa os documentos vinculados ao equipamento."""
        equipment_dir = EquipmentService._get_equipment_directory(user_id, equipment_id)
        equipment_dir.mkdir(parents=True, exist_ok=True)

        indexed_document_count = 0
        indexed_chunk_count = 0
        total_files = len(uploaded_files)
        for file_index, uploaded_file in enumerate(uploaded_files, start=1):
            file_name = Path(uploaded_file.name).name
            mime_type = EquipmentService._resolve_mime_type(uploaded_file)
            file_progress_callback = EquipmentService._build_file_progress_callback(
                progress_callback,
                file_index,
                total_files,
                file_name,
            )
            if callable(file_progress_callback):
                file_progress_callback(0.02, f"Iniciando upload logico do arquivo {file_name}")
            file_bytes = uploaded_file.getvalue()
            saved_path = equipment_dir / f"{uuid4().hex}_{file_name}"
            saved_path.write_bytes(file_bytes)
            if callable(file_progress_callback):
                file_progress_callback(0.12, f"Arquivo {file_name} salvo no servidor")
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
                progress_callback=file_progress_callback,
            )
            if chunk_count > 0:
                indexed_document_count += 1
                indexed_chunk_count += chunk_count
            if callable(file_progress_callback):
                file_progress_callback(1.0, f"Arquivo {file_name} concluido")

        return indexed_document_count, indexed_chunk_count

    @staticmethod
    def _delete_equipment_records(user_id: int, equipment_id: int) -> dict:
        """Exclui registros e arquivos de um equipamento sem validar papel."""
        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Equipamento nao encontrado"}

        documents = EquipmentModel.get_documents(equipment_id)
        ChatModel.delete_equipment_conversations(equipment_id, user_id)
        EquipmentModel.delete_documents(equipment_id)

        for doc in documents:
            file_path = Path(doc["file_path"])
            if file_path.exists():
                file_path.unlink()

        equipment_dir = EquipmentService._get_equipment_directory(equipment["user_id"], equipment_id)
        if equipment_dir.exists():
            shutil.rmtree(equipment_dir, ignore_errors=True)

        deleted = EquipmentModel.delete_equipment(equipment_id, equipment["user_id"])
        if not deleted:
            return {"success": False, "message": "Nao foi possivel excluir o equipamento"}

        return {"success": True, "message": "Equipamento excluido com sucesso"}

    @staticmethod
    def _is_admin(user_id: int) -> bool:
        """Confere se o usuario e administrador."""
        user = UserModel.get_user(user_id)
        return bool(user and (user.get("role") or "").strip().lower() == "admin")

    @staticmethod
    def _build_file_progress_callback(progress_callback, file_index: int, total_files: int, file_name: str):
        """Mapeia o progresso de um arquivo para o progresso total da operacao."""
        if not callable(progress_callback):
            return None

        base_progress = (file_index - 1) / max(total_files, 1)
        progress_span = 1 / max(total_files, 1)

        def callback(file_progress: float, message: str) -> None:
            bounded_progress = min(max(file_progress, 0.0), 1.0)
            total_progress = base_progress + (bounded_progress * progress_span)
            progress_callback(
                total_progress,
                f"Arquivo {file_index}/{total_files}: {message or file_name}",
            )

        return callback
