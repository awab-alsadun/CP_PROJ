from src.interface.base_datastore import BaseDatastore
from src.interface.base_retriever import BaseRetriever
from sentence_transformers import CrossEncoder
import numpy as np


class Retriever(BaseRetriever):
    def __init__(self, datastore: BaseDatastore):
        self.datastore = datastore
        self.reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

    def search(self, query: str, top_k: int = 3) -> list[str]:
        search_results = self.datastore.search(query, top_k=top_k * 3)
        reranked_results = self._rerank(query, search_results, top_k=top_k)
        return reranked_results

    def _rerank(
        self, query: str, search_results: list[str], top_k: int = 10
    ) -> list[str]:

        # Score each result with the query
        pairs = [[query, doc] for doc in search_results]
        scores = self.reranker.predict(pairs)
        
        # Get indices of top_k highest scores
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        print(f"✅ Reranked Indices: {top_indices.tolist()}")
        return [search_results[i] for i in top_indices]
