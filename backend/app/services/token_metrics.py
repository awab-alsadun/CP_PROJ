"""
Token Metrics
-------------
Real token counting using tiktoken (cl100k_base — used by GPT-4, Gemini-compatible
for counting purposes since Gemini tokenizes similarly at this granularity).

Replaces the char/4 heuristic with actual BPE token counts.

Usage:
    from app.services.token_metrics import (
        count_tokens,
        count_message_tokens,
        token_savings,
        record_query_path,
        get_metrics_summary,
    )

Telemetry collected per process lifetime (resets on restart):
    - keyword_classified: count of queries resolved by keyword pre-filter
    - llm_classified: count of queries that needed the LLM classifier
    - compression_savings: list of (before_tokens, after_tokens) per RAG query
    - classification_tokens_avoided: tokens saved per keyword-classified query
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger(__name__)

# ── Tiktoken setup ────────────────────────────────────────────────────────────

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _enc = None
    _TIKTOKEN_AVAILABLE = False
    log.warning(
        "tiktoken not installed — falling back to char/4 heuristic. "
        "Run: pip install tiktoken"
    )


def count_tokens(text: str | None) -> int:
    """Real BPE token count. Falls back to char/4 if tiktoken unavailable."""
    if not text:
        return 0
    if _TIKTOKEN_AVAILABLE and _enc is not None:
        return len(_enc.encode(text))
    # Fallback
    import math
    return max(1, math.ceil(len(text) / 4))


def count_message_tokens(messages: list[dict]) -> int:
    """
    Token count for an OpenAI-style messages list.
    Counts content of all messages + 4 tokens overhead per message
    (OpenAI's documented format overhead).
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content) + 4  # role + framing overhead
    total += 2  # priming tokens for assistant reply
    return total


def token_savings(
    before_text: str | None,
    after_text: str | None,
) -> tuple[int, int, int]:
    """Returns (before_tokens, after_tokens, tokens_saved)."""
    before = count_tokens(before_text)
    after = count_tokens(after_text)
    return before, after, max(0, before - after)


# ── In-process telemetry ──────────────────────────────────────────────────────

@dataclass
class _Telemetry:
    keyword_classified: int = 0
    llm_classified: int = 0
    compression_records: list[tuple[int, int]] = field(default_factory=list)
    classification_tokens_avoided: list[int] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_keyword_hit(self, tokens_avoided: int) -> None:
        with self._lock:
            self.keyword_classified += 1
            self.classification_tokens_avoided.append(tokens_avoided)

    def record_llm_hit(self) -> None:
        with self._lock:
            self.llm_classified += 1

    def record_compression(self, before: int, after: int) -> None:
        with self._lock:
            self.compression_records.append((before, after))

    def summary(self) -> dict:
        with self._lock:
            total = self.keyword_classified + self.llm_classified
            keyword_pct = (self.keyword_classified / total * 100) if total else 0

            avg_avoided = (
                sum(self.classification_tokens_avoided) / len(self.classification_tokens_avoided)
                if self.classification_tokens_avoided else 0
            )

            compression_pcts = []
            for before, after in self.compression_records:
                if before > 0:
                    compression_pcts.append((before - after) / before * 100)

            avg_compression_pct = (
                sum(compression_pcts) / len(compression_pcts)
                if compression_pcts else 0
            )

            total_saved_compression = sum(
                before - after for before, after in self.compression_records
            )

            return {
                "total_queries":             total,
                "keyword_classified":        self.keyword_classified,
                "llm_classified":            self.llm_classified,
                "keyword_pct":               round(keyword_pct, 1),
                "avg_tokens_avoided_per_keyword_query": round(avg_avoided, 1),
                "total_tokens_avoided_classification":  sum(self.classification_tokens_avoided),
                "compression_queries":       len(self.compression_records),
                "avg_compression_pct":       round(avg_compression_pct, 1),
                "total_tokens_saved_compression": total_saved_compression,
                "tiktoken_available":        _TIKTOKEN_AVAILABLE,
            }


_telemetry = _Telemetry()


def record_query_path(
    path: Literal["keyword", "llm"],
    tokens_avoided: int = 0,
) -> None:
    """Call from intent_classifier after each classification."""
    if path == "keyword":
        _telemetry.record_keyword_hit(tokens_avoided)
    else:
        _telemetry.record_llm_hit()


def record_compression(before_tokens: int, after_tokens: int) -> None:
    """Call from query_service after each context compression."""
    _telemetry.record_compression(before_tokens, after_tokens)


def get_metrics_summary() -> dict:
    """Returns all collected telemetry as a dict."""
    return _telemetry.summary()


# Backwards-compatible aliases for existing callers
def estimate_tokens(text: str | None, chars_per_token: int = 4) -> int:
    return count_tokens(text)


def estimate_message_tokens(messages: list[dict], chars_per_token: int = 4) -> int:
    return count_message_tokens(messages)