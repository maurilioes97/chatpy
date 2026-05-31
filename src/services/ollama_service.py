import os
import json
import re
import unicodedata

import requests

from utils.document_processing import extract_docx_text, extract_pdf_text, normalize_text


class OllamaServiceError(Exception):
    """Erro tratavel da integracao com Ollama."""


class OllamaService:
    """Servico de integracao com a API local do Ollama."""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.model_name = os.getenv("OLLAMA_MODEL", "gemma3:4b")
        self.timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT", "1200"))
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
        self.max_document_chars = int(os.getenv("OLLAMA_MAX_DOCUMENT_CHARS", "16000"))
        self.max_document_sections = int(os.getenv("OLLAMA_MAX_DOCUMENT_SECTIONS", "4"))
        self.max_history_messages = int(os.getenv("OLLAMA_MAX_HISTORY_MESSAGES", "6"))

    def get_response(
        self,
        user_message: str,
        conversation_history: list | None = None,
        document: dict | None = None,
        equipment_context: str | None = None,
        knowledge_chunks: list[dict] | None = None,
        had_direct_matches: bool = False,
    ) -> str:
        """Obtem resposta do Ollama usando historico e contexto de estudo opcional."""
        try:
            messages = self._build_messages(
                user_message=user_message,
                conversation_history=conversation_history or [],
                document=document,
                equipment_context=equipment_context,
                knowledge_chunks=knowledge_chunks or [],
                had_direct_matches=had_direct_matches,
            )

            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_ctx": self.num_ctx,
                    },
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
        except json.JSONDecodeError as exc:
            raise OllamaServiceError("O Ollama retornou uma resposta invalida.") from exc
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

    def stream_response(
        self,
        user_message: str,
        conversation_history: list | None = None,
        document: dict | None = None,
        equipment_context: str | None = None,
        knowledge_chunks: list[dict] | None = None,
        had_direct_matches: bool = False,
    ):
        """Entrega a resposta do Ollama em streaming incremental."""
        try:
            messages = self._build_messages(
                user_message=user_message,
                conversation_history=conversation_history or [],
                document=document,
                equipment_context=equipment_context,
                knowledge_chunks=knowledge_chunks or [],
                had_direct_matches=had_direct_matches,
            )

            with requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_ctx": self.num_ctx,
                    },
                },
                timeout=self.timeout_seconds,
                stream=True,
            ) as response:
                if response.status_code == 404:
                    raise OllamaServiceError(
                        f"Modelo {self.model_name} nao encontrado no Ollama. "
                        f"Rode 'ollama pull {self.model_name}' no container ou na maquina host."
                    )

                response.raise_for_status()

                yielded_any_content = False
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue

                    response_data = json.loads(raw_line)
                    message = response_data.get("message") or {}
                    content = (message.get("content") or "")
                    if content:
                        yielded_any_content = True
                        yield content

                if not yielded_any_content:
                    raise OllamaServiceError("O Ollama respondeu sem conteudo.")
        except json.JSONDecodeError as exc:
            raise OllamaServiceError("O Ollama retornou uma resposta invalida durante o streaming.") from exc
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

    def _build_messages(
        self,
        user_message: str,
        conversation_history: list,
        document: dict | None,
        equipment_context: str | None,
        knowledge_chunks: list[dict],
        had_direct_matches: bool,
    ) -> list[dict]:
        """Monta a lista de mensagens para o endpoint de chat do Ollama."""
        has_grounding = bool(document or equipment_context or knowledge_chunks)
        if has_grounding:
            prompt = self._build_grounded_prompt(
                user_message=user_message,
                conversation_history=conversation_history,
                document=document,
                equipment_context=equipment_context,
                knowledge_chunks=knowledge_chunks,
                had_direct_matches=had_direct_matches,
            )
            return [
                {
                    "role": "system",
                    "content": (
                        "Voce e um assistente de estudos para concursos, especializado em provas e gabaritos. "
                        "Responda em portugues de forma objetiva, clara e didatica. "
                        "Priorize os documentos e dados fornecidos, mas quando houver lacunas voce pode fazer inferencias razoaveis "
                        "com base em boas praticas de estudo e interpretacao de questoes. "
                        "Antes de responder, confira mentalmente se sua conclusao esta realmente sustentada pelo material. "
                        "Se houver mais de uma interpretacao plausivel, escolha a mais conservadora e sinalize a duvida. "
                        "Sempre deixe claro quando estiver inferindo algo."
                    ),
                },
                {"role": "user", "content": prompt},
            ]

        return [
            {
                "role": "system",
                "content": (
                    "Voce e um assistente de estudos para concursos, especializado em provas e gabaritos. "
                    "Responda em portugues de forma objetiva, clara e didatica. "
                    "Quando faltar contexto especifico, voce pode usar conhecimento geral de estudo e interpretacao de questoes. "
                    "Antes de responder, confira mentalmente se sua conclusao esta realmente sustentada pela conversa. "
                    "Se fizer suposicoes, sinalize isso com clareza e prefira a interpretacao mais conservadora."
                ),
            },
            *self._format_history(conversation_history),
            {"role": "user", "content": user_message},
        ]

    def _build_grounded_prompt(
        self,
        user_message: str,
        conversation_history: list,
        document: dict | None,
        equipment_context: str | None,
        knowledge_chunks: list[dict],
        had_direct_matches: bool,
    ) -> str:
        """Monta prompt de estudos com base em prova, trechos e material extra opcional."""
        history_text = self._build_history_text(conversation_history)
        history_section = f"Historico recente:\n{history_text}\n\n" if history_text else ""
        equipment_section = f"Contexto da prova:\n{equipment_context}\n\n" if equipment_context else ""

        exam_chunk_lines = []
        answer_key_chunk_lines = []
        supporting_chunk_lines = []
        for index, chunk in enumerate(knowledge_chunks, start=1):
            source_label = chunk.get("source_label") or "Trecho relevante"
            file_name = chunk.get("file_name") or "Arquivo"
            chunk_text = (chunk.get("chunk_text") or "").strip()
            if not chunk_text:
                continue
            line = f"[Trecho {index}] {file_name} | {source_label}\n{chunk_text}"
            document_role = chunk.get("document_role")
            if document_role == "exam":
                exam_chunk_lines.append(line)
            elif document_role == "answer_key":
                answer_key_chunk_lines.append(line)
            else:
                supporting_chunk_lines.append(line)

        chunks_section = ""
        if exam_chunk_lines:
            chunks_section += "Conteudo da prova:\n" + "\n\n".join(exam_chunk_lines) + "\n\n"
        if answer_key_chunk_lines:
            chunks_section += "Conteudo do gabarito:\n" + "\n\n".join(answer_key_chunk_lines) + "\n\n"
        if supporting_chunk_lines:
            chunks_section += "Conteudo de materiais complementares:\n" + "\n\n".join(supporting_chunk_lines) + "\n\n"

        document_section = ""
        if document:
            document_section = self._build_document_section(
                document,
                user_message=user_message,
                conversation_history=conversation_history,
            )

        retrieval_section = (
            "Foram encontrados trechos diretamente relevantes para esta pergunta.\n\n"
            if had_direct_matches
            else (
                "Nao foram encontrados trechos diretamente relevantes para esta pergunta.\n"
                "Nesse caso, use apenas o contexto geral da prova e os documentos disponiveis como apoio.\n"
                "Nao afirme gabaritos, enunciados ou detalhes especificos sem apoio explicito no material.\n"
                "Se faltar base suficiente, diga isso com clareza antes de inferir qualquer coisa.\n\n"
            )
        )

        return (
            "Voce e um assistente de estudos para concursos, especializado em provas, gabaritos e materiais de apoio.\n"
            "Priorize as informacoes da prova, do historico, dos trechos indexados e dos documentos fornecidos.\n"
            "Analise com cuidado antes de responder: primeiro localize os sinais mais relevantes no material, depois confira se a conclusao esta sustentada por eles.\n"
            "Prefira uma resposta um pouco mais pensada e conservadora do que uma resposta rapida e arriscada.\n"
            "Nunca invente ou reconstrua o texto exato de uma questao, alternativa ou enunciado.\n"
            "Se o usuario pedir o texto exato de uma questao, copie somente o que estiver no conteudo da prova.\n"
            "Quando reproduzir uma questao de multipla escolha, formate assim: enunciado em um paragrafo separado e cada alternativa em uma linha propria.\n"
            "Nao use o gabarito para deduzir ou reinventar o enunciado da questao.\n"
            "Se o texto exato nao estiver visivel no material, diga claramente que nao foi possivel localizar esse trecho.\n"
            "Se a resposta nao estiver claramente sustentada pelos dados, diga isso objetivamente.\n"
            "Voce pode complementar a resposta com conhecimento geral apenas quando isso nao criar fatos especificos ausentes no material.\n"
            "Sempre diferencie claramente o que veio dos documentos e o que e inferencia sua.\n"
            "Quando estiver inferindo, use marcacoes claras como 'Pelo material, a leitura mais provavel e...' ou 'Isso nao esta explicito, mas a interpretacao mais segura e...'.\n"
            "Quando houver base suficiente, explique o raciocinio da resposta correta e, se fizer sentido, por que as demais alternativas estao erradas.\n"
            "Se pedirem um simulado, monte questoes novas inspiradas no estilo e nos assuntos do material, deixando claro quando forem elaboradas por voce.\n"
            "Se usar a prova ou o gabarito como base, mencione o trecho ou a pagina de forma natural.\n\n"
            f"{history_section}"
            f"{equipment_section}"
            f"{retrieval_section}"
            f"{chunks_section}"
            f"{document_section}"
            f"Pergunta do estudante: {user_message}"
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

    def _build_document_section(self, document: dict, user_message: str, conversation_history: list) -> str:
        """Mantem apenas os excertos mais uteis do anexo para o prompt local."""
        extracted_text = self._extract_document_text(document)
        normalized_document = normalize_text(extracted_text)
        if not normalized_document:
            return ""

        search_text = "\n".join(
            part
            for part in (
                user_message,
                self._build_history_text(conversation_history[-2:]),
            )
            if part
        )
        selected_sections = self._select_document_sections(normalized_document, search_text)
        if not selected_sections:
            selected_sections = [normalized_document[:self.max_document_chars].strip()]

        excerpt_lines = []
        total_chars = 0
        for index, section in enumerate(selected_sections, start=1):
            cleaned_section = section.strip()
            if not cleaned_section:
                continue

            if excerpt_lines and total_chars + len(cleaned_section) > self.max_document_chars:
                break

            excerpt_lines.append(f"[Excerto {index}]\n{cleaned_section}")
            total_chars += len(cleaned_section)

        if not excerpt_lines:
            return ""

        return (
            f"Trechos relevantes do material complementar {document['name']}:\n"
            + "\n\n".join(excerpt_lines)
            + "\n\n"
        )

    def _select_document_sections(self, document_text: str, search_text: str) -> list[str]:
        """Seleciona excertos do anexo com base em sobreposicao lexical simples."""
        sections = self._split_text_into_sections(document_text)
        if not sections:
            return []

        query_tokens = self._build_search_tokens(search_text)
        numbers = {int(number) for number in re.findall(r"\b\d{1,3}\b", self._normalize_search_text(search_text))}
        scored_sections = []

        for index, section in enumerate(sections):
            normalized_section = self._normalize_search_text(section)
            section_tokens = self._build_search_tokens(section)
            overlap = query_tokens & section_tokens
            score = len(overlap) * 5

            if index == 0:
                score += 1

            for number in numbers:
                if re.search(rf"(?<!\d)0*{number}(?!\d)", normalized_section):
                    score += 8

            scored_sections.append({"index": index, "score": score, "text": section.strip()})

        scored_sections.sort(key=lambda item: (item["score"], -item["index"]), reverse=True)
        positive_sections = [item for item in scored_sections if item["score"] > 0]
        if not positive_sections:
            return []

        selected_indexes = sorted(item["index"] for item in positive_sections[:self.max_document_sections])
        return [sections[index] for index in selected_indexes]

    def _split_text_into_sections(self, text: str) -> list[str]:
        """Divide um texto grande em secoes menores para o prompt do Ollama."""
        normalized_text = normalize_text(text)
        if not normalized_text:
            return []

        sections = []
        chunk_size = 2200
        overlap = 260
        start = 0
        text_length = len(normalized_text)

        while start < text_length:
            end = min(start + chunk_size, text_length)
            if end < text_length:
                split_at = normalized_text.rfind(" ", start, end)
                if split_at > start + chunk_size // 2:
                    end = split_at

            section = normalized_text[start:end].strip()
            if section:
                sections.append(section)

            if end >= text_length:
                break

            start = max(end - overlap, 0)

        return sections

    def _normalize_search_text(self, text: str) -> str:
        """Normaliza texto para comparacoes tolerantes a acentos."""
        normalized = normalize_text(text or "").lower()
        ascii_text = unicodedata.normalize("NFD", normalized)
        return "".join(char for char in ascii_text if unicodedata.category(char) != "Mn")

    def _build_search_tokens(self, text: str) -> set[str]:
        """Extrai tokens simples para localizar trechos relevantes."""
        stopwords = {
            "para", "como", "sobre", "porque", "questao", "prova", "gabarito", "material",
            "documento", "estudo", "esta", "esse", "essa", "com", "sem", "mais", "menos",
        }
        normalized_text = self._normalize_search_text(text)
        return {
            token
            for token in re.findall(r"[a-z0-9]{4,}", normalized_text)
            if token not in stopwords
        }

    def _build_history_text(self, messages: list) -> str:
        """Transforma o historico recente em texto simples para contexto adicional."""
        lines = []
        for msg in messages[-self.max_history_messages:]:
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
