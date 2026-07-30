"""
Grok / xAI Provider
-------------------
Implements LLMProvider using xAI's OpenAI-compatible API.

This provider is intentionally LLM-only. Retrieval embeddings are selected
separately through EMBEDDING_PROVIDER because embeddings from different
models are not interchangeable semantic spaces.
"""

from openai import OpenAI

from app.core.config import get_settings
from app.providers.base import LLMProvider


class GrokLLMProvider(LLMProvider):
    """
    Chat completion via xAI/Grok.
    Uses xAI's OpenAI-compatible /v1/chat/completions endpoint.
    """

    def __init__(self):
        settings = get_settings()
        self._client = OpenAI(
            api_key=settings.XAI_API_KEY,
            base_url="https://api.x.ai/v1",
        )
        self._model = settings.GROK_MODEL

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
