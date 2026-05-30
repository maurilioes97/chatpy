import io
import os
import re
import time
import zipfile
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()


class GeminiServiceError(Exception):
    """Erro tratavel da integracao com Gemini."""


class GeminiService:
    """Servico de integracao com a API Gemini."""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise GeminiServiceError("GEMINI_API_KEY nao configurada no .env")

        genai.configure(api_key=api_key)
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        self.model = genai.GenerativeModel(self.model_name)

    def get_response(
        self,
        user_message: str,
        conversation_history: list | None = None,
        document: dict | None = None,
        equipment_context: str | None = None,
        knowledge_chunks: list[dict] | None = None,
        had_direct_matches: bool = False,
    ) -> str:
        """Obtem resposta do Gemini usando historico e contexto tecnico opcional."""
        try:
            has_grounding = bool(document or equipment_context or knowledge_chunks)
            if has_grounding:
                return self._get_grounded_response(
                    user_message,
                    conversation_history or [],
                    document,
                    equipment_context,
                    knowledge_chunks or [],
                    had_direct_matches,
                )

            history = self._format_history(conversation_history or [])
            chat = self.model.start_chat(history=history)
            response = chat.send_message(user_message)
            return response.text
        except GeminiServiceError:
            raise
        except Exception as exc:
            raise GeminiServiceError(self._build_friendly_error_message(str(exc))) from exc

    def _get_grounded_response(
        self,
        user_message: str,
        conversation_history: list,
        document: dict | None,
        equipment_context: str | None,
        knowledge_chunks: list[dict],
        had_direct_matches: bool,
    ) -> str:
        """Responde com base em equipamento, trechos indexados e documento extra opcional."""
        uploaded_files = []
        text_documents = []

        try:
            if document:
                mime_type = document["mime_type"]
                file_name = document["name"]
                file_bytes = document["content"]

                if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                    extracted_text = self._extract_docx_text(file_bytes)
                    if extracted_text.strip():
                        text_documents.append(f"Documento complementar {file_name}:\n{extracted_text[:120000]}")
                elif mime_type in {"application/pdf", "application/msword"}:
                    uploaded_file = self._upload_document(file_name, file_bytes, mime_type)
                    uploaded_files.append(uploaded_file)
                else:
                    raise GeminiServiceError(f"Formato de documento nao suportado: {file_name}")

            prompt = self._build_grounded_prompt(
                user_message=user_message,
                conversation_history=conversation_history,
                equipment_context=equipment_context,
                knowledge_chunks=knowledge_chunks,
                text_documents=text_documents,
                has_file_documents=bool(uploaded_files),
                had_direct_matches=had_direct_matches,
            )

            response_parts = [*uploaded_files, prompt] if uploaded_files else prompt
            response = self.model.generate_content(response_parts)
            return response.text
        finally:
            for uploaded_file in uploaded_files:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass

    def _upload_document(self, file_name: str, file_bytes: bytes, mime_type: str):
        """Envia documento temporario para o Gemini."""
        file_stream = io.BytesIO(file_bytes)
        file_stream.name = file_name
        uploaded_file = genai.upload_file(
            file_stream,
            mime_type=mime_type,
            display_name=file_name,
        )
        self._wait_for_uploaded_file(uploaded_file.name)
        return uploaded_file

    def _wait_for_uploaded_file(self, file_name: str, max_attempts: int = 12, delay_seconds: int = 2) -> None:
        """Aguarda o arquivo enviado ficar pronto para uso."""
        for _ in range(max_attempts):
            file_info = genai.get_file(file_name)
            state = getattr(file_info, "state", None)
            state_name = getattr(state, "name", str(state or ""))

            if state_name in {"ACTIVE", "SUCCEEDED", ""}:
                return
            if state_name == "FAILED":
                raise GeminiServiceError("O Gemini nao conseguiu processar o arquivo enviado.")

            time.sleep(delay_seconds)

    def _build_grounded_prompt(
        self,
        user_message: str,
        conversation_history: list,
        equipment_context: str | None,
        knowledge_chunks: list[dict],
        text_documents: list[str],
        has_file_documents: bool,
        had_direct_matches: bool,
    ) -> str:
        """Monta prompt tecnico com base em equipamento, trechos e documentos."""
        history_text = self._build_history_text(conversation_history)
        history_section = f"Historico recente:\n{history_text}\n\n" if history_text else ""
        equipment_section = f"Dados do equipamento:\n{equipment_context}\n\n" if equipment_context else ""

        chunk_lines = []
        for index, chunk in enumerate(knowledge_chunks, start=1):
            source_label = chunk.get("source_label") or "Trecho tecnico"
            file_name = chunk.get("file_name") or "Documento"
            chunk_text = (chunk.get("chunk_text") or "").strip()
            if chunk_text:
                chunk_lines.append(
                    f"[Trecho {index}] {file_name} | {source_label}\n{chunk_text}"
                )

        chunks_section = ""
        if chunk_lines:
            chunks_section = "Trechos mais relevantes dos manuais:\n" + "\n\n".join(chunk_lines) + "\n\n"

        documents_section = ""
        if text_documents:
            documents_section = "Conteudo textual de documento complementar:\n" + "\n\n".join(text_documents) + "\n\n"

        file_docs_section = ""
        if has_file_documents:
            file_docs_section = "Um arquivo complementar foi anexado a esta consulta. Considere-o na resposta.\n\n"

        retrieval_section = (
            "Foram encontrados trechos diretamente relevantes para esta pergunta.\n\n"
            if had_direct_matches
            else (
                "Nao foram encontrados trechos diretamente relevantes para esta pergunta.\n"
                "Nesse caso, use apenas o resumo de indexacao e os dados gerais do equipamento.\n"
                "Nao afirme que o manual termina nas primeiras paginas so porque poucos trechos foram mostrados.\n\n"
            )
        )

        return (
            "Voce e um assistente tecnico especializado em equipamentos e manuais industriais.\n"
            "Responda com base apenas nas informacoes do equipamento, no historico, nos trechos indexados e nos documentos fornecidos.\n"
            "Se a resposta nao estiver clara nos dados, diga isso objetivamente.\n"
            "Quando possivel, explique de forma pratica para um manutentor eletromecanico.\n"
            "Se usar os manuais como base, mencione o trecho ou a pagina de forma natural.\n\n"
            f"{history_section}"
            f"{equipment_section}"
            f"{retrieval_section}"
            f"{chunks_section}"
            f"{documents_section}"
            f"{file_docs_section}"
            f"Pergunta do manutentor: {user_message}"
        )

    def _build_history_text(self, messages: list) -> str:
        """Transforma o historico recente em texto simples para contexto adicional."""
        lines = []
        for msg in messages[-6:]:
            role = "Usuario" if msg.get("role") == "user" else "Assistente"
            content = (msg.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _extract_docx_text(self, file_bytes: bytes) -> str:
        """Extrai o texto principal de um arquivo DOCX."""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                xml_content = archive.read("word/document.xml")
        except KeyError as exc:
            raise GeminiServiceError("Arquivo DOCX invalido ou sem conteudo legivel.") from exc
        except zipfile.BadZipFile as exc:
            raise GeminiServiceError("Arquivo DOCX invalido.") from exc

        root = ET.fromstring(xml_content)
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

        trailing_paragraph = "".join(current_parts).strip()
        if trailing_paragraph:
            paragraphs.append(trailing_paragraph)

        return "\n".join(paragraphs)

    def _format_history(self, messages: list) -> list:
        """Formata o historico de mensagens para o Gemini."""
        formatted = []
        for msg in messages:
            content = (msg.get("content") or "").strip()
            if not content:
                continue

            role = "user" if msg.get("role") == "user" else "model"
            formatted.append({"role": role, "parts": [content]})
        return formatted

    def _build_friendly_error_message(self, raw_error: str) -> str:
        """Traduz erros tecnicos do Gemini para mensagens mais uteis na UI."""
        lowered_error = raw_error.lower()

        if "429" in raw_error or "quota" in lowered_error or "rate limit" in lowered_error:
            retry_delay = self._extract_retry_delay(raw_error)
            wait_hint = f" Aguarde cerca de {retry_delay} segundos e tente novamente." if retry_delay else ""
            return (
                f"Limite de uso do Gemini atingido para o modelo {self.model_name}.{wait_hint} "
                "Se isso continuar acontecendo, voce provavelmente esgotou a cota gratuita atual "
                "e vai precisar trocar de modelo na variavel GEMINI_MODEL ou revisar billing/cota da conta."
            )

        if "api key" in lowered_error or "permission denied" in lowered_error:
            return "Falha de autenticacao com o Gemini. Verifique a GEMINI_API_KEY e as permissoes da conta."

        return f"Erro ao comunicar com Gemini: {raw_error}"

    def _extract_retry_delay(self, raw_error: str) -> int | None:
        """Tenta extrair o tempo sugerido para nova tentativa."""
        patterns = [
            r"retry in\s+(\d+(?:\.\d+)?)s",
            r"retry_delay\s*\{\s*seconds:\s*(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw_error, flags=re.IGNORECASE)
            if match:
                return max(1, round(float(match.group(1))))
        return None
