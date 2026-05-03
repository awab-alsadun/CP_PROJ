"""
Cohere Reranking Provider
-------------------------
Reranks retrieved chunks using Cohere's cross-encoder rerank API.

Cross-encoders score (query, document) pairs jointly — much more accurate
than cosine similarity which embeds query and document independently.

Provider-agnostic wrapper: if you switch to a different reranker later
(e.g., local cross-encoder via sentence-transformers), implement the
same interface and swap in config.

Usage:
    from app.providers.cohere_provider import rerank_chunks
    top_chunks = rerank_chunks(question, chunks, top_n=6)
"""

import logging

import cohere

from app.core.config import get_settings
from app.services.retrieval.base import RetrievedChunk

log = logging.getLogger(__name__)


def _get_cohere_client() -> cohere.ClientV2:
    settings = get_settings()
    return cohere.ClientV2(api_key=settings.CO_API_KEY)


def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    top_n: int = 6,
) -> list[RetrievedChunk]:
    """
    Rerank chunks using Cohere rerank-v3.5.

    Args:
        query: The original user question.
        chunks: Candidate chunks from all retrieval sources.
        top_n: How many to keep after reranking.

    Returns:
        Top N chunks, re-sorted by rerank relevance score.
        Original similarity score is replaced with the rerank score.
    """
    if not chunks:
        return []

    if len(chunks) <= top_n:
        # Not enough chunks to justify a rerank call
        return chunks

    settings = get_settings()

    try:
        client = _get_cohere_client()
        documents = [c.chunk_text for c in chunks]

        response = client.rerank(
            model=settings.COHERE_RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=top_n,
        )

        reranked = []
        for result in response.results:
            chunk = chunks[result.index]
            chunk.similarity = round(result.relevance_score, 4)
            chunk.metadata["rerank_score"] = result.relevance_score
            chunk.metadata["original_vector_similarity"] = chunks[result.index].similarity
            reranked.append(chunk)

        return reranked

    except Exception as e:
        log.error(f"Cohere rerank failed, falling back to vector similarity order: {e}")
        # Graceful degradation: return top_n by original similarity
        return sorted(chunks, key=lambda c: c.similarity, reverse=True)[:top_n]