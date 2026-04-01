"""
state.py - Global state definition for Survey Agent

Uses TypedDict to ensure compatibility with LangGraph serialization.
All fields must be JSON-serializable.
"""

from __future__ import annotations

import operator
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional

from typing_extensions import TypedDict


# ──────────────────────────────────────────────────────────────────────────────
# Phase Enum
# ──────────────────────────────────────────────────────────────────────────────

class Phase(str, Enum):
    """Survey Agent workflow phases."""
    DIALOGUE = "dialogue"                    # Discuss topic with user, understand prior knowledge
    SURVEY_SEARCH = "survey_search"          # Retrieve existing surveys, check for duplicates
    RESEARCH = "research"                    # Build paper knowledge network (forward/backward expansion)
    EXTRACTION = "extraction"               # Structured extraction of each paper's contributions
    TAXONOMY_REVIEW = "taxonomy_review"     # Human confirmation of taxonomy (on major category changes)
    WRITING = "writing"                     # Write survey sections
    COMPLETE = "complete"                   # Finished


class TaxonomySensitivity(str, Enum):
    """Human-in-the-loop sensitivity for taxonomy updates."""
    STRICT = "strict"       # All changes require confirmation
    BALANCED = "balanced"   # Major category changes require confirmation, minor ones are automatic
    LIBERAL = "liberal"     # All changes are automatic


# ──────────────────────────────────────────────────────────────────────────────
# Main State TypedDict
# ──────────────────────────────────────────────────────────────────────────────

class SurveyState(TypedDict, total=False):
    """
    Global state for Survey Agent.

    LangGraph nodes receive this state and return partial updates (dict),
    which the framework automatically merges into the overall state.

    Notes:
    - All values must be JSON-serializable (no Python objects, no datetime instances)
    - messages uses Annotated[List, operator.add] for append-semantic merging
    - Large paper data is stored in the papers field (dict of dicts)
    """

    # ── Session metadata ──────────────────────────────────────────────────────
    session_id: str             # Unique session ID
    phase: str                  # Current phase (Phase enum value)
    started_at: str             # ISO timestamp

    # ── User input and prior knowledge ───────────────────────────────────────
    topic: str                  # Survey topic (user input)
    seed_paper_ids: list[str]   # Seed paper IDs (derived from reference_materials for compat)
    reference_materials: list[dict[str, Any]]
    # Uploaded reference materials:
    # [
    #   {"type": "paper_id", "value": "s2_id_here"},
    #   {"type": "paper_pdf", "filename": "paper.pdf", "path": "/abs/path"},
    #   {"type": "paper_title", "value": "Attention Is All You Need"},
    #   {"type": "start_document", "filename": "plan.md", "path": "/abs/path"}
    # ]
    start_document_text: str    # Extracted text from the Start document (empty if not provided)
    reading_depth: str          # "skim" | "standard" | "deep" (default: "standard")
    prior_knowledge: dict[str, Any]
    # Structure example:
    # {
    #   "known_concepts": ["Transformer", "attention mechanism"],
    #   "known_works": ["Vaswani et al. 2017"],
    #   "expected_findings": "attention replaces RNN",
    #   "research_questions": ["Why is attention better"],
    #   "unique_angle": "Re-analyze from hardware efficiency perspective"
    # }
    user_angle: str             # The unique angle the user wants the survey to focus on
    taxonomy_user_defined: dict[str, Any]
    # User-predefined taxonomy (optional), same format as taxonomy field

    # ── Dialogue state ────────────────────────────────────────────────────────
    dialogue_turn: int          # Current dialogue turn number
    dialogue_complete: bool     # Whether the dialogue is complete

    # ── Paper knowledge network ───────────────────────────────────────────────
    papers: dict[str, dict[str, Any]]
    # paper_id -> PaperCard.to_dict(), contains abstract, authors, year, citation count, etc.

    paper_edges: list[dict[str, str]]
    # Edge list: [{"from_id": ..., "to_id": ..., "edge_type": "reference"|"citation"}]

    # ── Research progress ─────────────────────────────────────────────────────
    frontier: list[str]         # Queue of paper IDs to be processed
    processed: list[str]        # Set of already-processed paper IDs
    duplicate_surveys: list[dict[str, Any]]
    # List of similar existing surveys: [{"paper_id", "title", "year", "similarity_reason"}]

    # ── Findings vs. user prior knowledge ────────────────────────────────────
    knowledge_confirmations: list[str]  # Findings consistent with user's prior knowledge
    knowledge_conflicts: list[str]      # Findings that conflict with user's prior knowledge
    new_findings: list[str]             # New discoveries beyond user's prior knowledge

    # ── Taxonomy ──────────────────────────────────────────────────────────────
    taxonomy: dict[str, Any]
    # Structure example:
    # {
    #   "version": 3,
    #   "categories": [
    #     {
    #       "id": "cat_01",
    #       "name": "Attention Mechanisms",
    #       "description": "...",
    #       "parent_id": null,
    #       "paper_ids": ["paper_123", ...],
    #       "subcategories": [...]
    #     }
    #   ],
    #   "changelog": ["v1: initial taxonomy", "v2: split Efficient Attention"]
    # }
    taxonomy_sensitivity: str   # TaxonomySensitivity enum value
    pending_taxonomy_update: Optional[dict[str, Any]]
    # Pending taxonomy update proposal (filled by TaxonomyAgent on major changes)

    # ── Structured extraction results ─────────────────────────────────────────
    paper_notes: dict[str, str]
    # paper_id -> structured notes (Markdown format, includes contributions/methods/limitations)

    # ── Survey writing ────────────────────────────────────────────────────────
    outline: list[dict[str, Any]]
    # Section outline: [{"section_id", "title", "description", "paper_ids", "order"}]
    draft_sections: dict[str, str]
    # section_id -> section draft (Markdown format)
    bib_entries: dict[str, str]
    # cite_key -> BibTeX entry string (full @article{...} format)

    # ── Human-computer interaction state ─────────────────────────────────────
    # LangGraph interrupt mechanism: node calls interrupt(human_prompt) to pause
    # CLI reads user input then calls Command(resume=user_input) to resume

    # ── Session message history ───────────────────────────────────────────────
    messages: Annotated[list[dict[str, str]], operator.add]
    # Append-semantic: [{"role": "agent"|"user", "content": ..., "timestamp": ...}]

    # ── Statistics ────────────────────────────────────────────────────────────
    total_papers_found: int
    error: Optional[str]        # Last error message (if any)

    # ── Output configuration ──────────────────────────────────────────────────
    output_format: str          # "markdown" (default) or "latex"
    generate_mindmap: bool      # Whether to generate a mind map

    # ── Local paper storage ───────────────────────────────────────────────────
    local_papers_dir: Optional[str]  # Local PDF storage directory (None = don't use local PDFs)

    # ── Research scale limits ─────────────────────────────────────────────────
    max_papers: int                  # Hard cap on total papers (default 200)


# ──────────────────────────────────────────────────────────────────────────────
# Initial state factory
# ──────────────────────────────────────────────────────────────────────────────

def create_initial_state(
    topic: str,
    seed_paper_ids: list[str] | None = None,
    taxonomy_sensitivity: str = TaxonomySensitivity.BALANCED,
    user_defined_taxonomy: dict[str, Any] | None = None,
    output_format: str = "markdown",
    generate_mindmap: bool = False,
    local_papers_dir: str | None = None,
    reference_materials: list[dict[str, Any]] | None = None,
    start_document_text: str = "",
    reading_depth: str = "standard",
    max_papers: int = 200,
) -> SurveyState:
    """
    Create the initial state for Survey Agent.

    Args:
        topic: Survey topic (natural language description)
        seed_paper_ids: List of seed paper IDs (backward compat; also derived from reference_materials)
        taxonomy_sensitivity: Level of human intervention for taxonomy updates
        user_defined_taxonomy: User-predefined taxonomy structure
        reference_materials: Uploaded reference materials (papers, Start doc, etc.)
        start_document_text: Extracted text from the Start document
        reading_depth: Paper reading depth ("skim" | "standard" | "deep")

    Returns:
        SurveyState: Initial state ready to be passed to LangGraph graph.invoke()
    """
    return SurveyState(
        session_id=str(uuid.uuid4()),
        phase=Phase.DIALOGUE.value,
        started_at=datetime.utcnow().isoformat(),
        topic=topic,
        seed_paper_ids=seed_paper_ids or [],
        reference_materials=reference_materials or [],
        start_document_text=start_document_text,
        reading_depth=reading_depth,
        prior_knowledge={},        user_angle="",
        taxonomy_user_defined=user_defined_taxonomy or {},
        dialogue_turn=0,
        dialogue_complete=False,
        papers={},
        paper_edges=[],
        frontier=list(seed_paper_ids or []),
        processed=[],
        duplicate_surveys=[],
        knowledge_confirmations=[],
        knowledge_conflicts=[],
        new_findings=[],
        taxonomy={
            "version": 0,
            "categories": [],
            "changelog": [],
        },
        taxonomy_sensitivity=taxonomy_sensitivity,
        pending_taxonomy_update=None,
        paper_notes={},
        outline=[],
        draft_sections={},
        bib_entries={},
        messages=[],
        total_papers_found=0,
        error=None,
        output_format=output_format,
        generate_mindmap=generate_mindmap,
        local_papers_dir=local_papers_dir,
        max_papers=max_papers,
    )
