"""
providers/semantic_scholar.py - Semantic Scholar API 实现

API 文档: https://api.semanticscholar.org/graph/v1
速率限制:
  - 无 API Key: 1 req/s
  - 有 API Key: 100 req/s

注入接口 (AcademicSearchAPI):
    api = SemanticScholarAPI(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"))

字段文档: https://api.semanticscholar.org/graph/v1/paper/search
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from survey_agent.interfaces.search import AcademicSearchAPI

logger = logging.getLogger(__name__)

# 默认返回的论文字段（在 API 请求中作为 fields 参数）
_DEFAULT_FIELDS = [
    "paperId", "title", "authors", "year", "abstract",
    "venue", "journal", "citationCount", "influentialCitationCount",
    "isOpenAccess", "externalIds", "url", "fieldsOfStudy",
]

_S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarAPI(AcademicSearchAPI):
    """
    Semantic Scholar Graph API 客户端。

    自动处理:
    - 速率限制退避（429 响应时指数退避）
    - 请求重试（最多 3 次）
    - 分页
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Args:
            api_key: Semantic Scholar API Key（可选，无 key 时自动降速）
            timeout: HTTP 请求超时时间（秒）
        """
        resolved_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY") or ""
        headers = {"x-api-key": resolved_key} if resolved_key else {}

        self._client = httpx.AsyncClient(
            base_url=_S2_BASE_URL,
            headers=headers,
            timeout=timeout,
        )
        self._has_api_key = bool(resolved_key)
        # 无 API Key 时每秒最多 1 次请求
        self._request_interval = 0.0 if self._has_api_key else 1.1

    async def search_papers(
        self,
        query: str,
        limit: int = 20,
        fields: list[str] | None = None,
        year_range: tuple[int, int] | None = None,
        is_survey: bool = False,
    ) -> list[dict[str, Any]]:
        """关键词检索论文（支持 survey 过滤）。"""
        if is_survey:
            query = f"survey review {query}"

        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
            "fields": ",".join(fields or _DEFAULT_FIELDS),
        }
        if year_range:
            params["year"] = f"{year_range[0]}-{year_range[1]}"

        data = await self._get("/paper/search", params=params)
        papers = data.get("data", [])

        logger.info(f"搜索 '{query}' 返回 {len(papers)} 篇论文")
        return papers

    async def get_paper_details(
        self,
        paper_id: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """获取单篇论文详情。"""
        params = {"fields": ",".join(fields or _DEFAULT_FIELDS)}
        try:
            return await self._get(f"/paper/{paper_id}", params=params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"论文 {paper_id} 不存在")
                return None
            raise

    async def get_references(
        self,
        paper_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取参考文献列表（此论文引用了哪些论文）。"""
        params = {
            "fields": ",".join(_DEFAULT_FIELDS),
            "limit": min(limit, 1000),
        }
        data = await self._get(f"/paper/{paper_id}/references", params=params)
        # S2 references API 返回 {"data": [{"citedPaper": {...}}]}
        return [item["citedPaper"] for item in data.get("data", []) if item.get("citedPaper")]

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取被引用列表（谁引用了此论文），按影响力排序。"""
        params = {
            "fields": ",".join(_DEFAULT_FIELDS),
            "limit": min(limit, 1000),
        }
        data = await self._get(f"/paper/{paper_id}/citations", params=params)
        # S2 citations API 返回 {"data": [{"citingPaper": {...}}]}
        papers = [item["citingPaper"] for item in data.get("data", []) if item.get("citingPaper")]

        # 按影响力引用数排序（降序），取前 limit 篇
        papers.sort(key=lambda p: p.get("influentialCitationCount") or 0, reverse=True)
        return papers[:limit]

    async def get_batch_details(
        self,
        paper_ids: list[str],
    ) -> list[dict[str, Any]]:
        """批量获取论文详情（POST /paper/batch，最多 500 条）。"""
        if not paper_ids:
            return []

        fields = ",".join(_DEFAULT_FIELDS)
        results: list[dict[str, Any]] = []

        # S2 batch API 每次最多 500 条
        for i in range(0, len(paper_ids), 500):
            chunk = paper_ids[i : i + 500]
            data = await self._post(
                "/paper/batch",
                json={"ids": chunk},
                params={"fields": fields},
            )
            results.extend([p for p in data if p])  # 过滤 None（不存在的论文）

        return results

    async def close(self) -> None:
        """关闭 HTTP 客户端（在应用退出时调用）。"""
        await self._client.aclose()

    # ── 私有 HTTP 方法 ─────────────────────────────────────────────────────────

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        """带重试和速率限制的 GET 请求。"""
        await self._rate_limit_wait()
        for attempt in range(retries):
            try:
                resp = await self._client.get(path, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # 速率限制: 指数退避
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"S2 API 速率限制，等待 {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                raise
            except httpx.NetworkError as e:
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"网络错误: {e}") from e
        raise RuntimeError(f"S2 API 请求失败（已重试 {retries} 次）: {path}")

    async def _post(
        self,
        path: str,
        json: dict[str, Any],
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> Any:
        """带重试的 POST 请求。"""
        await self._rate_limit_wait()
        for attempt in range(retries):
            try:
                resp = await self._client.post(path, json=json, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"S2 API POST 请求失败: {path}")

    async def _rate_limit_wait(self) -> None:
        """无 API Key 时执行速率限制等待。"""
        if self._request_interval > 0:
            await asyncio.sleep(self._request_interval)
