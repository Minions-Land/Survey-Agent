"""
interfaces/llm.py - Abstract interface for large language model providers

Supports two-tier model calls:
- cheap_model:     High-frequency calls for structured extraction (Haiku-class)
- expensive_model: Low-frequency calls for dialogue and writing (Opus-class)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Used via dependency injection:
        provider = AnthropicLLMProvider(api_key=..., cheap_model=..., expensive_model=...)
        agent = ExtractionAgent(llm=provider)

    Injection interface:
        - Implement __init__(api_key, cheap_model, expensive_model, **kwargs)
        - Any implementation conforming to this interface can be injected (OpenAI, local models, etc.)
    """

    @abstractmethod
    async def cheap_complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """
        Text completion using the cheap model (suitable for batch extraction tasks).

        Args:
            messages: [{"role": "user"|"assistant", "content": "..."}]
            system: System prompt
            max_tokens: Maximum output tokens
            **kwargs: Model-specific parameters (temperature, etc.)

        Returns:
            Model output text
        """
        raise NotImplementedError("TODO: Inject cheap model implementation")

    @abstractmethod
    async def expensive_complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 16384,
        thinking: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        Text completion using the high-quality model (suitable for writing and reasoning tasks).

        Args:
            messages: Message list
            system: System prompt
            max_tokens: Maximum output tokens
            thinking: Whether to enable extended thinking (adaptive mode)
            **kwargs: Model-specific parameters

        Returns:
            Model output text
        """
        raise NotImplementedError("TODO: Inject expensive model implementation")

    @abstractmethod
    async def expensive_stream(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int = 16384,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Streaming text output using the high-quality model (suitable for dialogue display).

        Yields:
            Text token fragments (delta)

        Usage:
            async for token in provider.expensive_stream(messages):
                print(token, end="", flush=True)
        """
        raise NotImplementedError("TODO: Inject streaming model implementation")
        yield  # Make it a generator (required by type system)
