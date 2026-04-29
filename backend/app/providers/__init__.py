"""
Provider Factory
----------------
Single entry point for getting the active LLM and embedding providers.

Usage in any service:
    from app.providers import get_embedding_provider, get_llm_provider

    embedder = get_embedding_provider()
    vectors = embedder.embed(["some invoice text"])

    llm = get_llm_provider()
    answer = llm.chat([{"role": "user", "content": "question"}])

Switching providers: change LLM_PROVIDER in .env. No other code changes.

Providers are instantiated fresh per call (not singletons) to avoid
stale config after settings reload. For high-throughput use, cache at
the request level if needed.
"""

from app.core.config import get_settings
from app.providers.base import EmbeddingProvider, LLMProvider


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider."""
    settings = get_settings()

    if settings.LLM_PROVIDER == "ollama":
        from app.providers.ollama_provider import OllamaEmbeddingProvider
        return OllamaEmbeddingProvider()

    # Default: openai
    from app.providers.openai_provider import OpenAIEmbeddingProvider
    return OpenAIEmbeddingProvider()


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM (chat completion) provider."""
    settings = get_settings()

    if settings.LLM_PROVIDER == "ollama":
        from app.providers.ollama_provider import OllamaLLMProvider
        return OllamaLLMProvider()

    # Default: openai
    from app.providers.openai_provider import OpenAILLMProvider
    return OpenAILLMProvider()