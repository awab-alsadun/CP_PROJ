from typing import List
import os
import re

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document

from src.interface.base_indexer import BaseIndexer
from src.interface.base_datastore import DataItem


class Indexer(BaseIndexer):

    def __init__(self):
        self.node_parser = SentenceSplitter(
            chunk_size=300,
            chunk_overlap=50,
        )

    def index(self, document_paths: List[str]) -> List[DataItem]:
        items: List[DataItem] = []

        for path in document_paths:
            source_id = os.path.basename(path)

            raw_docs = SimpleDirectoryReader(
                input_files=[path]
            ).load_data()

            documents = [
                Document(
                    text=self._normalize_text(doc.text),
                    metadata={
                        **doc.metadata,
                        "source_id": source_id,
                        "source_type": self._infer_source_type(path),
                    },
                )
                for doc in raw_docs
            ]

            nodes = self.node_parser.get_nodes_from_documents(documents)

            for idx, node in enumerate(nodes):
                items.append(
                    DataItem(
                        content=node.text,
                        metadata={
                            **node.metadata,
                            "chunk_id": f"{source_id}_chunk_{idx}",
                        },
                    )
                )

        return items

    def _normalize_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _infer_source_type(self, path: str) -> str:
        return os.path.splitext(path)[1].lstrip(".").lower()
