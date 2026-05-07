"""

Extensible retrieval source system. Import from here:

    from app.services.retrieval import get_all_sources, get_source, RetrievedChunk
"""

from app.services.retrieval.base import RetrievalSource, RetrievedChunk
from app.services.retrieval.registry import get_all_sources, get_source, get_source_names

__all__ = [
    "RetrievalSource",
    "RetrievedChunk",
    "get_all_sources",
    "get_source",
    "get_source_names",
]