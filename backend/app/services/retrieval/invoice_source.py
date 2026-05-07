"""
Invoice Retrieval Source
------------------------
Retrieves relevant invoice chunks from invoice_embeddings via pgvector.
"""

import logging

from app.services.retrieval.base import RetrievalSource, RetrievedChunk

log = logging.getLogger(__name__)


class InvoiceSource(RetrievalSource):

    @property
    def name(self) -> str:
        return "invoices"

    @property
    def display_name(self) -> str:
        return "Invoice Data"

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

        for vector in query_vectors:
            try:
                result = db.rpc(
                    "match_invoice_chunks",
                    {
                        "query_embedding": vector,
                        "match_threshold": match_threshold,
                        "match_count": match_count,
                        "filter_company_id": company_id,
                    },
                ).execute()

                for row in (result.data or []):
                    all_chunks.append(RetrievedChunk(
                        chunk_id=row["id"],
                        source_type="invoice",
                        source_id=row["invoice_id"],
                        source_name="",  # populated by enrich()
                        chunk_text=row["chunk_text"],
                        similarity=row.get("similarity", 0.0),
                        metadata={
                            "chunk_index": row.get("chunk_index"),
                            "model_name": row.get("model_name"),
                        },
                    ))
            except Exception as e:
                log.error(f"Invoice retrieval failed for one query vector: {e}")

        return self._deduplicate(all_chunks)

    def enrich(self, db, company_id: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return chunks

        invoice_ids = list({c.source_id for c in chunks})
        result = (
            db.table("invoices")
            .select("id, invoice_number")
            .eq("company_id", company_id)
            .in_("id", invoice_ids)
            .execute()
        )
        id_to_number = {row["id"]: row["invoice_number"] for row in result.data}

        for chunk in chunks:
            inv_num = id_to_number.get(chunk.source_id, "N/A")
            chunk.source_name = inv_num
            chunk.citation = f"Invoice {inv_num}"

        return chunks