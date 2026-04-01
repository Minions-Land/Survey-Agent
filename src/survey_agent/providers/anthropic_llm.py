"""
providers/anthropic_llm.py - Anthropic Claude LLM provider implementation

Usage:
- cheap_model:     claude-haiku-4-5    (for batch extraction)
- expensive_model: claude-opus-4-6    (for dialogue/writing, supports adaptive thinking)

Injection interface (LLMProvider):
    provider = AnthropicLLMProvider(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        cheap_model="claude-haiku-4-5",
        expensive_model="claude-opus-4-6",
    )
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from survey_agent.interfaces.llm import LLMProvider


class AnthropicLLMProvider(LLMProvider):
    """
    LLM provider based on the Anthropic Python SDK.

    - cheap_complete:    Uses Haiku, non-streaming call
    - expensive_complete: Uses Opus, supports adaptive thinking
    - expensive_stream:  Uses Opus, streaming output (for dialogue display)
    """

    def __init__(
        self,
        api_key: str | None = None,
        cheap_model: str = "claude-haiku-4-5",
        expensive_model: str = "claude-opus-4-6",
    ) -> None:
        """
        Initialize the LLM provider.

        Args:
            api_key: Anthropic API Key (defaults to ANTHROPIC_API_KEY environment variable)
            cheap_model: Model ID for batch extraction
            expensive_model: Model ID for writing/dialogue
        """
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Anthropic API Key not set. "
                "Please set the ANTHROPIC_API_KEY environment variable or configure it in .env."
            )

        # Async client (all calls are async)
        self._client = anthropic.AsyncAnthropic(api_key=resolved_key)
        self.cheap_model = cheap_model
        self.expensive_model = expensive_model

    async def cheap_complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """
        Text completion using the cheap model (Haiku).

        Use case: batch structured paper extraction (one call per paper)
        """
        kwargs_clean = {k: v for k, v in kwargs.items() if k != "thinking"}
        params: dict[str, Any] = {
            "model": self.cheap_model,
            "max_tokens": max_tokens,
            "messages": messages,
            **kwargs_clean,
        }
        if system:
            params["system"] = system

        response = await self._client.messages.create(**params)

        return next(
            (block.text for block in response.content if block.type == "text"),
            "",
        )

    async def expensive_complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 16384,
        thinking: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        Text completion using the high-quality model (Opus).

        Use case: dialogue, writing, taxonomy inference and other complex tasks

        Args:
            thinking: When True, enables adaptive thinking (for complex reasoning tasks)
        """
        params: dict[str, Any] = {
            "model": self.expensive_model,
            "max_tokens": max_tokens,
            "messages": messages,
            **{k: v for k, v in kwargs.items() if k != "thinking"},
        }
        if system:
            params["system"] = system
        if thinking:
            # Opus 4.6 uses adaptive thinking (budget_tokens is deprecated)
            params["thinking"] = {"type": "adaptive"}

        response = await self._client.messages.create(**params)

        return next(
            (block.text for block in response.content if block.type == "text"),
            "",
        )

    async def expensive_stream(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 16384,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Streaming text output using the high-quality model.

        Use case: dialogue interaction (display tokens in real time)

        Usage:
            async for token in provider.expensive_stream(messages):
                print(token, end="", flush=True)
        """
        params: dict[str, Any] = {
            "model": self.expensive_model,
            "max_tokens": max_tokens,
            "messages": messages,
            **{k: v for k, v in kwargs.items() if k != "thinking"},
        }
        if system:
            params["system"] = system

        async with self._client.messages.stream(**params) as stream:
            async for text in stream.text_stream:
                yield text
