"""
Retrieval Source Interface
--------------------------
Abstract base class for all retrieval sources.

To add a new data source (contracts, purchase orders, etc.):
1. Create a new file in this directory implementing RetrievalSource
2. Register it in registry.py

The query service never knows which sources exist — it iterates
the registry and merges results. Adding a source requires zero
changes to existing code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RetrievedChunk:
    """A single chunk returned by a retrieval source."""
    chunk_id: str
    source_type: str          # "invoice", "regulation", "contract", etc.
    source_id: str            # invoice_id, document_id, etc.
    source_name: str          # invoice_number, document_name, etc.
    chunk_text: str
    similarity: float
    metadata: dict = field(default_factory=dict)
    # Populated after enrichment
    citation: str = ""        # human-readable citation string


class RetrievalSource(ABC):
    """
    Interface every retrieval source must implement.

    Properties:
        name          — unique identifier, e.g. "invoices", "regulations"
        display_name  — human-readable, e.g. "Invoice Data", "Regulatory Documents"
        rpc_function  — Supabase RPC function name for similarity search

    Methods:
        retrieve()    — run vector similarity search
        enrich()      — add citation metadata (invoice numbers, section titles, etc.)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        ...

    @abstractmethod
    def retrieve(
        self,
        db,
        company_id: str,
        query_vectors: list[list[float]],
        match_count: int = 10,
        match_threshold: float = 0.45,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve relevant chunks using cosine similarity.

        Args:
            db: Supabase client.
            company_id: Tenant UUID.
            query_vectors: List of query embedding vectors (multi-query produces multiple).
            match_count: Max results per query vector.
            match_threshold: Minimum similarity score.
            filters: Source-specific filters (e.g. document_type for regulations).

        Returns:
            Deduplicated list of RetrievedChunk, sorted by similarity descending.
        """
        ...

    @abstractmethod
    def enrich(self, db, company_id: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """
        Add citation metadata to retrieved chunks.

        For invoices: adds invoice_number.
        For documents: adds section_title, page_number, document_name.
        """
        ...

    def _deduplicate(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Remove duplicate chunks (same chunk_id), keeping highest similarity."""
        seen = {}
        for chunk in chunks:
            if chunk.chunk_id not in seen or chunk.similarity > seen[chunk.chunk_id].similarity:
                seen[chunk.chunk_id] = chunk
        return sorted(seen.values(), key=lambda c: c.similarity, reverse=True)