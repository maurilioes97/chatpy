import requests

from utils.config import EMBEDDINGS_ENABLED, OLLAMA_EMBED_MODEL, OLLAMA_HOST, OLLAMA_TIMEOUT


class EmbeddingServiceError(Exception):
    """Erro tratavel da geracao de embeddings."""


class EmbeddingService:
    """Servico para gerar embeddings locais via Ollama."""

    def __init__(self):
        self.enabled = EMBEDDINGS_ENABLED
        self.base_url = OLLAMA_HOST.rstrip("/")
        self.model_name = OLLAMA_EMBED_MODEL
        self.timeout_seconds = OLLAMA_TIMEOUT

    def embed_text(self, text: str) -> list[float]:
        """Gera embedding para um unico texto."""
        embeddings = self.embed_texts([text])
        return embeddings[0] if embeddings else []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings para uma lista de textos."""
        if not self.enabled:
            raise EmbeddingServiceError("Embeddings desativados por configuracao.")

        normalized_inputs = [(text or "").strip() for text in texts if (text or "").strip()]
        if not normalized_inputs:
            return []

        try:
            response = requests.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model_name,
                    "input": normalized_inputs,
                    "truncate": True,
                },
                timeout=self.timeout_seconds,
            )

            if response.status_code == 404:
                raise EmbeddingServiceError(
                    f"Modelo de embedding {self.model_name} nao encontrado no Ollama. "
                    f"Rode 'ollama pull {self.model_name}' para habilitar a busca semantica."
                )

            response.raise_for_status()
            payload = response.json()
            embeddings = payload.get("embeddings") or []
            if len(embeddings) != len(normalized_inputs):
                raise EmbeddingServiceError("O Ollama retornou uma quantidade inesperada de embeddings.")

            return embeddings
        except EmbeddingServiceError:
            raise
        except requests.exceptions.ConnectionError as exc:
            raise EmbeddingServiceError(
                f"Nao foi possivel conectar ao Ollama em {self.base_url} para gerar embeddings."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise EmbeddingServiceError(
                f"O Ollama demorou mais do que {self.timeout_seconds} segundos para gerar embeddings."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise EmbeddingServiceError(f"Erro HTTP ao gerar embeddings no Ollama: {str(exc)}") from exc
        except Exception as exc:
            raise EmbeddingServiceError(f"Erro ao gerar embeddings: {str(exc)}") from exc
