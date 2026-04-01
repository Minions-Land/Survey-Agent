"""
interfaces/clustering.py - Abstract interface for local clustering algorithms

Reserves injection interfaces for the following clustering algorithms:
- HDBSCAN (density-based clustering, recommended, no need to specify number of clusters)
- KMeans (K-means, requires specifying number of clusters)
- AgglomerativeClustering (hierarchical clustering)

Injection example:
    clustering = HDBSCANClustering(min_cluster_size=3)
    agent = TaxonomyAgent(clustering=clustering)

Note: VectorMemory and LocalClustering are optional dependencies.
      When not installed, the system uses LLM directly for taxonomy inference.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LocalClustering(ABC):
    """
    Abstract base class for local clustering algorithms.

    Accepts paper embedding vectors and outputs cluster labels,
    used to assist TaxonomyAgent in automatically discovering topic clusters.
    """

    @abstractmethod
    def fit_predict(
        self,
        embeddings: dict[str, list[float]],
        **kwargs: Any,
    ) -> dict[str, int]:
        """
        Cluster paper embedding vectors.

        Args:
            embeddings: {paper_id: embedding_vector} dict
            **kwargs: Algorithm-specific parameters (e.g. min_samples, min_cluster_size)

        Returns:
            {paper_id: cluster_label} dict
            cluster_label = -1 indicates noise points (HDBSCAN-specific)
            cluster_label is an integer (starting from 0)

        Raises:
            NotImplementedError: When no implementation is injected
        """
        raise NotImplementedError("TODO: Inject LocalClustering implementation")

    @abstractmethod
    def get_cluster_summary(
        self,
        embeddings: dict[str, list[float]],
        labels: dict[str, int],
    ) -> dict[int, dict[str, Any]]:
        """
        Generate statistical summaries for each cluster.

        Args:
            embeddings: Paper embedding vectors
            labels: Cluster labels returned by fit_predict

        Returns:
            {cluster_id: {"center": [...], "size": int, "paper_ids": [...]}}
        """
        raise NotImplementedError("TODO: Inject LocalClustering implementation")
