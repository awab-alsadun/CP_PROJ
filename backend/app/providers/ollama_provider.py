"""
Ollama Provider
---------------
Implements EmbeddingProvider and LLMProvider using a local Ollama instance.

Ollama exposes an OpenAI-compatible API at /v1/, so we use the openai
Python library pointed at the local base URL — no extra dependencies.

Embedding config:
- bge-m3 outputs 1024-dim vectors and is the default local embedding model.
- EMBEDDING_DIMENSION must match the selected model output. The provider
  validates dimensions instead of padding or truncating.

Think-block stripping:
- Reasoning models (Qwen3, DeepSeek-R1, etc.) emit <think>...</think> blocks
  before their actual response. These are stripped before returning so that
  JSON parsers and downstream consumers never see them.

Requirements:
- Ollama must be running locally: `ollama serve`
- Models must be pulled: `ollama pull qwen3:4b` and `ollama pull bge-m3`
- OLLAMA_BASE_URL in .env (default: http://localhost:11434)
"""

import logging
import re

from openai import OpenAI

from app.core.config import get_settings
from app.providers.base import EmbeddingProvider, LLMProvider

log = logging.getLogger(__name__)

# Matches <think>...</think> blocks including multiline content.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_blocks(text: str) -> str:
    """Remove reasoning think-blocks emitted by Qwen3 and similar models."""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _validate_dimension(vector: list[float], target_dim: int, model: str) -> list[float]:
    """Ensure the embedding model output matches the configured pgvector size."""
    if len(vector) == target_dim:
        return vector
    raise ValueError(
        f"Embedding model '{model}' returned {len(vector)} dimensions, "
        f"but EMBEDDING_DIMENSION is {target_dim}. Update the DB vector "
        "dimension or choose a matching embedding model."
    )


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Embedding via local Ollama (bge-m3 or configured model).
    Uses OpenAI-compatible /v1/embeddings endpoint.
    """

    def __init__(self):
        settings = get_settings()
        self._client = OpenAI(
            api_key="ollama",  # Ollama ignores the key but the SDK requires it
            base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        )
        self._model      = settings.OLLAMA_EMBEDDING_MODEL
        self._target_dim = settings.EMBEDDING_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results = []
        for text in texts:
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=text,
                )
                vector = response.data[0].embedding
                results.append(_validate_dimension(vector, self._target_dim, self._model))
            except Exception as e:
                log.error(f"Ollama embedding failed: {e}")
                raise

        return results


class OllamaLLMProvider(LLMProvider):
    """
    Chat completion via local Ollama.
    Uses OpenAI-compatible /v1/chat/completions endpoint.
    Think-blocks (<think>...</think>) are stripped from all responses.
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
        raw = response.choices[0].message.content or ""
        return _strip_think_blocks(raw)