"""
utils/bib_manager.py - BibTeX manager (anti-hallucination citations)

Core principle: Writer Agent can only cite papers registered in this library,
                preventing LLM from generating non-existent references.

Workflow:
1. After RetrievalAgent fetches papers, call bib_manager.register_paper() to register
2. WriterAgent gets available citation list from bib_manager.get_all_cite_keys()
3. After writing, call bib_manager.validate_citations(text) to check validity
4. Call bib_manager.generate_bibliography() to generate the complete BibTeX file
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from survey_agent.utils.paper_card import PaperCard, generate_cite_key


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BibEntry:
    """Single BibTeX record."""
    cite_key: str           # Unique citation key, e.g. "vaswani2017attention"
    entry_type: str         # "article" | "inproceedings" | "misc" | "techreport"
    title: str
    authors: list[str]
    year: int
    venue: str              # journal/booktitle
    volume: str = ""
    pages: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    abstract_snippet: str = ""  # Store first 200 characters for writing reference

    def to_bibtex(self) -> str:
        """Generate standard BibTeX string."""
        # Author list format: "Last, First and Last2, First2 and ..."
        author_str = " and ".join(self.authors)

        # Choose field based on entry type
        if self.entry_type == "inproceedings":
            venue_field = f"  booktitle = {{{self.venue}}},"
        else:
            venue_field = f"  journal   = {{{self.venue}}},"

        lines = [
            f"@{self.entry_type}{{{self.cite_key},",
            f"  title     = {{{{{self.title}}}}},",
            f"  author    = {{{author_str}}},",
            f"  year      = {{{self.year}}},",
            venue_field,
        ]

        if self.volume:
            lines.append(f"  volume    = {{{self.volume}}},")
        if self.pages:
            lines.append(f"  pages     = {{{self.pages}}},")
        if self.doi:
            lines.append(f"  doi       = {{{self.doi}}},")
        if self.arxiv_id:
            lines.append(f"  eprint    = {{{self.arxiv_id}}},")
            lines.append(f"  archivePrefix = {{arXiv}},")
        if self.url:
            lines.append(f"  url       = {{{self.url}}},")

        lines.append("}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Manager
# ──────────────────────────────────────────────────────────────────────────────

class BibManager:
    """
    BibTeX registry and validator.

    Anti-hallucination mechanism:
    - All registered papers originate from API-verified Semantic Scholar data
    - Writing prompt explicitly lists the available cite_key set
    - After writing, validate all \\cite{} citations are in the registry
    """

    def __init__(self) -> None:
        self._registry: dict[str, BibEntry] = {}  # cite_key -> BibEntry
        # Used to resolve cite_key conflicts (same name but different papers)
        self._key_counters: dict[str, int] = {}

    def register_paper(self, paper: PaperCard) -> str:
        """
        Register a paper in the citation library.

        Args:
            paper: API-verified PaperCard

        Returns:
            Final assigned cite_key (may be modified due to conflict, e.g. "vaswani2017attention_2")
        """
        base_key = paper.cite_key or generate_cite_key(
            paper.title, paper.year, paper.authors
        )
        cite_key = self._resolve_key_conflict(base_key)

        # Infer venue type (heuristic)
        entry_type = _infer_entry_type(paper.venue)

        entry = BibEntry(
            cite_key=cite_key,
            entry_type=entry_type,
            title=paper.title,
            authors=paper.authors,
            year=paper.year,
            venue=paper.venue,
            doi=paper.doi or "",
            arxiv_id=paper.arxiv_id or "",
            url=paper.url,
            abstract_snippet=paper.abstract[:200] if paper.abstract else "",
        )

        self._registry[cite_key] = entry
        return cite_key

    def register_from_dict(self, paper_dict: dict[str, Any]) -> str:
        """Register from PaperCard.to_dict() format dict."""
        paper = PaperCard.from_dict(paper_dict)
        return self.register_paper(paper)

    def is_registered(self, cite_key: str) -> bool:
        """Check whether a cite_key is registered."""
        return cite_key in self._registry

    def get_entry(self, cite_key: str) -> BibEntry | None:
        """Get details for a specific citation."""
        return self._registry.get(cite_key)

    def get_all_cite_keys(self) -> list[str]:
        """Get list of all registered cite_keys (for use in writing prompts)."""
        return sorted(self._registry.keys())

    def get_cite_key_summary(self) -> str:
        """
        Generate a summary string of available citations (inserted directly into writing prompts).

        Format:
        Available citations (must only choose from these cite_keys):
        - vaswani2017attention: "Attention Is All You Need" (Vaswani et al., 2017)
        - ...
        """
        lines = [
            "Available citations (must only use cite_keys listed below; using any unlisted citation is strictly prohibited):\n"
        ]
        for key, entry in sorted(self._registry.items()):
            first_author = entry.authors[0] if entry.authors else "Unknown"
            # Extract last name
            last_name = first_author.split(",")[0] if "," in first_author else first_author.split()[-1]
            et_al = " et al." if len(entry.authors) > 1 else ""
            lines.append(
                f"- \\cite{{{key}}}: \"{entry.title}\" ({last_name}{et_al}, {entry.year})"
            )
        return "\n".join(lines)

    def validate_citations(self, text: str) -> tuple[bool, list[str]]:
        """
        Validate that all \\cite{} citations in the text are registered.

        Args:
            text: Text containing LaTeX \\cite{} commands

        Returns:
            (is_valid, list_of_invalid_keys)
            is_valid = True means all citations are valid
        """
        # Match \cite{key} and \cite{key1, key2}
        pattern = r"\\cite\{([^}]+)\}"
        matches = re.findall(pattern, text)

        invalid_keys: list[str] = []
        for match in matches:
            # Handle multi-citation \cite{key1, key2}
            keys = [k.strip() for k in match.split(",")]
            for key in keys:
                if key and not self.is_registered(key):
                    invalid_keys.append(key)

        return len(invalid_keys) == 0, invalid_keys

    def generate_bibliography(self) -> str:
        """
        Generate the complete BibTeX file content.

        Returns:
            BibTeX file string containing all registered papers
        """
        sections = [
            "% ============================================================",
            "% Auto-generated by Survey Agent",
            "% All entries are from Semantic Scholar API-verified data",
            "% ============================================================",
            "",
        ]
        for entry in sorted(self._registry.values(), key=lambda e: e.cite_key):
            sections.append(entry.to_bibtex())
            sections.append("")

        return "\n".join(sections)

    def export_to_state(self) -> dict[str, str]:
        """Export to LangGraph state-compatible format {cite_key: bibtex_string}."""
        return {key: entry.to_bibtex() for key, entry in self._registry.items()}

    @classmethod
    def from_state(cls, state_bib: dict[str, str]) -> "BibManager":
        """
        Restore BibManager from LangGraph state.

        Args:
            state_bib: state["bib_entries"] field
        """
        manager = cls()
        # Restore only cite_key from BibTeX string (full parsing requires bibtexparser)
        for cite_key in state_bib:
            # Simplified version: only record key, don't parse full BibTeX
            manager._registry[cite_key] = _stub_entry_from_bibtex(cite_key, state_bib[cite_key])
        return manager

    def _resolve_key_conflict(self, base_key: str) -> str:
        """Handle cite_key conflicts by automatically appending a numeric suffix."""
        if base_key not in self._registry:
            return base_key
        # Already exists, append counter
        count = self._key_counters.get(base_key, 1) + 1
        self._key_counters[base_key] = count
        return f"{base_key}_{count}"


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _infer_entry_type(venue: str) -> str:
    """Heuristically determine BibTeX entry type from venue string."""
    if not venue:
        return "misc"
    venue_lower = venue.lower()
    conference_keywords = {
        "conference", "proceedings", "workshop", "symposium",
        "acl", "emnlp", "naacl", "icml", "nips", "neurips",
        "iclr", "cvpr", "iccv", "eccv", "aaai", "ijcai",
        "sigir", "www", "kdd", "cikm", "wsdm", "icassp",
    }
    if any(kw in venue_lower for kw in conference_keywords):
        return "inproceedings"
    return "article"


def _stub_entry_from_bibtex(cite_key: str, bibtex_str: str) -> BibEntry:
    """Extract basic fields from BibTeX string (lightweight version, no bibtexparser dependency)."""
    def _extract(pattern: str, text: str, default: str = "") -> str:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    title = _extract(r"title\s*=\s*\{+([^}]+)\}+", bibtex_str)
    year_str = _extract(r"year\s*=\s*\{(\d{4})\}", bibtex_str)

    return BibEntry(
        cite_key=cite_key,
        entry_type="article",
        title=title or cite_key,
        authors=[],
        year=int(year_str) if year_str else 0,
        venue="",
    )
