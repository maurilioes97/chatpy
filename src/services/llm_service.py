import os

from dotenv import load_dotenv

load_dotenv()


class LLMServiceError(Exception):
    """Erro tratavel do provider de IA selecionado."""


class LLMService:
    """Seleciona e delega chamadas ao provider configurado."""

    def __init__(self, provider_name: str | None = None):
        provider = (provider_name or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
        self.provider_name = provider
        self.provider_errors = (Exception,)

        if provider == "gemini":
            from services.gemini_service import GeminiService, GeminiServiceError

            self.provider = GeminiService()
            self.provider_errors = (GeminiServiceError,)
            return

        if provider == "ollama":
            from services.ollama_service import OllamaService, OllamaServiceError

            self.provider = OllamaService()
            self.provider_errors = (OllamaServiceError,)
            return

        raise LLMServiceError(
            "Provider de IA invalido. Use LLM_PROVIDER=gemini ou LLM_PROVIDER=ollama no .env."
        )

    def get_response(
        self,
        user_message: str,
        conversation_history: list | None = None,
        document: dict | None = None,
        equipment_context: str | None = None,
        knowledge_chunks: list[dict] | None = None,
        had_direct_matches: bool = False,
        ) -> str:
        """Encaminha a solicitacao para o provider configurado."""
        try:
            return self.provider.get_response(
                user_message=user_message,
                conversation_history=conversation_history,
                document=document,
                equipment_context=equipment_context,
                knowledge_chunks=knowledge_chunks,
                had_direct_matches=had_direct_matches,
            )
        except self.provider_errors as exc:
            raise LLMServiceError(str(exc)) from exc
