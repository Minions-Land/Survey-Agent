"""
providers/openai_compatible.py - OpenAI 兼容 API 通用 LLM Provider

支持所有兼容 OpenAI API 格式的模型:
  - OpenAI GPT 系列 (gpt-4o, gpt-4o-mini)
  - Google Gemini (via OpenAI 兼容端点)
  - DeepSeek (deepseek-chat, deepseek-reasoner)
  - Kimi/Moonshot (moonshot-v1-8k, moonshot-v1-128k)
  - Qwen/通义千问 (qwen-max, qwen-turbo)
  - GLM/智谱AI (glm-4-plus, glm-4-flash)

使用 openai Python 库，通过 base_url 切换不同服务商。
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from survey_agent.interfaces.llm import LLMProvider

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 预定义模型配置（方便用户选择）
# ──────────────────────────────────────────────────────────────────────────────

PROVIDER_PRESETS: dict[str, dict] = {
    # OpenAI
    "openai": {
        "base_url": None,  # 使用默认 api.openai.com
        "cheap_model": "gpt-4o-mini",
        "expensive_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "description": "OpenAI GPT 系列",
    },
    # Google Gemini (OpenAI 兼容端点)
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "cheap_model": "gemini-2.0-flash-lite",
        "expensive_model": "gemini-2.5-pro-preview-03-25",
        "env_key": "GEMINI_API_KEY",
        "description": "Google Gemini 系列",
    },
    # DeepSeek
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "cheap_model": "deepseek-chat",
        "expensive_model": "deepseek-reasoner",
        "env_key": "DEEPSEEK_API_KEY",
        "description": "DeepSeek 系列",
    },
    # Kimi / Moonshot
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "cheap_model": "moonshot-v1-8k",
        "expensive_model": "moonshot-v1-128k",
        "env_key": "MOONSHOT_API_KEY",
        "description": "Kimi (Moonshot AI)",
    },
    # Qwen / 通义千问
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "cheap_model": "qwen-turbo",
        "expensive_model": "qwen-max",
        "env_key": "DASHSCOPE_API_KEY",
        "description": "Qwen (通义千问/阿里云)",
    },
    # GLM / 智谱 AI
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "cheap_model": "glm-4-flash",
        "expensive_model": "glm-4-plus",
        "env_key": "ZHIPUAI_API_KEY",
        "description": "GLM (智谱 AI)",
    },
}


class OpenAICompatibleProvider(LLMProvider):
    """
    基于 openai Python 库的通用 LLM Provider。

    通过 base_url + api_key 支持各类 OpenAI 兼容 API。

    Args:
        api_key: API 密钥
        cheap_model: 轻量模型名称（用于批量提取等低成本操作）
        expensive_model: 高质量模型名称（用于写作、对话等）
        base_url: API 端点，None 表示使用 OpenAI 官方地址
        max_retries: 最大重试次数
    """

    def __init__(
        self,
        api_key: str,
        cheap_model: str = "gpt-4o-mini",
        expensive_model: str = "gpt-4o",
        base_url: str | None = None,
        max_retries: int = 3,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "请安装 openai 库: pip install openai"
            )

        self._cheap_model = cheap_model
        self._expensive_model = expensive_model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
        )

    async def cheap_complete(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1500,
    ) -> str:
        """使用轻量模型（成本优先）完成请求。"""
        full_messages = _build_messages(messages, system)
        response = await self._client.chat.completions.create(
            model=self._cheap_model,
            messages=full_messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def expensive_complete(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 4096,
        thinking: bool = False,  # 忽略，OpenAI 兼容 API 不支持 Claude 的 thinking 参数
    ) -> str:
        """使用高质量模型完成请求。"""
        full_messages = _build_messages(messages, system)
        response = await self._client.chat.completions.create(
            model=self._expensive_model,
            messages=full_messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def expensive_stream(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """使用高质量模型流式输出。"""
        full_messages = _build_messages(messages, system)
        stream = await self._client.chat.completions.create(
            model=self._expensive_model,
            messages=full_messages,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    @classmethod
    def from_preset(cls, preset_name: str, api_key: str) -> "OpenAICompatibleProvider":
        """
        从预设配置创建 Provider。

        Args:
            preset_name: 预设名称（"openai", "gemini", "deepseek" 等）
            api_key: 对应服务商的 API 密钥

        Returns:
            配置好的 OpenAICompatibleProvider 实例
        """
        if preset_name not in PROVIDER_PRESETS:
            raise ValueError(
                f"未知 preset: {preset_name!r}。"
                f"可用: {list(PROVIDER_PRESETS.keys())}"
            )
        preset = PROVIDER_PRESETS[preset_name]
        return cls(
            api_key=api_key,
            cheap_model=preset["cheap_model"],
            expensive_model=preset["expensive_model"],
            base_url=preset["base_url"],
        )


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _build_messages(
    messages: list[dict],
    system: str | None,
) -> list[dict]:
    """将 Anthropic 格式的消息列表转换为 OpenAI 格式（含 system message）。"""
    result: list[dict] = []
    if system:
        result.append({"role": "system", "content": system})
    result.extend(messages)
    return result
