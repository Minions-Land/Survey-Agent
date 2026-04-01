"""
interfaces/memory.py - Abstract interface for vector memory stores

Reserves injection interfaces for the following vector databases:
- ChromaDB (local, recommended for getting started)
- Pinecone (cloud, production-grade)
- Weaviate
- pgvector (PostgreSQL extension)

Injection example:
    memory = ChromaVectorMemory(persist_dir="data/chroma")
    agent = TaxonomyAgent(memory=memory)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorMemory(ABC):
    """
    Abstract base class for vector memory stores.

    Used for:
    1. Storing semantic vector representations of paper abstracts
    2. Retrieving semantically similar papers during taxonomy construction
    3. Supporting content-based paper clustering
    """

    @abstractmethod
    async def add_paper(
        self,
        paper_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Add a paper to the vector store (abstract + metadata).

        Args:
            paper_id: Paper ID (used as unique key in the vector store)
            text: Text to embed (typically title + abstract)
            metadata: Associated metadata (year, venue, cite_key, etc.)
        """
        raise NotImplementedError("TODO: Inject VectorMemory implementation")

    @abstractmethod
    async def search_similar(
        self,
        query_text: str,
        limit: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for papers by semantic similarity.

        Args:
            query_text: Query text (topic description or abstract fragment)
            limit: Number of results to return
            filter_metadata: Metadata filter conditions (e.g. {"year": {"$gt": 2020}})

        Returns:
            List of similar papers, each containing:
            {
                "paper_id": str,
                "score": float,        # Similarity score (0-1)
                "metadata": dict,
            }
        """
        raise NotImplementedError("TODO: Inject VectorMemory implementation")

    @abstractmethod
    async def delete_paper(self, paper_id: str) -> None:
        """Remove the specified paper from the vector store."""
        raise NotImplementedError("TODO: Inject VectorMemory implementation")

    @abstractmethod
    async def get_all_embeddings(self) -> dict[str, list[float]]:
        """
        Return the embedding vectors of all stored papers (for offline clustering).

        Returns:
            {paper_id: embedding_vector}
        """
        raise NotImplementedError("TODO: Inject VectorMemory implementation")
