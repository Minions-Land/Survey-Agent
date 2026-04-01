"""
interfaces/search.py - Abstract interface for academic literature search APIs

Reserves injection interfaces for the following services:
- Semantic Scholar (free, recommended)
- OpenAlex (open, rich metadata)
- ArXiv API
- CrossRef

Injection example:
    api = SemanticScholarAPI(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"))
    agent = RetrievalAgent(search=api)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AcademicSearchAPI(ABC):
    """Abstract base class for academic literature search APIs."""

    @abstractmethod
    async def search_papers(
        self,
        query: str,
        limit: int = 20,
        fields: list[str] | None = None,
        year_range: tuple[int, int] | None = None,
        is_survey: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Search papers by keyword.

        Args:
            query: Search query (supports boolean operators)
            limit: Maximum number of results to return
            fields: List of fields to return (None returns default fields)
            year_range: (start_year, end_year) year filter
            is_survey: When True, prioritize survey/review papers

        Returns:
            List of paper metadata dicts, each containing:
            {
                "paper_id": str,       # Platform-internal ID
                "title": str,
                "authors": [{"name": str, "authorId": str}],
                "year": int,
                "abstract": str,
                "venue": str,          # Publication journal/conference
                "citation_count": int,
                "influential_citation_count": int,
                "is_open_access": bool,
                "external_ids": {"ArXiv": ..., "DOI": ..., "PubMed": ...},
                "url": str,
            }

        Raises:
            NotImplementedError: When no implementation is injected
        """
        raise NotImplementedError("TODO: Inject AcademicSearchAPI implementation")

    @abstractmethod
    async def get_paper_details(
        self,
        paper_id: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve detailed information for a single paper.

        Args:
            paper_id: Platform paper ID (Semantic Scholar format: "S2PaperId")
            fields: Required fields (None returns all basic fields)

        Returns:
            Paper detail dict with same keys as search_papers returns;
            None if the paper does not exist
        """
        raise NotImplementedError("TODO: Inject AcademicSearchAPI implementation")

    @abstractmethod
    async def get_references(
        self,
        paper_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get the reference list of a paper (papers cited by this paper).

        Use this method for backward traversal.

        Args:
            paper_id: Target paper ID
            limit: Maximum number of references to return

        Returns:
            List of reference paper metadata (same format as search_papers)
        """
        raise NotImplementedError("TODO: Inject AcademicSearchAPI implementation")

    @abstractmethod
    async def get_citations(
        self,
        paper_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get the list of papers that cite this paper (who cited this paper).

        Use this method for forward traversal.

        Args:
            paper_id: Target paper ID
            limit: Maximum number of results (sorted by influence)

        Returns:
            List of citing paper metadata
        """
        raise NotImplementedError("TODO: Inject AcademicSearchAPI implementation")

    @abstractmethod
    async def get_batch_details(
        self,
        paper_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        Retrieve detailed information for multiple papers in batch (reduces HTTP requests).

        Args:
            paper_ids: List of paper IDs (up to 500)

        Returns:
            List of paper details, in the same order as input IDs
        """
        raise NotImplementedError("TODO: Inject AcademicSearchAPI implementation")
