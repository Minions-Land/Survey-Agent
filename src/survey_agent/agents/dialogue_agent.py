"""
agents/dialogue_agent.py - Dialogue Agent

Responsible for workflow phase 1: multi-turn dialogue with user to understand prior knowledge.

Dialogue objectives:
1. Understand the user's existing knowledge of the topic (known works, core concepts)
2. Identify the angle the user wants to investigate (unique perspective)
3. Understand the user's expected findings and research questions
4. Determine dialogue completeness based on conversation quality

Human-in-the-loop: Uses LangGraph interrupt() to pause after each turn and wait for user reply.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from survey_agent.interfaces.llm import LLMProvider

logger = logging.getLogger(__name__)

# Maximum dialogue turns (auto-ends after exceeding this)
MAX_DIALOGUE_TURNS = 6
# Minimum dialogue turns (must ask at least this many before completing)
MIN_DIALOGUE_TURNS = 2

_PROMPT_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


class DialogueAgent:
    """
    Dialogue Agent: understand the user's prior knowledge and survey angle through multi-turn Q&A.

    Uses expensive_model (Opus) to generate responses, supports streaming output.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm
        self._initial_prompt = self._load_prompt("dialogue_initial.md")

    def _load_prompt(self, filename: str) -> str:
        path = _PROMPT_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""  # Use embedded default prompt

    async def generate_opening(
        self,
        topic: str,
        seed_paper_ids: list[str],
        start_doc_knowledge: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate the opening message (first turn).

        Args:
            topic: Survey topic provided by the user
            seed_paper_ids: Seed paper IDs provided by the user (may be empty)
            start_doc_knowledge: Pre-extracted knowledge from Start document (optional)

        Returns:
            Opening text (topic understanding confirmation + first question)
        """
        seed_info = ""
        if seed_paper_ids:
            seed_info = f"\nThe user also provided {len(seed_paper_ids)} seed papers: {', '.join(seed_paper_ids[:3])}"

        start_info = ""
        if start_doc_knowledge:
            parts = []
            concepts = start_doc_knowledge.get("known_concepts", [])
            works = start_doc_knowledge.get("known_works", [])
            angle = start_doc_knowledge.get("unique_angle", "")
            questions = start_doc_knowledge.get("research_questions", [])
            structure = start_doc_knowledge.get("proposed_structure", "")
            claims = start_doc_knowledge.get("claims_to_verify", [])
            expertise = start_doc_knowledge.get("expertise_level", "")

            if expertise:
                parts.append(f"User expertise level: {expertise}")
            if concepts:
                parts.append(f"Key concepts they outlined: {', '.join(concepts[:10])}")
            if works:
                parts.append(f"Papers/works they already know ({len(works)} total): "
                             + "; ".join(works[:8]))
            if structure:
                parts.append(f"Proposed structure/framework: {structure}")
            if angle:
                parts.append(f"Their unique angle: {angle}")
            if questions:
                parts.append(f"Research questions they posed: {'; '.join(questions[:5])}")
            if claims:
                parts.append(f"Claims to verify: {'; '.join(claims[:3])}")

            if parts:
                start_info = (
                    "\n\n[CONTEXT FROM START DOCUMENT — the user has already outlined their plan]\n"
                    + "\n".join(f"• {p}" for p in parts)
                    + "\n\nIMPORTANT: Reference these specifics in your opening. "
                    "Do NOT ask generic background questions — the user is clearly an expert. "
                    "Instead, acknowledge what they have outlined and ask targeted questions "
                    "about gaps, priorities, or specific design decisions within their framework."
                )

        system = self._initial_prompt or _DEFAULT_DIALOGUE_SYSTEM

        messages = [
            {
                "role": "user",
                "content": (
                    f"I want to write an academic survey on \"{topic}\".{seed_info}{start_info}\n\n"
                    "Please start the dialogue with me to understand my prior knowledge of this topic."
                ),
            }
        ]

        result: list[str] = []
        async for token in self._llm.expensive_stream(messages, system=system):
            result.append(token)
            print(token, end="", flush=True)
        print()  # New line

        return "".join(result)

    async def generate_followup(
        self,
        topic: str,
        conversation_history: list[dict[str, str]],
        turn: int,
    ) -> tuple[str, bool]:
        """
        Generate follow-up questions or closing remarks based on conversation history.

        Args:
            topic: Survey topic
            conversation_history: History message list [{"role", "content"}]
            turn: Current turn number

        Returns:
            (agent_response, is_complete)
            is_complete = True means dialogue is sufficient, ready to proceed
        """
        system = (self._initial_prompt or _DEFAULT_DIALOGUE_SYSTEM) + _FOLLOWUP_INSTRUCTION

        # Determine whether to wrap up the dialogue
        should_wrap_up = turn >= MAX_DIALOGUE_TURNS - 1

        messages = list(conversation_history)
        if should_wrap_up:
            messages.append({
                "role": "user",
                "content": "[System prompt: enough turns have passed, please summarize and announce the research is starting]",
            })

        result: list[str] = []
        async for token in self._llm.expensive_stream(messages, system=system):
            result.append(token)
            print(token, end="", flush=True)
        print()

        response = "".join(result)

        # Determine if dialogue is complete (LLM returns specific signal or max turns reached)
        is_complete = (
            turn >= MAX_DIALOGUE_TURNS
            or "[DIALOGUE COMPLETE]" in response
            or "research will now begin" in response.lower()
            or "starting the research" in response.lower()
        )

        return response, is_complete

    async def extract_prior_knowledge(
        self,
        topic: str,
        conversation_history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Extract structured prior knowledge from conversation history.

        Called after dialogue completes, using cheap_model for extraction.

        Returns:
            {
                "known_concepts": [...],
                "known_works": [...],
                "expected_findings": "...",
                "research_questions": [...],
                "unique_angle": "...",
                "expertise_level": "beginner|intermediate|expert"
            }
        """
        system = _EXTRACTION_SYSTEM
        conversation_text = "\n".join(
            f"{'Agent' if m['role'] == 'assistant' else 'User'}: {m['content']}"
            for m in conversation_history
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Survey topic: {topic}\n\n"
                    f"The following is the conversation transcript:\n{conversation_text}\n\n"
                    "Please extract the user's prior knowledge from the conversation and output it in JSON format."
                ),
            }
        ]

        response = await self._llm.cheap_complete(
            messages,
            system=system,
            max_tokens=2048,
        )

        try:
            # Extract JSON block
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            logger.warning("Prior knowledge extraction failed, using default empty structure")

        return {
            "known_concepts": [],
            "known_works": [],
            "expected_findings": "",
            "research_questions": [],
            "unique_angle": "",
            "expertise_level": "intermediate",
        }


# ──────────────────────────────────────────────────────────────────────────────
# Embedded default prompts (used when prompts/dialogue_initial.md does not exist)
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULT_DIALOGUE_SYSTEM = """\
You are an expert academic assistant specializing in helping researchers plan systematic literature surveys.

Your current task is to engage in a friendly, professional multi-turn dialogue to deeply understand the user's prior knowledge of the survey topic, including:
1. Core works and concepts the user already knows
2. Questions the user considers important but is uncertain about
3. The unique perspective the user wants the survey to present
4. What the user expects to find, or what they worry they may have misunderstood

Dialogue style:
- Academic and friendly
- Ask only 1-2 questions at a time (don't overwhelm the user)
- Probe deeper based on the user's answers to show genuine understanding
- Occasionally share your own academic insights to guide the user's thinking

When the dialogue has sufficient information, say "Great, I now have a thorough understanding of your background. The research will now begin. [DIALOGUE COMPLETE]"
"""

_FOLLOWUP_INSTRUCTION = """

Please generate appropriate follow-up questions or a summary based on the user's answer, advancing the dialogue to a deeper level.
"""

_EXTRACTION_SYSTEM = """\
Extract the user's prior knowledge from the conversation history and output it in JSON format with the following structure:

{
  "known_concepts": ["concept 1", "concept 2", ...],
  "known_works": ["Author + Year + Title", ...],
  "expected_findings": "What the user expects to find (a paragraph)",
  "research_questions": ["question 1", "question 2", ...],
  "unique_angle": "The unique angle the user wants to approach this survey from",
  "expertise_level": "beginner|intermediate|expert"
}

Output only JSON, no other text.
"""
