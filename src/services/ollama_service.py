import os

import requests

from utils.document_processing import extract_docx_text, extract_pdf_text


class OllamaServiceError(Exception):
    """Erro tratavel da integracao com Ollama."""


class OllamaService:
    """Servico de integracao com a API local do Ollama."""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.model_name = os.getenv("OLLAMA_MODEL", "gemma3:4b")
        self.timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT", "180"))

    def get_response(
        self,
        user_message: str,
        conversation_history: list | None = None,
        document: dict | None = None,
        equipment_context: str | None = None,
        knowledge_chunks: list[dict] | None = None,
        had_direct_matches: bool = False,
    ) -> str:
        """Obtem resposta do Ollama usando historico e contexto tecnico opcional."""
        try:
            has_grounding = bool(document or equipment_context or knowledge_chunks)
            if has_grounding:
                prompt = self._build_grounded_prompt(
                    user_message=user_message,
                    conversation_history=conversation_history or [],
                    document=document,
                    equipment_context=equipment_context,
                    knowledge_chunks=knowledge_chunks or [],
                    had_direct_matches=had_direct_matches,
                )
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um assistente tecnico especializado em equipamentos e manuais industriais. "
                            "Responda em portugues de forma objetiva, pratica e tecnicamente util. "
                            "Priorize os documentos e dados fornecidos, mas quando houver lacunas voce pode fazer inferencias tecnicas razoaveis "
                            "com base em boas praticas e conhecimento geral de manutencao. "
                            "Sempre deixe claro quando estiver inferindo algo."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]
            else:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um assistente tecnico especializado em equipamentos e manuais industriais. "
                            "Responda em portugues de forma objetiva, pratica e tecnicamente util. "
                            "Quando faltar contexto especifico, voce pode usar conhecimento tecnico geral e boas praticas de manutencao. "
                            "Se fizer suposicoes, sinalize isso com clareza."
                        ),
                    },
                    *self._format_history(conversation_history or []),
                    {"role": "user", "content": user_message},
                ]

            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "stream": False,
                },
                timeout=self.timeout_seconds,
            )

            if response.status_code == 404:
                raise OllamaServiceError(
                    f"Modelo {self.model_name} nao encontrado no Ollama. "
                    f"Rode 'ollama pull {self.model_name}' no container ou na maquina host."
                )

            response.raise_for_status()
            response_data = response.json()
            content = ((response_data.get("message") or {}).get("content") or "").strip()
            if not content:
                raise OllamaServiceError("O Ollama respondeu sem conteudo.")

            return content
        except OllamaServiceError:
            raise
        except requests.exceptions.ConnectionError as exc:
            raise OllamaServiceError(
                f"Nao foi possivel conectar ao Ollama em {self.base_url}. "
                "Verifique se o container ou servico local esta em execucao."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaServiceError(
                f"O Ollama demorou mais do que o limite de {self.timeout_seconds} segundos para responder."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise OllamaServiceError(f"Erro HTTP ao comunicar com Ollama: {str(exc)}") from exc
        except Exception as exc:
            raise OllamaServiceError(f"Erro ao comunicar com Ollama: {str(exc)}") from exc

    def _build_grounded_prompt(
        self,
        user_message: str,
        conversation_history: list,
        document: dict | None,
        equipment_context: str | None,
        knowledge_chunks: list[dict],
        had_direct_matches: bool,
    ) -> str:
        """Monta prompt tecnico com base em equipamento, trechos e documento extra opcional."""
        history_text = self._build_history_text(conversation_history)
        history_section = f"Historico recente:\n{history_text}\n\n" if history_text else ""
        equipment_section = f"Dados do equipamento:\n{equipment_context}\n\n" if equipment_context else ""

        chunk_lines = []
        for index, chunk in enumerate(knowledge_chunks, start=1):
            source_label = chunk.get("source_label") or "Trecho tecnico"
            file_name = chunk.get("file_name") or "Documento"
            chunk_text = (chunk.get("chunk_text") or "").strip()
            if chunk_text:
                chunk_lines.append(f"[Trecho {index}] {file_name} | {source_label}\n{chunk_text}")

        chunks_section = ""
        if chunk_lines:
            chunks_section = "Trechos mais relevantes dos manuais:\n" + "\n\n".join(chunk_lines) + "\n\n"

        document_section = ""
        if document:
            extracted_text = self._extract_document_text(document)
            if extracted_text:
                document_section = (
                    f"Conteudo do documento complementar {document['name']}:\n"
                    f"{extracted_text[:120000]}\n\n"
                )

        retrieval_section = (
            "Foram encontrados trechos diretamente relevantes para esta pergunta.\n\n"
            if had_direct_matches
            else (
                "Nao foram encontrados trechos diretamente relevantes para esta pergunta.\n"
                "Nesse caso, priorize os dados gerais do equipamento e os documentos disponiveis.\n"
                "Se ainda houver lacunas, complemente com inferencias tecnicas razoaveis e boas praticas de manutencao, "
                "sem inventar dados especificos.\n"
                "Quando estiver presumindo algo, deixe isso explicito com termos como 'provavelmente', 'e possivel que' ou "
                "'uma interpretacao plausivel e'.\n\n"
            )
        )

        return (
            "Voce e um assistente tecnico especializado em equipamentos e manuais industriais.\n"
            "Priorize as informacoes do equipamento, do historico, dos trechos indexados e dos documentos fornecidos.\n"
            "Se a resposta nao estiver completamente explicita nos dados, faca a melhor interpretacao tecnica possivel com base em boas praticas.\n"
            "Voce pode complementar a resposta com conhecimento tecnico geral, desde que nao invente fatos especificos ausentes no material.\n"
            "Sempre diferencie claramente o que veio dos documentos e o que e inferencia tecnica sua.\n"
            "Quando possivel, explique de forma pratica para um manutentor eletromecanico.\n"
            "Se usar os manuais como base, mencione o trecho ou a pagina de forma natural.\n\n"
            f"{history_section}"
            f"{equipment_section}"
            f"{retrieval_section}"
            f"{chunks_section}"
            f"{document_section}"
            f"Pergunta do manutentor: {user_message}"
        )

    def _extract_document_text(self, document: dict) -> str:
        """Extrai texto do documento complementar para uso no prompt."""
        mime_type = document["mime_type"]
        file_bytes = document["content"]

        if mime_type == "application/pdf":
            return self._extract_pdf_text(file_bytes)

        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return self._extract_docx_text(file_bytes)

        if mime_type == "application/msword":
            raise OllamaServiceError(
                "Arquivos DOC nao sao suportados no modo local. Converta o documento para PDF ou DOCX."
            )

        raise OllamaServiceError(f"Formato de documento nao suportado: {document['name']}")

    def _extract_pdf_text(self, file_bytes: bytes) -> str:
        """Extrai texto de todas as paginas de um PDF."""
        try:
            return extract_pdf_text(file_bytes)
        except Exception as exc:
            raise OllamaServiceError("Nao foi possivel ler o PDF anexado.") from exc

    def _extract_docx_text(self, file_bytes: bytes) -> str:
        """Extrai o texto principal de um arquivo DOCX."""
        extracted_text = extract_docx_text(file_bytes)
        if not extracted_text:
            raise OllamaServiceError("Arquivo DOCX invalido ou sem conteudo legivel.")
        return extracted_text

    def _build_history_text(self, messages: list) -> str:
        """Transforma o historico recente em texto simples para contexto adicional."""
        lines = []
        for msg in messages[-6:]:
            role = "Usuario" if msg.get("role") == "user" else "Assistente"
            content = (msg.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _format_history(self, messages: list) -> list[dict]:
        """Formata o historico de mensagens para o Ollama."""
        formatted = []
        for msg in messages:
            content = (msg.get("content") or "").strip()
            if not content:
                continue

            role = "user" if msg.get("role") == "user" else "assistant"
            formatted.append({"role": role, "content": content})
        return formatted
