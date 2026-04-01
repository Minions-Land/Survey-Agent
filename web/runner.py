"""
web/runner.py - LangGraph task runner (WebSocket bridge)

Bridges LangGraph's interrupt/resume mechanism to WebSocket:
- LangGraph's GraphInterrupt exception → sends interrupt event via WebSocket
- WebSocket receives resume message → resumes LangGraph with Command(resume=...)
- LLM streaming output → forwarded in real time via WebSocket

Progress phase percentage mapping:
  dialogue     → 5%
  search       → 15%
  research     → 35%
  extraction   → 55%
  taxonomy     → 65%
  outline      → 75%
  writing      → 85-99%
  complete     → 100%
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import WebSocket
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

logger = logging.getLogger(__name__)

_PHASE_PCT: dict[str, int] = {
    "dialogue": 5,
    "survey_search": 15,
    "research": 35,
    "extraction": 55,
    "taxonomy_review": 65,
    "writing": 85,
    "complete": 100,
}


class SurveyRunner:
    """
    Executor for a single Survey task, bridging LangGraph and WebSocket.

    WebSocket message output uses asyncio.Queue buffering, sent by a dedicated sender Task,
    avoiding blocking caused by calling websocket.send_json() directly inside LangGraph nodes.
    """

    def __init__(self, job_id: str, websocket: WebSocket) -> None:
        self.job_id = job_id
        self._ws = websocket
        self._send_queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._resume_queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the running task."""
        self._cancelled = True
        if self._task:
            self._task.cancel()

    async def run(self, config: dict[str, Any]) -> None:
        """
        Build provider, initialize state, and run LangGraph based on config.

        config fields:
          topic, seeds, sensitivity, output_format, generate_mindmap,
          local_papers_dir,
          llm_provider ("anthropic"|"openai"|"gemini"|...),
          llm_api_key, llm_cheap_model, llm_expensive_model,
          search_providers (list of "s2"|"arxiv"|"openreview"),
          s2_api_key
        """
        # Start message sender coroutine
        sender_task = asyncio.create_task(self._sender_loop())

        import builtins as _builtins
        original_print = _builtins.print  # saved here so finally can always restore it

        try:
            # Build LLM Provider
            llm = _build_llm(config)

            # Build search Provider
            search = _build_search(config)

            # Import agents and graph (lazy import to avoid circular imports)
            from survey_agent.agents.dialogue_agent import DialogueAgent
            from survey_agent.agents.extraction_agent import ExtractionAgent
            from survey_agent.agents.retrieval_agent import RetrievalAgent
            from survey_agent.agents.taxonomy_agent import TaxonomyAgent
            from survey_agent.agents.writer_agent import WriterAgent
            from survey_agent.state import TaxonomySensitivity, create_initial_state
            from survey_agent.workflow.graph import build_graph

            # Monkey-patch builtins.print → WebSocket messages
            _ws_queue = self._send_queue
            original_print = _builtins.print  # re-capture in case it changed
            _ws_queue = self._send_queue

            def _ws_print(*args, **kwargs):
                text = " ".join(str(a) for a in args)
                end = kwargs.get("end", "\n")
                try:
                    _ws_queue.put_nowait({"type": "output", "text": text + end})
                except Exception:
                    pass  # Queue full or closed — ignore
                # Keep writing to stdout for server-side logs
                original_print(*args, **kwargs)

            _builtins.print = _ws_print

            # Build graph
            graph = build_graph(
                dialogue_agent=DialogueAgent(llm=llm),
                retrieval_agent=RetrievalAgent(llm=llm, search=search),
                extraction_agent=ExtractionAgent(llm=llm),
                taxonomy_agent=TaxonomyAgent(llm=llm),
                writer_agent=WriterAgent(llm=llm),
            )

            # Initial state
            seed_ids = [s.strip() for s in config.get("seeds", "").split(",") if s.strip()]
            sensitivity_map = {
                "strict": TaxonomySensitivity.STRICT,
                "balanced": TaxonomySensitivity.BALANCED,
                "liberal": TaxonomySensitivity.LIBERAL,
            }

            # Read Start document if provided
            start_doc_text = ""
            start_doc_path = config.get("start_doc_path", "")
            if start_doc_path:
                try:
                    from survey_agent.utils.document_reader import read_document
                    start_doc_text = await read_document(start_doc_path)
                    await self._send({"type": "output", "text": f"Start document loaded ({len(start_doc_text)} chars)\n"})
                except Exception as exc:
                    await self._send({"type": "output", "text": f"Warning: could not read Start doc: {exc}\n"})

            initial_state = create_initial_state(
                topic=config.get("topic", ""),
                seed_paper_ids=seed_ids,
                taxonomy_sensitivity=sensitivity_map.get(
                    config.get("sensitivity", "balanced"),
                    TaxonomySensitivity.BALANCED,
                ),
                output_format=config.get("output_format", "markdown"),
                generate_mindmap=config.get("generate_mindmap", False),
                local_papers_dir=config.get("local_papers_dir") or None,
                start_document_text=start_doc_text,
                reading_depth=config.get("reading_depth", "standard"),
                max_papers=int(config.get("max_papers", 200)),
            )

            thread_config = {"configurable": {"thread_id": self.job_id}}
            current_input: Any = initial_state

            await self._send({"type": "progress", "phase": "starting", "pct": 2})

            while not self._cancelled:
                _lx_interrupt: dict[str, Any] | None = None  # LangGraph 1.x interrupt event

                try:
                    async for event in graph.astream(
                        current_input,
                        config=thread_config,
                        stream_mode="updates",
                    ):
                        if self._cancelled:
                            break

                        # ── LangGraph 1.x: interrupt emitted as {"__interrupt__": [...]} event ──
                        if "__interrupt__" in event:
                            raw_interrupts = event["__interrupt__"]
                            if raw_interrupts:
                                raw_val = raw_interrupts[0]
                                val = getattr(raw_val, "value", raw_val)
                                _lx_interrupt = val if isinstance(val, dict) else {}
                            break  # stop processing events; handle interrupt below

                        await self._handle_event(event)

                    if self._cancelled:
                        break

                    if _lx_interrupt is not None:
                        # LangGraph 1.x style interrupt — handle exactly like GraphInterrupt
                        await self._send({"type": "interrupt", "data": _lx_interrupt})
                        resume_value = await self._wait_for_resume()
                        if resume_value is None:
                            break
                        current_input = Command(resume=resume_value)
                        continue  # back to while loop

                    # Normal completion (no interrupt detected)
                    await self._send({"type": "progress", "phase": "complete", "pct": 100})
                    await self._send({"type": "done"})
                    break

                except GraphInterrupt as exc:
                    # LangGraph < 0.3 style: interrupt raised as Python exception (fallback)
                    interrupt_data: dict[str, Any] = {}
                    if exc.args:
                        raw = exc.args[0]
                        if isinstance(raw, dict):
                            interrupt_data = raw
                        elif hasattr(raw, "__iter__"):
                            for item in raw:
                                val = getattr(item, "value", item)
                                if isinstance(val, dict):
                                    interrupt_data = val
                                    break

                    await self._send({"type": "interrupt", "data": interrupt_data})
                    resume_value = await self._wait_for_resume()
                    if resume_value is None:
                        break
                    current_input = Command(resume=resume_value)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Runner {self.job_id} error")
            # Sanitize error message (remove control chars that could break JSON)
            error_msg = str(e).replace("\x00", "").replace("\r", " ")[:500]
            await self._send({"type": "error", "message": error_msg})
        finally:
            # Restore original print before closing
            try:
                import builtins as _builtins
                _builtins.print = original_print
            except Exception:
                pass
            # Drain the send queue so all queued messages are delivered before closing
            await self._send_queue.put(None)
            try:
                await asyncio.wait_for(sender_task, timeout=5.0)
            except asyncio.TimeoutError:
                sender_task.cancel()

    async def _handle_event(self, event: dict[str, Any]) -> None:
        """Handle LangGraph stream events and send progress updates."""
        for node_name, updates in event.items():
            if not isinstance(updates, dict):
                continue

            # Map phase progress
            phase = updates.get("phase", "")
            if phase and phase in _PHASE_PCT:
                pct = _PHASE_PCT[phase]
                await self._send({
                    "type": "progress",
                    "phase": phase,
                    "pct": pct,
                    "node": node_name,
                })

            # Paper count updates
            papers = updates.get("papers")
            if papers:
                await self._send({
                    "type": "stats",
                    "paper_count": len(papers),
                })

            # Taxonomy visualization update
            taxonomy = updates.get("taxonomy")
            if taxonomy and papers:
                await self._send({
                    "type": "taxonomy_update",
                    "data": _build_taxonomy_payload(
                        updates.get("topic", ""),
                        taxonomy,
                        papers,
                    ),
                })

    async def _wait_for_resume(self) -> str | None:
        """
        Wait for client to send a resume message.
        Also handles set_max_papers messages transparently.
        """
        while not self._cancelled:
            try:
                msg = await asyncio.wait_for(
                    self._ws.receive_json(), timeout=300.0
                )
                if msg.get("type") == "resume":
                    return str(msg.get("value", ""))
                # Ignore other message types (e.g. set_max_papers handled elsewhere)
            except asyncio.TimeoutError:
                await self._send({"type": "ping"})
            except Exception:
                return None
        return None

    async def _send(self, data: dict) -> None:
        """Put a message into the send queue."""
        await self._send_queue.put(data)

    async def _sender_loop(self) -> None:
        """Continuously dequeue messages and send to WebSocket client."""
        while True:
            msg = await self._send_queue.get()
            if msg is None:
                break
            try:
                await self._ws.send_json(msg)
            except Exception:
                break


# ──────────────────────────────────────────────────────────────────────────────
# Provider factory functions
# ──────────────────────────────────────────────────────────────────────────────

def _build_llm(config: dict[str, Any]):
    """Build LLM Provider based on config."""
    provider_name = config.get("llm_provider", "anthropic")
    api_key = config.get("llm_api_key", "")
    cheap_model = config.get("llm_cheap_model", "")
    expensive_model = config.get("llm_expensive_model", "")

    if provider_name == "anthropic":
        from survey_agent.providers.anthropic_llm import AnthropicLLMProvider
        return AnthropicLLMProvider(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY", ""),
            cheap_model=cheap_model or os.getenv("CHEAP_MODEL", "claude-haiku-4-5"),
            expensive_model=expensive_model or os.getenv("EXPENSIVE_MODEL", "claude-opus-4-6"),
        )

    from survey_agent.providers.openai_compatible import PROVIDER_PRESETS, OpenAICompatibleProvider
    preset = PROVIDER_PRESETS.get(provider_name, {})
    return OpenAICompatibleProvider(
        api_key=api_key or os.getenv(preset.get("env_key", ""), ""),
        cheap_model=cheap_model or preset.get("cheap_model", ""),
        expensive_model=expensive_model or preset.get("expensive_model", ""),
        base_url=preset.get("base_url"),
    )


def _build_search(config: dict[str, Any]):
    """Build search Provider based on config."""
    from survey_agent.providers.composite_search import build_composite_search
    providers = config.get("search_providers", ["s2", "arxiv"])
    return build_composite_search(
        s2_api_key=config.get("s2_api_key") or os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
        include_arxiv="arxiv" in providers,
        include_openreview="openreview" in providers,
    )


def _build_taxonomy_payload(
    topic: str,
    taxonomy: dict[str, Any],
    papers: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the frontend taxonomy_update payload.

    Enriches each paper entry with:
      abbr       — methods[0] or short cite_key
      confidence — classification_confidence if available, else 1.0
    """
    papers_out: dict[str, Any] = {}
    for pid, p in papers.items():
        if not isinstance(p, dict):
            continue
        methods = p.get("methods") or []
        abbr = methods[0] if methods else _short_cite_key(p.get("cite_key", pid))
        papers_out[pid] = {
            "title": p.get("title", ""),
            "year": p.get("year"),
            "cite_key": p.get("cite_key", ""),
            "abbr": abbr,
            "confidence": p.get("classification_confidence", 1.0),
        }
    return {
        "topic": topic,
        "taxonomy": taxonomy,
        "papers": papers_out,
    }


def _short_cite_key(key: str) -> str:
    """'vaswani2017attention' → 'Vaswani17'"""
    import re
    m = re.match(r"([a-z]+)(\d{4})", key or "")
    if m:
        return m.group(1).capitalize() + m.group(2)[2:]
    return (key or "")[:10]
