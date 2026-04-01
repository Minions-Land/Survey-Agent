"""
survey_agent/__main__.py - Survey Agent CLI entry point

Usage:
    survey-agent                                # Interactive start
    survey-agent --topic "topic"                # Specify topic directly
    survey-agent --topic "topic" --seeds "s2_id1,s2_id2"

LangGraph human-in-the-loop:
    - After each interrupt() pause, read user input
    - Call Command(resume=user_input) to resume execution
    - Until the graph finishes (END)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Load .env (before all other imports)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from survey_agent.agents.dialogue_agent import DialogueAgent
from survey_agent.agents.extraction_agent import ExtractionAgent
from survey_agent.agents.retrieval_agent import RetrievalAgent
from survey_agent.agents.taxonomy_agent import TaxonomyAgent
from survey_agent.agents.writer_agent import WriterAgent
from survey_agent.providers.anthropic_llm import AnthropicLLMProvider
from survey_agent.providers.semantic_scholar import SemanticScholarAPI
from survey_agent.state import TaxonomySensitivity, create_initial_state
from survey_agent.workflow.graph import build_graph

# ──────────────────────────────────────────────────────────────────────────────
# Logging configuration
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "WARNING"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Interactive prompt helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _prompt_user(interrupt_data: dict[str, Any]) -> str:
    """
    Display appropriate prompt and read user input based on interrupt type.

    Args:
        interrupt_data: Data dict passed to interrupt()

    Returns:
        User input string
    """
    interrupt_type = interrupt_data.get("type", "unknown")

    if interrupt_type == "dialogue":
        # Dialogue turn: read user reply directly
        print("\n" + "─" * 50)
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[User interrupted]")
            sys.exit(0)
        return user_input

    elif interrupt_type == "survey_decision":
        # Duplicate survey decision
        print("\n" + "─" * 50)
        print("Please enter your choice:")
        print("  [1] Continue - my survey has a unique angle")
        print("  [2] Abort - an existing survey already covers this")
        print("  [q] Quit")
        print("─" * 50)
        while True:
            try:
                choice = input("Choice [1/2/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n\n[User interrupted]")
                sys.exit(0)
            if choice in ("1", "2", "q"):
                if choice == "q":
                    print("Goodbye!")
                    sys.exit(0)
                return choice
            print("Please enter 1, 2, or q")

    elif interrupt_type == "taxonomy_review":
        # Taxonomy major change confirmation
        proposal = interrupt_data.get("proposal", {})
        print("\n" + "─" * 50)
        print(f"Taxonomy change proposal:")
        print(f"   Type: {proposal.get('type', '?')}")
        print(f"   Description: {proposal.get('description', '?')}")
        print(f"   Reason: {proposal.get('reason', '?')}")
        print("─" * 50)
        print("  [y] Approve this change")
        print("  [n] Reject this change (keep current taxonomy)")
        while True:
            try:
                choice = input("Decision [y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n\n[User interrupted]")
                sys.exit(0)
            if choice in ("y", "n", "yes", "no"):
                return "approve" if choice.startswith("y") else "reject"
            print("Please enter y or n")

    elif interrupt_type == "outline_review":
        # Outline review
        outline = interrupt_data.get("outline", [])
        print("\n" + "─" * 50)
        print("Survey outline preview:")
        for section in sorted(outline, key=lambda s: s.get("order", 99)):
            print(f"   {section['order']}. {section['title']}")
            if section.get("description"):
                print(f"      └ {section['description'][:60]}...")
        print("─" * 50)
        print("  [y] Confirm outline, start writing")
        print("  [e] Enter revision suggestions")
        while True:
            try:
                choice = input("Decision [y/e]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n\n[User interrupted]")
                sys.exit(0)
            if choice.startswith("y"):
                return "approve"
            elif choice.startswith("e"):
                try:
                    feedback = input("Enter revision suggestions: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n\n[User interrupted]")
                    sys.exit(0)
                return f"revise: {feedback}"
            print("Please enter y or e")

    else:
        # Unknown interrupt type, generic handling
        message = interrupt_data.get("message", "")
        if message:
            print(f"\n{message}")
        try:
            user_input = input("\nPlease enter your reply: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[User interrupted]")
            sys.exit(0)
        return user_input


# ──────────────────────────────────────────────────────────────────────────────
# Main execution logic
# ──────────────────────────────────────────────────────────────────────────────

async def run_survey(
    topic: str,
    seed_paper_ids: list[str],
    taxonomy_sensitivity: str,
    output_format: str = "latex",
    generate_mindmap: bool = False,
    local_papers_dir: str | None = None,
    start_doc: str | None = None,
    reading_depth: str = "standard",
) -> None:
    """
    Execute the Survey Agent main workflow.

    Uses LangGraph's interrupt/resume mechanism for human-in-the-loop:
    - When the graph encounters interrupt(), a GraphInterrupt exception is raised
    - We catch the exception, read user input, then resume with Command(resume=...)
    """
    # ── 1. Initialize Provider ──────────────────────────────────────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("   Please configure it in the .env file (see .env.example)")
        sys.exit(1)

    llm = AnthropicLLMProvider(
        api_key=anthropic_key,
        cheap_model=os.getenv("CHEAP_MODEL", "claude-haiku-4-5"),
        expensive_model=os.getenv("EXPENSIVE_MODEL", "claude-opus-4-6"),
    )

    s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")  # Optional
    search = SemanticScholarAPI(api_key=s2_key)

    # ── 2. Initialize Agents ────────────────────────────────────────────────────
    dialogue_agent = DialogueAgent(llm=llm)
    retrieval_agent = RetrievalAgent(llm=llm, search=search)
    extraction_agent = ExtractionAgent(llm=llm)
    taxonomy_agent = TaxonomyAgent(llm=llm)
    writer_agent = WriterAgent(llm=llm)

    # ── 3. Build LangGraph ──────────────────────────────────────────────────────
    graph = build_graph(
        dialogue_agent=dialogue_agent,
        retrieval_agent=retrieval_agent,
        extraction_agent=extraction_agent,
        taxonomy_agent=taxonomy_agent,
        writer_agent=writer_agent,
    )

    # ── 4. Create initial state ─────────────────────────────────────────────────
    # Read Start document if provided
    start_doc_text = ""
    if start_doc:
        from survey_agent.utils.document_reader import read_document
        import asyncio
        start_doc_text = await read_document(start_doc)
        print(f"   Start document loaded: {start_doc} ({len(start_doc_text)} chars)")

    initial_state = create_initial_state(
        topic=topic,
        seed_paper_ids=seed_paper_ids,
        taxonomy_sensitivity=taxonomy_sensitivity,
        output_format=output_format,
        generate_mindmap=generate_mindmap,
        local_papers_dir=local_papers_dir,
        start_document_text=start_doc_text,
        reading_depth=reading_depth,
    )

    # LangGraph needs thread_id to track checkpoints
    config = {"configurable": {"thread_id": initial_state["session_id"]}}

    print(f"\nSurvey Agent started")
    print(f"   Topic: {topic}")
    if seed_paper_ids:
        print(f"   Seed papers: {', '.join(seed_paper_ids)}")
    print(f"   Taxonomy sensitivity: {taxonomy_sensitivity}")
    print()

    # ── 5. Execute workflow (with interrupt/resume loop) ───────────────────────
    current_input: Any = initial_state
    is_first_call = True

    while True:
        try:
            if is_first_call:
                # First call: pass initial state
                async for event in graph.astream(
                    current_input,
                    config=config,
                    stream_mode="updates",
                ):
                    _log_event(event)
                is_first_call = False
            else:
                # Resume call: pass Command
                async for event in graph.astream(
                    current_input,
                    config=config,
                    stream_mode="updates",
                ):
                    _log_event(event)

            # Normal completion (graph finished)
            print("\n\nSurvey Agent complete!")
            break

        except GraphInterrupt as exc:
            # Graph encountered interrupt(), needs user input
            # exc.args[0] is the data passed to interrupt()
            interrupt_data: dict[str, Any] = {}
            if exc.args:
                raw = exc.args[0]
                if isinstance(raw, dict):
                    interrupt_data = raw
                elif hasattr(raw, "__iter__"):
                    # LangGraph sometimes wraps multiple interrupts as a list
                    for item in raw:
                        if hasattr(item, "value"):
                            interrupt_data = item.value
                            break
                        elif isinstance(item, dict):
                            interrupt_data = item
                            break

            user_response = _prompt_user(interrupt_data)
            current_input = Command(resume=user_response)
            is_first_call = False

        except KeyboardInterrupt:
            print("\n\n[User interrupted] Stopped")
            sys.exit(0)
        except Exception as e:
            logger.exception("Workflow execution error")
            print(f"\nError: {e}")
            print("   Check logs for details (set LOG_LEVEL=DEBUG)")
            sys.exit(1)


def _log_event(event: dict[str, Any]) -> None:
    """Log LangGraph stream events (only outputs in DEBUG mode)."""
    if logger.isEnabledFor(logging.DEBUG):
        for node_name, updates in event.items():
            if isinstance(updates, dict):
                keys = list(updates.keys())
                logger.debug(f"Node {node_name!r} updated fields: {keys}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI argument parsing
# ──────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="survey-agent",
        description="Survey Agent - Automated Academic Survey Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  survey-agent
  survey-agent --topic "Reasoning capabilities of large language models"
  survey-agent --topic "Vision Transformer" --seeds "204e3073870fae3d05bcbc2f6a8e263d612023ed"
  survey-agent --topic "Reinforcement learning" --sensitivity strict
        """,
    )
    parser.add_argument(
        "--web",
        action="store_true",
        default=False,
        help="Launch web interface (access at http://localhost:8080)",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8080,
        help="Web interface port (default: 8080)",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Survey topic (prompts interactively if not provided)",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="",
        help="Comma-separated list of seed paper Semantic Scholar IDs",
    )
    parser.add_argument(
        "--sensitivity",
        type=str,
        choices=["strict", "balanced", "liberal"],
        default=os.getenv("TAXONOMY_UPDATE_SENSITIVITY", "balanced"),
        help="Taxonomy update sensitivity (default: balanced)",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["latex", "markdown"],
        default="latex",
        help="Output format: latex (default) or markdown",
    )
    parser.add_argument(
        "--mindmap",
        action="store_true",
        default=False,
        help="Generate Mermaid mind map",
    )
    parser.add_argument(
        "--papers-dir",
        type=str,
        default=None,
        help="Local PDF papers directory (optional)",
    )
    parser.add_argument(
        "--start-doc",
        type=str,
        default=None,
        help="Path to Start document (PDF/MD/TXT/DOCX) with your initial understanding",
    )
    parser.add_argument(
        "--reading-depth",
        type=str,
        choices=["skim", "standard", "deep"],
        default="standard",
        help="Paper reading depth: skim, standard (default), deep",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="survey-agent 0.1.0",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point (registered by pyproject.toml entry_points)."""
    args = _parse_args()

    # ── Web mode ────────────────────────────────────────────────────────────────
    if args.web:
        _run_web(args.web_port)
        return

    # ── CLI mode ────────────────────────────────────────────────────────────────
    # Interactive topic input
    if not args.topic:
        print("=" * 60)
        print("  Survey Agent - Automated Academic Survey Assistant")
        print("=" * 60)
        try:
            topic = input("\nEnter survey topic: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            sys.exit(0)
        if not topic:
            print("Topic cannot be empty")
            sys.exit(1)
    else:
        topic = args.topic

    # Parse seed paper IDs
    seed_ids: list[str] = []
    if args.seeds:
        seed_ids = [s.strip() for s in args.seeds.split(",") if s.strip()]

    # Map sensitivity string to enum
    sensitivity_map = {
        "strict": TaxonomySensitivity.STRICT,
        "balanced": TaxonomySensitivity.BALANCED,
        "liberal": TaxonomySensitivity.LIBERAL,
    }
    sensitivity = sensitivity_map.get(args.sensitivity, TaxonomySensitivity.BALANCED)

    asyncio.run(
        run_survey(
            topic=topic,
            seed_paper_ids=seed_ids,
            taxonomy_sensitivity=sensitivity,
            output_format=args.output_format,
            generate_mindmap=args.mindmap,
            local_papers_dir=args.papers_dir,
            start_doc=args.start_doc,
            reading_depth=args.reading_depth,
        )
    )


def _run_web(port: int) -> None:
    """Launch the web interface."""
    try:
        import uvicorn
    except ImportError:
        print("Please install web dependencies: pip install -e '.[web]'")
        sys.exit(1)

    import webbrowser, threading

    # web/ 不是已安装包，将项目根目录加入 sys.path 让 uvicorn 能找到它
    # __file__ = src/survey_agent/__main__.py，上三级即项目根
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    print(f"Survey Agent Web Interface")
    print(f"   Visit: http://localhost:{port}")
    print(f"   Press Ctrl+C to stop")

    def _open_browser():
        import time; time.sleep(1.2)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("web.app:app", host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
