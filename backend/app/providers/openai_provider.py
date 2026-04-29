"""
OpenAI Provider
---------------
Implements EmbeddingProvider and LLMProvider using the OpenAI API.

Handles:
- Batch embedding with rate-limit retry (429 backoff)
- Chat completion with configurable model
- Vector dimension enforcement (always returns EMBEDDING_DIMENSION floats)
"""

import logging
import time

from openai import OpenAI, RateLimitError

from app.core.config import get_settings
from app.providers.base import EmbeddingProvider, LLMProvider

log = logging.getLogger(__name__)

_RETRY_WAIT_SECONDS = 60
_MAX_RETRIES = 3


def _pad_or_truncate(vector: list[float], target_dim: int) -> list[float]:
    """Ensure vector is exactly target_dim floats. Pads with 0.0 or truncates."""
    if len(vector) == target_dim:
        return vector
    if len(vector) < target_dim:
        return vector + [0.0] * (target_dim - len(vector))
    return vector[:target_dim]


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
                return [_pad_or_truncate(v, self._target_dim) for v in vectors]

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