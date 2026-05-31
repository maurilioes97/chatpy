import mimetypes
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.chat_model import ChatModel
from models.equipment_model import EquipmentModel
from models.user_model import UserModel
from utils.config import EQUIPMENT_FILES_DIR
from utils.document_processing import extract_docx_text, extract_pdf_pages, normalize_text


class EquipmentService:
    """Servico de logica de provas, gabaritos e materiais."""

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
    STOPWORDS = {
        "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
        "um", "uma", "uns", "umas", "para", "por", "com", "sem", "sobre", "que", "como", "qual",
        "quais", "onde", "quando", "porque", "porquê", "ser", "estar", "esta", "esse", "essa",
        "isso", "isto", "ele", "ela", "eles", "elas", "se", "ao", "aos", "à", "às", "ou", "mais",
        "menos", "muito", "muita", "manual", "maquina", "equipamento", "prova", "gabarito", "concurso",
    }
    KNOWLEDGE_SEARCH_DEFAULT_LIMIT = 8
    KNOWLEDGE_SEARCH_MAX_CONTEXT_CHARS = 14000
    KNOWLEDGE_SEARCH_NEIGHBOR_WINDOW = 1
    MAX_REASONABLE_QUESTION_NUMBER = 120

    @staticmethod
    def register_equipment(
        user_id: int,
        name: str,
        description: str,
        exam_file,
        answer_key_file,
        supporting_files: list | None = None,
        progress_callback=None,
    ) -> dict:
        """Cadastra uma prova com gabarito e materiais opcionais."""
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem cadastrar provas"}

        normalized_name = (name or "").strip()
        normalized_description = (description or "").strip()
        file_entries_result = EquipmentService._build_study_file_entries(
            exam_file,
            answer_key_file,
            supporting_files=supporting_files,
            require_primary_documents=True,
        )
        if not file_entries_result["success"]:
            return file_entries_result

        valid_files = file_entries_result["entries"]

        if not normalized_name:
            return {"success": False, "message": "Informe o nome da prova"}

        invalid_entry = next(
            (
                entry for entry in valid_files
                if not EquipmentService._resolve_mime_type(entry["file"])
            ),
            None,
        )
        if invalid_entry:
            return {"success": False, "message": f"Formato nao suportado para {invalid_entry['file'].name}"}

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
            return {"success": False, "message": f"Erro ao salvar os arquivos da prova: {str(exc)}"}

        message = "Prova cadastrada com sucesso."
        if indexed_document_count:
            message += f" {indexed_document_count} arquivo(s) indexado(s) em {indexed_chunk_count} trecho(s)."
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
    def add_equipment_documents(
        user_id: int,
        equipment_id: int,
        exam_file=None,
        answer_key_file=None,
        supporting_files: list | None = None,
        progress_callback=None,
    ) -> dict:
        """Adiciona novos arquivos a uma prova existente."""
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem adicionar arquivos"}

        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Prova nao encontrada"}

        file_entries_result = EquipmentService._build_study_file_entries(
            exam_file,
            answer_key_file,
            supporting_files=supporting_files,
            require_primary_documents=False,
        )
        if not file_entries_result["success"]:
            return file_entries_result

        valid_files = file_entries_result["entries"]

        invalid_entry = next(
            (
                entry for entry in valid_files
                if not EquipmentService._resolve_mime_type(entry["file"])
            ),
            None,
        )
        if invalid_entry:
            return {"success": False, "message": f"Formato nao suportado para {invalid_entry['file'].name}"}

        try:
            indexed_document_count, indexed_chunk_count = EquipmentService._store_equipment_documents(
                user_id=user_id,
                equipment_id=equipment_id,
                uploaded_files=valid_files,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            return {"success": False, "message": f"Erro ao salvar arquivos: {str(exc)}"}

        message = f"{len(valid_files)} arquivo(s) adicionado(s) a prova."
        if indexed_document_count:
            message += f" {indexed_document_count} arquivo(s) indexado(s) em {indexed_chunk_count} trecho(s)."
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
        """Lista provas visiveis para o usuario."""
        equipments = EquipmentModel.get_user_equipments()
        return {"success": True, "equipments": equipments, "total": len(equipments)}

    @staticmethod
    def update_equipment(user_id: int, equipment_id: int, name: str, description: str) -> dict:
        """Atualiza os dados principais de uma prova."""
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem editar provas"}

        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Prova nao encontrada"}

        normalized_name = (name or "").strip()
        normalized_description = (description or "").strip()

        if not normalized_name:
            return {"success": False, "message": "Informe o nome da prova"}

        updated = EquipmentModel.update_equipment(
            equipment_id,
            equipment["user_id"],
            normalized_name,
            normalized_description,
        )
        if not updated:
            return {"success": False, "message": "Nao foi possivel atualizar a prova"}

        return {"success": True, "message": "Prova atualizada com sucesso."}

    @staticmethod
    def get_equipment(equipment_id: int, user_id: int) -> dict:
        """Retorna dados de uma prova."""
        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Prova nao encontrada"}

        EquipmentService._ensure_equipment_chunks(equipment_id, user_id)
        documents = EquipmentModel.get_documents(equipment_id)
        equipment["documents"] = documents
        equipment["indexed_chunk_count"] = sum(int(doc.get("chunk_count") or 0) for doc in documents)
        return {"success": True, "equipment": equipment}

    @staticmethod
    def get_equipment_context(equipment_id: int, user_id: int) -> dict:
        """Monta contexto textual da prova."""
        result = EquipmentService.get_equipment(equipment_id, user_id)
        if not result["success"]:
            return {"success": False, "message": result["message"]}

        equipment = result["equipment"]
        exam_documents = [doc for doc in equipment["documents"] if doc.get("document_role") == "exam"]
        answer_key_documents = [doc for doc in equipment["documents"] if doc.get("document_role") == "answer_key"]
        supporting_documents = [
            doc for doc in equipment["documents"] if doc.get("document_role") not in {"exam", "answer_key"}
        ]
        document_summaries = EquipmentService._build_document_summaries(equipment["documents"])
        context_lines = [
            f"Prova: {equipment['name']}",
            f"Contexto da prova: {equipment['description'] or 'Nao informado.'}",
        ]
        if exam_documents:
            context_lines.append("Arquivos da prova: " + ", ".join(doc["file_name"] for doc in exam_documents))
        if answer_key_documents:
            context_lines.append("Gabaritos cadastrados: " + ", ".join(doc["file_name"] for doc in answer_key_documents))
        if supporting_documents:
            context_lines.append(
                "Materiais complementares: " + ", ".join(doc["file_name"] for doc in supporting_documents)
            )
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
    def resolve_direct_study_query(
        equipment_id: int,
        user_id: int,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Resolve consultas objetivas sobre questoes e gabaritos sem usar o LLM."""
        lookup = EquipmentService._parse_direct_study_lookup_with_history(query, conversation_history)
        if not lookup:
            return {"handled": False}

        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"handled": True, "success": False, "message": "Prova nao encontrada."}

        EquipmentService._ensure_equipment_chunks(equipment_id, user_id)
        documents = EquipmentModel.get_documents(equipment_id)
        all_chunks = EquipmentModel.get_equipment_chunks(equipment_id)
        exam_chunks = [chunk for chunk in all_chunks if chunk.get("document_role") == "exam"]
        answer_key_chunks = [chunk for chunk in all_chunks if chunk.get("document_role") == "answer_key"]
        exam_text = EquipmentService._merge_chunk_texts(exam_chunks)
        answer_key_text = EquipmentService._merge_chunk_texts(answer_key_chunks)
        filtered_answer_key_text = EquipmentService._extract_relevant_answer_key_text(
            answer_key_text,
            exam_text,
            equipment.get("name", ""),
        )
        question_number = lookup["question_number"]
        question_block = None
        answer_value = None

        if lookup["type"] in {"question_text", "question_and_answer_key", "explanation"}:
            question_block = EquipmentService._extract_question_block_from_chunks(
                exam_chunks,
                question_number,
            ) or EquipmentService._extract_question_block(
                exam_text,
                question_number,
            )
            if not question_block or EquipmentService._looks_incomplete_question_block(question_block):
                fallback_question_block = EquipmentService._extract_question_block_from_source_documents(
                    documents,
                    question_number,
                )
                if fallback_question_block and (
                    not question_block or len(fallback_question_block) > len(question_block)
                ):
                    question_block = fallback_question_block

        if lookup["type"] in {"question_and_answer_key", "answer_key", "explanation"}:
            answer_value = EquipmentService._extract_answer_key_value(
                filtered_answer_key_text,
                question_number,
            )

        if lookup["type"] == "explanation":
            requested_option = EquipmentService._extract_requested_option(query)
            explanation_context = EquipmentService._build_explanation_context(
                question_number,
                question_block,
                answer_value,
                requested_option=requested_option,
            )
            if explanation_context:
                if requested_option:
                    rewritten_query = (
                        f"Explique, com base na prova e no gabarito, por que a alternativa {requested_option} "
                        f"da questao {question_number} esta "
                        f"{'correta' if answer_value and requested_option == answer_value else 'errada'}."
                        " Compare essa alternativa com o que o enunciado pede e, se houver gabarito identificado, "
                        "mostre por que ela difere da alternativa oficial. Nao invente nada que nao esteja sustentado pelo material."
                    )
                else:
                    rewritten_query = (
                        f"Explique, com base na prova e no gabarito, por que a resposta da questao {question_number} "
                        f"{'(' + answer_value + ')' if answer_value else ''} esta certa ou errada. "
                        "Aponte o raciocinio das afirmativas e das alternativas, sem inventar nada que nao esteja sustentado pelo material."
                    )
                rewritten_query = rewritten_query.replace("  ", " ").strip()
                return {
                    "handled": False,
                    "resolved_question_number": question_number,
                    "resolved_context_text": explanation_context,
                    "rewritten_query": rewritten_query,
                }

        if lookup["type"] in {"question_text", "question_and_answer_key"}:
            if not question_block and lookup["type"] == "question_and_answer_key" and answer_value:
                return {
                    "handled": True,
                    "success": True,
                    "response": (
                        f"Nao consegui localizar o texto exato da questao {lookup['question_number']} no arquivo da prova, "
                        f"mas encontrei o gabarito: {answer_value}."
                    ),
                }

            if not question_block:
                return {
                    "handled": True,
                    "success": True,
                    "response": (
                        f"Nao consegui localizar o texto exato da questao {lookup['question_number']} "
                        "no arquivo da prova."
                    ),
                }

            response = {
                "handled": True,
                "success": True,
                "response": (
                    f"Questao {lookup['question_number']} encontrada no arquivo da prova:\n\n"
                    f"{EquipmentService._format_question_block_for_display(question_block)}"
                ),
            }

            if answer_value:
                response["response"] += f"\n\nGabarito da questao {lookup['question_number']}: {answer_value}"

            return response

        if lookup["type"] == "answer_key":
            answer_value = EquipmentService._extract_answer_key_value(
                filtered_answer_key_text,
                lookup["question_number"],
            )
            if not answer_value:
                return {
                    "handled": True,
                    "success": True,
                    "response": (
                        f"Nao consegui localizar o gabarito da questao {lookup['question_number']} "
                        "no arquivo de gabarito."
                    ),
                }

            return {
                "handled": True,
                "success": True,
                "response": f"Gabarito da questao {lookup['question_number']}: {answer_value}",
            }

        return {"handled": False}

    @staticmethod
    def search_equipment_knowledge(equipment_id: int, user_id: int, query: str, limit: int | None = None) -> dict:
        """Seleciona os trechos mais relevantes da prova para a pergunta atual."""
        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Prova nao encontrada", "chunks": []}

        EquipmentService._ensure_equipment_chunks(equipment_id, user_id)
        all_chunks = EquipmentModel.get_equipment_chunks(equipment_id)
        if not all_chunks:
            return {"success": True, "chunks": [], "total_indexed_chunks": 0}

        effective_limit = max(1, min(limit or EquipmentService.KNOWLEDGE_SEARCH_DEFAULT_LIMIT, 12))
        ranked_chunks, had_direct_matches = EquipmentService._rank_chunks(
            all_chunks,
            query,
            effective_limit,
        )

        return {
            "success": True,
            "chunks": ranked_chunks,
            "total_indexed_chunks": len(all_chunks),
            "selected_chunk_count": len(ranked_chunks),
            "had_direct_matches": had_direct_matches,
        }

    @staticmethod
    def delete_equipment(user_id: int, equipment_id: int) -> dict:
        """Exclui prova, arquivos e conversas associadas."""
        if not EquipmentService._is_admin(user_id):
            return {"success": False, "message": "Apenas administradores podem excluir provas"}

        return EquipmentService._delete_equipment_records(user_id, equipment_id)

    @staticmethod
    def delete_user_equipments(user_id: int) -> None:
        """Exclui todas as provas e arquivos de um usuario."""
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
        for index, chunk in enumerate(extracted_chunks, start=1):
            EquipmentModel.add_document_chunk(
                document_id=document_id,
                equipment_id=equipment_id,
                chunk_index=index,
                chunk_text=chunk["text"],
                source_label=chunk["source_label"],
                extraction_method=chunk.get("extraction_method", "text"),
            )

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
    def _build_document_summaries(documents: list[dict]) -> list[str]:
        """Cria um resumo da cobertura dos documentos indexados."""
        summaries = []
        for document in documents:
            role_label = EquipmentService._describe_document_role(document.get("document_role")).rstrip(":")
            page_start, page_end = EquipmentService._extract_page_range_for_document(document["id"])
            chunk_count = int(document.get("chunk_count") or 0)
            if page_start is not None and page_end is not None:
                summaries.append(
                    f"- {role_label} {document['file_name']}: {chunk_count} trecho(s), cobrindo da pagina {page_start} ate a pagina {page_end}."
                )
            elif chunk_count > 0:
                summaries.append(
                    f"- {role_label} {document['file_name']}: {chunk_count} trecho(s) indexados."
                )
            else:
                summaries.append(
                    f"- {role_label} {document['file_name']}: sem trechos textuais indexados."
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
    def _parse_direct_study_lookup(query: str) -> dict | None:
        """Identifica pedidos objetivos como texto da questao ou gabarito."""
        return EquipmentService._parse_direct_study_lookup_with_history(query)

    @staticmethod
    def _parse_direct_study_lookup_with_history(query: str, conversation_history: list[dict] | None = None) -> dict | None:
        """Identifica pedidos objetivos, com fallback para o contexto recente do chat."""
        normalized = EquipmentService._normalize_lookup_text(query or "")
        if not normalized:
            return None

        question_number = EquipmentService._extract_question_number_from_query(normalized)
        shorthand_question_number = EquipmentService._extract_shorthand_question_number(normalized)
        recent_question_number = EquipmentService._extract_recent_question_number(conversation_history or [])
        asks_for_next_question = any(
            token in normalized
            for token in {
                "proxima", "mostra a proxima", "mostre a proxima", "proxima questao", "questao seguinte",
                "seguinte", "proxima pergunta",
            }
        )

        asks_for_answer_key = any(
            token in normalized
            for token in {
                "gabarito", "resposta", "alternativa correta", "alternativa certa", "letra correta",
            }
        )
        asks_for_explanation = any(
            token in normalized
            for token in {
                "por que", "porque", "porquê", "motivo", "justifique", "justificar",
                "explique", "explica", "explicar", "fundamente", "fundamenta",
                "comente", "comentario", "comentário",
            }
        )
        asks_for_question_text = any(
            token in normalized
            for token in {
                "questao", "enunciado", "primeira questao", "segunda questao", "terceira questao",
            }
        )

        if question_number is None and asks_for_next_question and recent_question_number is not None:
            question_number = recent_question_number + 1
            asks_for_question_text = True

        if question_number is None and EquipmentService._looks_like_short_question_reference(normalized):
            question_number = shorthand_question_number if shorthand_question_number is not None else recent_question_number
            asks_for_question_text = True

        if question_number is None and EquipmentService._looks_like_short_answer_reference(normalized):
            question_number = shorthand_question_number if shorthand_question_number is not None else recent_question_number
            asks_for_answer_key = True

        if question_number is None and (asks_for_answer_key or asks_for_question_text):
            question_number = recent_question_number

        if question_number is None:
            return None

        if asks_for_explanation:
            return {"type": "explanation", "question_number": question_number}

        if asks_for_answer_key and asks_for_question_text:
            return {"type": "question_and_answer_key", "question_number": question_number}

        if asks_for_answer_key and not asks_for_question_text:
            return {"type": "answer_key", "question_number": question_number}

        if asks_for_question_text:
            return {"type": "question_text", "question_number": question_number}

        return None

    @staticmethod
    def _extract_recent_question_number(conversation_history: list[dict]) -> int | None:
        """Tenta descobrir a ultima questao referenciada na conversa."""
        for message in reversed(conversation_history or []):
            content = EquipmentService._normalize_lookup_text(message.get("content") or "")
            if not content:
                continue

            direct_number = EquipmentService._extract_question_number_from_query(content)
            if direct_number is not None:
                return direct_number

            assistant_match = re.search(r"\bquestao\s+0*(\d{1,3})\b", content, flags=re.IGNORECASE)
            if assistant_match:
                return int(assistant_match.group(1))

        return None

    @staticmethod
    def _looks_like_short_question_reference(text: str) -> bool:
        """Detecta follow-ups curtos como 'e a 2?' ou 'mostra ela'."""
        return any(
            token in text
            for token in {
                "e a", "e a questao", "e ela", "mostra ela", "mostra a questao", "mostre a questao",
            }
        )

    @staticmethod
    def _looks_like_short_answer_reference(text: str) -> bool:
        """Detecta follow-ups curtos como 'e o gabarito dela?'."""
        return any(
            token in text
            for token in {
                "gabarito dela", "gabarito dessa", "gabarito desta", "resposta dela", "resposta dessa",
                "resposta desta", "e a resposta", "e o gabarito", "qual a resposta", "qual o gabarito",
            }
        )

    @staticmethod
    def _extract_shorthand_question_number(text: str) -> int | None:
        """Extrai numeros de referencias curtas como 'e a 2?'."""
        match = re.search(r"\b(?:e\s+a|e\s+o|mostra\s+a|mostre\s+a|da|de|da\s+questao)\s+0*(\d{1,3})\b", text)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_question_number_from_query(text: str) -> int | None:
        """Extrai o numero da questao a partir da pergunta do usuario."""
        number_match = re.search(r"\bquestao\s*(?:numero\s*)?0*(\d{1,3})\b", text, flags=re.IGNORECASE)
        if number_match:
            return int(number_match.group(1))

        standalone_number_match = re.search(r"\b(?:da|de|na|a)?\s*0*(\d{1,3})\b", text)
        if standalone_number_match and any(token in text for token in {"gabarito", "questao", "enunciado"}):
            return int(standalone_number_match.group(1))

        ordinal_map = {
            "primeira": 1,
            "segunda": 2,
            "terceira": 3,
            "quarta": 4,
            "quinta": 5,
            "sexta": 6,
            "setima": 7,
            "sétima": 7,
            "oitava": 8,
            "nona": 9,
            "decima": 10,
            "décima": 10,
        }
        for ordinal, number in ordinal_map.items():
            if ordinal in text:
                return number

        return None

    @staticmethod
    def _normalize_lookup_text(text: str) -> str:
        """Normaliza texto para comparacoes tolerantes a acentos."""
        normalized = EquipmentService._normalize_text(text or "").lower()
        ascii_text = unicodedata.normalize("NFD", normalized)
        ascii_text = "".join(char for char in ascii_text if unicodedata.category(char) != "Mn")
        return ascii_text

    @staticmethod
    def _merge_chunk_texts(chunks: list[dict]) -> str:
        """Une chunks sequenciais minimizando duplicacao por sobreposicao."""
        merged_text = ""
        for chunk in chunks:
            chunk_text = EquipmentService._normalize_text(chunk.get("chunk_text") or "")
            if not chunk_text:
                continue
            merged_text = EquipmentService._append_text_with_overlap(merged_text, chunk_text)

        return merged_text.strip()

    @staticmethod
    def _append_text_with_overlap(base_text: str, next_text: str) -> str:
        """Concatena textos removendo sobreposicao entre o fim e o inicio."""
        base_text = base_text or ""
        next_text = next_text or ""
        if not next_text:
            return base_text
        if not base_text:
            return next_text

        max_overlap = min(len(base_text), len(next_text), EquipmentService.CHUNK_OVERLAP + 80)
        overlap_size = 0
        for size in range(max_overlap, 30, -1):
            if base_text.endswith(next_text[:size]):
                overlap_size = size
                break

        separator = "" if overlap_size > 0 else "\n"
        return base_text + separator + next_text[overlap_size:]

    @staticmethod
    def _rank_chunks(chunks: list[dict], query: str, limit: int) -> tuple[list[dict], bool]:
        """Pontua trechos por relevancia lexical e preserva vizinhos imediatos."""
        if not chunks:
            return [], False

        profile = EquipmentService._build_chunk_query_profile(query)
        scored_chunks = []
        for index, chunk in enumerate(chunks):
            score = EquipmentService._score_chunk_relevance(chunk, profile)
            scored_chunks.append({"index": index, "score": score})

        scored_chunks.sort(key=lambda item: (item["score"], -item["index"]), reverse=True)
        positive_hits = [item for item in scored_chunks if item["score"] > 0]
        if not positive_hits:
            return EquipmentService._select_representative_chunks(chunks, limit), False

        selected_indexes = set()
        seed_count = max(1, min(len(positive_hits), max(2, limit // 2)))
        for item in positive_hits[:seed_count]:
            EquipmentService._add_chunk_with_neighbors(selected_indexes, chunks, item["index"])

        for item in positive_hits[seed_count:]:
            if len(selected_indexes) >= limit:
                break
            selected_indexes.add(item["index"])

        ordered_indexes = [index for index in range(len(chunks)) if index in selected_indexes]
        selected_chunks = []
        total_chars = 0
        min_chunk_target = min(limit, 3)

        for index in ordered_indexes:
            chunk = chunks[index]
            chunk_text = (chunk.get("chunk_text") or "").strip()
            if not chunk_text:
                continue

            if (
                selected_chunks
                and total_chars + len(chunk_text) > EquipmentService.KNOWLEDGE_SEARCH_MAX_CONTEXT_CHARS
                and len(selected_chunks) >= min_chunk_target
            ):
                break

            selected_chunks.append(chunk)
            total_chars += len(chunk_text)

            if len(selected_chunks) >= limit:
                break

        if not selected_chunks:
            return EquipmentService._select_representative_chunks(chunks, limit), False

        return selected_chunks, True

    @staticmethod
    def _build_chunk_query_profile(query: str) -> dict:
        """Resume a consulta em sinais simples para ranquear os trechos."""
        normalized_query = EquipmentService._normalize_lookup_text(query or "")
        question_number = EquipmentService._extract_question_number_from_query(normalized_query)
        numbers = {int(number) for number in re.findall(r"\b\d{1,3}\b", normalized_query)}
        if question_number:
            numbers.add(question_number)

        return {
            "normalized_query": normalized_query,
            "tokens": EquipmentService._extract_lookup_tokens(normalized_query),
            "numbers": numbers,
            "mentions_answer_key": any(
                marker in normalized_query
                for marker in ("gabarito", "resposta correta", "resposta oficial", "alternativa correta", "letra ")
            ),
            "mentions_question_text": any(
                marker in normalized_query
                for marker in ("questao", "enunciado", "alternativa", "texto da questao")
            ),
            "mentions_supporting_context": any(
                marker in normalized_query
                for marker in ("resumo", "simulado", "assunto", "tema", "explic", "conteudo")
            ),
        }

    @staticmethod
    def _score_chunk_relevance(chunk: dict, profile: dict) -> int:
        """Calcula uma pontuacao lexical simples para cada trecho."""
        chunk_text = (chunk.get("chunk_text") or "").strip()
        if not chunk_text:
            return -1

        source_label = chunk.get("source_label") or ""
        file_name = chunk.get("file_name") or ""
        normalized_source_label = EquipmentService._normalize_lookup_text(source_label)
        normalized_file_name = EquipmentService._normalize_lookup_text(file_name)
        normalized_haystack = EquipmentService._normalize_lookup_text(
            f"{file_name}\n{source_label}\n{chunk_text}"
        )
        chunk_tokens = EquipmentService._extract_lookup_tokens(normalized_haystack)
        overlap_tokens = profile["tokens"] & chunk_tokens
        score = len(overlap_tokens) * 6

        if profile["normalized_query"] and profile["normalized_query"] in normalized_haystack:
            score += 16

        for token in overlap_tokens:
            if token in normalized_source_label:
                score += 2
            if token in normalized_file_name:
                score += 1

        for number in profile["numbers"]:
            if re.search(rf"(?<!\d)0*{number}(?!\d)", normalized_haystack):
                score += 12

        document_role = chunk.get("document_role")
        if profile["mentions_answer_key"]:
            if document_role == "answer_key":
                score += 8
            elif document_role == "exam":
                score += 2

        if profile["mentions_question_text"] and document_role == "exam":
            score += 6

        if profile["mentions_supporting_context"] and document_role == "supporting":
            score += 4

        if not profile["tokens"]:
            if document_role == "exam":
                score += 2
            elif document_role == "answer_key":
                score += 1

        return score

    @staticmethod
    def _add_chunk_with_neighbors(selected_indexes: set[int], chunks: list[dict], index: int) -> None:
        """Inclui um trecho relevante e seus vizinhos do mesmo documento."""
        document_id = chunks[index].get("document_id")
        start = max(0, index - EquipmentService.KNOWLEDGE_SEARCH_NEIGHBOR_WINDOW)
        end = min(len(chunks) - 1, index + EquipmentService.KNOWLEDGE_SEARCH_NEIGHBOR_WINDOW)

        for candidate_index in range(start, end + 1):
            if chunks[candidate_index].get("document_id") != document_id:
                continue
            selected_indexes.add(candidate_index)

    @staticmethod
    def _select_representative_chunks(chunks: list[dict], limit: int) -> list[dict]:
        """Monta um fallback enxuto com exemplos da prova, gabarito e apoio."""
        selected_chunks = []
        seen_document_ids = set()
        seen_chunk_ids = set()
        total_chars = 0

        for document_role in ("exam", "answer_key", "supporting"):
            for chunk in chunks:
                document_id = chunk.get("document_id")
                if chunk.get("document_role") != document_role or document_id in seen_document_ids:
                    continue

                chunk_text = (chunk.get("chunk_text") or "").strip()
                if not chunk_text:
                    continue

                selected_chunks.append(chunk)
                seen_document_ids.add(document_id)
                seen_chunk_ids.add(chunk.get("id"))
                total_chars += len(chunk_text)
                break

            if len(selected_chunks) >= limit or total_chars >= EquipmentService.KNOWLEDGE_SEARCH_MAX_CONTEXT_CHARS:
                return selected_chunks[:limit]

        for chunk in chunks:
            if len(selected_chunks) >= limit or total_chars >= EquipmentService.KNOWLEDGE_SEARCH_MAX_CONTEXT_CHARS:
                break

            chunk_identifier = chunk.get("id")
            if chunk_identifier in seen_chunk_ids:
                continue

            chunk_text = (chunk.get("chunk_text") or "").strip()
            if not chunk_text:
                continue

            selected_chunks.append(chunk)
            seen_chunk_ids.add(chunk_identifier)
            total_chars += len(chunk_text)

        return selected_chunks[:limit]

    @staticmethod
    def _extract_question_block(exam_text: str, question_number: int) -> str | None:
        """Extrai o bloco textual de uma questao numerada."""
        if not exam_text.strip():
            return None

        searchable_text = EquipmentService._isolate_exam_questions_text(exam_text)
        matches = EquipmentService._find_question_markers(searchable_text)
        if not matches:
            return None

        best_index = None
        best_score = -1
        numbered_matches = [int(match.group(1)) for match in matches]
        for index, number in enumerate(numbered_matches):
            if number != question_number:
                continue

            score = 0
            previous_number = numbered_matches[index - 1] if index > 0 else None
            next_number = numbered_matches[index + 1] if index + 1 < len(numbered_matches) else None
            next_next_number = numbered_matches[index + 2] if index + 2 < len(numbered_matches) else None

            if previous_number == question_number - 1:
                score += 2
            if next_number == question_number + 1:
                score += 3
            if next_next_number == question_number + 2:
                score += 1
            if question_number == 1 and next_number == 2:
                score += 3

            if score > best_score:
                best_score = score
                best_index = index

        if best_index is None:
            return None

        start = matches[best_index].start()
        end = matches[best_index + 1].start() if best_index + 1 < len(matches) else len(searchable_text)
        question_block = searchable_text[start:end].strip()
        return EquipmentService._clean_question_block_artifacts(question_block)

        return None

    @staticmethod
    def _extract_question_block_from_chunks(exam_chunks: list[dict], question_number: int) -> str | None:
        """Extrai uma questao percorrendo os chunks sequenciais da prova."""
        if not exam_chunks:
            return None

        chunk_texts = [EquipmentService._normalize_text(chunk.get("chunk_text") or "") for chunk in exam_chunks]

        occurrences = []
        for chunk_index, chunk_text in enumerate(chunk_texts):
            for match in EquipmentService._find_question_markers(chunk_text):
                occurrences.append(
                    {
                        "chunk_index": chunk_index,
                        "start": match.start(),
                        "number": int(match.group(1)),
                    }
                )

        if not occurrences:
            return None

        candidate_indexes = [index for index, occurrence in enumerate(occurrences) if occurrence["number"] == question_number]
        if not candidate_indexes:
            return None

        best_occurrence_index = None
        best_score = -1
        for occurrence_index in candidate_indexes:
            score = 0
            previous_number = occurrences[occurrence_index - 1]["number"] if occurrence_index > 0 else None
            next_number = occurrences[occurrence_index + 1]["number"] if occurrence_index + 1 < len(occurrences) else None
            next_next_number = occurrences[occurrence_index + 2]["number"] if occurrence_index + 2 < len(occurrences) else None

            if previous_number == question_number - 1:
                score += 2
            if next_number == question_number + 1:
                score += 4
            if next_next_number == question_number + 2:
                score += 1
            if question_number == 1 and next_number == 2:
                score += 4

            if score > best_score:
                best_score = score
                best_occurrence_index = occurrence_index

        if best_occurrence_index is None:
            return None

        start_occurrence = occurrences[best_occurrence_index]
        end_occurrence = None
        for occurrence in occurrences[best_occurrence_index + 1:]:
            if occurrence["number"] > question_number:
                end_occurrence = occurrence
                break

        assembled_text = ""
        for chunk_index in range(start_occurrence["chunk_index"], len(chunk_texts)):
            chunk_text = chunk_texts[chunk_index]
            if not chunk_text:
                continue

            if chunk_index == start_occurrence["chunk_index"]:
                segment = chunk_text[start_occurrence["start"]:]
            else:
                segment = chunk_text

            if end_occurrence and chunk_index == end_occurrence["chunk_index"]:
                if chunk_index == start_occurrence["chunk_index"]:
                    segment = chunk_text[start_occurrence["start"]:end_occurrence["start"]]
                else:
                    segment = segment[:end_occurrence["start"]]

            assembled_text = EquipmentService._append_text_with_overlap(assembled_text, segment)

            if end_occurrence and chunk_index == end_occurrence["chunk_index"]:
                break

        cleaned_text = EquipmentService._clean_question_block_artifacts(assembled_text.strip())
        return cleaned_text or None

    @staticmethod
    def _find_question_markers(text: str) -> list[re.Match]:
        """Localiza inicios plausiveis de questoes sem confundir numeros internos ou cabecalhos."""
        marker_pattern = re.compile(
            r"(?<!\d)(?:(?i:quest[aã]o)\s*)?0*(\d{1,3})(?=\s+(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ]|\())"
        )
        matches = []
        for match in marker_pattern.finditer(text or ""):
            number = int(match.group(1))
            if number > EquipmentService.MAX_REASONABLE_QUESTION_NUMBER:
                continue
            matches.append(match)
        return matches

    @staticmethod
    def _clean_question_block_artifacts(question_block: str) -> str:
        """Remove cabecalhos recorrentes do PDF quando a questao atravessa mais de uma pagina."""
        cleaned_text = EquipmentService._normalize_text(question_block or "")
        if not cleaned_text:
            return ""

        artifact_patterns = [
            r"pcimarkpci\s+[^\s]+\s+www\.pciconcursos\.com\.br",
            r"INSTITUTO\s+ADM&TEC\s+\|\s+.*?-\s+P[aá]gina\s+\d+\s+de\s+\d+\s+v\.\d+/\d+",
            r"AGENTE\s+COMUNIT[ÁA]RIO\s+\(A\)\s+DE\s+SA[ÚU]DE\s*-\s*P[aá]gina\s+\d+\s+de\s+\d+",
        ]
        for pattern in artifact_patterns:
            cleaned_text = re.sub(pattern, " ", cleaned_text, flags=re.IGNORECASE)

        return EquipmentService._normalize_text(cleaned_text)

    @staticmethod
    def _build_explanation_context(
        question_number: int,
        question_block: str | None,
        answer_value: str | None,
        requested_option: str | None = None,
    ) -> str:
        """Monta um contexto curto e objetivo para a IA explicar o gabarito."""
        context_lines = [f"Questao em foco: {question_number}"]
        if question_block:
            context_lines.append("Enunciado da questao:")
            context_lines.append(EquipmentService._format_question_block_for_display(question_block))
        if answer_value:
            context_lines.append(f"Gabarito oficial identificado: {answer_value}")
        if requested_option:
            context_lines.append(f"Alternativa mencionada pelo usuario: {requested_option}")
        if len(context_lines) <= 1:
            return ""
        return "\n".join(context_lines).strip()

    @staticmethod
    def _format_question_block_for_display(question_block: str) -> str:
        """Organiza enunciado e alternativas em um formato mais legivel."""
        normalized = EquipmentService._normalize_text(question_block or "")
        if not normalized:
            return ""

        option_pattern = re.compile(r"(?i)(?<!\w)([a-e])\)")
        matches = list(option_pattern.finditer(normalized))
        if not matches:
            return normalized

        enunciado = normalized[:matches[0].start()].strip()
        alternatives = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            alternative_text = normalized[start:end].strip()
            if alternative_text:
                alternatives.append(alternative_text)

        lines = []
        if enunciado:
            lines.append(enunciado)
        if alternatives:
            lines.append("")
            lines.extend(alternatives)

        return "\n".join(lines).strip()

    @staticmethod
    def _extract_requested_option(query: str) -> str | None:
        """Extrai a alternativa citada pelo usuario, como 'letra C' ou 'alternativa b'."""
        normalized = EquipmentService._normalize_lookup_text(query or "")
        if not normalized:
            return None

        patterns = [
            r"\bletra\s+([a-e])\b",
            r"\balternativa\s+([a-e])\b",
            r"\bopcao\s+([a-e])\b",
            r"\bopção\s+([a-e])\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None

    @staticmethod
    def _extract_question_block_from_source_documents(documents: list[dict], question_number: int) -> str | None:
        """Tenta localizar a questao diretamente no arquivo original da prova."""
        for document in documents:
            if document.get("document_role") != "exam":
                continue

            file_path = Path(document.get("file_path") or "")
            if not file_path.exists():
                continue

            try:
                file_bytes = file_path.read_bytes()
            except OSError:
                continue

            file_type = document.get("file_type") or ""
            if file_type == "application/pdf":
                page_texts = [page.get("text", "") for page in extract_pdf_pages(file_bytes)]
                source_text = "\n\n".join(text for text in page_texts if text)
            elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                source_text = extract_docx_text(file_bytes)
            else:
                continue

            question_block = EquipmentService._extract_question_block(source_text, question_number)
            if question_block:
                return question_block

        return None

    @staticmethod
    def _looks_incomplete_question_block(question_block: str) -> bool:
        """Sinaliza quando o texto da questao parece ter sido cortado no meio."""
        normalized = EquipmentService._normalize_text(question_block or "")
        if not normalized:
            return True

        trailing_tokens = {
            "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "para",
            "por", "com", "sem", "mais", "menos", "ao", "aos", "na", "nas", "no", "nos",
        }
        tokens = re.findall(r"[a-z0-9áàâãéêíóôõúç]+", normalized.lower())
        if tokens and tokens[-1] in trailing_tokens:
            return True

        if normalized[-1] in ".!?)]":
            return False

        has_alternatives = bool(re.search(r"\b[a-e]\)", normalized, flags=re.IGNORECASE))
        has_statement_sequence = bool(re.search(r"\b(?:i|ii|iii|iv|v)\.\s", normalized, flags=re.IGNORECASE))
        return has_alternatives or has_statement_sequence

    @staticmethod
    def _isolate_exam_questions_text(exam_text: str) -> str:
        """Remove a abertura da prova para facilitar a localizacao das questoes."""
        if not exam_text.strip():
            return ""

        marker_patterns = [
            r"quest[oõ]es?\s+de\s+1\s+a\s+\d+",
            r"conhecimentos\s+espec[ií]ficos",
            r"conhecimentos\s+gerais",
        ]
        for pattern in marker_patterns:
            match = re.search(pattern, exam_text, flags=re.IGNORECASE)
            if match:
                return exam_text[match.end():].strip()

        return exam_text

    @staticmethod
    def _extract_relevant_answer_key_text(answer_key_text: str, exam_text: str, fallback_name: str = "") -> str:
        """Filtra a secao do gabarito correspondente a prova atual."""
        if not answer_key_text.strip():
            return ""

        section_pattern = re.compile(
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç \(\)\/\-]{4,}?)\s+Quest[aã]o\s+Gabarito",
            flags=re.IGNORECASE,
        )
        matches = list(section_pattern.finditer(answer_key_text))
        if not matches:
            return answer_key_text

        reference_tokens = EquipmentService._extract_lookup_tokens(exam_text)
        reference_tokens.update(EquipmentService._extract_lookup_tokens(fallback_name))

        best_index = None
        best_score = -1
        for index, match in enumerate(matches):
            title = match.group(1)
            title_tokens = EquipmentService._extract_lookup_tokens(title)
            score = len(title_tokens & reference_tokens)
            if score > best_score:
                best_score = score
                best_index = index

        if best_index is not None and best_score > 0:
            start = matches[best_index].start()
            end = matches[best_index + 1].start() if best_index + 1 < len(matches) else len(answer_key_text)
            return answer_key_text[start:end].strip()

        return answer_key_text

    @staticmethod
    def _extract_lookup_tokens(text: str) -> set[str]:
        """Extrai tokens utilitarios para casar prova com secao de gabarito."""
        normalized = EquipmentService._normalize_lookup_text(text or "")
        return {
            token
            for token in re.findall(r"[a-z0-9]{4,}", normalized)
            if token not in {"questao", "gabarito", "pagina", "instituto", "admtec", "conhecimentos"}
        }

    @staticmethod
    def _extract_answer_key_value(answer_key_text: str, question_number: int) -> str | None:
        """Extrai a alternativa/resposta da questao no gabarito."""
        if not answer_key_text.strip():
            return None

        patterns = [
            rf"(?im)(?:^|\s)(?:quest[aã]o\s*)?0*{question_number}\s*[-:.)]+\s*([A-E])\b",
            rf"(?im)(?:^|\s)(?:quest[aã]o\s*)?0*{question_number}\s+([A-E])\b",
            rf"(?im)(?:^|\s)(?:quest[aã]o\s*)?0*{question_number}\s*[-:.)]+\s*([A-E0-9]{1,10})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, answer_key_text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip().upper()

        return None

    def _normalize_text(text: str) -> str:
        """Normaliza espacos em branco do texto."""
        return normalize_text(text)

    @staticmethod
    def _get_equipment_directory(user_id: int, equipment_id: int) -> Path:
        """Retorna a pasta de arquivos de uma prova."""
        return Path(EQUIPMENT_FILES_DIR) / f"user_{user_id}" / f"equipment_{equipment_id}"

    @staticmethod
    def _build_study_file_entries(
        exam_file=None,
        answer_key_file=None,
        supporting_files: list | None = None,
        require_primary_documents: bool = True,
    ) -> dict:
        """Normaliza uploads em uma lista com papeis semanticos."""
        entries = []

        if exam_file is not None:
            entries.append({"file": exam_file, "role": "exam"})
        elif require_primary_documents:
            return {"success": False, "message": "Envie o arquivo da prova"}

        if answer_key_file is not None:
            entries.append({"file": answer_key_file, "role": "answer_key"})
        elif require_primary_documents:
            return {"success": False, "message": "Envie o arquivo do gabarito"}

        for uploaded_file in supporting_files or []:
            if uploaded_file is not None:
                entries.append({"file": uploaded_file, "role": "supporting"})

        if not entries:
            return {"success": False, "message": "Selecione pelo menos um arquivo para adicionar"}

        return {"success": True, "entries": entries}

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

    def _store_equipment_documents(user_id: int, equipment_id: int, uploaded_files: list, progress_callback=None) -> tuple[int, int]:
        """Salva arquivos e indexa os documentos vinculados a prova."""
        equipment_dir = EquipmentService._get_equipment_directory(user_id, equipment_id)
        equipment_dir.mkdir(parents=True, exist_ok=True)

        indexed_document_count = 0
        indexed_chunk_count = 0
        total_files = len(uploaded_files)
        for file_index, upload_entry in enumerate(uploaded_files, start=1):
            uploaded_file = upload_entry["file"]
            document_role = upload_entry.get("role", "supporting")
            role_label = EquipmentService._describe_document_role(document_role).rstrip(":")
            file_name = Path(uploaded_file.name).name
            mime_type = EquipmentService._resolve_mime_type(uploaded_file)
            file_progress_callback = EquipmentService._build_file_progress_callback(
                progress_callback,
                file_index,
                total_files,
                file_name,
            )
            if callable(file_progress_callback):
                file_progress_callback(0.02, f"Iniciando upload do arquivo {role_label.lower()} {file_name}")
            file_bytes = uploaded_file.getvalue()
            saved_path = equipment_dir / f"{uuid4().hex}_{file_name}"
            saved_path.write_bytes(file_bytes)
            if callable(file_progress_callback):
                file_progress_callback(0.12, f"Arquivo {role_label.lower()} {file_name} salvo no servidor")
            document_id = EquipmentModel.add_document(
                equipment_id,
                file_name,
                str(saved_path),
                mime_type,
                document_role=document_role,
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
                file_progress_callback(1.0, f"Arquivo {role_label.lower()} {file_name} concluido")

        return indexed_document_count, indexed_chunk_count

    @staticmethod
    def _delete_equipment_records(user_id: int, equipment_id: int) -> dict:
        """Exclui registros e arquivos de uma prova sem validar papel."""
        equipment = EquipmentModel.get_equipment(equipment_id)
        if not equipment:
            return {"success": False, "message": "Prova nao encontrada"}

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
            return {"success": False, "message": "Nao foi possivel excluir a prova"}

        return {"success": True, "message": "Prova excluida com sucesso"}

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

    @staticmethod
    def _describe_document_role(document_role: str | None) -> str:
        """Retorna um rotulo amigavel para o papel do arquivo."""
        if document_role == "exam":
            return "Prova:"
        if document_role == "answer_key":
            return "Gabarito:"
        return "Material complementar:"
