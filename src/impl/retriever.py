from typing import List, Dict, Any
import numpy as np
from sentence_transformers import CrossEncoder

from src.interface.base_retriever import BaseRetriever
from src.interface.base_datastore import BaseDatastore, DataItem


class Retriever(BaseRetriever):

    def __init__(self, datastore: BaseDatastore):
        self.datastore = datastore
        self.reranker = CrossEncoder("BAAI/bge-reranker-base")

    def search(self, query: str, top_k: int = 3) -> List[str]:
        """Search and return top-k content strings enriched with metadata context."""
        candidates = self.datastore.search(query, top_k=top_k * 3)
        reranked = self._rerank(query, candidates, top_k)
        # Return just the content for response generation
        return [item["content"] for item in reranked]

    def _rerank(
        self,
        query: str,
        items: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Rerank items using metadata context for better scoring."""
        pairs = []
        for item in items:
            content = item["content"]
            # Optionally enhance with metadata context (source, etc.)
            metadata_context = f" [Source: {item.get('source', 'unknown')}]"
            enhanced_text = content + metadata_context
            pairs.append([query, enhanced_text])
        
        scores = self.reranker.predict(pairs)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [items[i] for i in top_indices]
