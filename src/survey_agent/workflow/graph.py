"""
workflow/graph.py - LangGraph StateGraph definition

Assembles all nodes and routing functions into an executable LangGraph workflow.

Workflow structure:
  dialogue → search_surveys → (present_surveys?) → research_init
  → expand_papers (loop) → extraction → build_taxonomy
  → (taxonomy_review?) → generate_outline → write_sections → finalize

Human-in-the-loop points (interrupt):
  - dialogue: each dialogue turn
  - present_surveys: duplicate survey decision
  - taxonomy_review: major category change confirmation
  - generate_outline: outline confirmation
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from survey_agent.agents.dialogue_agent import DialogueAgent
from survey_agent.agents.extraction_agent import ExtractionAgent
from survey_agent.agents.retrieval_agent import RetrievalAgent
from survey_agent.agents.taxonomy_agent import TaxonomyAgent
from survey_agent.agents.writer_agent import WriterAgent
from survey_agent.state import SurveyState
from survey_agent.workflow.nodes import (
    make_nodes,
    route_after_dialogue,
    route_after_survey_search,
    route_after_survey_decision,
    route_research,
    route_after_taxonomy,
    route_after_writing,
)

logger = logging.getLogger(__name__)


def build_graph(
    dialogue_agent: DialogueAgent,
    retrieval_agent: RetrievalAgent,
    extraction_agent: ExtractionAgent,
    taxonomy_agent: TaxonomyAgent,
    writer_agent: WriterAgent,
    checkpointer: Any | None = None,
) -> Any:
    """
    Build and compile the LangGraph StateGraph.

    Args:
        dialogue_agent: Dialogue Agent
        retrieval_agent: Retrieval Agent
        extraction_agent: Extraction Agent
        taxonomy_agent: Taxonomy Agent
        writer_agent: Writing Agent
        checkpointer: LangGraph checkpointer (for checkpoint/resume)
                      Defaults to MemorySaver (in-memory)

    Returns:
        Compiled CompiledGraph, ready to call .ainvoke() or .astream()
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    # Get all node functions (keys from make_nodes are node names)
    nodes = make_nodes(
        dialogue_agent=dialogue_agent,
        retrieval_agent=retrieval_agent,
        extraction_agent=extraction_agent,
        taxonomy_agent=taxonomy_agent,
        writer_agent=writer_agent,
    )

    # ── Build StateGraph ───────────────────────────────────────────────────────
    graph = StateGraph(SurveyState)

    # Register all nodes (keys match those in make_nodes return dict)
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    # ── Register edges ────────────────────────────────────────────────────────

    # Start → preprocess reference materials → dialogue
    graph.add_edge(START, "preprocess_materials")
    graph.add_edge("preprocess_materials", "dialogue")

    # Dialogue: conditional routing (continue dialogue or advance to survey search)
    graph.add_conditional_edges(
        "dialogue",
        route_after_dialogue,
        {
            "dialogue": "dialogue",
            "search_surveys": "search_surveys",
        },
    )

    # Survey search → conditional routing
    graph.add_conditional_edges(
        "search_surveys",
        route_after_survey_search,
        {
            "present_surveys": "present_surveys",  # Duplicate found, needs user decision
            "research_init": "research_init",       # No duplicate, proceed to research
        },
    )

    # Present surveys → conditional routing (after user decision)
    graph.add_conditional_edges(
        "present_surveys",
        route_after_survey_decision,
        {
            "research_init": "research_init",  # Continue (with unique angle)
            "__end__": END,                    # Abort (topic already fully covered)
        },
    )

    # Research init → conditional routing (expand or directly extract)
    graph.add_conditional_edges(
        "research_init",
        route_research,
        {
            "expand_papers": "expand_papers",  # Papers available for expansion
            "extraction": "extraction",         # Frontier empty, proceed to extraction
        },
    )

    # Expand papers → conditional routing (continue expansion or proceed to extraction)
    graph.add_conditional_edges(
        "expand_papers",
        route_research,
        {
            "expand_papers": "expand_papers",  # Frontier still has papers
            "extraction": "extraction",         # Frontier empty
        },
    )

    # Extraction → build taxonomy (fixed edge)
    graph.add_edge("extraction", "build_taxonomy")

    # Build taxonomy → conditional routing
    graph.add_conditional_edges(
        "build_taxonomy",
        route_after_taxonomy,
        {
            "taxonomy_review": "taxonomy_review",    # Major change needs human review
            "generate_outline": "generate_outline",  # Proceed to outline generation
        },
    )

    # Taxonomy review → conditional routing (after review)
    graph.add_conditional_edges(
        "taxonomy_review",
        route_after_taxonomy,
        {
            "taxonomy_review": "taxonomy_review",    # More pending changes
            "generate_outline": "generate_outline",  # All changes handled
        },
    )

    # Generate outline → write sections (fixed edge; generate_outline has interrupt, resumes on this edge)
    graph.add_edge("generate_outline", "write_sections")

    # Write sections → conditional routing (done or continue)
    graph.add_conditional_edges(
        "write_sections",
        route_after_writing,
        {
            "write_sections": "write_sections",  # More sections to write (current impl writes all at once)
            "finalize": "finalize",               # All sections complete
        },
    )

    # Finalize → END
    graph.add_edge("finalize", END)

    # ── Compile ───────────────────────────────────────────────────────────────
    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("LangGraph workflow compiled successfully")
    return compiled
