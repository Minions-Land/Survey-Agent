"""
utils/paper_card.py - Paper metadata card data model

PaperCard is the core data unit flowing through the system,
encapsulating metadata fetched from Semantic Scholar + structured notes extracted by LLM.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Core data model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PaperCard:
    """
    Complete information card for a single academic paper.

    Base metadata is fetched from the Semantic Scholar API,
    and LLM-extracted fields (key_contributions, etc.) are added by ExtractionAgent.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    s2_paper_id: str                # Semantic Scholar paper ID
    title: str
    authors: list[str]              # Author name list (in order)
    year: int
    venue: str                      # Journal/conference name (may be empty string)

    # ── Content ───────────────────────────────────────────────────────────────
    abstract: str

    # ── Citation statistics ───────────────────────────────────────────────────
    citation_count: int = 0
    influential_citation_count: int = 0

    # ── External IDs ─────────────────────────────────────────────────────────
    arxiv_id: str | None = None
    doi: str | None = None
    url: str = ""

    # ── BibTeX ───────────────────────────────────────────────────────────────
    cite_key: str = ""              # E.g. "vaswani2017attention"

    # ── Taxonomy annotation ───────────────────────────────────────────────────
    taxonomy_category_ids: list[str] = field(default_factory=list)
    # List of taxonomy node IDs this paper belongs to (may belong to multiple)

    # ── Relevance to survey topic ─────────────────────────────────────────────
    relevance_score: float = 0.0    # 0-1, scored by ExtractionAgent
    relevance_reason: str = ""

    # ── Network navigation (filled by RetrievalAgent) ────────────────────────
    reference_ids: list[str] = field(default_factory=list)   # Papers cited by this paper
    citation_ids: list[str] = field(default_factory=list)    # Papers that cite this paper

    # ── LLM-extracted fields (filled by ExtractionAgent) ─────────────────────
    key_contributions: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    comparison_to_prior: str = ""   # Comparison to prior work
    relation_to_topic: str = ""     # Relationship description to survey topic

    # ── Meta tags ────────────────────────────────────────────────────────────
    is_survey: bool = False         # Whether this paper itself is a survey
    source: str = "unknown"         # "seed" | "backward" | "forward" | "survey"
    added_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self) -> None:
        """Auto-generate cite_key after initialization (if not provided)."""
        if not self.cite_key:
            self.cite_key = generate_cite_key(self.title, self.year, self.authors)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict (for LangGraph state storage)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaperCard":
        """Restore PaperCard from dict (used when recovering from LangGraph state)."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_s2_response(cls, data: dict[str, Any], source: str = "search") -> "PaperCard":
        """
        Construct PaperCard from Semantic Scholar API response.

        Args:
            data: Paper dict returned by S2 API
            source: Paper source label
        """
        authors = [
            a.get("name", "") for a in data.get("authors", [])
        ]
        external_ids = data.get("externalIds") or {}

        return cls(
            s2_paper_id=data.get("paperId", ""),
            title=data.get("title", ""),
            authors=authors,
            year=data.get("year") or 0,
            venue=data.get("venue") or (data.get("journal") or {}).get("name", ""),
            abstract=data.get("abstract") or "",
            citation_count=data.get("citationCount") or 0,
            influential_citation_count=data.get("influentialCitationCount") or 0,
            arxiv_id=external_ids.get("ArXiv"),
            doi=external_ids.get("DOI"),
            url=data.get("url") or "",
            is_survey=_detect_is_survey(data.get("title", ""), data.get("abstract") or ""),
            source=source,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def generate_cite_key(title: str, year: int, authors: list[str]) -> str:
    """
    Generate a BibTeX cite_key in the format: {first_author_last_name}{year}{first_title_word}

    Example: "Attention Is All You Need", 2017, ["Vaswani, A.", ...]
             -> "vaswani2017attention"

    Rules:
    - All lowercase
    - Only ASCII alphanumerics retained
    - If no author, use "anon"
    - If no year, use "0000"
    """
    # First author's last name
    first_author = _extract_last_name(authors[0]) if authors else "anon"

    # First meaningful word of title (excluding stop words)
    stop_words = {"a", "an", "the", "is", "are", "of", "in", "on", "at",
                  "to", "for", "and", "or", "but", "with", "from", "by"}
    title_words = re.sub(r"[^a-zA-Z0-9\s]", "", title.lower()).split()
    title_word = next((w for w in title_words if w not in stop_words), "paper")

    year_str = str(year) if year else "0000"
    raw_key = f"{first_author}{year_str}{title_word}"

    # Keep only ASCII alphanumerics
    return re.sub(r"[^a-z0-9]", "", raw_key.lower())


def _extract_last_name(author: str) -> str:
    """Extract last name from author string (supports 'Last, First' and 'First Last' formats)."""
    author = _normalize_unicode(author.strip())
    if "," in author:
        # "Last, First" format
        last = author.split(",")[0].strip()
    else:
        # "First Last" format
        parts = author.split()
        last = parts[-1] if parts else author

    # Remove non-alpha characters, convert to lowercase
    return re.sub(r"[^a-z]", "", last.lower())


def _normalize_unicode(text: str) -> str:
    """Normalize Unicode characters to ASCII (e.g. ü -> u)."""
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _detect_is_survey(title: str, abstract: str) -> bool:
    """Heuristically determine whether a paper is a survey/review article."""
    survey_keywords = {
        "survey", "review", "overview", "tutorial", "taxonomy",
        "systematic review", "literature review", "comprehensive review",
        "survey of", "review of",
    }
    combined = (title + " " + abstract[:200]).lower()
    return any(kw in combined for kw in survey_keywords)
