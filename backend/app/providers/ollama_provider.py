"""
Ollama Provider
---------------
Implements EmbeddingProvider and LLMProvider using a local Ollama instance.

Ollama exposes an OpenAI-compatible API at /v1/, so we use the openai
Python library pointed at the local base URL — no extra dependencies.

Key difference from OpenAI provider:
- nomic-embed-text outputs 768-dim vectors
- These are zero-padded to 1536 to match the pgvector column
- This is transparent to all callers

Requirements:
- Ollama must be running locally: `ollama serve`
- Models must be pulled: `ollama pull llama3` and `ollama pull nomic-embed-text`
- OLLAMA_BASE_URL in .env (default: http://localhost:11434)
"""

import logging

from openai import OpenAI

from app.core.config import get_settings
from app.providers.base import EmbeddingProvider, LLMProvider

log = logging.getLogger(__name__)


def _pad_to_dim(vector: list[float], target_dim: int) -> list[float]:
    """
    Zero-pad a vector to target_dim.

    nomic-embed-text → 768 dims → padded to 1536.
    Cosine similarity is unaffected by zero-padding because zero components
    do not contribute to the dot product or the norm calculation.
    """
    if len(vector) == target_dim:
        return vector
    if len(vector) < target_dim:
        return vector + [0.0] * (target_dim - len(vector))
    # Truncate if somehow larger (shouldn't happen)
    log.warning(f"Vector dim {len(vector)} exceeds target {target_dim}. Truncating.")
    return vector[:target_dim]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Embedding via local Ollama (nomic-embed-text or configured model).
    Uses OpenAI-compatible /v1/embeddings endpoint.
    """

    def __init__(self):
        settings = get_settings()
        # Ollama's OpenAI-compatible endpoint lives at /v1
        self._client = OpenAI(
            api_key="ollama",  # Ollama ignores the key but the SDK requires it
            base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        )
        self._model = settings.OLLAMA_EMBEDDING_MODEL
        self._target_dim = settings.EMBEDDING_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # Ollama embedding endpoint processes one at a time reliably
        # For batch: loop and collect. No rate limits locally.
        results = []
        for text in texts:
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=text,
                )
                vector = response.data[0].embedding
                results.append(_pad_to_dim(vector, self._target_dim))
            except Exception as e:
                log.error(f"Ollama embedding failed for text snippet: {e}")
                raise

        return results


class OllamaLLMProvider(LLMProvider):
    """
    Chat completion via local Ollama.
    Uses OpenAI-compatible /v1/chat/completions endpoint.
    """

    def __init__(self):
        settings = get_settings()
        self._client = OpenAI(
            api_key="ollama",
            base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        )
        self._model = settings.OLLAMA_MODEL

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""