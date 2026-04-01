"""
workflow/nodes.py - LangGraph workflow node functions

Each node function:
- Accepts SurveyState and returns a state update dict (partial update)
- Nodes requiring human input use interrupt() to pause
- Data is passed between nodes via state

Human-in-the-loop nodes (using interrupt):
- dialogue_node: waits for user reply after each dialogue turn
- present_surveys_node: waits for user decision after showing duplicate surveys
- taxonomy_review_node: waits for user confirmation on major category changes
- outline_review_node: waits for user confirmation after outline is generated
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.types import interrupt

from survey_agent.agents.dialogue_agent import DialogueAgent
from survey_agent.agents.extraction_agent import ExtractionAgent
from survey_agent.agents.retrieval_agent import RetrievalAgent
from survey_agent.agents.taxonomy_agent import TaxonomyAgent
from survey_agent.agents.writer_agent import WriterAgent
from survey_agent.state import Phase, SurveyState, TaxonomySensitivity
from survey_agent.utils.bib_manager import BibManager
from survey_agent.utils.paper_card import PaperCard
from survey_agent.utils.taxonomy import Taxonomy

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Node factory - inject Agents into node closures
# ──────────────────────────────────────────────────────────────────────────────

def make_nodes(
    dialogue_agent: DialogueAgent,
    retrieval_agent: RetrievalAgent,
    extraction_agent: ExtractionAgent,
    taxonomy_agent: TaxonomyAgent,
    writer_agent: WriterAgent,
) -> dict[str, Any]:
    """
    Create all LangGraph node functions and inject corresponding Agent dependencies.

    Args:
        dialogue_agent: Dialogue Agent
        retrieval_agent: Retrieval Agent
        extraction_agent: Extraction Agent
        taxonomy_agent: Taxonomy Agent
        writer_agent: Writing Agent

    Returns:
        {node_name: node_function} dict, passed to graph.add_node()
    """

    # ── Phase 0: Pre-process reference materials ──────────────────────────────

    async def preprocess_materials_node(state: SurveyState) -> dict[str, Any]:
        """
        Pre-process uploaded reference materials before the main pipeline.

        1. If a Start document is present, extract prior knowledge from it
        2. Sets phase to DIALOGUE so the dialogue node runs next
        """
        import json as _json
        start_text = state.get("start_document_text", "")
        topic = state["topic"]

        if not start_text:
            return {"phase": Phase.DIALOGUE.value}

        print("\nReading your Start document...\n")

        prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "start_document.md"
        system = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

        # Truncate to ~15k chars to stay within cheap_model budget
        truncated = start_text[:15_000]
        messages = [{
            "role": "user",
            "content": (
                f"Survey topic: {topic}\n\n"
                f"The user's initial plan/understanding document:\n\n{truncated}"
            ),
        }]

        try:
            response = await dialogue_agent._llm.cheap_complete(
                messages, system=system, max_tokens=2048,
            )
            start = response.find("{")
            end = response.rfind("}") + 1
            prior = _json.loads(response[start:end]) if start >= 0 and end > start else {}
        except Exception as exc:
            logger.warning(f"Failed to parse Start document: {exc}")
            prior = {}

        print(f"Start document processed. Extracted {len(prior.get('known_concepts', []))} concepts, "
              f"{len(prior.get('known_works', []))} known works.\n")

        return {
            "prior_knowledge": prior,
            "user_angle": prior.get("unique_angle", ""),
            "phase": Phase.DIALOGUE.value,
        }

    # ── Phase 1: Dialogue node ────────────────────────────────────────────────

    async def dialogue_node(state: SurveyState) -> dict[str, Any]:
        """
        Dialogue node: multi-turn dialogue with user to understand prior knowledge.

        Flow:
        1. First turn: generate opening
        2. Subsequent turns: generate follow-up questions or summary
        3. After dialogue complete: extract prior knowledge
        """
        topic = state["topic"]
        turn = state.get("dialogue_turn", 0)
        messages = state.get("messages", [])

        # Rebuild conversation history (for LLM)
        history = [
            {"role": "assistant" if m["role"] == "agent" else "user", "content": m["content"]}
            for m in messages
        ]

        if turn == 0:
            # First turn: generate opening
            print("\n" + "=" * 60)
            print(f"Survey Agent - Topic: {topic}")
            print("=" * 60 + "\n")

            response = await dialogue_agent.generate_opening(
                topic=topic,
                seed_paper_ids=state.get("seed_paper_ids", []),
                start_doc_knowledge=state.get("prior_knowledge") if state.get("start_document_text") else None,
            )
            agent_message = _make_message("agent", response)

            # interrupt: wait for user reply (include response so web client can display it)
            user_input: str = interrupt({
                "type": "dialogue",
                "message": response,
                "turn": turn,
            })

            user_message = _make_message("user", user_input)

            return {
                "messages": [agent_message, user_message],
                "dialogue_turn": 1,
            }

        else:
            # Subsequent turns: generate follow-up questions
            response, is_complete = await dialogue_agent.generate_followup(
                topic=topic,
                conversation_history=history,
                turn=turn,
            )
            agent_message = _make_message("agent", response)

            if is_complete:
                # Dialogue complete: extract prior knowledge
                dialogue_prior = await dialogue_agent.extract_prior_knowledge(
                    topic=topic,
                    conversation_history=history,
                )
                # Merge with pre-existing knowledge from Start doc
                existing_prior = state.get("prior_knowledge", {})
                merged = _merge_prior_knowledge(existing_prior, dialogue_prior)
                print("\nDialogue phase complete. Prior knowledge extracted.\n")
                return {
                    "messages": [agent_message],
                    "dialogue_turn": turn + 1,
                    "dialogue_complete": True,
                    "prior_knowledge": merged,
                    "user_angle": merged.get("unique_angle", ""),
                    "phase": Phase.SURVEY_SEARCH.value,
                }
            else:
                # Continue dialogue
                user_input = interrupt({
                    "type": "dialogue",
                    "message": response,
                    "turn": turn,
                })
                user_message = _make_message("user", user_input)

                return {
                    "messages": [agent_message, user_message],
                    "dialogue_turn": turn + 1,
                }

    # ── Phase 2: Survey search node ───────────────────────────────────────────

    async def search_surveys_node(state: SurveyState) -> dict[str, Any]:
        """
        Search for and assess existing surveys for duplication.

        No interrupt: executes automatically, results saved to duplicate_surveys.
        """
        topic = state["topic"]
        user_angle = state.get("user_angle", "")

        print("\nSearching for existing surveys...\n")

        try:
            surveys = await retrieval_agent.search_surveys(topic, limit=10)
        except Exception as exc:
            logger.warning(f"Survey search failed (continuing without duplicate check): {exc}")
            surveys = []
        if not surveys:
            print("No highly relevant existing surveys found. Ready to start fresh research.\n")
            return {
                "duplicate_surveys": [],
                "phase": Phase.RESEARCH.value,
            }

        # Use LLM to assess similarity
        assessments = await retrieval_agent.assess_duplicate_surveys(
            topic=topic,
            surveys=surveys,
            user_angle=user_angle,
        )

        # Filter for highly similar surveys
        high_similarity = [
            a for a in assessments
            if a.get("similarity_level") in ("identical", "highly_similar")
        ]

        if not high_similarity:
            print(f"Found {len(surveys)} related surveys, but significantly different from current topic.\n")
            return {
                "duplicate_surveys": assessments,
                "phase": Phase.RESEARCH.value,
            }

        # Highly similar surveys found: require human decision
        return {
            "duplicate_surveys": assessments,
        }

    async def present_surveys_node(state: SurveyState) -> dict[str, Any]:
        """
        Present duplicate surveys and wait for user decision.

        interrupt: display existing surveys and ask user whether to continue.
        """
        duplicates = state.get("duplicate_surveys", [])

        # Build display text
        print("\nFound highly similar existing surveys:\n")
        for survey in duplicates:
            level = survey.get("similarity_level", "unknown")
            emoji = "[HIGH]" if level == "identical" else "[MEDIUM]"
            print(f"{emoji} [{level.upper()}] {survey.get('title', '?')} ({survey.get('year', '?')})")
            print(f"   Reason: {survey.get('similarity_reason', 'N/A')}")
        print()

        user_input: str = interrupt({
            "type": "survey_decision",
            "message": (
                "Please choose:\n"
                "1. Abort (an identical survey already exists)\n"
                "2. Continue (provide your unique angle)\n"
                "Enter '1' or describe your unique angle: "
            ),
        })

        if user_input.strip() == "1" or "abort" in user_input.lower():
            print("\nResearch stopped (an identical survey already exists).\n")
            return {
                "phase": Phase.COMPLETE.value,
                "messages": [_make_message("user", user_input)],
            }
        else:
            # User provided a new angle
            angle = user_input if len(user_input) > 2 else state.get("user_angle", "")
            print("\nContinuing research with your unique angle.\n")
            return {
                "user_angle": angle,
                "phase": Phase.RESEARCH.value,
                "messages": [_make_message("user", user_input)],
            }

    # ── Phase 3: Research/expansion nodes ────────────────────────────────────

    async def research_init_node(state: SurveyState) -> dict[str, Any]:
        """
        Initialize research phase: fetch seed paper details and build initial frontier queue.
        """
        topic = state["topic"]
        seed_ids = state.get("seed_paper_ids", [])
        existing_papers = state.get("papers", {})
        existing_processed = set(state.get("processed", []))

        print("\nInitializing research phase...\n")

        new_papers: dict[str, Any] = {}
        new_edges: list[dict[str, str]] = []
        bib_manager = BibManager()

        # Fetch seed paper details
        frontier_ids: list[str] = []
        for paper_id in seed_ids:
            if paper_id in existing_papers:
                continue
            card = await retrieval_agent.fetch_paper_details(paper_id, source="seed")
            if card:
                new_papers[card.s2_paper_id] = card.to_dict()
                bib_manager.register_paper(card)
                frontier_ids.append(card.s2_paper_id)
                print(f"  Seed paper: {card.title[:60]}")

        # If no seed papers, search for classic works by topic
        if not seed_ids and not existing_papers:
            # Extract a clean search query from the (possibly verbose) topic text
            search_query = _extract_search_query(topic)
            print(f"  No seed papers provided. Searching for classic works: '{search_query[:60]}'...")
            classic_papers = await retrieval_agent._search.search_papers(
                query=search_query, limit=5
            )
            for p_data in classic_papers:
                pid = p_data.get("paperId", "")
                if pid and pid not in existing_papers:
                    card = PaperCard.from_s2_response(p_data, source="seed")
                    new_papers[card.s2_paper_id] = card.to_dict()
                    bib_manager.register_paper(card)
                    frontier_ids.append(card.s2_paper_id)
                    print(f"  Found: {card.title[:60]}")

        total = len(existing_papers) + len(new_papers)
        print(f"\nResearch initialization complete. Frontier queue: {len(frontier_ids)} papers\n")

        if total == 0:
            # No papers at all — interrupt to ask user for seed paper IDs
            print("⚠️  No papers found. Please provide seed paper IDs.\n")
            user_input: str = interrupt({
                "type": "dialogue",
                "message": (
                    "⚠️ 未找到任何论文。请提供至少一篇种子论文的 ID（Semantic Scholar / arXiv ID / DOI），"
                    "多个 ID 用逗号分隔，以便开始构建论文网络。\n\n"
                    "如果暂时没有具体论文，也可以输入一个相关关键词，系统会尝试自动搜索。"
                ),
                "turn": -1,
            })
            # Retry research_init with user-provided seeds
            new_seed_ids = [s.strip() for s in user_input.split(",") if s.strip()]
            return {
                "seed_paper_ids": new_seed_ids,
                "messages": [_make_message("user", user_input)],
                "phase": Phase.RESEARCH.value,
            }

        return {
            "papers": {**existing_papers, **new_papers},
            "frontier": frontier_ids,
            "processed": list(existing_processed),
            "bib_entries": bib_manager.export_to_state(),
            "total_papers_found": total,
            "phase": Phase.RESEARCH.value,
        }

    async def expand_papers_node(state: SurveyState) -> dict[str, Any]:
        """
        Paper expansion node: process papers in the frontier queue, expand network forward/backward.

        Each call processes batch_size papers; called multiple times until the queue is empty.
        """
        topic = state["topic"]
        frontier = list(state.get("frontier", []))
        processed = set(state.get("processed", []))
        existing_papers = state.get("papers", {})
        existing_edges = list(state.get("paper_edges", []))
        prior_knowledge = state.get("prior_knowledge", {})
        bib_state = state.get("bib_entries", {})
        max_papers = state.get("max_papers", 200)

        # Extract topic keywords once for relevance filtering during expansion
        topic_keywords = _extract_topic_keywords(topic)

        # Stop expanding if we've already hit the paper cap
        if len(existing_papers) >= max_papers:
            print(f"\nPaper cap reached ({max_papers} papers). Moving to extraction.\n")
            return {"frontier": [], "phase": Phase.EXTRACTION.value}

        if not frontier:
            return {"phase": Phase.EXTRACTION.value}

        BATCH_SIZE = 3  # Process 3 papers at a time (controls API call volume)
        batch = frontier[:BATCH_SIZE]
        remaining = frontier[BATCH_SIZE:]

        print(f"\nExpanding paper network ({len(batch)}/{len(frontier)} papers)...\n")

        new_papers: dict[str, Any] = {}
        new_edges: list[dict[str, str]] = []
        new_frontier: list[str] = list(remaining)
        bib_manager = BibManager.from_state(bib_state)

        for paper_id in batch:
            if paper_id in processed:
                continue

            processed.add(paper_id)

            # Ensure paper details have been fetched
            if paper_id not in existing_papers:
                card = await retrieval_agent.fetch_paper_details(paper_id, source="backward")
                if not card:
                    continue
                new_papers[paper_id] = card.to_dict()
                bib_manager.register_paper(card)
            else:
                card = PaperCard.from_dict(existing_papers[paper_id])

            print(f"  Expanding: {card.title[:60]}")

            # Backward expansion (references)
            refs = await retrieval_agent.expand_backward(
                paper_id=paper_id,
                existing_ids=set(existing_papers) | set(new_papers),
                limit=5,
            )
            for ref in refs:
                new_papers[ref.s2_paper_id] = ref.to_dict()
                bib_manager.register_paper(ref)
                new_edges.append({
                    "from_id": paper_id,
                    "to_id": ref.s2_paper_id,
                    "edge_type": "reference",
                })
                if ref.s2_paper_id not in processed and _is_topic_relevant(
                    topic_keywords, ref.title, ref.abstract or ""
                ):
                    new_frontier.append(ref.s2_paper_id)

            # Forward expansion (papers citing this paper)
            citations = await retrieval_agent.expand_forward(
                paper_id=paper_id,
                existing_ids=set(existing_papers) | set(new_papers),
                limit=5,
            )
            for cit in citations:
                new_papers[cit.s2_paper_id] = cit.to_dict()
                bib_manager.register_paper(cit)
                new_edges.append({
                    "from_id": cit.s2_paper_id,
                    "to_id": paper_id,
                    "edge_type": "citation",
                })
                if cit.s2_paper_id not in processed and _is_topic_relevant(
                    topic_keywords, cit.title, cit.abstract or ""
                ):
                    new_frontier.append(cit.s2_paper_id)

        # Deduplicate frontier queue
        seen = set(processed)
        new_frontier_dedup = []
        for pid in new_frontier:
            if pid not in seen:
                new_frontier_dedup.append(pid)
                seen.add(pid)

        # Limit frontier queue length (prevent infinite expansion)
        max_total = int(state.get("total_papers_found", 0)) or 200
        if len(new_frontier_dedup) > max_total:
            new_frontier_dedup = new_frontier_dedup[:max_total]

        # Compare against prior knowledge
        new_card_list = [PaperCard.from_dict(v) for v in new_papers.values()]
        alignment = await retrieval_agent.check_knowledge_alignment(
            topic=topic,
            prior_knowledge=prior_knowledge,
            new_papers=new_card_list[:10],
        )

        all_papers = {**existing_papers, **new_papers}
        all_edges = existing_edges + new_edges
        total = len(all_papers)

        print(f"\n  Total papers: {total}, remaining frontier: {len(new_frontier_dedup)}")

        update: dict[str, Any] = {
            "papers": all_papers,
            "paper_edges": all_edges,
            "frontier": new_frontier_dedup,
            "processed": list(processed),
            "bib_entries": bib_manager.export_to_state(),
            "total_papers_found": total,
            "knowledge_confirmations": list(state.get("knowledge_confirmations", []))
                + alignment.get("confirmations", []),
            "knowledge_conflicts": list(state.get("knowledge_conflicts", []))
                + alignment.get("conflicts", []),
            "new_findings": list(state.get("new_findings", []))
                + alignment.get("new_findings", []),
        }

        # Queue empty -> move to extraction phase
        if not new_frontier_dedup:
            update["phase"] = Phase.EXTRACTION.value
            print("\nPaper expansion complete. Moving to information extraction phase.\n")

        return update

    # ── Phase 4: Extraction node ──────────────────────────────────────────────

    async def extraction_node(state: SurveyState) -> dict[str, Any]:
        """
        Information extraction node: structured extraction for all papers.
        """
        topic = state["topic"]
        papers = state.get("papers", {})
        existing_notes = state.get("paper_notes", {})
        bib_state = state.get("bib_entries", {})

        # Only extract papers not yet processed
        pending = [
            PaperCard.from_dict(v) for k, v in papers.items()
            if k not in existing_notes and v.get("abstract")
        ]

        if not pending:
            print("\nAll papers have been extracted.\n")
            return {"phase": Phase.TAXONOMY_REVIEW.value}

        print(f"\nExtracting structured information for {len(pending)} papers...\n")

        bib_manager = BibManager.from_state(bib_state)
        new_notes: dict[str, str] = {}

        def _progress(current: int, total: int, title: str) -> None:
            print(f"  [{current}/{total}] {title}...")

        # Batch extraction with reading depth
        reading_depth = state.get("reading_depth", "standard")
        local_dir = state.get("local_papers_dir")
        paper_storage = None
        if local_dir:
            try:
                from survey_agent.utils.paper_storage import PaperStorage
                paper_storage = PaperStorage(root=local_dir)
            except Exception:
                pass

        extraction_results = await extraction_agent.extract_batch(
            papers=pending,
            topic=topic,
            reading_depth=reading_depth,
            paper_storage=paper_storage,
            progress_callback=_progress,
        )

        for paper_id, extraction in extraction_results.items():
            paper_dict = papers.get(paper_id, {})
            if not paper_dict:
                continue
            paper = PaperCard.from_dict(paper_dict)
            updated_paper = await extraction_agent.update_paper_card(paper, extraction)
            papers[paper_id] = updated_paper.to_dict()
            # Update BibTeX cite_key
            bib_manager.register_paper(updated_paper)
            # Generate paper note
            new_notes[paper_id] = extraction_agent.generate_paper_note(updated_paper)

        print(f"\nExtraction complete. Generated {len(new_notes)} paper notes.\n")

        return {
            "papers": papers,
            "paper_notes": {**existing_notes, **new_notes},
            "bib_entries": bib_manager.export_to_state(),
            "phase": Phase.TAXONOMY_REVIEW.value,
        }

    # ── Phase 5: Taxonomy nodes ───────────────────────────────────────────────

    async def build_taxonomy_node(state: SurveyState) -> dict[str, Any]:
        """
        Build/update taxonomy and assign papers to categories.
        """
        topic = state["topic"]
        papers = state.get("papers", {})
        paper_notes = state.get("paper_notes", {})
        taxonomy_dict = state.get("taxonomy", {})
        sensitivity = state.get("taxonomy_sensitivity", TaxonomySensitivity.BALANCED)
        existing_surveys = state.get("duplicate_surveys", [])
        user_defined = state.get("taxonomy_user_defined", {})

        print("\nBuilding taxonomy...\n")

        paper_cards = [PaperCard.from_dict(v) for v in papers.values()]
        notes_list = list(paper_notes.values())

        # Initialize taxonomy (if empty)
        current_taxonomy = Taxonomy.from_dict(taxonomy_dict) if taxonomy_dict.get("categories") else None

        if current_taxonomy is None or not current_taxonomy.categories:
            current_taxonomy = await taxonomy_agent.initialize_taxonomy(
                topic=topic,
                paper_notes=notes_list[:20],
                existing_surveys=existing_surveys,
                user_defined=user_defined or None,
            )
            print(f"  Taxonomy initialized: {len(current_taxonomy.categories)} major categories\n")

        # Assess whether update is needed (based on new papers)
        proposal = await taxonomy_agent.propose_taxonomy_update(
            new_papers=paper_cards[-20:],  # Most recent 20 papers
            current_taxonomy=current_taxonomy,
            topic=topic,
            sensitivity=sensitivity,
        )

        if proposal and proposal.get("is_major_change") and sensitivity in (
            TaxonomySensitivity.STRICT, TaxonomySensitivity.BALANCED
        ):
            # Major change requires human confirmation
            print(f"\nTaxonomy update proposal (requires confirmation): {proposal.get('description', '')}\n")
            return {
                "taxonomy": current_taxonomy.to_dict(),
                "pending_taxonomy_update": proposal,
                "phase": Phase.TAXONOMY_REVIEW.value,
            }
        elif proposal and proposal.get("type") != "none":
            # Automatically apply minor changes
            current_taxonomy = taxonomy_agent.apply_taxonomy_update(current_taxonomy, proposal)
            print(f"  Auto-applied taxonomy update: {proposal.get('description', '')}")

        # Assign papers to categories
        assignments = await taxonomy_agent.assign_papers_to_categories(
            papers=paper_cards,
            taxonomy=current_taxonomy,
            topic=topic,
        )
        for cat_id, pids in assignments.items():
            for pid in pids:
                from survey_agent.utils.taxonomy import TaxonomyManager
                mgr = TaxonomyManager(current_taxonomy)
                mgr.assign_paper(pid, cat_id)

        print(f"\nTaxonomy complete: {len(current_taxonomy.categories)} major categories\n")

        from survey_agent.utils.taxonomy import TaxonomyManager as _TM
        print(_TM(current_taxonomy).to_markdown_outline())

        return {
            "taxonomy": current_taxonomy.to_dict(),
            "pending_taxonomy_update": None,
            "phase": Phase.WRITING.value,
        }

    async def taxonomy_review_node(state: SurveyState) -> dict[str, Any]:
        """
        Taxonomy human review node: display major change proposal and wait for confirmation.
        """
        proposal = state.get("pending_taxonomy_update")
        if not proposal:
            return {"phase": Phase.WRITING.value}

        taxonomy_dict = state.get("taxonomy", {})
        current_taxonomy = Taxonomy.from_dict(taxonomy_dict)

        from survey_agent.utils.taxonomy import TaxonomyManager
        manager = TaxonomyManager(current_taxonomy)

        print("\nCurrent taxonomy:\n")
        print(manager.to_markdown_outline())

        print(f"\nTaxonomy update proposal:\n"
              f"Type: {proposal.get('type', '?')}\n"
              f"Description: {proposal.get('description', '?')}\n"
              f"Reason: {proposal.get('reason', '?')}\n")

        user_input: str = interrupt({
            "type": "taxonomy_review",
            "message": "Accept this taxonomy update? (yes/no, or enter revision suggestions): ",
        })

        if "yes" in user_input.lower() or "approve" in user_input.lower() or "accept" in user_input.lower():
            updated = taxonomy_agent.apply_taxonomy_update(current_taxonomy, proposal)
            print("\nTaxonomy update applied.\n")
            return {
                "taxonomy": updated.to_dict(),
                "pending_taxonomy_update": None,
                "phase": Phase.WRITING.value,
                "messages": [_make_message("user", user_input)],
            }
        else:
            print("\nSkipping this taxonomy update.\n")
            return {
                "pending_taxonomy_update": None,
                "phase": Phase.WRITING.value,
                "messages": [_make_message("user", user_input)],
            }

    # ── Phase 6: Writing nodes ────────────────────────────────────────────────

    async def generate_outline_node(state: SurveyState) -> dict[str, Any]:
        """Generate survey outline and wait for user confirmation."""
        topic = state["topic"]
        taxonomy_dict = state.get("taxonomy", {})
        paper_notes = state.get("paper_notes", {})
        prior_knowledge = state.get("prior_knowledge", {})
        user_angle = state.get("user_angle", "")

        taxonomy = Taxonomy.from_dict(taxonomy_dict)

        print("\nGenerating survey outline...\n")

        outline = await writer_agent.generate_outline(
            topic=topic,
            taxonomy=taxonomy,
            paper_notes=paper_notes,
            prior_knowledge=prior_knowledge,
            user_angle=user_angle,
        )

        print("\nSurvey outline:\n")
        for section in sorted(outline, key=lambda s: s.get("order", 99)):
            print(f"  {section['order']}. {section['title']}")
            print(f"     {section.get('description', '')[:80]}")
        print()

        user_input: str = interrupt({
            "type": "outline_review",
            "message": "Is the outline satisfactory? (yes/continue, or enter revision suggestions): ",
        })

        # TODO: Revise outline based on user feedback (current version accepts feedback but does not regenerate)
        print("\nOutline confirmed. Starting to write.\n")

        return {
            "outline": outline,
            "phase": Phase.WRITING.value,
            "messages": [_make_message("user", user_input)],
        }

    async def write_sections_node(state: SurveyState) -> dict[str, Any]:
        """
        Write survey sections chapter by chapter.
        """
        topic = state["topic"]
        outline = state.get("outline", [])
        paper_notes = state.get("paper_notes", {})
        prior_knowledge = state.get("prior_knowledge", {})
        bib_state = state.get("bib_entries", {})
        existing_drafts = state.get("draft_sections", {})

        bib_manager = BibManager.from_state(bib_state)
        new_drafts: dict[str, str] = {}

        # Find sections not yet written
        pending_sections = [
            s for s in sorted(outline, key=lambda x: x.get("order", 99))
            if s["section_id"] not in existing_drafts
        ]

        if not pending_sections:
            print("\nAll sections have been written.\n")
            return {"phase": Phase.COMPLETE.value}

        for section in pending_sections:
            content = await writer_agent.write_section(
                section=section,
                topic=topic,
                paper_notes=paper_notes,
                bib_manager=bib_manager,
                prior_knowledge=prior_knowledge,
                full_outline=outline,
            )
            new_drafts[section["section_id"]] = content

        all_drafts = {**existing_drafts, **new_drafts}
        bib_str = bib_manager.generate_bibliography()

        return {
            "draft_sections": all_drafts,
            "bib_entries": bib_manager.export_to_state(),
            "phase": Phase.COMPLETE.value,
        }

    async def finalize_node(state: SurveyState) -> dict[str, Any]:
        """
        Final assembly node: assemble the complete survey and save to file.
        """
        import os
        from pathlib import Path

        topic = state["topic"]
        outline = state.get("outline", [])
        drafts = state.get("draft_sections", {})
        prior_knowledge = state.get("prior_knowledge", {})
        bib_state = state.get("bib_entries", {})

        print("\nGenerating final survey document...\n")

        # Assemble the complete survey
        survey_text = await writer_agent.assemble_survey(
            outline=outline,
            sections=drafts,
            topic=topic,
            prior_knowledge=prior_knowledge,
        )

        # Generate BibTeX
        bib_manager = BibManager.from_state(bib_state)
        bibliography = bib_manager.generate_bibliography()

        # Save files
        output_dir = Path(os.getenv("OUTPUT_DIR", "data/surveys"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Clean up filename
        import re
        safe_topic = re.sub(r"[^\w\s-]", "", topic)[:50].strip().replace(" ", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base_name = f"{safe_topic}_{timestamp}"

        survey_path = output_dir / f"{base_name}.md"
        bib_path = output_dir / f"{base_name}.bib"

        survey_path.write_text(survey_text, encoding="utf-8")
        bib_path.write_text(bibliography, encoding="utf-8")

        print(f"Survey saved:\n"
              f"   Main text: {survey_path}\n"
              f"   References: {bib_path}\n")

        # Print statistics
        total_papers = len(state.get("papers", {}))
        total_refs = len(bib_state)
        conflicts = len(state.get("knowledge_conflicts", []))
        new_findings = len(state.get("new_findings", []))

        print("Research statistics:")
        print(f"   Total papers: {total_papers}")
        print(f"   Cited papers: {total_refs}")
        print(f"   Confirmed prior knowledge: {len(state.get('knowledge_confirmations', []))} items")
        print(f"   Conflicts with prior knowledge: {conflicts} items")
        print(f"   New findings: {new_findings} items")

        if conflicts > 0:
            print("\nFindings that conflict with your prior knowledge:")
            for c in state.get("knowledge_conflicts", [])[:3]:
                print(f"   - {c}")

        return {
            "phase": Phase.COMPLETE.value,
            "messages": [
                _make_message(
                    "agent",
                    f"Survey complete! Saved to: {survey_path}",
                )
            ],
        }

    return {
        "preprocess_materials": preprocess_materials_node,
        "dialogue": dialogue_node,
        "search_surveys": search_surveys_node,
        "present_surveys": present_surveys_node,
        "research_init": research_init_node,
        "expand_papers": expand_papers_node,
        "extraction": extraction_node,
        "build_taxonomy": build_taxonomy_node,
        "taxonomy_review": taxonomy_review_node,
        "generate_outline": generate_outline_node,
        "write_sections": write_sections_node,
        "finalize": finalize_node,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Routing functions
# ──────────────────────────────────────────────────────────────────────────────

def route_after_dialogue(state: SurveyState) -> str:
    """Route after dialogue node: continue dialogue vs. proceed to survey search."""
    if state.get("dialogue_complete"):
        return "search_surveys"
    return "dialogue"


def route_after_survey_search(state: SurveyState) -> str:
    """Route after survey search: duplicate found vs. proceed to research."""
    duplicates = state.get("duplicate_surveys", [])
    has_high_similarity = any(
        d.get("similarity_level") in ("identical", "highly_similar")
        for d in duplicates
    )
    if has_high_similarity:
        return "present_surveys"
    return "research_init"


def route_after_survey_decision(state: SurveyState) -> str:
    """Route after user decision: abort vs. continue research."""
    if state.get("phase") == Phase.COMPLETE.value:
        return "__end__"
    return "research_init"


def route_research(state: SurveyState) -> str:
    """Research loop routing: continue expansion vs. proceed to extraction."""
    frontier = state.get("frontier", [])
    if frontier:
        return "expand_papers"
    return "extraction"


def route_after_extraction(state: SurveyState) -> str:
    """Route after extraction: build taxonomy."""
    return "build_taxonomy"


def route_after_taxonomy(state: SurveyState) -> str:
    """Route after taxonomy: human review required vs. writing."""
    if state.get("pending_taxonomy_update"):
        return "taxonomy_review"
    return "generate_outline"


def route_after_writing(state: SurveyState) -> str:
    """Route after writing: complete vs. more sections (current version writes all in one pass)."""
    if state.get("phase") == Phase.COMPLETE.value:
        return "finalize"
    return "write_sections"


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _make_message(role: str, content: str) -> dict[str, str]:
    """Create a timestamped message dict."""
    return {
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _merge_prior_knowledge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge two prior_knowledge dicts — combine lists, prefer overlay for scalars."""
    merged: dict[str, Any] = {}
    for key in set(list(base.keys()) + list(overlay.keys())):
        bv, ov = base.get(key), overlay.get(key)
        if isinstance(bv, list) and isinstance(ov, list):
            merged[key] = list(dict.fromkeys(bv + ov))
        elif ov:
            merged[key] = ov
        else:
            merged[key] = bv
    return merged


def _extract_search_query(topic: str) -> str:
    """
    Extract a concise, Semantic Scholar-friendly search query from a (possibly verbose) topic string.

    Handles cases where the user pastes a full system prompt or instructions as the topic field.
    Looks for quoted titles (《...》, "..."), falls back to first 120 meaningful characters.
    """
    import re
    # 1. Try CJK book title marks: 《LLM Architecture: A Survey》
    m = re.search(r"[《]([^》]{5,120})[》]", topic)
    if m:
        return m.group(1).strip()
    # 2. Try English double quotes
    m = re.search(r'"([A-Z][^"]{5,120})"', topic)
    if m:
        return m.group(1).strip()
    # 3. Strip common instruction prefixes ("You are a...", "你是一个...")
    stripped = re.sub(r"^(You are[^.。\n]{0,200}[.。\n]|你是[^。\n]{0,200}[。\n])", "", topic.strip())
    stripped = stripped.strip()
    # 4. Take first sentence or 120 chars
    first_sent = re.split(r"[.。\n]", stripped)[0].strip()
    if 5 < len(first_sent) <= 150:
        return first_sent[:120]
    return stripped[:120] or topic[:120]


def _extract_topic_keywords(topic: str) -> set[str]:
    """
    Extract meaningful English keywords from the survey topic for relevance filtering.

    Returns a set of lowercase tokens (length > 3, non-stopwords).
    Used by _is_topic_relevant() to filter expansion candidates.
    """
    import re
    _STOPWORDS = {
        "the", "and", "for", "with", "using", "based", "from", "that", "this",
        "into", "over", "their", "have", "been", "will", "such", "which",
        "also", "more", "other", "than", "about", "these", "used", "study",
        "approach", "method", "proposed", "novel", "paper", "work", "show",
        "results", "models", "model", "deep", "learning", "neural", "network",
    }
    query = _extract_search_query(topic)
    words = re.findall(r"[a-zA-Z]{4,}", query)
    return {w.lower() for w in words if w.lower() not in _STOPWORDS}


def _is_topic_relevant(keywords: set[str], title: str, abstract: str) -> bool:
    """
    Quick keyword-overlap relevance check.

    Returns True if at least one topic keyword appears in the paper's title or abstract.
    Allows all papers through when no keywords are available.
    """
    if not keywords:
        return True
    text = (title + " " + (abstract or "")).lower()
    return any(kw in text for kw in keywords)
