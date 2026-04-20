from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class DataItem(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseDatastore(ABC):
    @abstractmethod
    def add_items(self, items: List[DataItem]) -> None:
        pass

    @abstractmethod
    def get_vector(self, content: str) -> List[float]:
        pass

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[DataItem]:
        pass
