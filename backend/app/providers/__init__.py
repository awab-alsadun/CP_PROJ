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

Switching generation providers: change LLM_PROVIDER in .env.
Switching embedding providers: change EMBEDDING_PROVIDER only when the
database/index is isolated by embedding profile or has been re-embedded.

Providers are instantiated fresh per call (not singletons) to avoid
stale config after settings reload. For high-throughput use, cache at
the request level if needed.
"""

from app.core.config import get_settings
from app.providers.base import EmbeddingProvider, LLMProvider


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider."""
    settings = get_settings()

    if settings.EMBEDDING_PROVIDER == "ollama":
        from app.providers.ollama_provider import OllamaEmbeddingProvider
        return OllamaEmbeddingProvider()

    if settings.EMBEDDING_PROVIDER == "openai":
        from app.providers.openai_provider import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider()

    raise ValueError(f"Unsupported embedding provider: {settings.EMBEDDING_PROVIDER}")


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM (chat completion) provider."""
    settings = get_settings()

    if settings.LLM_PROVIDER == "ollama":
        from app.providers.ollama_provider import OllamaLLMProvider
        return OllamaLLMProvider()

    if settings.LLM_PROVIDER == "grok":
        from app.providers.grok_provider import GrokLLMProvider
        return GrokLLMProvider()

    if settings.LLM_PROVIDER == "gemini":
        from app.providers.gemini_provider import GeminiLLMProvider
        return GeminiLLMProvider()

    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")


def rerank_chunks(
    query,
    chunks,
    top_n: int = 6,
):
    """Dispatch reranking to the configured provider."""
    settings = get_settings()

    if settings.RERANK_PROVIDER == "bge":
        from app.providers.bge_reranker import rerank_chunks as provider
    else:
        from app.providers.cohere_reranker import rerank_chunks as provider

    return provider(query, chunks, top_n)