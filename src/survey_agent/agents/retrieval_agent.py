"""
agents/retrieval_agent.py - Paper retrieval and network construction Agent

Responsibilities:
1. Search for survey papers related to the topic (duplication detection)
2. Backward traversal from seed papers (following references)
3. Forward traversal from seed papers (following citations)
4. Maintain the paper network graph (nodes=papers, edges=citation relationships)
5. Update comparison between discovered papers and user's prior knowledge
"""

from __future__ import annotations

import logging
from typing import Any

from survey_agent.interfaces.llm import LLMProvider
from survey_agent.interfaces.search import AcademicSearchAPI
from survey_agent.utils.bib_manager import BibManager
from survey_agent.utils.paper_card import PaperCard

logger = logging.getLogger(__name__)


class RetrievalAgent:
    """
    Paper retrieval and network expansion Agent.

    Uses AcademicSearchAPI to fetch paper data and builds
    a citation network centered on seed papers.
    """

    def __init__(
        self,
        search: AcademicSearchAPI,
        llm: LLMProvider,
        max_papers_per_expansion: int = 20,
    ) -> None:
        """
        Args:
            search: Academic search API (Semantic Scholar, etc.)
            llm: LLM provider (used for relevance assessment)
            max_papers_per_expansion: Maximum papers to process per expansion
        """
        self._search = search
        self._llm = llm
        self._max_per_expansion = max_papers_per_expansion

    async def search_surveys(
        self,
        topic: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search for survey papers highly relevant to the topic.

        Used in phase 2: duplication detection.

        Args:
            topic: Survey topic
            limit: Maximum number of results to return

        Returns:
            List of paper metadata (survey papers prioritized)
        """
        papers = await self._search.search_papers(
            query=topic,
            limit=limit * 2,  # Fetch more, then filter down to limit
            is_survey=True,
        )
        # Filter: keep only genuine survey papers
        survey_papers = [p for p in papers if _is_survey_paper(p)][:limit]
        logger.info(f"Found {len(survey_papers)} related surveys")
        return survey_papers

    async def assess_duplicate_surveys(
        self,
        topic: str,
        surveys: list[dict[str, Any]],
        user_angle: str,
    ) -> list[dict[str, Any]]:
        """
        Use LLM to assess overlap between existing surveys and the current topic.

        Args:
            topic: Survey topic
            surveys: List of found survey papers
            user_angle: User's unique angle

        Returns:
            List of similarity assessment results:
            [{"paper_id", "title", "year", "similarity_reason", "similarity_level"}]
            similarity_level: "identical" | "highly_similar" | "partially_similar" | "different"
        """
        if not surveys:
            return []

        survey_descriptions = "\n".join(
            f"- [{p.get('paperId', '?')}] {p.get('title', 'Unknown')} "
            f"({p.get('year', '?')}): {(p.get('abstract') or '')[:200]}..."
            for p in surveys[:10]
        )

        prompt = f"""Survey topic: {topic}
User's unique angle: {user_angle or "Not specified"}

The following are existing related surveys. Please assess their overlap with the current topic:
{survey_descriptions}

For each survey, output a JSON array where each item contains:
{{
  "paper_id": "S2 ID",
  "title": "Paper title",
  "year": year,
  "similarity_level": "identical|highly_similar|partially_similar|different",
  "similarity_reason": "One sentence explaining why they are similar or different"
}}

Output only the JSON array, no other text.
"""
        import json
        response = await self._llm.cheap_complete(
            [{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse survey similarity assessment")

        # Fallback: return original list with simple annotations
        return [
            {
                "paper_id": p.get("paperId", ""),
                "title": p.get("title", ""),
                "year": p.get("year", 0),
                "similarity_level": "partially_similar",
                "similarity_reason": "Requires manual review",
            }
            for p in surveys[:5]
        ]

    async def fetch_paper_details(
        self,
        paper_id: str,
        source: str = "unknown",
    ) -> PaperCard | None:
        """
        Fetch complete metadata for a single paper and construct a PaperCard.

        Args:
            paper_id: Semantic Scholar paper ID
            source: Source label ("seed"/"backward"/"forward"/"survey")

        Returns:
            PaperCard or None (when the paper does not exist)
        """
        data = await self._search.get_paper_details(paper_id)
        if not data:
            return None
        return PaperCard.from_s2_response(data, source=source)

    async def expand_backward(
        self,
        paper_id: str,
        existing_ids: set[str],
        limit: int | None = None,
    ) -> list[PaperCard]:
        """
        Backward expansion: get references of paper_id (papers cited by this paper).

        Args:
            paper_id: Central paper ID
            existing_ids: Set of already-processed paper IDs (skip existing)
            limit: Maximum number of results (None uses default)

        Returns:
            List of newly discovered PaperCards
        """
        max_count = limit or self._max_per_expansion
        refs = await self._search.get_references(paper_id, limit=max_count * 2)

        new_cards: list[PaperCard] = []
        for ref in refs:
            ref_id = ref.get("paperId", "")
            if not ref_id or ref_id in existing_ids:
                continue
            card = PaperCard.from_s2_response(ref, source="backward")
            new_cards.append(card)
            if len(new_cards) >= max_count:
                break

        logger.info(f"Backward expansion of {paper_id}: added {len(new_cards)} references")
        return new_cards

    async def expand_forward(
        self,
        paper_id: str,
        existing_ids: set[str],
        limit: int | None = None,
    ) -> list[PaperCard]:
        """
        Forward expansion: get papers that cite paper_id (who cited this paper).

        Sorted by influential citation count, prioritizes high-impact citing papers.

        Args:
            paper_id: Central paper ID
            existing_ids: Set of already-processed paper IDs
            limit: Maximum number of results

        Returns:
            List of newly discovered PaperCards
        """
        max_count = limit or self._max_per_expansion
        citations = await self._search.get_citations(paper_id, limit=max_count * 2)

        new_cards: list[PaperCard] = []
        for cit in citations:
            cit_id = cit.get("paperId", "")
            if not cit_id or cit_id in existing_ids:
                continue
            card = PaperCard.from_s2_response(cit, source="forward")
            new_cards.append(card)
            if len(new_cards) >= max_count:
                break

        logger.info(f"Forward expansion of {paper_id}: added {len(new_cards)} citing papers")
        return new_cards

    async def check_knowledge_alignment(
        self,
        topic: str,
        prior_knowledge: dict[str, Any],
        new_papers: list[PaperCard],
    ) -> dict[str, list[str]]:
        """
        Compare newly discovered papers against the user's prior knowledge.

        Args:
            topic: Survey topic
            prior_knowledge: User's prior knowledge extracted from dialogue
            new_papers: List of newly discovered papers

        Returns:
            {
                "confirmations": [...],  # Findings consistent with prior knowledge
                "conflicts": [...],      # Findings that conflict with prior knowledge
                "new_findings": [...],   # New discoveries beyond prior knowledge
            }
        """
        if not prior_knowledge or not new_papers:
            return {"confirmations": [], "conflicts": [], "new_findings": []}

        paper_titles = "\n".join(
            f"- {p.title} ({p.year})" for p in new_papers[:30]
        )
        known_works = "\n".join(
            f"- {w}" for w in prior_knowledge.get("known_works", [])
        )
        expected = prior_knowledge.get("expected_findings", "")

        prompt = f"""Survey topic: {topic}
Known works by user: {known_works or "None"}
User's expected findings: {expected or "None"}

Newly discovered papers:
{paper_titles}

Analyze the relationship between the new papers and the user's prior knowledge. Output JSON:
{{
  "confirmations": ["Finding description that confirms user's prior knowledge 1", ...],
  "conflicts": ["Finding description that conflicts with user's prior knowledge 1", ...],
  "new_findings": ["New finding description beyond user's prior knowledge 1", ...]
}}

Be concise, one sentence per item. Output only JSON.
"""
        import json
        response = await self._llm.cheap_complete(
            [{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        return {"confirmations": [], "conflicts": [], "new_findings": []}


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _is_survey_paper(paper: dict[str, Any]) -> bool:
    """Heuristically determine whether a paper is a survey/review."""
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()[:300]
    survey_keywords = {"survey", "review", "overview", "tutorial", "taxonomy", "systematic review"}
    return any(kw in title or kw in abstract for kw in survey_keywords)
