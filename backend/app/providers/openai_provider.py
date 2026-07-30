"""
OpenAI Provider
---------------
Implements EmbeddingProvider and LLMProvider using the OpenAI API.

Handles:
- Batch embedding with rate-limit retry (429 backoff)
- Chat completion with configurable model
- Vector dimension validation
"""

import logging
import time

from openai import OpenAI, RateLimitError

from app.core.config import get_settings
from app.providers.base import EmbeddingProvider, LLMProvider

log = logging.getLogger(__name__)

_RETRY_WAIT_SECONDS = 60
_MAX_RETRIES = 3


def _validate_dimension(vector: list[float], target_dim: int, model: str) -> list[float]:
    """Ensure the embedding model output matches the configured pgvector size."""
    if len(vector) == target_dim:
        return vector
    raise ValueError(
        f"Embedding model '{model}' returned {len(vector)} dimensions, "
        f"but EMBEDDING_DIMENSION is {target_dim}. Update the DB vector "
        "dimension or choose a matching embedding model."
    )


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    Embedding via OpenAI text-embedding-3-small (1536 dims).
    Retries on 429 with exponential-ish backoff.
    """

    def __init__(self):
        settings = get_settings()
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_EMBEDDING_MODEL
        self._target_dim = settings.EMBEDDING_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=texts,
                )
                vectors = [item.embedding for item in response.data]
                return [_validate_dimension(v, self._target_dim, self._model) for v in vectors]

            except RateLimitError:
                if attempt == _MAX_RETRIES:
                    raise
                wait = _RETRY_WAIT_SECONDS * attempt
                log.warning(f"OpenAI 429 rate limit. Waiting {wait}s (attempt {attempt}/{_MAX_RETRIES})")
                time.sleep(wait)

            except Exception as e:
                log.error(f"OpenAI embedding failed (attempt {attempt}): {e}")
                if attempt == _MAX_RETRIES:
                    raise

        return []  # unreachable, satisfies type checker


class OpenAILLMProvider(LLMProvider):
    """
    Chat completion via OpenAI gpt-4o (or configured model).
    """

    def __init__(self):
        settings = get_settings()
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL

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
