"""
Gemini Provider
---------------
Implements LLMProvider using Gemini's OpenAI-compatible API.

This provider is intentionally LLM-only. Retrieval embeddings are selected
separately through EMBEDDING_PROVIDER so the existing vector index remains
stable.
"""

from openai import OpenAI

from app.core.config import get_settings
from app.providers.base import LLMProvider


class GeminiLLMProvider(LLMProvider):
    """
    Chat completion via Google Gemini.
    Uses Gemini's OpenAI-compatible /chat/completions endpoint.
    """

    def __init__(self):
        settings = get_settings()
        self._client = OpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        self._model = settings.GEMINI_MODEL

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
