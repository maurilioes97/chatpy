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
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.model = genai.GenerativeModel(self.model_name)

    def get_response(
        self,
        user_message: str,
        conversation_history: list | None = None,
        document: dict | None = None,
    ) -> str:
        """Obtem resposta do Gemini usando historico e documento opcional."""
        try:
            if document:
                return self._get_document_response(user_message, conversation_history or [], document)

            history = self._format_history(conversation_history or [])
            chat = self.model.start_chat(history=history)
            response = chat.send_message(user_message)
            return response.text
        except GeminiServiceError:
            raise
        except Exception as e:
            raise GeminiServiceError(self._build_friendly_error_message(str(e))) from e

    def _get_document_response(self, user_message: str, conversation_history: list, document: dict) -> str:
        """Responde com base em um documento anexado."""
        file_name = document["name"]
        mime_type = document["mime_type"]
        file_bytes = document["content"]
        prompt = self._build_document_prompt(user_message, conversation_history, file_name)

        if mime_type == "application/pdf":
            return self._get_pdf_response(prompt, file_name, file_bytes)

        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            extracted_text = self._extract_docx_text(file_bytes)
            return self._get_text_document_response(prompt, file_name, extracted_text)

        raise GeminiServiceError("Formato de documento nao suportado. Use PDF ou DOCX.")

    def _get_pdf_response(self, prompt: str, file_name: str, file_bytes: bytes) -> str:
        """Envia um PDF para o Gemini e devolve a resposta."""
        uploaded_file = None
        try:
            file_stream = io.BytesIO(file_bytes)
            file_stream.name = file_name
            uploaded_file = genai.upload_file(
                file_stream,
                mime_type="application/pdf",
                display_name=file_name,
            )
            self._wait_for_uploaded_file(uploaded_file.name)
            response = self.model.generate_content([uploaded_file, prompt])
            return response.text
        finally:
            if uploaded_file is not None:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass

    def _get_text_document_response(self, prompt: str, file_name: str, extracted_text: str) -> str:
        """Usa o texto extraido de um DOCX como contexto da resposta."""
        if not extracted_text.strip():
            raise GeminiServiceError(f"Nao consegui extrair texto de {file_name}.")

        full_prompt = (
            f"{prompt}\n\n"
            f"Conteudo do documento ({file_name}):\n"
            f"{extracted_text[:120000]}"
        )
        response = self.model.generate_content(full_prompt)
        return response.text

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

    def _build_document_prompt(self, user_message: str, conversation_history: list, file_name: str) -> str:
        """Monta o prompt com instrucao para responder com base no documento."""
        history_text = self._build_history_text(conversation_history)
        history_section = f"Historico recente:\n{history_text}\n\n" if history_text else ""

        return (
            "Voce vai responder com base no documento anexado.\n"
            "Use o conteudo do documento como fonte principal.\n"
            "Se a resposta nao estiver no documento, diga isso claramente.\n"
            "Quando fizer sentido, cite trechos ou secoes relevantes de forma resumida.\n\n"
            f"{history_section}"
            f"Documento anexado: {file_name}\n"
            f"Pergunta do usuario: {user_message}"
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
