"""
providers/arxiv_search.py - arXiv 论文搜索 Provider

使用 arXiv 公开 API（无需 API Key）。
适合检索最新预印本，尤其是 CS/ML 领域。

arXiv API 文档: https://info.arxiv.org/help/api/index.html
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

import httpx

from survey_agent.interfaces.search import AcademicSearchAPI
from survey_agent.utils.paper_card import PaperCard

logger = logging.getLogger(__name__)

_ARXIV_BASE = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArXivSearchAPI(AcademicSearchAPI):
    """
    arXiv 公开 API，无需 API Key。

    特点:
    - 免费，无速率限制（建议请求间隔 3s）
    - 覆盖最新预印本
    - 返回论文全文 PDF 链接
    - 不含引用计数信息
    """

    def __init__(self, request_interval: float = 3.0) -> None:
        self._interval = request_interval
        self._last_request: float = 0.0

    async def _get(self, params: dict[str, Any]) -> str:
        """发送 arXiv API 请求，带速率控制。"""
        import time
        now = time.monotonic()
        wait = self._interval - (now - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)

        url = f"{_ARXIV_BASE}?{urlencode(params)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        self._last_request = time.monotonic()
        return resp.text

    async def search_papers(
        self,
        query: str,
        limit: int = 20,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        搜索 arXiv 论文。

        Args:
            query: 搜索查询（支持 arXiv 语法，如 ti:transformer au:vaswani）
            limit: 最大返回数量
            fields: 忽略（arXiv API 总是返回所有字段）

        Returns:
            arXiv 论文字典列表（已转换为统一格式）
        """
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(limit, 100),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        try:
            xml_text = await self._get(params)
            return _parse_arxiv_response(xml_text)
        except Exception as e:
            logger.warning(f"arXiv 搜索失败: {e}")
            return []

    async def get_paper_details(
        self,
        paper_id: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        通过 arXiv ID 获取单篇论文详情。

        Args:
            paper_id: arXiv ID（如 2010.11929 或 arxiv:2010.11929）
        """
        arxiv_id = paper_id.replace("arxiv:", "").strip()
        params = {"id_list": arxiv_id, "max_results": 1}
        try:
            xml_text = await self._get(params)
            results = _parse_arxiv_response(xml_text)
            return results[0] if results else None
        except Exception as e:
            logger.warning(f"arXiv 获取论文 {paper_id} 失败: {e}")
            return None

    async def get_references(
        self,
        paper_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """arXiv 不提供参考文献 API，返回空列表。"""
        logger.debug("arXiv 不支持参考文献查询，跳过")
        return []

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """arXiv 不提供引用 API，返回空列表。"""
        logger.debug("arXiv 不支持引用查询，跳过")
        return []

    async def get_batch_details(
        self,
        paper_ids: list[str],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """批量获取多篇论文详情。"""
        id_list = ",".join(
            pid.replace("arxiv:", "").strip() for pid in paper_ids
        )
        params = {"id_list": id_list, "max_results": len(paper_ids)}
        try:
            xml_text = await self._get(params)
            return _parse_arxiv_response(xml_text)
        except Exception as e:
            logger.warning(f"arXiv 批量获取失败: {e}")
            return []


# ──────────────────────────────────────────────────────────────────────────────
# XML 解析辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _parse_arxiv_response(xml_text: str) -> list[dict[str, Any]]:
    """将 arXiv API 的 Atom XML 解析为统一格式字典列表。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"arXiv XML 解析失败: {e}")
        return []

    entries = root.findall("atom:entry", _NS)
    results = []

    for entry in entries:
        arxiv_id = _text(entry, "atom:id", "")
        # ID 格式: http://arxiv.org/abs/2010.11929v1 → 2010.11929
        if "/" in arxiv_id:
            arxiv_id = arxiv_id.rsplit("/", 1)[-1].split("v")[0]

        title = _text(entry, "atom:title", "").replace("\n", " ").strip()
        abstract = _text(entry, "atom:summary", "").replace("\n", " ").strip()

        # 发布日期 → 年份
        published = _text(entry, "atom:published", "")
        year = int(published[:4]) if published else 0

        # 作者列表
        authors = [
            _text(author, "atom:name", "")
            for author in entry.findall("atom:author", _NS)
        ]

        # arXiv 分类（作为 venue 的近似替代）
        categories = [
            cat.get("term", "")
            for cat in entry.findall("atom:category", _NS)
        ]
        venue = categories[0] if categories else "arXiv"

        # PDF 链接
        pdf_url = ""
        for link in entry.findall("atom:link", _NS):
            if link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")

        results.append({
            "paperId": f"arxiv:{arxiv_id}",
            "externalIds": {"ArXiv": arxiv_id},
            "title": title,
            "abstract": abstract,
            "year": year,
            "authors": [{"name": a} for a in authors],
            "venue": venue,
            "citationCount": 0,  # arXiv 无引用计数
            "influentialCitationCount": 0,
            "openAccessPdf": {"url": pdf_url} if pdf_url else None,
            "source": "arxiv",
        })

    return results


def _text(element: ET.Element, tag: str, default: str = "") -> str:
    """从 XML 元素提取文本，带命名空间支持。"""
    found = element.find(tag, _NS)
    return found.text or default if found is not None else default
