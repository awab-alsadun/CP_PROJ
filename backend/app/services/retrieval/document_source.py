"""
Document Retrieval Source
-------------------------
Retrieves relevant regulation/compliance document chunks
from company_documents via pgvector.
"""

import logging

from app.services.retrieval.base import RetrievalSource, RetrievedChunk

log = logging.getLogger(__name__)


class DocumentSource(RetrievalSource):

    @property
    def name(self) -> str:
        return "regulations"

    @property
    def display_name(self) -> str:
        return "Regulatory Documents"

    def retrieve(
        self,
        db,
        company_id: str,
        query_vectors: list[list[float]],
        match_count: int = 10,
        match_threshold: float = 0.45,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:

        all_chunks = []
        doc_type_filter = (filters or {}).get("document_type")

        for vector in query_vectors:
            try:
                params = {
                    "query_embedding": vector,
                    "match_threshold": match_threshold,
                    "match_count": match_count,
                    "filter_company_id": company_id,
                }
                if doc_type_filter:
                    params["filter_document_type"] = doc_type_filter

                result = db.rpc("match_company_documents", params).execute()

                for row in (result.data or []):
                    # Build citation from section info
                    citation_parts = [row.get("document_name", "Unknown Document")]
                    if row.get("section_number"):
                        citation_parts.append(f"Section {row['section_number']}")
                    if row.get("section_title"):
                        citation_parts.append(row["section_title"])
                    if row.get("page_number"):
                        citation_parts.append(f"p.{row['page_number']}")

                    all_chunks.append(RetrievedChunk(
                        chunk_id=row["id"],
                        source_type="regulation",
                        source_id=row["document_id"],
                        source_name=row.get("document_name", "Unknown"),
                        chunk_text=row["chunk_text"],
                        similarity=row.get("similarity", 0.0),
                        metadata={
                            "document_type": row.get("document_type"),
                            "country": row.get("country"),
                            "section_title": row.get("section_title"),
                            "section_number": row.get("section_number"),
                            "page_number": row.get("page_number"),
                        },
                        citation=" — ".join(citation_parts),
                    ))
            except Exception as e:
                log.error(f"Document retrieval failed for one query vector: {e}")

        return self._deduplicate(all_chunks)

    def enrich(self, db, company_id: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        # Citations are already built during retrieve() from the RPC result columns.
        # No extra DB call needed — unlike invoices, documents carry their own metadata.
        return chunks