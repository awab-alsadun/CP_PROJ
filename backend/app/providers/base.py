"""
Provider Interfaces
-------------------
Abstract base classes that define the contract every LLM/embedding
provider must fulfill.

Rules:
- Services import ONLY from here and from the factory in __init__.py
- Services never import openai, ollama, or any vendor SDK directly
- Adding a new provider = create a new file + register in __init__.py
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """
    Contract for embedding providers.

    embed() always returns vectors padded/truncated to EMBEDDING_DIMENSION
    (1536 by default) so the pgvector column never receives a wrong-size vector.
    """

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts.

        Args:
            texts: List of strings to embed. Send as many as rate limits allow.

        Returns:
            List of float vectors, one per input text.
            Each vector is exactly settings.EMBEDDING_DIMENSION floats.
        """
        ...

    def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for single-text embedding."""
        return self.embed([text])[0]


class LLMProvider(ABC):
    """
    Contract for chat completion providers.
    """

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        """
        Run a chat completion.

        Args:
            messages: OpenAI-format message list:
                      [{"role": "system"|"user"|"assistant", "content": "..."}]
            temperature: 0.0 = deterministic, 1.0 = creative.
            max_tokens: Hard cap on response length.

        Returns:
            The assistant's response as a plain string.
        """
        ...