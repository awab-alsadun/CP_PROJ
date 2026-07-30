"""
Local BGE reranker provider.

Uses BAAI/bge-reranker-v2-m3 via raw transformers — no FlagEmbedding dependency.
Model and tokenizer are cached as module-level singletons after first load.
"""

import logging

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.core.config import get_settings
from app.services.retrieval.base import RetrievedChunk

log = logging.getLogger(__name__)

_tokenizer = None
_model     = None


def _get_reranker():
    global _tokenizer, _model

    if _tokenizer is None or _model is None:
        settings   = get_settings()
        model_name = settings.BGE_RERANK_MODEL
        device     = "cuda" if torch.cuda.is_available() else "cpu"

        log.info(f"Loading BGE reranker '{model_name}' on {device}")

        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        _model     = AutoModelForSequenceClassification.from_pretrained(model_name)
        _model.to(device)
        _model.eval()

        log.info("BGE reranker loaded")

    return _tokenizer, _model


def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    top_n: int = 6,
) -> list[RetrievedChunk]:

    if not chunks:
        return []

    if len(chunks) <= top_n:
        return chunks

    try:
        tokenizer, model = _get_reranker()
        device = next(model.parameters()).device

        pairs = [[query, chunk.chunk_text] for chunk in chunks]

        encoded = tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        encoded = {k: v.to(device) for k, v in encoded.items()}

        with torch.no_grad():
            logits = model(**encoded).logits

        # bge-reranker-v2-m3 is a binary classifier; score = sigmoid(logit[:,0])
        if logits.dim() == 2:
            scores = F.sigmoid(logits[:, 0]).cpu().tolist()
        else:
            scores = F.sigmoid(logits).cpu().tolist()

        for chunk, score in zip(chunks, scores):
            chunk.metadata["original_vector_similarity"] = chunk.similarity
            chunk.metadata["rerank_score"]               = round(float(score), 6)
            chunk.similarity                             = float(score)

        chunks.sort(key=lambda c: c.similarity, reverse=True)
        return chunks[:top_n]

    except Exception as e:
        log.error(f"BGE rerank failed: {e}")
        return sorted(chunks, key=lambda c: c.similarity, reverse=True)[:top_n]