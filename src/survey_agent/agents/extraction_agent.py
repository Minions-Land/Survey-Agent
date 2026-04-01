"""
agents/extraction_agent.py - Structured information extraction Agent

Responsible for extracting from each paper's abstract (and available full-text):
- Core contributions
- Methods/techniques
- Datasets used
- Limitations
- Comparison to prior work
- Relationship to the survey topic

Uses cheap_model (Haiku) for large-scale batch extraction to reduce costs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from survey_agent.interfaces.llm import LLMProvider
from survey_agent.utils.paper_card import PaperCard

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


class ExtractionAgent:
    """
    Paper structured information extraction Agent.

    Generates structured "notes" for each paper,
    for use by TaxonomyAgent and WriterAgent.

    Supports multiple reading depths:
      - skim: title + abstract only (fast, minimal output)
      - standard: title + abstract + intro + methods (default, balanced)
      - deep: full paper text (thorough, expensive)

    Uses survey-specific prompts when paper.is_survey is True.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm
        # Depth-specific prompts for regular papers
        self._prompt_skim = self._load_prompt("read_skim.md")
        self._prompt_standard = self._load_prompt("read_standard.md")
        self._prompt_deep = self._load_prompt("read_deep.md")
        # Survey-specific prompt
        self._prompt_survey = self._load_prompt("read_survey.md")
        # Legacy fallback
        self._extraction_prompt = self._load_prompt("extraction_card.md")

    def _load_prompt(self, filename: str) -> str:
        path = _PROMPT_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _select_prompt(self, paper: PaperCard, reading_depth: str) -> tuple[str, int]:
        """Select system prompt and max_tokens based on paper type and depth."""
        if paper.is_survey:
            return (self._prompt_survey or _DEFAULT_EXTRACTION_SYSTEM, 3000)
        depth_map = {
            "skim": (self._prompt_skim, 800),
            "standard": (self._prompt_standard, 2000),
            "deep": (self._prompt_deep, 4000),
        }
        prompt, tokens = depth_map.get(reading_depth, depth_map["standard"])
        return (prompt or self._extraction_prompt or _DEFAULT_EXTRACTION_SYSTEM, tokens)

    async def extract_paper_info(
        self,
        paper: PaperCard,
        topic: str,
        reading_depth: str = "standard",
        paper_text: str = "",
    ) -> dict[str, Any]:
        """
        Extract structured information from a single paper.

        Args:
            paper: Paper card (requires title, abstract)
            topic: Survey topic (for relevance assessment)
            reading_depth: "skim" | "standard" | "deep"
            paper_text: Additional text from PDF (intro+methods or full text)
        """
        if not paper.abstract and not paper_text:
            logger.warning(f"Paper {paper.s2_paper_id} has no abstract, skipping extraction")
            return _empty_extraction()

        system, max_tokens = self._select_prompt(paper, reading_depth)

        # Build content based on available text
        content = _build_extraction_prompt(paper, topic, reading_depth, paper_text)

        messages = [{"role": "user", "content": content}]

        response = await self._llm.cheap_complete(
            messages,
            system=system,
            max_tokens=max_tokens,
        )

        return _parse_extraction_response(response, paper)

    async def extract_batch(
        self,
        papers: list[PaperCard],
        topic: str,
        reading_depth: str = "standard",
        paper_storage: Any = None,
        progress_callback: Any = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Batch extract paper information (sequential, respects rate limits).

        Args:
            papers: List of papers to extract
            topic: Survey topic
            reading_depth: "skim" | "standard" | "deep"
            paper_storage: Optional PaperStorage for reading PDF content
            progress_callback: Optional callback(current, total, paper_title)
        """
        results: dict[str, dict[str, Any]] = {}
        total = len(papers)

        for i, paper in enumerate(papers):
            if progress_callback:
                progress_callback(i + 1, total, paper.title[:50])

            # Fetch paper text from storage based on depth
            paper_text = ""
            if paper_storage and reading_depth in ("standard", "deep"):
                paper_text = self._get_paper_text(paper, paper_storage, reading_depth)

            extraction = await self.extract_paper_info(
                paper, topic, reading_depth=reading_depth, paper_text=paper_text,
            )
            results[paper.s2_paper_id] = extraction

        logger.info(f"Completed {reading_depth} extraction for {total} papers")
        return results

    @staticmethod
    def _get_paper_text(paper: PaperCard, paper_storage: Any, depth: str) -> str:
        """Get paper text from PaperStorage based on reading depth."""
        try:
            pid = paper.s2_paper_id
            if depth == "deep":
                return paper_storage.read_full_paper(pid) or ""
            else:  # standard
                return paper_storage.read_abstract_pages(pid) or ""
        except Exception:
            return ""

    async def update_paper_card(
        self,
        paper: PaperCard,
        extraction: dict[str, Any],
    ) -> PaperCard:
        """
        Merge extraction results back into PaperCard (returns new object, original unchanged).

        Args:
            paper: Original PaperCard
            extraction: Return value from extract_paper_info

        Returns:
            Updated PaperCard
        """
        from dataclasses import replace
        return replace(
            paper,
            key_contributions=extraction.get("key_contributions", []),
            methods=extraction.get("methods", []),
            datasets=extraction.get("datasets", []),
            limitations=extraction.get("limitations", []),
            comparison_to_prior=extraction.get("comparison_to_prior", ""),
            relation_to_topic=extraction.get("relation_to_topic", ""),
            relevance_score=extraction.get("relevance_score", 0.5),
            relevance_reason=extraction.get("relevance_reason", ""),
        )

    def generate_paper_note(self, paper: PaperCard) -> str:
        """
        Render a PaperCard as a Markdown-formatted paper note (for WriterAgent reference).

        Format:
        ### vaswani2017attention
        **Attention Is All You Need** (Vaswani et al., 2017)
        - Key contributions: ...
        - Methods: ...
        ...
        """
        authors_str = _format_authors(paper.authors)
        lines = [
            f"### \\cite{{{paper.cite_key}}}",
            f"**{paper.title}** ({authors_str}, {paper.year})",
            f"*Published in: {paper.venue or 'Unknown venue'}*",
            "",
        ]

        if paper.key_contributions:
            lines.append("**Key Contributions:**")
            for c in paper.key_contributions:
                lines.append(f"- {c}")
            lines.append("")

        if paper.methods:
            lines.append("**Methods/Techniques:**")
            for m in paper.methods:
                lines.append(f"- {m}")
            lines.append("")

        if paper.datasets:
            lines.append(f"**Datasets:** {', '.join(paper.datasets)}")
            lines.append("")

        if paper.limitations:
            lines.append("**Limitations:**")
            for lim in paper.limitations:
                lines.append(f"- {lim}")
            lines.append("")

        if paper.relation_to_topic:
            lines.append(f"**Relation to topic:** {paper.relation_to_topic}")
            lines.append("")

        lines.append(f"*Relevance score: {paper.relevance_score:.1f}* | *Source: {paper.source}*")
        lines.append("")

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _build_extraction_prompt(
    paper: PaperCard, topic: str, reading_depth: str = "standard", paper_text: str = "",
) -> str:
    authors_str = _format_authors(paper.authors)
    sections = [
        f"Survey topic: {topic}",
        "",
        "Paper information:",
        f"Title: {paper.title}",
        f"Authors: {authors_str}",
        f"Year: {paper.year}",
        f"Published in: {paper.venue or 'Unknown'}",
        f"Citation count: {paper.citation_count}",
    ]

    if paper.abstract:
        sections.append(f"\nAbstract:\n{paper.abstract}")

    if paper_text and reading_depth in ("standard", "deep"):
        label = "Full paper text" if reading_depth == "deep" else "Introduction and methods"
        # Truncate to budget: standard ~8k chars, deep ~25k chars
        limit = 25_000 if reading_depth == "deep" else 8_000
        sections.append(f"\n{label}:\n{paper_text[:limit]}")

    sections.append("\nPlease extract the structured information and output JSON only.")
    return "\n".join(sections)


def _parse_extraction_response(response: str, paper: PaperCard) -> dict[str, Any]:
    """Parse the JSON extraction result returned by the LLM."""
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response[start:end])
            # Ensure relevance_score is within valid range
            score = result.get("relevance_score", 0.5)
            result["relevance_score"] = max(0.0, min(1.0, float(score)))
            return result
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"Failed to parse extraction for {paper.title}: {e}")

    return _empty_extraction()


def _empty_extraction() -> dict[str, Any]:
    return {
        "key_contributions": [],
        "methods": [],
        "datasets": [],
        "limitations": [],
        "comparison_to_prior": "",
        "relation_to_topic": "",
        "relevance_score": 0.3,
        "relevance_reason": "Abstract missing or parsing failed",
    }


def _format_authors(authors: list[str]) -> str:
    """Format the author list as 'First, Second, et al.'."""
    if not authors:
        return "Unknown"
    if len(authors) <= 2:
        return " and ".join(authors)
    return f"{authors[0]} et al."


_DEFAULT_EXTRACTION_SYSTEM = """\
You are an expert in extracting information from academic papers.
Extract key information from the given paper title and abstract and output structured JSON.
Requirements:
1. Output only JSON, no additional text
2. Each item in key_contributions should be concise (one sentence)
3. relevance_score: 0=completely irrelevant, 1=core paper
4. If the abstract is insufficient to determine a field, leave it as an empty list or empty string
"""
