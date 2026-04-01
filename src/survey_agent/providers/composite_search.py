"""
providers/composite_search.py - 多源搜索聚合 Provider

按优先级依次查询多个学术搜索 API，合并去重结果。

默认优先级:
  1. Semantic Scholar（最全面，有引用数）
  2. arXiv（最新预印本，免费）
  3. OpenReview（顶会审稿内容，如 NeurIPS/ICLR）

可根据用户配置调整顺序或禁用某些 Provider。
"""

from __future__ import annotations

import logging
from typing import Any

from survey_agent.interfaces.search import AcademicSearchAPI

logger = logging.getLogger(__name__)


class CompositeSearchAPI(AcademicSearchAPI):
    """
    聚合多个 AcademicSearchAPI 的复合 Provider。

    搜索策略:
    - 主 Provider 先搜索，收集结果
    - 若结果不足 min_results，继续从次级 Provider 补充
    - 按论文标题/arXiv ID 去重

    Args:
        providers: 按优先级排列的 Provider 列表
        min_results: 触发补充搜索的最低结果数阈值
    """

    def __init__(
        self,
        providers: list[AcademicSearchAPI],
        min_results: int = 10,
    ) -> None:
        if not providers:
            raise ValueError("providers 列表不能为空")
        self._providers = providers
        self._min_results = min_results

    async def search_papers(
        self,
        query: str,
        limit: int = 20,
        fields: list[str] | None = None,
        is_survey: bool = False,
    ) -> list[dict[str, Any]]:
        """
        从所有 Provider 搜索并合并去重。

        策略：主 Provider 先搜到 limit 条；如不足 min_results，
        补充次级 Provider 的结果，总数不超过 limit。
        """
        all_results: list[dict[str, Any]] = []
        seen_titles: set[str] = set()

        for provider in self._providers:
            if len(all_results) >= limit:
                break
            remaining = limit - len(all_results)
            try:
                import inspect as _inspect
                sig = _inspect.signature(provider.search_papers)
                kwargs: dict = {"limit": remaining + 5, "fields": fields}
                if "is_survey" in sig.parameters:
                    kwargs["is_survey"] = is_survey
                results = await provider.search_papers(query, **kwargs)
            except Exception as e:
                logger.warning(f"{provider.__class__.__name__} 搜索失败: {e}")
                continue

            for r in results:
                key = _dedup_key(r)
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_results.append(r)
                if len(all_results) >= limit:
                    break

            # 若主 Provider 已有足够结果，不再补充
            if (
                provider is self._providers[0]
                and len(all_results) >= self._min_results
            ):
                break

        return all_results[:limit]

    async def get_paper_details(
        self,
        paper_id: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """依次尝试各 Provider，返回第一个成功的结果。"""
        for provider in self._providers:
            try:
                result = await provider.get_paper_details(paper_id, fields=fields)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"{provider.__class__.__name__} get_paper_details 失败: {e}")
        return None

    async def get_references(
        self,
        paper_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """使用第一个支持参考文献查询的 Provider。"""
        for provider in self._providers:
            try:
                results = await provider.get_references(paper_id, limit=limit)
                if results:
                    return results
            except Exception as e:
                logger.debug(f"{provider.__class__.__name__} get_references 失败: {e}")
        return []

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """使用第一个支持引用查询的 Provider。"""
        for provider in self._providers:
            try:
                results = await provider.get_citations(paper_id, limit=limit)
                if results:
                    return results
            except Exception as e:
                logger.debug(f"{provider.__class__.__name__} get_citations 失败: {e}")
        return []

    async def get_batch_details(
        self,
        paper_ids: list[str],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """批量获取：主 Provider 优先，失败则逐篇尝试其他 Provider。"""
        try:
            results = await self._providers[0].get_batch_details(
                paper_ids, fields=fields
            )
            if results:
                return results
        except Exception as e:
            logger.warning(f"主 Provider 批量获取失败: {e}")

        # fallback: 逐篇获取
        all_results = []
        for pid in paper_ids:
            detail = await self.get_paper_details(pid, fields=fields)
            if detail:
                all_results.append(detail)
        return all_results


# ──────────────────────────────────────────────────────────────────────────────
# 工厂函数
# ──────────────────────────────────────────────────────────────────────────────

def build_composite_search(
    s2_api_key: str | None = None,
    include_arxiv: bool = True,
    include_openreview: bool = False,
) -> CompositeSearchAPI:
    """
    按推荐配置构建复合搜索 Provider。

    Args:
        s2_api_key: Semantic Scholar API Key（可选，无 key 则速率限制较严）
        include_arxiv: 是否加入 arXiv Provider
        include_openreview: 是否加入 OpenReview Provider

    Returns:
        CompositeSearchAPI 实例
    """
    from survey_agent.providers.semantic_scholar import SemanticScholarAPI
    from survey_agent.providers.arxiv_search import ArXivSearchAPI

    providers: list[AcademicSearchAPI] = [
        SemanticScholarAPI(api_key=s2_api_key),
    ]

    if include_arxiv:
        providers.append(ArXivSearchAPI())

    if include_openreview:
        try:
            from survey_agent.providers.openreview_search import OpenReviewSearchAPI
            providers.append(OpenReviewSearchAPI())
        except ImportError:
            logger.warning("OpenReview provider 不可用，已跳过")

    return CompositeSearchAPI(providers=providers)


def _dedup_key(paper: dict[str, Any]) -> str:
    """生成用于去重的键（小写标题，或 arXiv ID）。"""
    ext_ids = paper.get("externalIds") or {}
    if arxiv_id := ext_ids.get("ArXiv"):
        return f"arxiv:{arxiv_id}"
    title = paper.get("title", "")
    return title.lower().strip()[:80]
