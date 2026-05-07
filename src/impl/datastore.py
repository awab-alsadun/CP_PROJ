from typing import List
from concurrent.futures import ThreadPoolExecutor
import json

import lancedb
import pyarrow as pa
from lancedb.table import Table

from src.interface.base_datastore import BaseDatastore, DataItem
from src.util.get_embeddings import get_embeddings


class Datastore(BaseDatastore):

    DB_PATH = "data/sample-lancedb"
    DB_TABLE_NAME = "rag-table"

    def __init__(self):
        self.embedding_dimension = 384
        self.vector_db = lancedb.connect(self.DB_PATH)
        self.table: Table = self._get_table()

    def reset(self) -> Table:
        try:
            self.vector_db.drop_table(self.DB_TABLE_NAME)
        except Exception:
            pass

        schema = pa.schema(
            [
                pa.field("vector", pa.list_(pa.float32(), self.embedding_dimension)),
                pa.field("content", pa.utf8()),
                pa.field("source", pa.utf8()),
                pa.field("metadata", pa.utf8()),  # Store as JSON string
            ]
        )

        self.vector_db.create_table(self.DB_TABLE_NAME, schema=schema)
        self.table = self.vector_db.open_table(self.DB_TABLE_NAME)
        return self.table

    def get_vector(self, content: str) -> List[float]:
        return get_embeddings(content)

    def add_items(self, items: List[DataItem]) -> None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            entries = list(executor.map(self._convert_item_to_entry, items))

        self.table.merge_insert("content") \
            .when_matched_update_all() \
            .when_not_matched_insert_all() \
            .execute(entries)

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        vector = self.get_vector(query)

        results = (
            self.table.search(vector)
            .select(["content", "source", "metadata"])
            .limit(top_k)
            .to_list()
        )

        # Parse metadata JSON strings back to dicts
        parsed_results = []
        for row in results:
            metadata = {}
            if row.get("metadata"):
                try:
                    metadata = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    pass
            parsed_results.append({
                "content": row["content"],
                "source": row["source"],
                "metadata": metadata,
            })
        return parsed_results

    def _get_table(self) -> Table:
        try:
            return self.vector_db.open_table(self.DB_TABLE_NAME)
        except Exception:
            return self.reset()

    def _convert_item_to_entry(self, item: DataItem) -> dict:
        # Extract source from metadata (indexer sets source_id and source_type)
        source = item.metadata.get("source_id", "unknown") if item.metadata else "unknown"
        return {
            "vector": self.get_vector(item.content),
            "content": item.content,
            "source": source,
            "metadata": json.dumps(item.metadata),  # Convert dict to JSON string
        }
